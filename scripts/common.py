# -*- coding: utf-8 -*-
"""各阶段脚本共用的小工具

被以下脚本 import：
    scripts/02_mesh/mesh_half.py        tui()
    scripts/02_mesh/mesh_preview.py     quiet_pyfluent() / surface()
    scripts/03_solve/final_solve.py     quiet_pyfluent()
    scripts/04_post/extract_post.py     quiet_pyfluent() / surface() / lines_of()

"""

from __future__ import annotations

import json
import sys
import threading
import traceback
import warnings

import numpy as np


# ==============================================================================
# 1. 静音 PyFluent 的已知无害缺陷
# ==============================================================================
def quiet_pyfluent():
    """消除 PyFluent 0.42 + protobuf 5.x 的两处噪声。

    ① 后台事件流线程抛 `ValueError: invalid literal for int() with base 10: ''`
       根因：`_events_info_store.EventInfoBase.__post_init__` 把 gRPC 报文里
       的空字符串直接 `int()`。新版 protobuf 的 `MessageToDict(..., True)`
       会把未设置的整型字段序列化成 ""，于是每来一个事件就炸一次。
       这里把类型转换改成容错版（根因修复），只丢该事件的字段值，不影响求解。

    ② 装过 PyPrimeMesh 之后 protobuf 被降级，上一条的兜底路径在这里：
       即便 ① 没生效，threading.excepthook 也只吞掉**来自事件流线程**的
       ValueError，其它线程的异常照常打印。
    """
    _patch_event_info_cast()
    _install_thread_excepthook()
    return True


def _patch_event_info_cast():
    try:
        from dataclasses import fields

        from ansys.fluent.core.streaming_services import _events_info_store as E
    except Exception:
        return False

    base = getattr(E, "EventInfoBase", None)
    if base is None or getattr(base, "_uav_safe_cast", False):
        return False

    def _safe_post_init(self):
        for f in fields(self):
            v = getattr(self, f.name)
            try:
                setattr(self, f.name, f.type(v))
            except (TypeError, ValueError):
                # 未设置的字段：给该类型的零值，而不是让整个线程崩掉
                try:
                    setattr(self, f.name, f.type())
                except Exception:
                    setattr(self, f.name, None)

    base.__post_init__ = _safe_post_init
    base._uav_safe_cast = True
    return True


def _install_thread_excepthook():
    prev = getattr(threading, "excepthook", None)

    def hook(args):
        tb = "".join(traceback.format_tb(args.exc_traceback))
        benign = (
            "events_streaming" in tb
            or "_events_info_store" in tb
            or "events_service" in tb
        )
        if benign and isinstance(args.exc_value, (ValueError, TypeError)):
            return  # 事件流线程的已知缺陷，静默
        if prev is not None:
            prev(args)
        else:
            sys.__excepthook__(args.exc_type, args.exc_value, args.exc_traceback)

    threading.excepthook = hook
    return True


def suppress(*categories):
    """按需屏蔽指定告警类别（仅用于无法从调用侧修掉的第三方告警）。"""
    for cat in categories:
        try:
            warnings.filterwarnings("ignore", category=cat)
        except Exception:
            pass


# ==============================================================================
# 2. 硬件探测与 GPU / CPU 求解器选择
# ==============================================================================
def detect_gpus():
    """用 nvidia-smi 探测可用的 NVIDIA GPU。

    返回 list[dict]，每项含 index / name / driver / memory_gb / compute_cap。
    没有 nvidia-smi（或无 NVIDIA 卡）时返回空列表 —— 这就是"回退 CPU"的判据。
    """
    try:
        import subprocess

        q = (
            "--query-gpu=index,name,driver_version,memory.total,compute_cap"
            "--format=csv,noheader,nounits"
        ).replace("--format", ",--format")
        # 上面拼接容易出错，这里写清楚
        args = [
            "nvidia-smi",
            "--query-gpu=index,name,driver_version,memory.total,compute_cap",
            "--format=csv,noheader,nounits",
        ]
        out = subprocess.run(args, capture_output=True, text=True, timeout=20)
        if out.returncode != 0 or not out.stdout.strip():
            return []
        gpus = []
        for line in out.stdout.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 4:
                continue
            gpus.append(
                {
                    "index": parts[0],
                    "name": parts[1],
                    "driver": parts[2] if len(parts) > 2 else "",
                    "memory_gb": round(float(parts[3]) / 1024.0, 2)
                    if len(parts) > 3
                    else 0.0,
                    "compute_cap": parts[4] if len(parts) > 4 else "",
                }
            )
        return gpus
    except Exception:
        return []


def cpu_cores():
    """返回逻辑处理器数（拿不到就返回 4）。"""
    try:
        import os

        n = os.cpu_count()
        return int(n) if n else 4
    except Exception:
        return 4


def resolve_device(prefer="auto", gpu_nproc=1, cpu_nproc=0, auto_max=8):
    """决定这一轮用什么设备 + 几个 MPI 进程。

    prefer : "auto" —— 有 NVIDIA GPU 就用 GPU，否则 CPU
             "gpu"  —— 强制 GPU（不可用时由 launch_solver 决定是否回退）
             "cpu"  —— 强制 CPU
    cpu_nproc : 0 = 自动（min(逻辑核数, auto_max)，下限 2）

    返回 dict：{"device", "nproc", "gpus", "reason"}
    """
    gpus = detect_gpus()
    cores = cpu_cores()
    if not cpu_nproc or cpu_nproc <= 0:
        cpu_nproc = max(2, min(cores, auto_max))
    if prefer == "cpu":
        return {
            "device": "cpu",
            "nproc": int(cpu_nproc),
            "gpus": gpus,
            "reason": "config.SOLVE_DEVICE = cpu（强制）",
        }
    if prefer == "hybrid":
        # CPU 播种 + GPU 主迭代：主迭代段在 GPU 上，所以按 GPU 报告
        if gpus:
            return {
                "device": "hybrid",
                "nproc": int(gpu_nproc),
                "gpus": gpus,
                "reason": "CPU 播种 + GPU 主迭代（%s）" % gpus[0]["name"],
            }
        return {
            "device": "cpu",
            "nproc": int(cpu_nproc),
            "gpus": gpus,
            "reason": "要求 hybrid 但没有可用 NVIDIA 设备，全程 CPU",
        }
    if prefer in ("auto", "gpu") and gpus:
        return {
            "device": "gpu",
            "nproc": int(gpu_nproc),
            "gpus": gpus,
            "reason": "检测到 %s（%.1f GB）" % (gpus[0]["name"], gpus[0]["memory_gb"]),
        }
    if prefer == "gpu":
        return {
            "device": "cpu",
            "nproc": int(cpu_nproc),
            "gpus": gpus,
            "reason": "要求 GPU 但没有可用 NVIDIA 设备，回退 CPU",
        }
    return {
        "device": "cpu",
        "nproc": int(cpu_nproc),
        "gpus": gpus,
        "reason": "未检测到 NVIDIA GPU",
    }


def gpu_memory_gb(session):
    """查询当前会话已占用的 GPU 显存（GB）。<=0 表示 GPU 求解器没真正启用。"""
    try:
        v = session.scheme.string_eval("(%gpuapp-get-gpu-memory-usage)")
        return round(float(str(v).strip().split()[0]), 3)
    except Exception:
        return 0.0


def launch_solver(
    prefer="auto",
    gpu_nproc=1,
    cpu_nproc=4,
    precision="double",
    cwd=None,
    fallback=True,
    performance_mode=0,
    log=print,
):
    """启动 Fluent **求解器**会话；优先 GPU，失败自动回退 CPU。

    返回 (session, device)。device 为 "gpu" / "cpu"，调用方据此记录日志。

    为什么 GPU 只开 1 个 MPI 进程：本机实测（318k 格、RTX 5060 Laptop 8 GB）
        CPU×4  1.593 s/步
        GPU×4  0.269 s/步   (5.9×)
        GPU×2  0.247 s/步   (6.5×)
        GPU×1  0.196 s/步   (8.1×)  ← 最快
    单卡多进程会争用同一块 GPU，进程越少越快。
    """
    from ansys.fluent.core import launch_fluent

    info = resolve_device(prefer, gpu_nproc=gpu_nproc, cpu_nproc=cpu_nproc)
    log("求解设备 : %s  —— %s" % (info["device"].upper(), info["reason"]))

    if info["device"] == "gpu":
        try:
            log("启动 Fluent（-gpu, %d 进程）..." % info["nproc"])
            s = launch_fluent(
                mode="solver",
                precision=precision,
                processor_count=info["nproc"],
                gpu=True,
                cwd=cwd,
            )
            if performance_mode:
                try:
                    s.scheme.string_eval(
                        "(rpsetvar 'gpuapp/performance-mode %d)" % int(performance_mode)
                    )
                    log("  gpuapp/performance-mode = %d" % performance_mode)
                except Exception as e:
                    log("  performance-mode 设置失败（忽略）：%s" % str(e)[:100])
            return s, "gpu"
        except Exception as e:
            log("  !! GPU 启动失败：%s" % str(e)[:200])
            if not fallback:
                raise
            log("  回退到 CPU ...")

    log("启动 Fluent（CPU, %d 进程）..." % cpu_nproc)
    s = launch_fluent(
        mode="solver", precision=precision, processor_count=int(cpu_nproc), cwd=cwd
    )
    return s, "cpu"


# ==============================================================================
# 3. TUI 命令包装
# ==============================================================================
def tui(session, cmd: str) -> str:
    """执行一条 Fluent TUI 命令并返回 transcript 文本。

    坑：`session.execute_tui()` 的签名虽然写着 `-> str`，但函数体里没有
    return，**永远返回 None**。旧代码因此“以为它没执行”，回退到

        session.scheme_eval.string_eval(f'(ti-menu-load-string "{cmd}")')

    而这个写法把未经转义的 Windows 路径（`C:\\Users\\...`）直接塞进 Scheme
    字符串，引号提前闭合；`ti-menu-load-string` 执行完前半截后，剩下的
    `c:\\users\\...` 被当成 Scheme 变量求值 —— Fluent 于是打印

        Error: eval: unbound variable
        Error Object: c:\\users\\...\\aircraft_mesh.msh.h5

    虽然网格其实已经写好了，但每次都刷一屏红字。这里用 json.dumps 做
    标准转义，保证整条命令是**一个**完整的 Scheme 表达式。
    """
    expr = "(ti-menu-load-string %s)" % json.dumps(cmd)
    try:
        return session.scheme.string_eval(expr) or ""
    except Exception:
        try:
            session.execute_tui(cmd)  # 老接口兜底
        except Exception:
            pass
        return ""


# ==============================================================================
# 3. 面/线连接表：扁平格式 -> 逐面索引
# ==============================================================================
def flat_to_faces(conn) -> list:
    """扁平连接表 ``[n, v0, ..., v_{n-1}, n, v0, ...]`` -> 逐面 ndarray 列表。

    PyFluent 0.42 起推荐 ``flatten_connectivity=True``（否则每次调用都刷一条
    PyFluentDeprecationWarning）。扁平化之后 connectivity 是一整条 1-D 数组，
    ``conn_list()`` 那种“ndarray 就当一整张面”的旧写法会全错，必须展开。
    """
    a = np.asarray(conn).ravel()
    out, i, n = [], 0, a.size
    while i < n:
        k = int(a[i])
        end = i + 1 + k
        if k <= 0 or end > n:
            break
        out.append(a[i + 1 : end].astype(np.int64))
        i = end
    return out


def faces_of(conn) -> list:
    """统一入口：扁平 ndarray 与逐面 list 都能吃。"""
    if isinstance(conn, np.ndarray):
        return flat_to_faces(conn)
    return [np.asarray(c, dtype=np.int64).ravel() for c in (conn or [])]


def lines_of(lines) -> list:
    """Pathlines 的 lines 字段同样可能是扁平数组。"""
    if lines is None:
        return []
    if isinstance(lines, np.ndarray):
        return flat_to_faces(lines)
    return [np.asarray(l, dtype=np.int64).ravel() for l in lines]


# ==============================================================================
# 4. 表面数据请求（自动使用新格式）
# ==============================================================================
class Surface:
    """一个面的几何数据容器，字段命名与旧代码保持一致。"""

    __slots__ = ("vertices", "faces", "connectivity", "centroids", "normals")

    def __init__(self, vertices=None, faces=None, centroids=None, normals=None):
        self.vertices = vertices
        self.faces = list(faces or [])
        self.connectivity = self.faces  # 兼容旧字段名
        self.centroids = centroids
        self.normals = normals


def surface(fd, name, with_normals=False, with_scalar=None):
    """取一个面的顶点 + 连接表（+ 可选面心/法向）。

    ``flatten_connectivity=True`` 之后不会再触发 PyFluentDeprecationWarning，
    返回的 ``.faces`` 恒为“逐面索引列表”，调用侧不需要再关心格式差异。
    """
    from ansys.fluent.core.fields.field_data_interfaces import (
        SurfaceDataType,
        SurfaceFieldDataRequest,
    )

    types = [SurfaceDataType.Vertices, SurfaceDataType.FacesConnectivity]
    if with_normals:
        types += [SurfaceDataType.FacesCentroid, SurfaceDataType.FacesNormal]
    req_kwargs = {"flatten_connectivity": True}
    try:
        r = fd.get_field_data(
            SurfaceFieldDataRequest(surfaces=[name], data_types=types, **req_kwargs)
        )
    except TypeError:  # 旧版 PyFluent 没有该参数
        r = fd.get_field_data(
            SurfaceFieldDataRequest(surfaces=[name], data_types=types)
        )
    d = r[name]
    return Surface(
        vertices=np.asarray(d.vertices),
        faces=faces_of(d.connectivity),
        centroids=(
            np.asarray(d.face_centroids)
            if getattr(d, "face_centroids", None) is not None
            else None
        ),
        normals=(
            np.asarray(d.face_normals)
            if getattr(d, "face_normals", None) is not None
            else None
        ),
    )
