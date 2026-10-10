"""全套后端测试共用的一件事：**任何一条都不许碰用户真正的模型库。**

本仓此前没有 `conftest.py`，所有夹具都写在各测试文件里（这是第一份，也是
唯一一份）。这条规则值得破一次例，理由在**它的性质**：

2026-10-08 起，「这次用哪一份模型」要读 MySQL（`deps.current_bundle()`），
而它挂在**每一条**走 field / calibration / live 路由的用例下面 —— 本轮一次
就牵动 6 个文件、51 条用例。同一段夹具抄上十几遍，最危险的不是重复，是
**漏抄**：漏掉的那一份会连上用户真正的 `tfield_models`。那不会报错 ——
它只是让「这一条过不过」取决于用户库里存了几个模型；而 `models_db` 那一支
还会**清空**那张表（用户攒下来的模型就这么没了，屏幕上没有一个字提示）。

所以规则只写一处：

1. 这一整轮测试的库名钉死在 `tfield_models_test` 上（`_pin_test_library`）；
2. 谁把 `TFIELD_MYSQL_DB` 指到用户真正的库上，**当场报错**，不是跳过 ——
   skip 会让「这台机器上 MySQL 没配好」在结果里长得跟「全都通过」一样，
   而这两件事要人做的事完全不同；
3. 需要模型库的用例只写一行 `models_db` / `current_model`，
   见下面两个夹具的说明。

**数据库必须真的在**（127.0.0.1:3306，root/123456）。连不上就让它抛
`pymysql.err.OperationalError` —— 与 `api/models_store.py` 那条「绝不静默
降级成空库」是同一条规则，只是这里把它贯彻到测试上。
"""
from __future__ import annotations

import dataclasses
import os

import pytest

#: 测试库。与 `tests/test_models_store.py` 用的是同一个 —— 那个文件是这条
#: 约定的起点，这里的 `models_db` 就是它那个 `db` 夹具上移过来的。
TEST_DB = "tfield_models_test"

#: 用户真正的库。**任何一条测试都不许碰它**（规格书 §四）。
REAL_DB = "tfield_models"


def pytest_configure(config):
    """登记 `empty_library` 这个标记。

    不登记的话 `-W error` 或 `--strict-markers` 下它会红，而更常见的后果是
    拼错一个字（`empty_libary`）之后**静默失效**：标了等于没标，用例照旧
    拿到一份有模型可用的库，于是「空态」那一组全都在测有包的那条路 ——
    红绿都还在，测的东西换了。
    """
    config.addinivalue_line(
        "markers",
        "empty_library: 这一条要一个**空**的模型库。"
        "默认相反：库里存着交付数据集训练段的那一份真包（见 current_model）。")


@pytest.fixture(scope="session", autouse=True)
def _pin_test_library():
    """把这一整轮测试钉在测试库上。**只改环境变量，不碰数据库。**

    session 级：一旦钉上，本轮里没有任何一条用例能读到别的库名。
    """
    name = os.environ.get("TFIELD_MYSQL_DB") or TEST_DB
    assert name != REAL_DB, (
        f"TFIELD_MYSQL_DB 指着用户真正的模型库（{REAL_DB}）—— 测试会清空它。"
        f"去掉这个环境变量（就会用 {TEST_DB}），或者把它指到别的库上。")
    os.environ["TFIELD_MYSQL_DB"] = name
    return name


def empty_library():
    """一个**空的**模型库：库和表都在，一行模型都没有。返回 `models_store`。

    底下三样一起做，缺一个都测不成：
      · `init()` —— 库与表**真的存在**（`connect()` 对不存在的库直接抛，
        不会替你建）；
      · `TRUNCATE` —— 上一个用例存进去的东西不许留到这里；
      · 不开着连接不放 —— 夹具只负责摆好桌子，取数由被测代码自己连，
        否则测的就成了「夹具那条连接」而不是生产路径。

    写成模块级函数而不是夹具体：`models_db` / `library_module` / `empty_now`
    三个夹具都要它，而 pytest 的夹具不能互相调用。
    """
    from api import models_store

    models_store.init()
    conn = models_store.connect()
    try:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE model")
        conn.commit()
    finally:
        conn.close()
    return models_store


@pytest.fixture()
def models_db():
    """空库（见 `empty_library` 的说明）。要的只是「库连得上」的用例用它。"""
    return empty_library()


#: 交付数据集那两份包在 `configs/` 里的**文件名**。
#:
#: ⚠️ 写死文件名，而不是「按 `dataset_sig` 去认」—— 那个字段是**逐机**的，
#: 理由在 `_delivered_bundle` 上。这两份是仓库里**跟踪**的文件（本机盘上另外
#: 那两份 `0066856d…` / `3fbf0c…` 没进仓库），别人的克隆里它们在、指纹却对不上。
DELIVERED_FULL = "bundle_6145fa9261e89f1b_d6294c09.json"
DELIVERED_TRAIN = "bundle_6145fa9261e89f1b-h20260727T1200_d6294c09.json"

#: 读过的包按文件名缓存（包是 frozen dataclass，且解一份 794 KB 的 JSON 不便宜）。
_DELIVERED: dict[str, object] = {}


def _load_delivered(name: str):
    """按**文件名**读 `configs/` 里那份交付包；读不到就**当场报错**。

    报错而不是返回 None：这两份包是跟踪进仓库的，少了它就是有人删了不该删的
    东西 —— 而用它的用例会**静默**退到兜底参数那条路（见 `_delivered_bundle`），
    红绿都还在、测的东西换了。宁可炸在夹具里。
    """
    from api import paths
    from tfield.calibration import load_bundle

    if name not in _DELIVERED:
        p = paths.CONFIGS / name
        b = load_bundle(p)
        assert b is not None, (
            f"`{p}` 不在或读不动 —— 这两份交付包是**仓库里跟踪的**文件，"
            "新克隆里它们必须原样在（用它的用例一条都验不成）")
        _DELIVERED[name] = b
    return _DELIVERED[name]


def _delivered_bundle(full: bool = False):
    """盘上那份交付包，`dataset_sig` 已**重签成本机的指纹**。

    ⚠️ 为什么必须重签：`dataset_signature(path)` = `sha1(绝对路径 | mtime |
    大小)[:16]` —— **绝对路径本身就是数据集身份的一部分**（根 `README.md`
    §「标定包为什么在 `configs/` 里是那个怪名字」整节在讲这件事）。包身上那串
    指纹是**产出它的那台机器、那个目录**算出来的。于是：

      · 在**本机**（产出这两份包的那台），`want` 与包上那个字段逐位相同，
        重签是个 no-op；
      · 在**别人的克隆**里路径变了，`want` 是新指纹。不重签的话，
        `current_bundle()` 会（**正确地**）判它「与训练段对不上」而当作库里
        没有模型 —— 于是每一个用 `current_model` 的用例都退到兜底参数那条路
        上：红/绿都还在，测的东西换了，而没有一个字提示。
        **2026-10-11 那次「新克隆 92 error + 7 failed」的全部内容就是这个。**

    重签动的只有 `dataset_sig` 这一个**指路**字段，包里的参数、效果、逐折
    MAE 一个字节都不动 —— 这正是 `scripts/relocate_bundle.py` 对真实项目做的
    事。⚠️ 唯一少的是那道**逐字节证明**（那份脚本用 sha256 比对新旧数据集，
    证明内容真是同一份）；这里拿不到原项目的数据集，证不了。它成立的前提是
    **数据集与这两份包一起跟踪在仓库里**，「同一份文件、不同路径」由 git 保证。
    真有人把数据集换掉了，是另一件事 —— 那时要重标，而逐折 MAE 那几条用例
    （`test_api_train.py`）会说话。

    ⚠️ 也不能图省事写 `sorted(paths.CONFIGS.glob("bundle_*.json"))[0]`：本机盘上
    有**四份**包，排序第一的是 `0066856dc40a8bbc-…`（**另一份数据集**标的，没进
    仓库）。本机取到它、克隆里取到的是另一份 —— 同一个文件在两台机器上测的是
    两份不同的包，而画面上什么都看不出来。
    """
    from api import deps

    # 「当前数据集」还空着时先指到交付那一份 —— 否则 `get_train_dataset()` 会抛
    # `NoDatasetError`，而报错地点在一次夹具调用里、离现场很远（见 `_ensure_dataset`）。
    _ensure_dataset()
    name = DELIVERED_FULL if full else DELIVERED_TRAIN
    want = (deps.get_dataset() if full else deps.get_train_dataset()).signature
    b = _load_delivered(name)
    if b.dataset_sig == want:
        return b
    return dataclasses.replace(b, dataset_sig=want)


def delivered_train_bundle():
    """交付数据集**训练段**那一份包，已重签成本机指纹。见 `_delivered_bundle`。"""
    return _delivered_bundle()


def delivered_full_bundle():
    """交付数据集**整份文件**那一份包，已重签成本机指纹。见 `_delivered_bundle`。"""
    return _delivered_bundle(full=True)


def bundle_for_another_dataset():
    """一份**为别的数据集标的**包：拿交付那份换个签名。

    ⚠️ 合成而不是「从盘上找一份别人的」：盘上有没有别的包取决于谁在这台机器上
    跑过标定（本机那两份就没进仓库），**克隆的人手上根本没有**，于是「用它的
    用例」在别人那里一条都跑不起来。

    ⚠️ 换的是**这一个对象**，行与包因此一起变：`save_model` 把
    `bundle.dataset_sig` 抄进行里、又把整包写进 LONGTEXT。只改库里那一行的
    字段才是不行的 —— `current_bundle()` 从行上读、构场从包上读，那样会造出
    「行说 A、包说 B」这种线上不存在的状态，测的东西就换了。
    """
    return dataclasses.replace(delivered_train_bundle(),
                               dataset_sig="别的一份数据集")


def _ensure_dataset() -> None:
    """「当前数据集」还空着时指到交付那一份。已经设好时**不覆盖**。

    ⚠️ 这一句不是客套。conftest 里的夹具会**先于**各测试文件自己的 autouse
    夹具（`_current_dataset`）跑，于是此刻指针多半还是空的，「当前数据集」那条
    路会抛 `NoDatasetError`，而报错地点在一份夹具里，离现场很远。

    已经设好时**不覆盖**：有的用例故意把数据集换成另一份（换数据集那几条），
    覆盖它等于把它们的前提悄悄改掉。
    """
    from api import deps, paths
    from api.errors import NoDatasetError

    try:
        deps.current_dataset_path()
    except NoDatasetError:
        deps.set_current_dataset(paths.dataset_path())


@pytest.fixture()
def delivered_bundle():
    """交付数据集训练段那一份真包，**已重签成本机指纹**。见 `_delivered_bundle`。

    要它的用例关心的是包里的东西（参数 / 效果 / 搜索区间），与库无关；
    指纹为什么要重签、为什么不是 `sorted(glob)[0]`，那两件事写在
    `_delivered_bundle` 上。
    """
    _ensure_dataset()
    return _delivered_bundle()


def seed_delivered_model():
    """把交付数据集训练段那一份包存成**当前模型**，返回那一行。

    与 `empty_library` 同理，是模块级函数而不是夹具体：三个夹具要用它。
    """
    from api import deps, paths

    _ensure_dataset()
    ds = deps.get_train_dataset()
    return empty_library().save_model("交付那一份", _delivered_bundle(), ds,
                                      paths.dataset_path().name)


@pytest.fixture()
def current_model(models_db, request):
    """库里那一份**当前模型**，默认是交付数据集训练段的那一份真包。

    **为什么默认是「有」而不是「没有」**：2026-10-08 之前，「用哪一份模型」
    是 `load_for(ds, groups, paths.CONFIGS)` —— 盘上那份包一直在，所以
    `/api/calibration` 的 `present` 一直是 `true`。现在唯一的来路是模型库，
    要想让那些用例**原样**成立（包括它们断言的那些数：`created_at`
    `2026-10-05T13:52:09+00:00`、`groups_sig d6294c09`、八折、A/B 两组的
    MAE），库里就必须存着**同一份**包。这是逐位复现，不是另造一个样本。

    要空态的用例标 `@pytest.mark.empty_library` —— 那些用例过去是把
    `CONFIGS_ROOT` 指到一个空目录来造空态的，而空态现在由**库里有没有当前
    模型**决定，那条路已经不灵了（指了也是空转：`present` 不再问盘）。
    """
    if request.node.get_closest_marker("empty_library") is not None:
        return None
    return seed_delivered_model()


@pytest.fixture(scope="module")
def library_module():
    """`current_model` 的**模块级**版本：清一次、种一次，整个模块共用。

    ⚠️ 给的是那些用 module 级数据夹具的文件（`test_api_field` /
    `test_api_volume` / `test_api_diagnostics`：它们把一次真实请求的响应体
    缓存在 `sections` / `volume` / `oof` 里，模块里每条用例都拿它当基准比）。
    pytest **先建大作用域的夹具**，函数级的 `current_model` 对它们来说跑得
    太晚 —— 那些夹具会拿着**空库**建出载荷，而后面每一条都在拿这个载荷
    比：红绿都还在，测的东西换了。

    ⚠️ 也因此，用它的文件**不能**靠 `@pytest.mark.empty_library` 要空态
    （标记是逐个用例看的，而种子是整个模块一次性种的）。要空态的那条用例
    自己请求 `empty_now`。
    """
    empty_library()
    return seed_delivered_model()


@pytest.fixture()
def empty_now():
    """临时把库清空（模块级种好的那一份被删掉），**用完种回去**。

    给「模块级种着、但某一条用例要空态」的那几处用。不种回去的话，同一
    模块里排在它后面的用例会拿到一个空库 —— 而它们多半对此毫无意见
    （`present: false` 也是合法响应），于是静默地测了另一条路。
    """
    empty_library()
    yield None
    seed_delivered_model()
