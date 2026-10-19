"""模型库门面：默认通过 Java 读取模型，原 SQL 实现仅用于显式 legacy 模式。

阶段 3 起，Java 是模型库唯一写入方；此处保持 ModelRow 和模型解释接口，
让现有计算与展示继续复用。下方原 SQL 和建表逻辑只在 legacy 模式可达。

原实现为什么单出一个模块：`api/` 下别的东西要么在把 HTTP 翻成函数调用，要么在管
进程内的活。这一份管的是**进程外**的一个真数据库 —— 它会连不上、会超时、
会在磁盘满的时候报 1406，而那些语义不该渗进路由层。
`api/routes/models.py` 只认这里出去的那几个 dataclass。

**为什么不引 SQLAlchemy**：整个需求是「一张表、四个查询、没有 join、没有
迁移」。加一个 ORM 换来的是一层映射、一份 declarative 基类、和一套「它到底
发了哪条 SQL」的猜谜 —— 而这一轮要的是能一眼读出来的存取代码。

**凭据为什么写在源码里**：本机演示项目，`root` / `123456` 是用户当面给的。
这是一个**有意记在案的取舍**（规格书 D1 第 3 点）：将来若要往外走，这是
第一个要改的地方。环境变量能覆盖每一个值，所以改起来不必动代码。
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import pymysql
from pymysql.cursors import DictCursor

from tfield import config as C
from tfield.calibration import CalibrationBundle

from . import business_client
from .dataset_context import DatasetContextError
from .model_context import current_model_context

#: 建库语句。**不带 `COLLATE`**：规格书写的是 `utf8mb4_0900_ai_ci`，那是
#: MySQL 8 独有的排序规则名，在 5.7 上会直接报错。我们不需要任何一个特定
#: 的排序规则 —— 库里存的是中文名字与哈希，没有一处按字典序比较。
_DDL_DATABASE = ("CREATE DATABASE IF NOT EXISTS `{db}` "
                 "DEFAULT CHARACTER SET utf8mb4")

#: 建表语句。
#:
#: ⚠️ `dataset_sig` 是 **VARCHAR(64)**，不是规格书 §四 写的 `CHAR(16)`。
#: 它的值是训练段派生签名（`loader.py:53-63`），实测长这样：
#: `0066856dc40a8bbc-h20260727T1200` —— **31 个字符**。`CHAR(16)` 在
#: MySQL 8 的严格模式下会当场报 1406，宽松模式下会把 `-h…` 那一段悄悄砍掉，
#: 于是「整份文件」与「它的训练段」会撞成同一个签名 —— 而兼容性判定比的就是它。
#:
#: `groups_sig` 是 `sha1(...)[:8]`，8 个字符，`CHAR(8)` 正好。
#: `bundle` 用 LONGTEXT 不用 JSON 类型：我们要的是**原样存取**，不是在库里查它。
_DDL_TABLE = """
CREATE TABLE IF NOT EXISTS model (
  id          BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
  name        VARCHAR(120) NOT NULL,
  saved_at    DATETIME     NOT NULL,
  dataset_sig VARCHAR(64)  NOT NULL,
  groups_sig  CHAR(8)      NOT NULL,
  data_file   VARCHAR(255) NOT NULL,
  data_start  DATETIME     NOT NULL,
  data_end    DATETIME     NOT NULL,
  mae         DOUBLE       NULL,
  rmse        DOUBLE       NULL,
  r2          DOUBLE       NULL,
  is_current  TINYINT(1)   NOT NULL DEFAULT 0,
  bundle      LONGTEXT     NOT NULL,
  -- 成品：训练好的那一份里属于「模型」的字节（0.895 MB）。
  -- LONGBLOB 不是 BLOB：BLOB 上限 64 KiB，而这一份 0.9 MB —— 会**静默截断**，
  -- 而截断的成品在读回来时是「字节坏了」（回落现训），不是「存不进」。
  artifact    LONGBLOB     NULL,
  KEY idx_current (is_current)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

_COLUMNS = ("id, name, saved_at, dataset_sig, groups_sig, data_file, "
            "data_start, data_end, mae, rmse, r2, is_current, "
            "artifact IS NOT NULL AS has_artifact")


def db_name() -> str:
    """库名。**每次调用现读环境** —— 测试靠 `monkeypatch.setenv` 把它指到
    `tfield_models_test` 上；读成模块级常量就改不动了，测试会静默地跑到
    用户真正的库上，把里面的模型清掉。"""
    return os.environ.get("TFIELD_MYSQL_DB", "tfield_models")


#: MySQL 的「这个库不存在」（`ER_BAD_DB_ERROR`）。第一次连时自建库表就靠认
#: 这个错号 —— 见 `connect()` 里那一段。
_ER_BAD_DB_ERROR = 1049

#: MySQL 的「这一列已经在了」（`ER_DUP_FIELDNAME`）。补列语句靠认它保持幂等。
#: 只认这一个错号，别的错号一律原样抛 —— 与 `connect()` 里「只认 1049」同一条
#: 规则：糊成「那就当它在了吧」会把「表比代码旧」和「库根本没连上」变成同一件事。
_ER_DUP_FIELDNAME = 1060

#: 给老库补成品那一列。`CREATE TABLE IF NOT EXISTS` 对已存在的表是空操作，
#: 所以新加一列必须有这一句，否则跑着的那台机器永远停在旧表上。
_ALTER_ADD_ARTIFACT = ("ALTER TABLE model ADD COLUMN artifact LONGBLOB NULL "
                       "AFTER bundle")

#: 「这一版新加的列已经补过了吗」。**进程级**的一次性闸门 —— `connect()` 每个
#: 请求都会调，而那条 DDL 只需要在第一次真的连上之后发一遍（见 `_ensure_columns`）。
_ENSURED = False


def _add_artifact_column(conn) -> None:
    """给**已有的**表补成品那一列。幂等：只认 1060，别的错号原样抛。

    `init()` 与 `connect()` 两条路共用这一句 —— 各写一遍的话，早晚会一处改了
    一处没改，而表现是「新装的机器有这一列、老机器没有」这种最难查的分叉。
    """
    with conn.cursor() as cur:
        try:
            cur.execute(_ALTER_ADD_ARTIFACT)
        except pymysql.err.MySQLError as e:
            if not (e.args and e.args[0] == _ER_DUP_FIELDNAME):
                raise


def _ensure_columns(conn) -> None:
    """连上以后补一次列（规格书 D10）。**一个进程里只真跑一遍。**

    ⚠️ 这是这一版唯一一处**跨版本的状态迁移**，而 `CREATE TABLE IF NOT EXISTS`
    对已存在的表是空操作 —— 只有这一句能把 `artifact` 补到**老库**上。不补，
    跑着的那台机器就永远停在旧表上：`_COLUMNS` 里带着那一列，于是模型库列表、
    构场、实时、标定**一起**报 1054。用户那台就是这种库 —— `model` 表建于
    2026-10-09（规格书 §二），实测没有 `artifact`。

    ⚠️ **接在普通连接上，不接在 `create_app()` 里**：放进启动，MySQL 没起来时
    整个应用起不来。而本仓那条门槛「连不上要**大声报错**」指的是每次请求把原始
    那句话报出来，不是把服务变成起不来。接在这里，第一台连上库的机器自己就把
    表补上了。

    ⚠️ 每条连接都判一次闸门，但只有第一次真发语句：补列是个写库的操作，而模型库
    是每个请求都要读的东西 —— 每请求一次 DDL，第一个并发请求就会排在元数据锁上。
    """
    global _ENSURED
    if _ENSURED:
        return
    _add_artifact_column(conn)
    conn.commit()
    _ENSURED = True


def connect(*, with_db: bool = True):
    """开一条连接。**连不上就抛，绝不返回 None。**

    这条规则是整个模块的门槛：静默降级成「空库」会让「一条模型都没有」与
    「数据库连不上」在屏上长得一模一样，而这两件事要用户做的事完全不同。

    ⚠️ **唯一的例外是「库还不存在」** —— 那不是故障，是第一次跑（规格书 §四：
    「程序第一次连时 `CREATE DATABASE IF NOT EXISTS` 自建」）。没有这一步，
    任何一台还没建过 `tfield_models` 的机器上，模型库那四条路由**以及每一条走
    `get_pipeline` 的 field 路由**（它们都要读「当前模型」）在第一次启动时
    全部 500。这里现建、再连一次。

    ⚠️ **只认 1049 这一个错号**，别的错误一律原样抛：MySQL 没起来是 2003、
    口令不对是 1045 —— 把它们也当成「那就建一个吧」，会去连一个根本连不上的
    服务端，最后报的还是原来那句，而中间多了一次注定失败的建库尝试。更要紧的
    是，「连不上」与「还没有库」要用户做的事完全不同，这条线不能糊。
    """
    if business_client.java_store():
        raise DatasetContextError(409, "模型库已由 Java 管理，Python 数据库写入口已停用。")
    kw: dict[str, Any] = {
        "host": os.environ.get("TFIELD_MYSQL_HOST", "127.0.0.1"),
        "port": int(os.environ.get("TFIELD_MYSQL_PORT", "3306")),
        "user": os.environ.get("TFIELD_MYSQL_USER", "root"),
        "password": os.environ.get("TFIELD_MYSQL_PASSWORD", "123456"),
        "charset": "utf8mb4",
        "cursorclass": DictCursor,
        "autocommit": False,
    }
    if with_db:
        kw["database"] = db_name()
    try:
        conn = pymysql.connect(**kw)
    except pymysql.err.OperationalError as e:
        if not (with_db and e.args and e.args[0] == _ER_BAD_DB_ERROR):
            raise
        # 库还不存在。`init()` 走的是 `with_db=False`，所以不会绕回这里；
        # 它自己把表建出来时已经带上新列了，这里不必再补。
        init()
        return pymysql.connect(**kw)
    if with_db:
        # 库在、**表可能还是旧的**：那是这一版唯一一处跨版本迁移，
        # 靠的就是紧接在第一次连上之后补这一列（规格书 D10）。
        _ensure_columns(conn)
    return conn


def init() -> None:
    """确保库与表都在。第一次连时自建（规格书 §四）。幂等。"""
    global _ENSURED
    conn = connect(with_db=False)
    try:
        with conn.cursor() as cur:
            cur.execute(_DDL_DATABASE.format(db=db_name()))
        conn.commit()
        conn.select_db(db_name())
        with conn.cursor() as cur:
            cur.execute(_DDL_TABLE)
        _add_artifact_column(conn)
        conn.commit()
    finally:
        conn.close()
    _ENSURED = True          # 表是这一版建的，列一定在


@dataclass(frozen=True)
class ModelRow:
    """库里的**一行**，不含 `bundle`。

    列表页一次可能拉十几行，而每份包 794 KB —— 把包一起搬出来，一个十行的
    列表就是 8 MB 的响应体，而列表页一个字都不用包里的东西。
    """

    id: int
    name: str
    saved_at: str
    dataset_sig: str
    groups_sig: str
    data_file: str
    data_start: str
    data_end: str
    mae: float | None
    rmse: float | None
    r2: float | None
    is_current: bool
    #: 这一行有没有成品。**列表页只带这一个布尔**，不带那 0.9 MB 本身。
    has_artifact: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "name": self.name, "saved_at": self.saved_at,
            "dataset_sig": self.dataset_sig, "groups_sig": self.groups_sig,
            "data_file": self.data_file,
            "data_start": self.data_start, "data_end": self.data_end,
            "mae": self.mae, "rmse": self.rmse, "r2": self.r2,
            "is_current": self.is_current,
            "has_artifact": self.has_artifact,
        }


def _stamp(v: Any) -> str:
    """DATETIME 列出来的是 `datetime`，转成 ISO 串。

    `timespec="seconds"`：列本身就是秒级精度，多印几个 `.000000` 只是噪声。
    """
    if isinstance(v, datetime):
        return v.isoformat(timespec="seconds")
    return str(v)


def _row(r: dict[str, Any]) -> ModelRow:
    return ModelRow(
        id=int(r["id"]), name=str(r["name"]), saved_at=_stamp(r["saved_at"]),
        dataset_sig=str(r["dataset_sig"]), groups_sig=str(r["groups_sig"]),
        data_file=str(r["data_file"]),
        data_start=_stamp(r["data_start"]), data_end=_stamp(r["data_end"]),
        mae=None if r["mae"] is None else float(r["mae"]),
        rmse=None if r["rmse"] is None else float(r["rmse"]),
        r2=None if r["r2"] is None else float(r["r2"]),
        is_current=bool(r["is_current"]),
        has_artifact=bool(r["has_artifact"]),
    )


def report_metrics(bundle: CalibrationBundle
                   ) -> tuple[float | None, float | None, float | None]:
    """列表上那三个数：`metrics` 里 `group == "B"` 那四行的平均。

    为什么是 B 组：A/B 标签只在位置折上挂着（`validation/report.py:50-56`），
    而 A 组是**被调过参**的那一组，它比 B 组好是必然的。列表上只能放一个
    数，放 A 组的数就是把一个必然更好的数印成「这个模型多好」。

    ⚠️ 一个有限值都没有时返回 `(None, None, None)`，**不返回 0**。
    0 会被读成「误差是零」，而真相是「这一族指标没算出来」。
    """
    metrics = bundle.metrics
    if metrics is None or len(metrics) == 0 or "group" not in metrics.columns:
        return (None, None, None)
    rows = metrics[metrics["group"] == "B"]
    if len(rows) == 0:
        return (None, None, None)
    out: list[float | None] = []
    for col in ("mae", "rmse", "r2"):
        if col not in rows.columns:
            out.append(None)
            continue
        vals: list[float] = []
        for v in rows[col].tolist():
            if v is None:
                continue
            f = float(v)
            if math.isfinite(f):
                vals.append(f)
        out.append(sum(vals) / len(vals) if vals else None)
    return (out[0], out[1], out[2])


def list_models() -> list[ModelRow]:
    """全部模型，新的在前。**不含 `bundle`。** 连不上就抛。"""
    if business_client.java_store():
        return [_row(row) for row in business_client.fetch("/models")["rows"]]
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT {_COLUMNS} FROM model ORDER BY id DESC")
            return [_row(r) for r in cur.fetchall()]
    finally:
        conn.close()


def get_model(model_id: int) -> ModelRow | None:
    if business_client.java_store():
        row = business_client.fetch(f"/models/{model_id}", missing_ok=True)
        return None if row is None else _row(row)
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT {_COLUMNS} FROM model WHERE id = %s", (model_id,))
            r = cur.fetchone()
            return None if r is None else _row(r)
    finally:
        conn.close()


def load_bundle(model_id: int) -> CalibrationBundle | None:
    """把那一行里整份 JSON 读回一个 `CalibrationBundle`。

    读不动的那一份**抛**，不返回 None：`None` 与「没有这一行」长得一样，
    而这两件事一个是「库里存坏了」、一个是「你点了一个不存在的 id」。
    """
    if business_client.java_store():
        raw = business_client.fetch(f"/models/{model_id}/bundle", raw=True, missing_ok=True)
        return None if raw is None else CalibrationBundle.from_json(raw.decode("utf-8"))
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT bundle FROM model WHERE id = %s", (model_id,))
            r = cur.fetchone()
    finally:
        conn.close()
    if r is None:
        return None
    return CalibrationBundle.from_json(str(r["bundle"]))


def artifact_of(model_id: int) -> bytes | None:
    """那一行里的成品字节。没有这一行、或这一行没有成品时给 `None`。

    ⚠️ **不放进 `ModelRow`**：一屏十几行 × 0.9 MB 就是十几 MB 的响应体，
    而列表页一个字都不用成品里的东西。

    ⚠️ 返回的是 `bytes` —— `pymysql` 的 `LONGBLOB` 出来就是 `bytes`。别在这里
    做 `from_bytes`：**是不是一份读得动的成品，是 `deps` 的判断**，
    这一层只负责把字节原样搬出来（`None` / 坏字节 / 版本不对三种，
    在 `deps._artifact_of` 里分成三件事）。
    """
    if business_client.java_store():
        return business_client.fetch(f"/models/{model_id}/artifact", raw=True, missing_ok=True)
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT artifact FROM model WHERE id = %s", (model_id,))
            r = cur.fetchone()
    finally:
        conn.close()
    if r is None or r["artifact"] is None:
        return None
    return bytes(r["artifact"])


def current_id() -> int | None:
    """当前模型的行号。**`ORDER BY id DESC LIMIT 1`，不是裸 `LIMIT 1`。**

    唯一性由应用层在同一个事务里保证，但进程在事务中途被杀会留下两行都是
    当前。那时随 InnoDB 的返回次序摇摆意味着页② 说一个、页③ 画另一个，
    而屏上没有一个字提示这件事。挑 id 最大的那个是**确定的**。
    """
    context = current_model_context()
    if context is not None:
        return context.model_id
    if business_client.java_store():
        return business_client.fetch("/selection")["current_id"]
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM model WHERE is_current = 1 "
                        "ORDER BY id DESC LIMIT 1")
            r = cur.fetchone()
            return None if r is None else int(r["id"])
    finally:
        conn.close()


def save_model(name: str, bundle: CalibrationBundle, ds,
               data_file: str, *, artifact: bytes | None = None) -> ModelRow:
    """存一份**并置为当前**（规格书 D7：一个动作两个结果）。

    ⚠️ 置当前的两条 UPDATE 在**同一个事务**里：先全清零、再把这一行点起来。
    分两个事务的话，中间那一瞬库里一行当前都没有 —— 而页③ 正好在那一瞬
    取数就是空场。

    ⚠️ `data_file` / `data_start` / `data_end` 必须在**这一刻**从 `ds` 上
    抄下来：包里只有 `dataset_sig`（一个 31 字符的派生签名），**没有文件名、
    没有时间范围**。不抄，「这份模型是拿哪一段数据训的」在库上就永远看不出来，
    而它正是用户点名要看的那一列。

    ⚠️ `artifact` 走关键字、带默认 `None`：**它与包同生共死**（规格书 D3）——
    同一条 INSERT，不在事务之外另写一次 UPDATE。中间那一瞬库里会有一行
    「有包没成品」，而那正是「这一条还没有成品，选中时会现训一遍」的样子。
    """
    mae, rmse, r2 = report_metrics(bundle)
    ts = ds.wide[C.COL_TIMESTAMP]
    # DATETIME 列没有时区，存 UTC 的 naive 值。
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    start = ts.iloc[0]
    end = ts.iloc[-1]
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE model SET is_current = 0")
            cur.execute(
                "INSERT INTO model (name, saved_at, dataset_sig, groups_sig,"
                " data_file, data_start, data_end, mae, rmse, r2, is_current,"
                " bundle, artifact)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1, %s, %s)",
                (name, now, bundle.dataset_sig, bundle.groups_sig, data_file,
                 start.to_pydatetime() if hasattr(start, "to_pydatetime") else start,
                 end.to_pydatetime() if hasattr(end, "to_pydatetime") else end,
                 mae, rmse, r2, bundle.to_json(), artifact))
            new_id = int(cur.lastrowid)
        conn.commit()
    finally:
        conn.close()
    got = get_model(new_id)
    assert got is not None, "刚写进去的那一行读不回来 —— 事务提交了吗"
    return got


def set_current(model_id: int) -> bool:
    """把某一行点成当前。**没有这一行时返回 False**，不是假装成功。

    与 `save_model` 同一个事务形状（先全清零、再点起来），理由也一样。
    """
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM model WHERE id = %s", (model_id,))
            if cur.fetchone() is None:
                return False
            cur.execute("UPDATE model SET is_current = 0")
            cur.execute("UPDATE model SET is_current = 1 WHERE id = %s", (model_id,))
        conn.commit()
        return True
    finally:
        conn.close()
