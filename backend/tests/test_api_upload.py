"""上传：要么全成，要么系统不动（规格书 §4.2）。

**所有落盘都落在 `tmp_path` 上**：`paths.UPLOADS` 是模块级常量，夹具把它换掉，
所以这个文件碰不到真的 `backend/configs/` —— 也就不会把交付数据集或某个
标定包覆盖掉（那个 xlsx 在演示时可能正被 Excel 打开着）。
"""
from __future__ import annotations

import pathlib
import sys

import pandas as pd
import pytest
from fastapi.testclient import TestClient

BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from api import deps, paths, uploads   # noqa: E402
from api.main import create_app        # noqa: E402
from tfield import config as C         # noqa: E402
from tfield.data.loader import HOLDOUT_CUTOFF, test_data_path  # noqa: E402

pytestmark = pytest.mark.skipif(not test_data_path().exists(),
                                reason="交付数据集不在（与 test_api_live.py 同一口径）")

#: 交付数据集的原始字节。**只读**：这个文件演示时可能正在 Excel 里开着。
ORIGINAL = test_data_path().read_bytes()
NAME = "人参棚_副本.xlsx"


@pytest.fixture
def uploads_dir(tmp_path, monkeypatch) -> pathlib.Path:
    """把上传目录换到 tmp_path 上。**这是这个文件里最重要的一行。**

    目录**在这个夹具里就建好**：`_rewrite` / `_minimal` 造的样本要写在里面，
    而它们是**上传之前**跑的 —— 等 `accept()` 自己去 `mkdir` 就太晚了
    （报出来的是 `OSError: Cannot save file into a non-existent directory`，
    离现场很远）。反正 `accept()` 的 `mkdir(exist_ok=True)` 不介意它已存在。
    """
    d = tmp_path / "uploads"
    d.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(paths, "UPLOADS", d)
    return d


@pytest.fixture
def client(uploads_dir) -> TestClient:
    deps.set_current_dataset(paths.dataset_path())
    return TestClient(create_app())


def post(client, data: bytes, name: str = NAME):
    """`name` 走 `params=` 而不是拼进 URL。

    拼进去的话，`..\\..\\evil.xlsx` 这种带反斜杠的名字会以**原始形态**进 URL，
    由 httpx 决定怎么处理 —— 而这条路径的整个要点就是「后端收到的名字是什么」。
    交给 `params=` 编码，走的就是浏览器会走的那条路。
    """
    return client.post("/api/dataset/upload", params={"name": name}, content=data,
                       headers={"Content-Type": "application/octet-stream"})


def _rewrite(dst: pathlib.Path, *, day: str | None = None) -> pathlib.Path:
    """把交付数据集逐 sheet 读出来、改一改、写成一个新 xlsx。

    **为什么是「改交付数据集」而不是手搭一份**：`load_dataset` 要三个 sheet、
    要 24 个测点列齐全（`check_sensor_columns`）、还要「测点字典」里的
    `变量名/水平坐标(m)/高度坐标(m)`。手搭一份就是把这些约束在测试里
    再写一遍 —— 而且库改了它不会跟着改。逐 sheet 往返一次，这些都自动成立。

    `day` 给了就把所有时刻整体挪到那天（用来造跨不到切点的数据集）。
    """
    sheets = pd.read_excel(test_data_path(), sheet_name=None)
    if day is not None:
        for df in sheets.values():
            if C.COL_TIMESTAMP in df.columns:
                ts = pd.to_datetime(df[C.COL_TIMESTAMP])
                df[C.COL_TIMESTAMP] = ts + (pd.Timestamp(day) - ts.iloc[0])
    with pd.ExcelWriter(dst) as w:
        for sheet, df in sheets.items():
            df.to_excel(w, sheet_name=sheet, index=False)
    return dst


def _minimal(dst: pathlib.Path) -> pathlib.Path:
    """小到极点的数据集：**切点前后各留一行**。

    ⚠️ 计划里写的是「只剩一个时刻」。那做不到 —— 一个时刻必然有一侧是空的，
    于是那样造出来的只会是「被拒」的例子，与这条测试要证的事（**不预跑管线**，
    见 §4.2 的取舍）正好相反。
    （2026-10-16 起上传只查训练段非空，但这里仍然要两行：这条样本要证的是
    「极小的、管线 train 不起来的文件也能导入」。）
    两行是这个取舍的最小例子：能导入，但库的管线一定 train 不起来。

    只截「建模对齐数据」与「插值标记」两张逐行的表；其余 sheet 原样带过去，
    免得把「测点字典」也截成两行，动到库的解析。
    """
    sheets = pd.read_excel(test_data_path(), sheet_name=None)
    ts = pd.to_datetime(sheets[C.SHEET_MAIN][C.COL_TIMESTAMP])
    before = (ts < HOLDOUT_CUTOFF).to_numpy().nonzero()[0]
    after = (~(ts < HOLDOUT_CUTOFF)).to_numpy().nonzero()[0]
    keep = [int(before[-1]), int(after[0])]          # 训练段最后一行 + 留出段第一行
    with pd.ExcelWriter(dst) as w:
        for sheet, df in sheets.items():
            (df.iloc[keep] if sheet in (C.SHEET_MAIN, C.SHEET_QUALITY) else df) \
                .to_excel(w, sheet_name=sheet, index=False)
    return dst


# ── T3 导入成功 ──


def test_导入成功之后_current_dataset_换成了新文件(client):
    """T3：防「写了盘但没换指针」。

    断言的是 `GET /api/dataset` 报出来的**文件名与签名都换了** ——
    只看上传返回 200 是不够的：那条路径完全可能写完盘就返回，
    而指针还指着旧的。
    """
    before = client.get("/api/dataset").json()
    r = post(client, ORIGINAL)
    assert r.status_code == 200, r.text

    body = r.json()
    assert body["file"] == NAME
    assert body["n_times"] == before["n_times"]      # 同一份数据，只是换了个名字
    assert body["time_start"] == before["time_start"]

    after = client.get("/api/dataset").json()
    assert after["file"] == NAME
    assert after["signature"] != before["signature"]   # 签名含路径，必然不同
    assert after["n_times"] == before["n_times"]


def test_上传的摘要就是_GET_dataset_的那几个数(client):
    """摘要（规格书 §4.3）不是另一套算法 —— 它是同一份 Dataset 的同一批字段。"""
    body = post(client, ORIGINAL).json()
    full = client.get("/api/dataset").json()
    for k in ("n_times", "time_start", "time_end", "signature", "file"):
        assert body[k] == full[k], k


def test_极小但两侧非空的数据集能导入_管线报错留到后面几页(client, uploads_dir):
    """Review Focus 1：不预跑管线（§4.2 的取舍）。

    两行的数据集能加载、切分两侧也都非空（各一行），所以导入**必须成功** ——
    哪怕它小到训练不出任何东西。库会在页②③ 报出原话，而那是刻意的：
    宁可晚报，也不发明一个没人能背书的门槛数字。
    """
    tiny = _minimal(uploads_dir / "tmp-tiny.xlsx")
    r = post(client, tiny.read_bytes(), name="只有两行.xlsx")
    assert r.status_code == 200, r.text
    assert r.json()["n_times"] == 2


# ── T6 失败不动系统 ──


def test_失败不动系统(client):
    """T6：先导入 A（成功），再传一份坏文件 → 400，且**仍在用 A**。

    这是本文件最要紧的一条：失败路径把系统留在半坏状态的话，用户看到的是
    「导入失败了」加一屏不知道是谁算出来的内容。
    """
    first = post(client, ORIGINAL, name="第一份.xlsx")
    assert first.status_code == 200, first.text
    a = client.get("/api/dataset").json()

    bad = post(client, b"not an xlsx, just a few bytes", name="坏的.xlsx")
    assert bad.status_code == 400, bad.text
    assert bad.json()["detail"]                      # 有话说，不是空串

    still = client.get("/api/dataset").json()
    assert still["file"] == a["file"] == "第一份.xlsx"
    assert still["signature"] == a["signature"]


def test_失败之后盘上不留半份文件(client, uploads_dir):
    """§4.2 第 4 步：不通过就删临时文件。

    **`uploads_dir` 里只该有第一份那个文件**。半份的 `.part` 留着不只是脏：
    下一次同名上传会撞上它，而报出来的是个没人看得懂的 OS 错误。
    """
    post(client, ORIGINAL, name="好的.xlsx")
    assert post(client, b"nope", name="坏的.xlsx").status_code == 400
    left = sorted(p.name for p in uploads_dir.iterdir())
    assert left == ["好的.xlsx"], left


@pytest.mark.skipif(sys.platform != "win32", reason="「文件被别的程序开着」是 Windows 的语义")
def test_目标文件被占用时报_409_且不改系统(client, uploads_dir):
    """Review Focus 3：演示时那个 xlsx 很可能正被 Excel 开着。

    先导入甲（成功），再让乙这个名字在盘上存在且**被一个句柄持有**，
    然后传一份同名的 —— `os.replace` 在 Windows 上撞到被持有的目标会抛
    `PermissionError`，那必须翻成一句能照做的中文（409），而不是 500。

    持句柄这件事**已经实测过**：同进程 `open(target, "rb")` 就足以让
    `Path.replace` 抛 `PermissionError`（WinError 5）。
    """
    assert post(client, ORIGINAL, name="甲.xlsx").status_code == 200
    stuck = uploads_dir / "乙.xlsx"
    stuck.write_bytes(b"placeholder, just so the file exists")
    with open(stuck, "rb"):
        r = post(client, ORIGINAL, name="乙.xlsx")
    assert r.status_code == 409, r.text
    assert "占用" in r.json()["detail"]
    # 系统仍停在甲上，而且盘上不留半份
    assert client.get("/api/dataset").json()["file"] == "甲.xlsx"
    assert sorted(p.name for p in uploads_dir.iterdir()) == ["乙.xlsx", "甲.xlsx"]


# ── T7 切点校验 ──


def test_切点校验_留出段为空不再被拒(client, uploads_dir):
    """裁定 B 的**字面**在这里被有意推翻（规格 R6）。

    裁定①之后，用户上传的**就是** `train.xlsx`，而它的留出段按定义是空的。
    还按「两侧都必须非空」拦，正常演示的第一步就会被拒。

    ⚠️ 这份样本（全部行挪到 2026-01）训练段是满的 —— 它要证明的正是
    「留出段空」这一条**不再**是拒绝理由。
    """
    early = _rewrite(uploads_dir / "tmp-early.xlsx", day="2026-01-05 00:00:00")
    r = post(client, early.read_bytes(), name="一月的.xlsx")
    assert r.status_code == 200, f"上传 train.xlsx 这种文件被拒了：{r.text}"


def test_切点校验_训练段为空被拒(client, uploads_dir):
    """整份都在切点之后 → **训练段空** → 400。

    ⚠️ 这是放开之后**唯一**还拦着的那一侧：一份整份落在切点之后的文件，
    模型没有可学的部分。它顺手挡住了「用户交一份只含留出段的数据来训练」。
    """
    late = _rewrite(uploads_dir / "tmp-late.xlsx", day="2026-08-05 00:00:00")
    r = post(client, late.read_bytes(), name="八月的.xlsx")
    assert r.status_code == 400, r.text
    assert "2026-08-05" in r.json()["detail"]


def test_不是_xlsx_的字节报_400(client):
    r = post(client, b"\x00\x01\x02 not a zip archive", name="假.xlsx")
    assert r.status_code == 400, r.text
    assert r.json()["detail"]


# ── T8 文件名不许逃出目录 ──


@pytest.mark.parametrize("bad,want", [
    ("../../evil.xlsx", "evil.xlsx"),
    ("..\\..\\evil.xlsx", "evil.xlsx"),
    ("C:\\Windows\\evil.xlsx", "evil.xlsx"),
    ("/etc/evil.xlsx", "evil.xlsx"),
    # ⚠️ **盘符前缀是另一类，不是上面四种的又一种写法。** 上面四种都含分隔符，
    # 取 basename 就干净了；`D:evil.xlsx` 一个分隔符都没有，于是
    # `PurePosixPath("D:evil.xlsx").name` 就是整串。而它在 Windows 上是
    # **盘符相对路径** —— `上传目录 / "D:evil.xlsx"` 会**丢掉左边**
    # （右操作数带盘符就顶掉左边的盘符），临时文件跟着落到 D: 那一侧。
    # 实测：`D:evil.xlsx` 与 `Z:pwn.xlsx` 两种形状都会逃出去。
    ("D:evil.xlsx", "evil.xlsx"),
    ("Z:pwn.xlsx", "pwn.xlsx"),
])
def test_文件名不许逃出上传目录(client, uploads_dir, bad, want):
    """T8：路径穿越。六种写法，全是「文件落在 uploads 里、名字只剩 basename」。"""
    assert post(client, ORIGINAL, name=bad).status_code == 200
    assert [p.name for p in uploads_dir.iterdir()] == [want]
    assert not (uploads_dir.parent / want).exists()


def test_盘符名在_safe_name_这一层就被拿掉():
    """上一条的单测版，**故意不碰磁盘**。

    `D:evil.xlsx` 在修好之前会让 `accept()` 往 D: 上写临时文件 ——
    在 D: 存在、且它有 per-drive 当前目录的机器上，那是**真的写出去了**，
    只是随后被 `finally` 删掉。一条测试不该有这种副作用，所以这里直接问
    `safe_name` 要答案：它是被改的那个函数，也是唯一该有盘符知识的地方。
    """
    for bad, want in [("D:evil.xlsx", "evil.xlsx"), ("Z:pwn.xlsx", "pwn.xlsx"),
                      ("c:..\\evil.xlsx", "evil.xlsx")]:
        assert uploads.safe_name(bad) == want, bad


def test_中文文件名正常落盘(client, uploads_dir):
    """T8 的另一半：限路径不许把中文一起限掉。

    （`name` 走 query 不走请求头，正是为了这一条 —— §4.1。）
    """
    assert post(client, ORIGINAL, name="人参棚 第二份.xlsx").status_code == 200
    assert [p.name for p in uploads_dir.iterdir()] == ["人参棚 第二份.xlsx"]


def test_后缀不对报_415_且更早(client, uploads_dir):
    """§4.4：415 是「不是 .xlsx」，比 400 更早、更便宜 —— 一字节都不读。"""
    r = post(client, ORIGINAL, name="数据集.csv")
    assert r.status_code == 415, r.text
    assert not uploads_dir.exists() or not list(uploads_dir.iterdir())


# ── T9 上限 ──


def test_超过上限报_413_且一个字节都没落盘(client, uploads_dir, monkeypatch):
    """T9：先判后读，不先读后判。

    把上限压到 16 字节再传 100 字节 —— 断言 413，**并断言上传目录里什么都没有**。
    落盘那一侧是可观测的；「没读进内存」那一侧由 `precheck` 的单元测试钉住
    （它拿的是 `Content-Length`，在 `await request.body()` 之前）。
    """
    monkeypatch.setattr(uploads, "MAX_UPLOAD_BYTES", 16)
    r = post(client, b"x" * 100)
    assert r.status_code == 413, r.text
    assert "16" in r.json()["detail"]
    assert not uploads_dir.exists() or not list(uploads_dir.iterdir())


def test_precheck_只看名字与长度_不碰内容():
    """T9 的那一半：上限判断是**纯函数**，输入里根本没有 body。

    签名里没有 `data` 这件事本身就是「先判后读」的证据 —— 它不可能读到内容。
    """
    assert uploads.precheck("a.xlsx", 1024) is None
    assert uploads.precheck("a.xlsx", None) is None            # 没有长度头时放行
    too_big = uploads.precheck("a.xlsx", uploads.MAX_UPLOAD_BYTES + 1)
    assert too_big is not None and too_big.status == 413
    wrong_kind = uploads.precheck("a.csv", 10)
    assert wrong_kind is not None and wrong_kind.status == 415
    # 大小写不敏感：用户从相机/手机导出时后缀大小写是随机的
    assert uploads.precheck("A.XLSX", 10) is None


def test_上限由后端报出来():
    """§4.4：这个数由后端给，前端不许自己写死一个。

    `/api/health` 是既有接口里最自然的那一处（它已经在报「后端库版本」）。
    """
    deps.set_current_dataset(paths.dataset_path())
    c = TestClient(create_app())
    assert c.get("/api/health").json()["max_upload_bytes"] == uploads.MAX_UPLOAD_BYTES
    assert uploads.MAX_UPLOAD_BYTES == 32 * 1024 * 1024


# ── 起点那一头：空态 → 导入 → 有数据（验收 ①②）──


def test_从空态导入一份_这条路走得通(client):
    """**整个系统的第一条路**：还没有在用数据集 → 传一份 → 各页就有数据了。

    这一条只有在这个文件里测得出来的差别：别的上传用例都先
    `deps.set_current_dataset(...)` 把起点放在「已经有一份」上，于是
    「空态」这个**真正的起点**从来没有和上传这条路一起走过。上传路由恰好
    不在导入前读当前数据集，所以它现在是对的 —— 但没有任何东西钉着它：
    哪天有人在 `accept()` 前面加一句 `deps.current_dataset_path()`（很自然：
    想「顺手确认一下现在用的是什么」），这条路上就会多出一个 409，
    而所有别的用例照样全绿。
    """
    deps.clear_current_dataset()
    deps.reset_cache()
    empty = client.get("/api/dataset")
    assert empty.status_code == 409, empty.text      # 起点：空态

    r = post(client, ORIGINAL, name=NAME)
    assert r.status_code == 200, r.text

    after = client.get("/api/dataset")
    assert after.status_code == 200, after.text      # 导入之后，这一页就有数据了
    assert after.json()["signature"] == r.json()["signature"]
    assert after.json()["file"] == NAME


# ── 服务端自己写不动盘的时候 ──


def test_写不进上传目录时报得清_而不是裸_500(client, monkeypatch):
    """磁盘满 / 没权限时，用户要看的是「服务端写不动」，不是一片空白。

    与「文件被占用」那条（409）**必须分开**：一个是服务端自己的问题
    （换个地方、清磁盘），一个是用户关掉 Excel 就能解决的。同一条消息
    会把前者的用户指到一个关不掉的程序上去。

    ⚠️ 用 `raise_server_exceptions=False` 收 500：默认那个会把异常直接抛进
    测试里，于是断言永远跑不到 —— 而这一条要断言的正是「返回了什么」。
    """
    def boom(self, data):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(pathlib.Path, "write_bytes", boom)
    c = TestClient(create_app(), raise_server_exceptions=False)
    r = post(c, ORIGINAL, name=NAME)
    assert r.status_code == 507, r.text
    assert "写不进" in r.json()["detail"]


# ── 全局那两条 handler 各自的范围 ──


def test_别的文件不见了_不许报成数据集文件不见了(monkeypatch):
    """`FileNotFoundError → 404` 只该罩住**当前数据集**那一条路。

    非数据集的缺文件借「数据集文件不见了：<路径>」这句话混过去，是把一句
    真话用错了地方：它会让用户去重导数据集，而真正缺的可能完全是别的东西。
    更要紧的是它把**服务端自己的故障**翻成一个看着像用户问题的 404 ——
    排查的时候，手上连一条栈都没有。

    `/api/calibration` 走到这一步是因为它问 `deps.get_train_dataset()`，
    而那个出口在本仓里没有自己接住缺文件（只有 `/api/dataset` 接了）。
    """
    def boom(*a, **k):
        raise FileNotFoundError(2, "No such file or directory",
                                "C:/somewhere/else/notes.txt")

    monkeypatch.setattr(deps, "get_train_dataset", boom)
    deps.set_current_dataset(paths.dataset_path())
    c = TestClient(create_app(), raise_server_exceptions=False)
    r = c.get("/api/calibration")
    assert r.status_code != 404, r.text
    assert "数据集文件不见了" not in r.text
