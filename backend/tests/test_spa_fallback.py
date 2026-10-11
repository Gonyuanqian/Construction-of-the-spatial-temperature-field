"""生产形态的路由回退：F5 与直接粘地址都要看得见系统，而不是 404。

**为什么需要回退**：前端路由用 `createWebHistory()`（`frontend/src/router/index.ts`），
所以真实路径就是 `/data` 与 `/train`。开发形态（Vite 5173）自带 history 回退，
没这个问题；但生产形态只起 8503 一个进程时，`StaticFiles(html=True)` **只对
「目录请求」**回 `index.html` —— 任何「不是真实文件」的路径一律 404。
于是「在 8503 上按 F5」或「把 http://localhost:8503/train 贴进地址栏」看到的
是一页 404，而不是系统。

**回退的边界**（这条测试盯的就是它）：
- 非 API 的未知路径 → 200 `text/html`，内容是构建产物里的 `index.html`；
- `/assets/<真实产物>` → 仍然 200，MIME 仍然对；
- `/api/<写错的接口>` → **必须仍是 404 JSON**。回退做宽了，「接口名写错」
  会被伪装成一张能打开的空页面 —— 比 404 危险得多。

**为什么 dist 不在就 skip**：`frontend/dist` 不进 git（新克隆里没有），
这条测试依赖构建产物。缺席时平白变红是最糟的，所以显式 skip 并写明原因。
"""
from __future__ import annotations

import pathlib
import sys

import pytest
from fastapi.testclient import TestClient

BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from api import paths                                    # noqa: E402
from api.main import create_app                          # noqa: E402

INDEX = paths.DIST / "index.html"

pytestmark = pytest.mark.skipif(
    not INDEX.is_file(),
    reason="需要先跑过 npm run build：frontend/dist/index.html 不在，"
           "生产形态的角色回退无从谈起。frontend/dist 不进 git，"
           "新克隆里这条测试不该平白变红。",
)


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


def _index_text() -> str:
    """构建产物的正文，**按它自己的行尾**读出来。

    不能用 `Path.read_text()`：它默认走通用换行，把 CRLF 折成 LF。而 Vite 在
    Windows 上生成的 `dist/index.html` 行尾是 **Windows 的 CRLF 掺着少数 LF**
    （HTML 变换自己吐的行是 LF）—— 响应把磁盘字节原样送出，于是拿折过的文本去比
    `r.text`，永远差一个 `\\r`，5 条参数化用例全红，而错的是**读法**不是实现。

    这里要的是「磁盘上的字节解码成 str」，不是「按文本行读」——`newline=""` 关掉
    换行翻译。用它还有个好处：将来在哪台机器上构建，产物是 LF 还是 CRLF，这条
    断言都成立（两边都不翻译，就永远同形）。
    """
    with INDEX.open("r", encoding="utf-8", newline="") as f:
        return f.read()


@pytest.mark.parametrize(
    "path",
    ["/", "/data", "/train", "/index.html", "/一个不存在的页面/子路径"],
)
def test_前端路由与未知路径都回退到_index_html(client, path):
    r = client.get(path)
    assert r.status_code == 200, f"{path} 返回 {r.status_code}，应是 200"
    assert r.headers["content-type"].startswith("text/html"), r.headers["content-type"]
    assert r.text == _index_text(), f"{path} 回的不是构建产物里的 index.html"


def test_真实产物文件仍然照常返回(client):
    """回退不能把 `/assets/**` 一起吞掉 —— 那正是全局 catch-all 会犯的错。"""
    assets = sorted(p for p in (paths.DIST / "assets").iterdir() if p.is_file())
    assert assets, "构建产物里没有 assets/ 下的文件，无法验证静态文件仍可访问"
    for f in assets:
        r = client.get(f"/assets/{f.name}")
        assert r.status_code == 200, f"/assets/{f.name} 返回 {r.status_code}"
    js = [f for f in assets if f.suffix == ".js"]
    css = [f for f in assets if f.suffix == ".css"]
    if js:
        ct = client.get(f"/assets/{js[0].name}").headers["content-type"]
        assert "javascript" in ct, f"JS 产物的 MIME 不对：{ct}"
    if css:
        ct = client.get(f"/assets/{css[0].name}").headers["content-type"]
        assert "css" in ct, f"CSS 产物的 MIME 不对：{ct}"


def test_接口名写错仍然是_404_不是一张能打开的空页面(client):
    """**这条最关键。** 回退如果做宽了，`/api/date` 这种手滑会被回一张
    200 的 index.html —— 前端路由再把未知路径重定向回页①，于是「接口写错」
    看起来像「打开了一页」，报错信号彻底消失。"""
    r = client.get("/api/这个接口根本不存在")
    assert r.status_code == 404, f"未知接口返回了 {r.status_code} —— 回退做宽了"
    assert r.headers["content-type"].startswith("application/json"), r.headers["content-type"]


@pytest.mark.parametrize("path", ["/api", "/api/", "/api?x=1"])
def test_裸_api_也要_404_JSON(client, path):
    """只差一个斜杠也不能被伪装成页面。

    回退守卫若写成 `scope["path"].startswith("/api/")`，裸 `/api` 会漏过去 ——
    它不满足 `/api/` 前缀，于是被回一张 200 的 index.html。而「把接口路径写错」
    最常见的形态恰恰就是少一个斜杠或漏一段（`/api`、`/api?t=1`）。
    """
    r = client.get(path)
    assert r.status_code == 404, f"{path} 返回了 {r.status_code} —— 裸 /api 被回退成了页面"
    assert r.headers["content-type"].startswith("application/json"), r.headers["content-type"]



@pytest.fixture(autouse=True)
def _current_dataset():
    """空态成为默认之后，这个文件也必须**显式声明**它测的是哪一份数据集。

    2026-10-06 起，「当前在用哪一份数据集」是一个进程级的模块变量，启动时为空
    （规格书 §1.1 的空态）。不声明的话，这个模块里凡是碰数据集的用例都会拿到 409，
    而报错位置离现场很远。

    写成 autouse 而不是改各文件形状各异的 `client` 夹具，是因为本仓还有 **6 处**
    在测试里**内联**建 `TestClient(create_app())`（test_api.py ×2、
    test_api_train.py ×3、test_deps.py ×1）—— 它们同样要碰数据集，
    而只改 `client` 夹具会漏掉它们。一段代码、12 个文件、一模一样。
    """
    from api import deps, paths
    deps.set_current_dataset(paths.dataset_path())
