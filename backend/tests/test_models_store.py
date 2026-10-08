"""模型库的存取层：连接、建表、存一份、取回来。

⚠️ **这个文件要一个活着的 MySQL。** 本仓此前的后端测试都是全封闭的（临时目录 +
`TestClient`），这一条改变那件事 —— 代价由规格书 D1 第 2 点当面记着。连不上时
**不 skip**：skip 会让「这台机器上 MySQL 没了」在测试结果里长得跟「全都通过」
一样，而验收第 7 条要的恰恰是相反的行为。

⚠️ **用独立的库 `tfield_models_test`**（环境变量 `TFIELD_MYSQL_DB` 覆盖）。
绝不动用户真正的 `tfield_models`。
"""
from __future__ import annotations

import dataclasses
import pathlib
import sys

import pytest
from pymysql.err import MySQLError

BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from api import deps, models_store, paths              # noqa: E402
from tfield.calibration import load_bundle             # noqa: E402


def _real_bundle():
    """一份真包。**只读**，不改盘上任何东西。"""
    real = load_bundle(sorted(paths.CONFIGS.glob("bundle_*.json"))[0])
    assert real is not None
    return real


@pytest.fixture(scope="module")
def ds():
    """训练段。整份 1308 行的 xlsx 加载约 1 秒，一个模块只加载一次。"""
    deps.set_current_dataset(paths.dataset_path())
    return deps.get_train_dataset()


@pytest.fixture()
def db(monkeypatch):
    """把这一整套测试指到 `tfield_models_test` 上，每格从空表开始。

    ⚠️ 改的是**环境变量**而不是模块常量：`models_store` 每次调用现读环境，
    所以这里改一个变量就够了 —— 而如果它把配置读成模块级常量，这个夹具就
    改不动它，测试会静默地跑到用户真正的库上去。
    """
    monkeypatch.setenv("TFIELD_MYSQL_DB", "tfield_models_test")
    models_store.init()                      # 连不上就抛，不 skip（见文件头）
    conn = models_store.connect()
    try:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE model")
        conn.commit()
    finally:
        conn.close()


def test_存进去再取出来_整份签名一个字符都不少(db, ds):
    """⭐ Review Focus 1b：`dataset_sig` 是 31 个字符。

    规格书 §四 的 DDL 写的是 `CHAR(16)`，那会把这个签名截成
    `0066856dc40a8bbc` —— 丢掉 `-h20260727T1200` 那一段。截断之后
    「同一份文件的训练段」与「整份文件」会撞成同一个值，而兼容性判定
    比的就是它。这条测试就是那个截断的钉子。
    """
    bundle = _real_bundle()
    row = models_store.save_model("棚里那套", bundle, ds, "人参棚.xlsx")
    assert row.id > 0
    assert row.dataset_sig == bundle.dataset_sig
    assert len(row.dataset_sig) == 31, "签名被列宽截断了"
    got = models_store.get_model(row.id)
    assert got is not None
    assert got.dataset_sig == bundle.dataset_sig
    assert got.groups_sig == bundle.groups_sig
    assert got.name == "棚里那套"
    assert got.data_file == "人参棚.xlsx"


def test_训练段的时间范围跟着_ds_走(db, ds):
    """用户要看的那一列是「这份模型是拿哪一段数据训的」—— 包里没有，必须抄。"""
    import pandas as pd

    from tfield import config as C

    row = models_store.save_model("x", _real_bundle(), ds, "f.xlsx")
    ts = ds.wide[C.COL_TIMESTAMP]
    assert pd.Timestamp(row.data_start) == pd.Timestamp(ts.iloc[0])
    assert pd.Timestamp(row.data_end) == pd.Timestamp(ts.iloc[-1])


def test_指标取的是_B_组那四行的平均(db, ds):
    """⭐ Review Focus：A 组是**被调过参**的位置，把它的数印在列表上
    就是把一个必然更好的数说成「这个模型多好」。B 组是唯一带「没参与挑参」
    这个标签的一族（`validation/report.py:50-56`）。
    """
    bundle = _real_bundle()
    mae, rmse, r2 = models_store.report_metrics(bundle)
    rows = bundle.metrics[bundle.metrics["group"] == "B"]
    assert len(rows) == 4, "B 组不是四行 —— 报告的分组变了，这条得跟着改"
    assert mae == pytest.approx(float(rows["mae"].mean()))
    assert rmse == pytest.approx(float(rows["rmse"].mean()))
    assert r2 == pytest.approx(float(rows["r2"].mean()))


def test_一个有限值都没有时给_None_不给_0():
    """0 会被读成「误差是零」，而真相是「这一折没算出来」。"""
    bundle = _real_bundle()
    nan = float("nan")
    blank = dataclasses.replace(
        bundle, metrics=bundle.metrics.assign(mae=nan, rmse=nan, r2=nan))
    assert models_store.report_metrics(blank) == (None, None, None)


def test_保存即置为当前_而且只有一行是当前(db, ds):
    bundle = _real_bundle()
    a = models_store.save_model("一", bundle, ds, "f.xlsx")
    b = models_store.save_model("二", bundle, ds, "f.xlsx")
    assert models_store.current_id() == b.id
    conn = models_store.connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM model WHERE is_current = 1")
            assert cur.fetchone()["n"] == 1
    finally:
        conn.close()
    assert a.id != b.id


def test_设为当前之后原来那一行不再是当前(db, ds):
    bundle = _real_bundle()
    a = models_store.save_model("一", bundle, ds, "f.xlsx")
    models_store.save_model("二", bundle, ds, "f.xlsx")
    assert models_store.set_current(a.id) is True
    assert models_store.current_id() == a.id
    assert models_store.set_current(999999) is False, "没有这一行时要说 false，不是假装成功"


def test_两行都标了当前时确定性挑一行(db, ds):
    """⭐ Review Focus 2。

    唯一性由应用层在同一个事务里保证，但**进程在事务中途被杀**会留下两行。
    那时人期待的是「确定地拿到一个模型、两页拿到同一个」—— 而不是随
    InnoDB 的返回次序摇摆（页② 说这个、页③ 画那个，屏上没有一个字提示）。
    """
    bundle = _real_bundle()
    a = models_store.save_model("一", bundle, ds, "f.xlsx")
    b = models_store.save_model("二", bundle, ds, "f.xlsx")
    conn = models_store.connect()
    try:
        with conn.cursor() as cur:                  # 手工造出「两行都是当前」
            cur.execute("UPDATE model SET is_current = 1")
        conn.commit()
    finally:
        conn.close()
    assert models_store.current_id() == max(a.id, b.id)
    assert models_store.current_id() == models_store.current_id()


def test_包原样存取_一个字节都不差(db, ds):
    """库里那一列是 `LONGTEXT`，存的是整份 JSON。

    ⚠️ **比的是 `to_json()`，不是 `to_dict()`。** 这一条原来写的是
    `back.to_dict() == bundle.to_dict()`，它**永远红**：`search.trials` 里
    有一千多个 NaN（每个试验里没被抽到的参数），而 `nan != nan` —— 两边
    内容一模一样，字典比较照样为假。红的理由与存取无关，改起来会一路改歪。

    `to_json()` 在这里是稳定的：`to_dict()` 是一个字面量字典（插入序固定），
    `json.dumps` 的 `indent=2` 也固定，所以同一份内容两次序列化逐字节相同。
    （「键序不保证稳定」那句话是对**任意**字典说的，对这个函数不成立。）

    而且它比 `to_dict()` 更贴题：库里那一列存的就是 `to_json()` 出来的这串
    文本，逐字节相等即「存进去什么、取出来什么」。
    """
    bundle = _real_bundle()
    row = models_store.save_model("x", bundle, ds, "f.xlsx")
    back = models_store.load_bundle(row.id)
    assert back is not None
    assert back.to_json() == bundle.to_json()
    assert models_store.load_bundle(999999) is None


def test_连不上时报原话_不静默当成空库(monkeypatch):
    """⭐ Review Focus 1。

    静默返回 `[]` 会让「一条模型都没有」与「数据库连不上」在屏上长得
    一模一样 —— 而这两件事要用户做的事完全不同（一个是去训一个，一个是
    去把 MySQL 起起来）。所以这里断言它**抛**，而不是返回空。
    """
    monkeypatch.setenv("TFIELD_MYSQL_PORT", "1")     # 这个端口上没有东西在听
    with pytest.raises(MySQLError):
        models_store.list_models()


def test_列表不带包_只有一行字段(db, ds):
    """列表要能一列扫下来。794 KB 的 JSON 一行一个，十个模型就是 8 MB。"""
    models_store.save_model("x", _real_bundle(), ds, "f.xlsx")
    rows = models_store.list_models()
    assert len(rows) == 1
    assert "bundle" not in rows[0].to_dict()
    assert set(rows[0].to_dict()) == {
        "id", "name", "saved_at", "dataset_sig", "groups_sig", "data_file",
        "data_start", "data_end", "mae", "rmse", "r2", "is_current"}
