"""源码级守卫：`api/routes/**` 的处理器是普通的 `def`，不是 `async def`。

**为什么需要它**（复查实测出来的，不是推理出来的）：

`POST /api/calibration/diagnostics` 是**一次真实的训练** —— 八折各拟合一遍，
只是不搜参数。它原来写成 `async def`（为了 `await request.json()` 拿请求体），
而 **FastAPI 对 `async def` 处理器的分派方式是「直接在事件循环上跑」**；
解析完请求体之后那一段又全是同步算力（`_validated_domain`、`_config_from`、
`diagnostics.get_or_compute`）。于是：

- 这份数据集 + 这份包，一次 `oof_table` 约 **15.8 秒**；
- 假替身实测：处理器里同步睡 3 秒，并发的那个 `await asyncio.sleep(0.2)`
  **到 t=4.0 秒**才被调度到 —— 循环被那 3 秒整个占住；
- 对照：同样的活儿写成普通 `def`，并发的 `/api/health` 延迟 **0.0 秒**
  （非协程处理器由 FastAPI 丢进线程池，循环是空的）。

代价：缓存未命中的那一次「开始训练」，`/api/health`、驱动参数优选进度的那条
1 秒轮询、页③ 的场与体、页⑤ 的实时帧，**全部一起等**这一个人点的那一下。
这一条没有任何运行期测试盖得住 —— `TestClient` 不断言事件循环的响应性。

**规则（不是名单）**：`backend/api/routes/**` 里的**每一个**路由处理器都写成
普通的 `def`。理由**不是**「这条接口慢」，是**这个仓的处理器普遍在做同步算力**
（pandas 切片、xgboost 拟合、IDW 插值）—— 一条新接口只要写成 `async def`，
它那一段算力就自动压在事件循环上，而写的人多半只是想 `await` 一下请求体。
按名字开白名单的路子在这里是错的：它保护不了下一条接口，而下一条接口正是
会犯同一个错的那条。

真要 `await` 的时候有两条路，都不必碰这条守卫的规则：
1. 把同步那段交给 `starlette.concurrency.run_in_threadpool` —— 于是它**真的**
   在等一个线程，`async def` 是诚实的。加进 `ASYNC_ALLOWED` 并写明理由。
2. 能拆就拆成「普通 `def` 处理器 + FastAPI 的 `Body(...)`」—— 请求体交给框架
   自己解析，你这边从头到尾同步。

`ASYNC_ALLOWED` 是本仓当前唯一一个合法例外：`dataset.py` 的 `upload_dataset`，
它 `await request.body()` 读上传流（同步的字面量体读不出来）。`test_例外只有那一个`
把它钉死 —— **每一次生长都必须落在 diff 里**，这正是那条测试存在的意义。

**为什么用 AST，而不是去查运行期的路由表**：本仓的 FastAPI / Starlette 版本
（0.139.0 / 1.3.1）把 `include_router` 注册的路由收进 `_IncludedRouter`，
`app.routes` 里**没有**那些 `/api/...` 的 `APIRoute` ——（实测：`app.routes`
共 12 条，6 条是 `_IncludedRouter`、1 条是 `Mount`，它们的 `path` 读出来是
`None`）。要翻进去得走 `effective_candidates()`、`include_context` 这些私有件，
版本一动就烂，而**烂掉的方式恰好是静默的**（找不到 = 看起来全绿）。
AST 读的是源文件，与框架版本无关；这也是本仓既有的抓手
（`test_routes_use_cache.py` 同族）。

**已知且有意接受的残余（边界，不是漏）**：
- 只认 `@router.<method>(...)` 这个形状的装饰器。有人换成
  `app.add_api_route(...)`，或者自己写一个装饰器套上去，本守卫看不见 ——
  那时要么补上这一种形状，要么承认它够不着。**别把这条守卫当成滴水不漏。**
- 只扫**模块顶层**的函数。处理器定义在别的函数体里（本仓没有这个写法）扫不到。
- 它只看「是不是 `async def`」，**看不出那段算力到底重不重**。一个真正
  便宜的 `async def` 处理器也会被拦下 —— 这是故意的：判据要能从源码一眼判定，
  而「重不重」不能。被拦下的人按上面两条路之一改，再进 `ASYNC_ALLOWED`。
"""
from __future__ import annotations

import ast
import pathlib

ROUTES = pathlib.Path(__file__).resolve().parents[1] / "api" / "routes"

#: 认得的 HTTP 方法装饰器名（`@router.get(...)` 之类）。`api_route` 一并算上。
HTTP_METHODS = frozenset({
    "get", "post", "put", "patch", "delete", "head", "options", "api_route",
})

#: **显式例外。** 键是 `(相对 api/routes 的 posix 路径, 函数名)`，不是「按后缀
#: 自动放行」那种隐式过滤：增删一行都必须改这个集合，diff 里一眼可见。
#:
#: `upload_dataset` 是**当前唯一**一个合法例外 —— 它 `await request.body()`
#: 读上传流。（它后面那段 `uploads.accept()` 也是同步的，但那不是这条守卫
#: 要管的事；改它要动数据导入那条路，不在本次改动范围内。）
ASYNC_ALLOWED = frozenset({("dataset.py", "upload_dataset")})


def _is_router_decorator(node: ast.expr) -> bool:
    """`@router.<method>(...)` 形状 —— 值的名字不叫 `router` 也行（本仓都叫它）。"""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in HTTP_METHODS
        and isinstance(node.func.value, ast.Name)
    )


def _decorator_path(node: ast.expr) -> str | None:
    """装饰器第一个位置参数的字面量（本仓的路由路径都是字符串常量）。"""
    if not isinstance(node, ast.Call) or not node.args:
        return None
    first = node.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return first.value
    return None


def _handlers() -> list[tuple[str, str, str, bool]]:
    """扫 `api/routes/*.py`，返回 `(文件, 函数名, 路由路径, 是不是协程)`。

    只认模块**顶层**的函数定义 —— 处理器就该定义在顶层，这是本仓的写法。
    """
    found: list[tuple[str, str, str, bool]] = []
    for f in sorted(ROUTES.glob("*.py")):
        tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in node.decorator_list:
                if _is_router_decorator(dec):
                    found.append((
                        f.name,
                        node.name,
                        _decorator_path(dec) or "",
                        isinstance(node, ast.AsyncFunctionDef),
                    ))
                    break
    return found


def test_路由处理器不压在事件循环上():
    """`api/routes/**` 的处理器一律是普通的 `def`，除 `ASYNC_ALLOWED` 那一行。

    ⚠️ 先确认守卫**没有空转**：扫不到处理器时下面那句 `assert` 会先红，
    免得装饰器形状一改、这条用例就成了一句永远绿的谎话。
    """
    handlers = _handlers()

    # 非空断言。底是怎么来的：本仓 `api/routes/` 下现共 **23** 个处理器
    # （calibration 2 / calibration_jobs 3 / dataset 5 / features 1 /
    # field 5 / live 7）。取 18 是留了余量、又足够说明「确实扫到了东西」的下界。
    assert len(handlers) >= 18, (
        f"`backend/api/routes/` 下只扫到 {len(handlers)} 个处理器（本仓当前 23 个）"
        " —— 装饰器形状或目录结构变了，这条守卫已经扫不到东西，成了空过"
    )

    # 把守卫与**这条**发现绑在一起：它必须确实覆盖到出问题的那条路径，
    # 而不只是「扫到了一堆别的处理器」。
    diagnostics = [h for h in handlers if h[2] == "/calibration/diagnostics"]
    assert diagnostics, (
        "扫不到 `/calibration/diagnostics` 的处理器 —— 路径改了的话，"
        "这条守卫要跟着改，而不是删掉。"
    )

    offenders = [
        f"{fname}:{name}（{path}）"
        for fname, name, path, is_async in handlers
        if is_async and (fname, name) not in ASYNC_ALLOWED
    ]
    assert not offenders, (
        "这些路由处理器写成了 `async def`：\n  "
        + "\n  ".join(offenders)
        + "\nFastAPI 会把 `async def` 的处理器**直接放在事件循环上跑** —— "
        "本仓的处理器普遍在做同步算力（pandas 切片 / xgboost 拟合 / IDW 插值），"
        "于是那一段会把整个服务冻住：`/api/health`、作业轮询、页③ 与页⑤ 的请求"
        "一起等。改成普通的 `def`（FastAPI 丢进线程池），或者保留 async 而把那段"
        "同步算力交给 `run_in_threadpool` —— 后者要加进 `ASYNC_ALLOWED` 并写明理由。"
    )


def test_例外只有那一个():
    """`ASYNC_ALLOWED` 是一份**写死的声明**。它悄悄变长，是这道守卫失效的第一种方式。

    当前只有 `dataset.py` 的 `upload_dataset`：它 `await request.body()` 读上传流，
    同步的写法读不出字面量体。加第二个之前先回答：「它那一段 `await` 真的需要
    事件循环吗，还是只是想顺手解析个请求体？」—— 后者有 `Body(...)` 这条不用
    进这份名单的路。
    """
    assert ASYNC_ALLOWED == frozenset({("dataset.py", "upload_dataset")})
