"""把一次上传的字节，变成一份可用的数据集文件 —— 或者一个字节都不动。

**这个模块不 import fastapi**：它可以脱离 HTTP 被单测（`precheck` 那条就是），
而它的每一条规则都会被演示现场碰到（后缀、路径穿越、太大、内容不是 xlsx）。

**为什么走原始请求体不走 multipart**（规格书 §4.1）：FastAPI 的
`UploadFile` / `File` / `Form` 需要 `python-multipart`，而它**不在
`backend/requirements-api.txt` 里**（本机装了，是环境里另外带进来的）。
干净机器按 requirements 装完，带 `UploadFile` 的路由会让**整个应用起不来**
（FastAPI 在注册路由时就抛），而「`requirements-api.txt` 一个字不改」
是多份规格书的全局约束。
"""
from __future__ import annotations

import os
import pathlib
import re
from dataclasses import dataclass

import pandas as pd

from tfield import config as C
from tfield.data.loader import HOLDOUT_CUTOFF, split_holdout

from . import deps

#: 上限定 32 MiB。现在的数据集约 1 MB，32 倍余量。
#:
#: 它**由后端报给前端**（`GET /api/health` 的 `max_upload_bytes`）：
#: 这是硬约束 1「凡是可以被后端说了算的数，就由后端说」的同一条精神。
MAX_UPLOAD_BYTES: int = 32 * 1024 * 1024

#: 一条数据都没有时也要有话说（`ts.iloc[0]` 会在空轴上抛 IndexError）。
_NO_TIMES = "这份文件里一个时刻都没有。"


@dataclass(frozen=True)
class Rejected(Exception):
    """拒绝的理由。`status` 是 HTTP 状态码，`detail` 是**要原样上屏**的那句话。

    ⚠️ **必须继承 `Exception`**：它有两种用法 —— `precheck()` 把它当**返回值**
    （最便宜的拒绝连抛都不用抛），`accept()` / `_load_or_reject()` 把它**抛出去**
    （那里已经写进了临时文件，得靠异常穿过 `finally` 去删）。
    计划原文写的是 `raise Rejected(400, ...)` 配一个不继承异常的 dataclass，
    那句话在运行时是 `TypeError: exceptions must derive from BaseException`。
    """
    status: int
    detail: str


@dataclass(frozen=True)
class Uploaded:
    """收下之后的事实。`signature` 不在里面 —— 它要等改名之后才算得对（见 `accept`）。"""

    path: pathlib.Path
    n_times: int
    n_columns: int
    time_start: str
    time_end: str


def precheck(name: str, content_length: int | None) -> Rejected | None:
    """最便宜的那一类拒绝：不读 body，光看名字与 `Content-Length`。

    ⚠️ **签名里没有 `data`**，这不是省事：它就是「先判后读」的**结构性**证据。
    先读后判等于给了一个内存耗尽的入口 —— 一个 1 GB 的 body 会先被读进内存，
    然后才被判太胖。
    """
    if not name.lower().endswith(".xlsx"):
        return Rejected(415, f"只收 .xlsx 文件，收到的是：{name or '（没有文件名）'}")
    if content_length is not None and content_length > MAX_UPLOAD_BYTES:
        return Rejected(
            413,
            f"这个文件 {_size(content_length)}，超过上限 {_size(MAX_UPLOAD_BYTES)}。",
        )
    return None


def _size(n: int) -> str:
    """把字节数说成人话，**按量级选单位**。

    ⚠️ 一律按 MiB 印的话，16 字节会印成「0.0 MiB」—— 那句话既没说清上限、
    也没说清实际大小，而 413 这条消息的全部价值就在这两个数上。
    （计划原文写的是 `_mb`，它自己那条断言 `"16" in detail` 永远不可能成立；
    这是执行时按规格书 §4.4「报出上限与实际大小」做的修正。）
    """
    if n < 1024:
        return f"{n} 字节"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KiB"
    return f"{n / 1024 / 1024:.1f} MiB"


#: 盘符前缀。`D:evil.xlsx` / `Z:pwn.xlsx` / `c:..\\evil.xlsx` 都从这儿拿掉。
#:
#: ⚠️ 这不是上面那四种穿越写法的「又一种」，是**另一类**：那四种都含分隔符，
#: 取 basename 就干净了；而 `D:evil.xlsx` 一个分隔符都没有，`PurePosixPath` 眼里
#: 它就是一个普通文件名。可它在 Windows 上是**盘符相对路径** ——
#: `上传目录 / "D:evil.xlsx"` 会**丢掉左边**（`pathlib` 的规矩：右操作数带盘符
#: 就顶掉左边的盘符），于是临时文件与最终文件双双落到 `D:` 那一侧。
#: 实测过：`Uploaded.path` 会变成 `WindowsPath('D:evil.xlsx')`。
#: 一旦落在那儿，`Rejected` 之后 `finally` 里的 `tmp.unlink()` 删的是 D: 上那份，
#: 上传目录里干干净净 —— 看起来像什么都没发生。
_DRIVE = re.compile(r"^[A-Za-z]:")


def safe_name(name: str) -> str:
    """只留 basename。`../../evil.xlsx` 与 `..\\..\\evil.xlsx` 都回 `evil.xlsx`。

    ⚠️ **先反斜杠换成正斜杠再取 basename**：Windows 上 `PurePosixPath("..\\a.xlsx").name`
    是整串 `..\\a.xlsx`（反斜杠在 POSIX 语义里是**普通字符**），于是它会变成一个
    文件名里的反斜杠 —— 或者更糟，落在 `pathlib` 眼里仍是一条相对路径。
    两种写法都要在测试里钉住。

    ⚠️ **再拿掉盘符前缀**（见 `_DRIVE`）。Windows 上文件名本来就不许含 `:`，
    所以这一步不会误伤一个合法的名字 —— 它只可能拿掉一个盘符。

    **不回退成「随机名」**：中文文件名要能原样保留（§4.1 把文件名放进 query
    正是为了这个），把名字换掉会让「我刚才传的是哪一份」无从对照。
    """
    base = pathlib.PurePosixPath(name.replace("\\", "/")).name
    base = _DRIVE.sub("", base)
    if base in ("", ".", ".."):
        return "dataset.xlsx"
    return base


def accept(data: bytes, name: str, *, dest_dir: pathlib.Path) -> Uploaded:
    """**要么全成，要么系统不动**（规格书 §4.2 的次序）。

    1. 写到 `dest_dir` 下的**临时文件**（`.名字.pid.part`）—— 落盘用临时名，
       下一步失败时盘上不留半份；
    2. 用**库的 loader** 试加载 + 切点校验 —— 「这份数据能不能跑」的唯一
       oracle 是库，不是这里另写的一套检查；
    3. 通过才改名到最终路径。

    任何一步抛 `Rejected`，临时文件都被删掉 —— 当前数据集由调用方负责保持不变。
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / safe_name(name)
    # ⚠️ 这一句是「不许逃出上传目录」的**执行点**，不是 `safe_name` 的复述。
    # `safe_name` 是尽力而为的清洗（它现在会把盘符拿掉），而这里问的是不变量：
    # 拼出来的目标文件是不是就在上传目录里。两者都要有，理由不同 ——
    # 清洗解决「用户传了什么」，断言解决「这段代码将来被改坏了没有」。
    # 那条盘符的 bug 就是这样绕过全部四种穿越写法的：名字里没有分隔符，
    # 而 `pathlib` 把右操作数的盘符当成了地址的一部分。
    if target.parent != dest_dir:
        raise Rejected(400, f"文件名不能带盘符或路径：{name}")
    tmp = target.with_name(f".{target.name}.{os.getpid()}.part")
    try:
        try:
            tmp.write_bytes(data)
        except OSError as exc:
            # ⚠️ 与下面那条 409 **必须分开**：那个是「目标文件被 Excel 开着」，
            # 用户关掉程序就好；这一条是**服务端自己**写不动（磁盘满、没权限），
            # 用户在这里做不了任何事。合成一条消息会把后者的用户指到一个
            # 关不掉的程序上去；不接的话则是一片裸 500，连「写不动」都没说。
            raise Rejected(507, f"服务端写不进上传目录，请检查磁盘空间与权限：{exc}") from exc
        ds = _load_or_reject(tmp)
        try:
            tmp.replace(target)
        except PermissionError as exc:
            # ⚠️ 只包 `replace`，不包 `write_bytes`：演示时那个 xlsx 很可能
            # 正被 Excel 开着，撞的就是这一步（Windows 的 `os.replace` 遇到
            # 被持有的**目标**会抛 PermissionError，实测过）。
            #
            # 把 `write_bytes` 也包进来（计划原文的形状）会把**磁盘写不动**
            # 也报成「文件正被占用」—— 那句话会把人指到一个关不掉的程序上。
            raise Rejected(
                409, f"这个文件正被另一个程序占用，关掉它再试：{target.name}"
            ) from exc
    finally:
        # 成功时 `tmp` 已经不在（replace 把它搬走了），这句是空操作。
        # 失败时它是唯一该留下的动作 —— 写进 finally，就没有一条提前返回能绕过它。
        if tmp.exists():
            tmp.unlink()
    ts = pd.to_datetime(ds.wide[C.COL_TIMESTAMP])
    return Uploaded(path=target, n_times=int(ds.wide.shape[0]),
                    n_columns=int(ds.wide.shape[1]),
                    time_start=ts.iloc[0].isoformat(), time_end=ts.iloc[-1].isoformat())


def validate_existing(path: pathlib.Path) -> Uploaded:
    """验证已落盘的不可变文件，复用上传的校验逻辑且不切换当前选择。"""
    ds = _load_or_reject(path)
    ts = pd.to_datetime(ds.wide[C.COL_TIMESTAMP])
    return Uploaded(path=path, n_times=int(ds.wide.shape[0]),
                    n_columns=int(ds.wide.shape[1]),
                    time_start=ts.iloc[0].isoformat(), time_end=ts.iloc[-1].isoformat())


def _load_or_reject(path: pathlib.Path):
    """用库的 loader 加载并校验**训练段非空**。不通过就抛 `Rejected(400, ...)`。"""
    try:
        # 走 `deps.probe_dataset`（而不是直接 import `load_dataset`）：
        # 本仓的源码守卫规定 load_dataset 只许出现在 `api/deps.py`。
        # 那个出口**不进缓存**，正是这里要的 —— 文件下一步就改名了。
        ds = deps.probe_dataset(path)
    except Exception as exc:
        # **库的原话**，不吞、不翻译成「文件格式错误」那种没有信息量的话：
        # 演示时拿到的可能是一句「Sheet '宽表' not found」，那句话直接指出该改什么。
        raise Rejected(400, f"这份文件读不成数据集：{type(exc).__name__}: {exc}") from exc

    ts = pd.to_datetime(ds.wide[C.COL_TIMESTAMP])
    if len(ts) == 0:
        raise Rejected(400, _NO_TIMES)
    hold = split_holdout(ds)
    # ⚠️ 2026-10-16 放开：只查**训练段**非空（规格 R6）。裁定①之后用户上传的
    # 就是 `configs/live/train.xlsx`，而它的留出段**按定义**是空的 —— 还按
    # 「两侧都必须非空」拦，正常演示的第一步就会被拒。
    # 拦住的还在：整份落在切点之后的文件训练段为空，模型没有可学的部分。
    if len(hold.train.wide) == 0:
        raise Rejected(
            400,
            f"这份数据集是 {ts.iloc[0]} 到 {ts.iloc[-1]}，整份都在留出切点 "
            f"{HOLDOUT_CUTOFF} 之后：训练段是空的，模型没有可学的部分。",
        )
    return ds
