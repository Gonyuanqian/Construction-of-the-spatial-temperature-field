"""页② 第二段：标定长任务的提交、轮询、取消（规格书 §四）。

**为什么是 `/calibration/jobs` 这个复数子资源**：`POST /api/calibration`
与既有的 `GET /api/calibration` 同路径不同方法，能跑，但 `GET
/api/calibration/{id}` 这种写法会把将来的 `/api/calibration/space` 吃掉。
多一层 `jobs` 就再没有歧义，而 POST 的返回物**就是一个 job**。

**这个模块只读、不写 `routes/calibration.py` 的任何东西** ——
反过来那个模块读 `jobs.current()` 来填 `GET /api/calibration` 的 `job` 字段。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from starlette.responses import JSONResponse

from tfield import config as C
from tfield.calibration import CalibrationAborted, run_calibration

from .. import deps, jobs, paths, business_client

router = APIRouter(tags=["calibration"])

#: 写回哪儿。与 `routes/calibration.py` 的 `CONFIGS_ROOT` **各自一份**：
#: 测试要把两边都指到 tmp 上，而合成一个共享对象要动那个模块的既有测试。
#: 两个常量都从 `paths.CONFIGS` 起，改路径只改一处。
CONFIGS_ROOT = paths.CONFIGS


@router.post("/calibration/jobs", status_code=202)
def start_job() -> JSONResponse:
    """启动一次标定。已经在跑时 **409 + 那个 job 的 id**（规格书 §4.5）。

    用 `JSONResponse` 而不是 `raise HTTPException`：`detail` 要给前端
    `client.ts` 当**一句人话**读（它是 `String(body.detail)`），而 job id
    要另带一格。两者塞进同一个字符串，前端就只能靠解析文本拿 id ——
    那是把一句文案当成协议。

    *为什么不排队*：「排在你前面还有一次」是另一个子系统（队列、位置、
    前面那次失败了你怎么办），而它解决的是一个**用户点重了**的问题。指路就够了。
    *为什么不幂等返回 200 + 旧 id*：那会让「我点的是新的一次」与「系统给我的是
    上一次」说不清 —— 而这一页最不能出的错就是「屏上这个数是哪一次算的」说不清。
    """
    running = jobs.current()
    if business_client.java_store():
        raise HTTPException(409, "训练任务已由 Java 管理，请通过业务服务提交。")
    if running is not None and running.state == jobs.RUNNING:
        return JSONResponse(status_code=409,
                            content={"detail": "已经有一次标定在跑",
                                     "job_id": running.id})
    return JSONResponse(status_code=202, content=jobs.submit(_work).to_dict())


@router.get("/calibration/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    """轮询。**不读包、不算任何东西** —— 它答的是「跑到哪一句了」。"""
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="没有这个标定任务")
    return job.to_dict()


@router.delete("/calibration/jobs/{job_id}")
def cancel_job(job_id: str) -> dict[str, Any]:
    """取消。真正的取消点在库里那个 `should_stop` 下一次被问到时。

    ⚠️ **这里不把状态改成 `cancelled`**：提前改的话，界面会在库里那次搜索
    还没真的停下来的时候说「已取消」—— 而那正是验收要否掉的一幕。
    回的是**当下**的状态，前端接着轮询，让后端说。
    """
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="没有这个标定任务")
    if job.state != jobs.RUNNING:
        # 已经跑完的不能再取消：它已经给了结论，报「已取消」是句谎话。
        raise HTTPException(status_code=409,
                            detail=f"这一次标定已经结束（{job.state}），来不及取消了")
    job.cancel.set()
    return job.to_dict()


def _work(job: jobs.Job) -> None:
    """标定。跑在 `jobs` 的执行器线程上。

    **故意不调 `calibrate_or_load`**：那个函数末尾自己 `save_bundle`，
    而这一轮起「要不要留下」由用户回答 —— 系统不再替他决定（规格书 D2）。
    所以这里直接调 `run_calibration`：它只写参数曲面 CSV，**不写包**。

    包的去处是 `job.result`（见函数尾部），消费它的是 `POST /api/models`。
    """
    ds = deps.get_train_dataset()
    groups = tuple(C.DEFAULT_FEATURE_GROUPS)
    root = CONFIGS_ROOT

    try:
        bundle = run_calibration(ds, groups, root=root,
                                 progress=lambda line: jobs.set_progress(job, line),
                                 should_stop=job.stop_requested)
    except CalibrationAborted:
        # 库的保证是「中断即什么都没发生」：CSV 与包都只在搜索全部成功之后
        # 才落盘，所以这里**不需要**做任何清理（硬约束 2）。
        jobs.finish(job, jobs.CANCELLED)
        return

    # ⚠️ 再问一次取消。搜索跑完到「结果定下来」之间有一小段没有 `should_stop`
    # 的问询点，不在这里补一次的话，「取消之后什么都不留」在「恰好在这一刻取消」
    # 这条窄路上是假的 —— 而典型路径走不到它。
    if job.stop_requested():
        jobs.finish(job, jobs.CANCELLED)
        return

    # 2026-10-08（模型库）：**不再写回盘**。跑出来的那一份只挂在这个 job 对象
    # 上；用户看过那些数、判它合格之后，由 `POST /api/models` 把它存进模型库
    # （规格书 D2、§5.3）。于是 `save_bundle` / `.bak` / `shutil` 三样一起退场。
    #
    # ⚠️ 这一份**活不过重启**：它在内存里，进程一停就没了。这与「不保存就
    # 丢掉」是同一条规则，不是缺陷。
    job.result = bundle
    jobs.finish(job, jobs.DONE)
