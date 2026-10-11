"""FastAPI 应用。

启动（开发）：
    cd backend && python -m uvicorn api.main:app --port 8503 --reload
端口 8503 写在 `paths.API_PORT`（单一真源），不靠命令行参数 —— 免得谁直接敲 uvicorn 时落回 8000，
前端却还以为它在 8503。
"""
from __future__ import annotations

import os
import pathlib
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.types import Scope

from tfield.calibration import TOOL_VERSION

from . import deps, paths, uploads
from .errors import NO_DATASET_DETAIL, NoDatasetError
from .routes import calibration as calibration_routes
from .routes import calibration_jobs as calibration_jobs_routes
from .routes import dataset as dataset_routes
from .routes import features as features_routes
from .routes import field as field_routes
from .routes import live as live_routes
from .routes import models as models_routes

VITE_DEV_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]


def _is_api_path(path: str) -> bool:
    """/api 与 /api/** 都算接口路径。**裸 `/api` 也要算** ——
    只写 `startswith("/api/")` 的话，少一个斜杠的 `/api`（接口路径写错最常见
    的形态）会漏进前端回退，被伪装成一张 200 的空页面。`scope["path"]` 不含
    query，所以 `?x=1` 之类不必在这里处理。"""
    return path == "/api" or path.startswith("/api/")


class SPAStaticFiles(StaticFiles):
    """静态产物 + SPA history 回退。

    **为什么需要它**：前端用 `createWebHistory()`，真实路径是 `/data` 与 `/train`。
    开发形态（Vite 5173）自带回退，没问题；生产形态只起 8503 一个进程时，
    `StaticFiles(html=True)` **只对「目录请求」**回 `index.html`，任何「不是真实
    文件」的路径一律 404 —— 于是 F5 或直接粘 `/train` 地址看到的是 404 而不是系统。

    **为什么用子类，不用 `@app.get("/{full_path:path}")` 全局 catch-all**：
    catch-all 会把 `/assets/**` 一起吞掉 —— 真实产物反过来变成 404，或者回一张
    index.html（MIME 全错，浏览器拒绝执行脚本，页面白屏）。子类只在**基类已经
    判定 404 之后**才插手，产物文件走的是同一条 `file_response`，MIME 一个字节不变。

    **为什么 `/api` 与 `/api/**` 要重新抛出**：回退做宽了，「接口名写错」（`/api/date`）
    会被回一张 200 的 index.html，前端路由再把未知路径重定向回页① —— 报错信号彻底
    消失，比一个诚实的 404 危险得多。判据见 `_is_api_path`（裸 `/api` 也算）。
    """

    def __init__(self, *, directory: str, **kwargs: Any) -> None:
        super().__init__(directory=directory, html=True, **kwargs)
        # 回退目标在构造时算好：不用 `paths.DIST`，否则测试里 monkeypatch 不到，
        # 而且请求线程里再拼路径纯属多余。
        self._index = os.path.join(directory, "index.html")

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code == 404 and not _is_api_path(scope["path"]):
                # 交给前端路由去分派（`/:rest(.*)*` 会落回页①）。
                return FileResponse(self._index)
            raise


def _is_current_dataset(target: Any) -> bool:
    """这个缺掉的文件，是不是**现在正该用的那一份数据集**。

    ⚠️ 判据是「就是它」，不是「在上传目录里」：后者会把上传目录里任何一个
    别的缺文件也算进来，而那正是这条 handler 要划清的那条线。

    取不到当前数据集（压根是空态）时返回 False —— 空态下「还没有在用数据集」
    由 409 那条 handler 管，此时冒出来的 `FileNotFoundError` 必然不是数据集的事。

    ⚠️ 拿不到 `filename` 也返回 False，不猜。猜错的方向只有一个：把一次真故障
    说成「数据集文件不见了」，然后让人去重导一份数据集。
    """
    if not target:
        return False
    try:
        current = deps.current_dataset_path()
    except NoDatasetError:
        return False
    # `Path` 的比较在 Windows 上不分大小写（`PureWindowsPath` 的语义），
    # 正是这里要的：盘符与路径的大小写不该决定报 404 还是 500。
    return pathlib.Path(str(target)) == pathlib.Path(current)


def create_app() -> FastAPI:
    # version 取自 `tfield.calibration.TOOL_VERSION`，不写字面量：
    # 标定包的 `tool_version` 用的是同一个数，两处各写一份就会漂 ——
    # 漂开之后 OpenAPI 文档说一个版本、盘上的标定包说另一个，
    # 验收对盘时不知道该信谁。这里与 /api/health 也共用同一个来源。
    # 标题与前端 `design/copy.ts` 里的 SYSTEM_TITLE 是同一个名字（`/docs` 上给
    # 人看的就是它）。前端那边有一条守卫扫全仓盯着这个名字，这里不写名字的
    # 第二份定义 —— 跨语言拼不出单一来源，就靠那条守卫把两处钉成同一个串。
    app = FastAPI(title="棚式空间温度场重建系统 API", version=TOOL_VERSION)
    # 开发时前端在 5173，与 API 不同源。生产形态是同源（下面的静态托管），
    # 那份 CORS 配置不起作用也不碍事。
    app.add_middleware(
        CORSMiddleware,
        allow_origins=VITE_DEV_ORIGINS,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # ── 数据集那两种错，各翻各的 ──
    #
    # **为什么写进全局 handler 而不是每一条路由自己判**：这两个判断要在
    # **每一条**接口上成立，而「以后新加的路由也不会漏」只有挂在全局才成立。
    # 路由里各写一遍，漏一条就是一个 500 —— 而且漏的那条看起来和别的没区别。
    #
    # ⚠️ 两者**必须分开**（规格书 §二.1）：
    #   409 = 还没导入。这是系统的**起点**，不是故障。
    #   404 = 刚才还在用，盘上没了。这是故障。
    # 合成一种，界面就会把「你还没开始」说成「出错了」，
    # 而验收的人第一次打开系统看到的正是那一屏。
    @app.exception_handler(NoDatasetError)
    async def _no_dataset(_req: Request, _exc: NoDatasetError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": NO_DATASET_DETAIL})

    # ⚠️ 这条只管**当前数据集那一份文件**。
    #
    # 上一版是不管谁的缺文件一律 404。那样把「文件不见了」在每一条接口上都
    # 立起来了，代价是认下来的：**非数据集的缺文件也被说成数据集的事**。
    # 那句话会让用户去重导数据集，而真正缺的可能完全是别的东西；更要紧的是
    # 它把**服务端自己的故障**（磁盘、权限、写坏的路径）翻成一个看着像用户
    # 问题的 404 —— 排查的时候手上连一条栈都没有。
    #
    # 划清之后，计划原本要的那件事一点没少：数据集可能在任何一条接口上
    # 缺掉，而这里判的是「缺的就是它」，与哪条接口无关。
    @app.exception_handler(FileNotFoundError)
    async def _file_gone(_req: Request, exc: FileNotFoundError) -> JSONResponse:
        # `filename` 由 `open()` 那一层填，实测就是这个文件的绝对路径。
        # **不再回退到 `exc.args[0]`**：errno 风格的 FileNotFoundError 里
        # `args[0]` 是 errno（一个整数），那样会印出「数据集文件不见了：2」。
        # 拿不到就当作不是数据集的事，交给下面那条 500。
        target = getattr(exc, "filename", None)
        if not _is_current_dataset(target):
            raise exc
        return JSONResponse(status_code=404,
                            content={"detail": f"数据集文件不见了：{target}"})

    app.include_router(dataset_routes.router, prefix="/api")
    app.include_router(field_routes.router, prefix="/api")
    app.include_router(features_routes.router, prefix="/api")
    app.include_router(calibration_routes.router, prefix="/api")
    app.include_router(calibration_jobs_routes.router, prefix="/api")
    app.include_router(live_routes.router, prefix="/api")
    app.include_router(models_routes.router, prefix="/api")

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        # spec §5.1：健康接口的契约是「存活 **+ 后端库版本**」。
        # 只回 ok 会让前端无从回答「跑着的后端是哪个版本」——
        # 而一台机器上可能同时跑着好几个版本的后端时，这正是第一个要看的数。
        #
        # `max_upload_bytes` 也在这里：上限这个数**由后端说了算**，
        # 前端不许自己写死一个（规格书 §4.4）。前端不读它也不碍事 ——
        # 413 的 detail 里带着同一个数，这条只是让它有地方问。
        return {"status": "ok", "version": TOOL_VERSION,
                "max_upload_bytes": uploads.MAX_UPLOAD_BYTES}

    # 生产形态：一个进程同时供 API 与前端构建产物（spec §二）。
    # 必须带守卫 —— StaticFiles 在目录不存在时构造就抛错，那会让
    # 「没跑过 npm run build 的人连 API 都起不来」。
    # 挂在最后：路由按注册顺序匹配，挂载点 / 会吃掉所有剩下的路径。
    # 走 paths.DIST 而不是 `from .paths import DIST`：后者在 import 时就把值绑死了，
    # 测试里 monkeypatch 不到 —— 那两条守卫测试会静默地测到真的 dist 上去。
    if paths.DIST.is_dir():
        app.mount("/", SPAStaticFiles(directory=str(paths.DIST)), name="static")

    return app


app = create_app()


def main() -> None:
    import uvicorn
    uvicorn.run("api.main:app", host="127.0.0.1", port=paths.API_PORT, reload=False)


if __name__ == "__main__":
    main()
