"""FastAPI 应用。

启动（开发）：
    cd backend && python -m uvicorn api.main:app --port 8503 --reload
端口 8503 写在 `paths.API_PORT`（单一真源），不靠命令行参数 —— 免得谁直接敲 uvicorn 时落回 8000，
前端却还以为它在 8503。
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from tfield.calibration import TOOL_VERSION

from . import paths
from .routes import calibration as calibration_routes
from .routes import dataset as dataset_routes
from .routes import features as features_routes
from .routes import field as field_routes

VITE_DEV_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]


def create_app() -> FastAPI:
    # version 取自 `tfield.calibration.TOOL_VERSION`，不写字面量：
    # 标定包的 `tool_version` 用的是同一个数，两处各写一份就会漂 ——
    # 漂开之后 OpenAPI 文档说一个版本、盘上的标定包说另一个，
    # 验收对盘时不知道该信谁。这里与 /api/health 也共用同一个来源。
    app = FastAPI(title="人参棚空间温度场重建系统 API", version=TOOL_VERSION)
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
        app.mount("/", StaticFiles(directory=str(paths.DIST), html=True),
                  name="static")

    return app


app = create_app()


def main() -> None:
    import uvicorn
    uvicorn.run("api.main:app", host="127.0.0.1", port=paths.API_PORT, reload=False)


if __name__ == "__main__":
    main()
