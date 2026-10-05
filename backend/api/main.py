"""FastAPI 应用。

启动（开发）：
    cd backend && python -m uvicorn api.main:app --port 8503 --reload
端口 8503 写在 `paths.API_PORT`（单一真源），不靠命令行参数 —— 免得谁直接敲 uvicorn 时落回 8000，
前端却还以为它在 8503。
"""
from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
from starlette.responses import FileResponse, Response
from starlette.types import Scope

from tfield.calibration import TOOL_VERSION

from . import paths
from .routes import calibration as calibration_routes
from .routes import dataset as dataset_routes
from .routes import features as features_routes
from .routes import field as field_routes
from .routes import live as live_routes

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
    app.include_router(dataset_routes.router, prefix="/api")
    app.include_router(field_routes.router, prefix="/api")
    app.include_router(features_routes.router, prefix="/api")
    app.include_router(calibration_routes.router, prefix="/api")
    app.include_router(live_routes.router, prefix="/api")

    @app.get("/api/health")
    def health() -> dict[str, str]:
        # spec §5.1：健康接口的契约是「存活 **+ 后端库版本**」。
        # 只回 ok 会让前端无从回答「跑着的后端是哪个版本」——
        # 而多版本并存（Streamlit 版还在一台机器上）时这正是第一个要看的数。
        return {"status": "ok", "version": TOOL_VERSION}

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
