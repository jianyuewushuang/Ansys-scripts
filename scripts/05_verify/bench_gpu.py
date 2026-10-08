# -*- coding: utf-8 -*-
"""Fluent GPU / CPU 求解速度实测。

一次性开销（GPU 求解器初始化、上传数据）用 warm-up 抵消，只测稳态 s/步。

用法：
    ./.venv/Scripts/python.exe scripts/05_verify/bench_gpu.py                 # 默认对比 cpu×4 / gpu×4
    ./.venv/Scripts/python.exe scripts/05_verify/bench_gpu.py "gpu:4" "gpu:1" # 自定义
    ./.venv/Scripts/python.exe scripts/05_verify/bench_gpu.py "gpu:2:perf"    # 开 performance-mode
"""
import json
import os
import sys
import time

os.environ.setdefault("PYFLUENT_SHOW_SERVER_GUI", "0")

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(BASE, "scripts"))
import common  # noqa: E402

common.quiet_pyfluent()

from ansys.fluent.core import launch_fluent  # noqa: E402

CASE = os.path.join(BASE, "artifacts", "cases", "final_aoa0.cas.h5")
WARM = int(os.environ.get("WARM", 10))
NITER = int(os.environ.get("NITER", 40))
t0 = time.time()


def log(*a):
    print("[%6.1fs]" % (time.time() - t0), *a, flush=True)


def run(spec):
    """spec = "cpu:4" / "gpu:2" / "gpu:4:perf" """
    parts = spec.split(":")
    mode, nproc = parts[0], int(parts[1]) if len(parts) > 1 else 4
    perf = "perf" in parts
    tag = "%s×%d%s" % (mode.upper(), nproc, "+perf" if perf else "")
    log("=== %s ===" % tag)
    kw = dict(mode="solver", precision="double", processor_count=nproc,
              cwd=os.path.join(BASE, "work"))
    if mode == "gpu":
        kw["gpu"] = True
    try:
        s = launch_fluent(**kw)
    except Exception as e:
        log("  启动失败: %s" % str(e)[:250])
        return {"spec": spec, "ok": False, "err": str(e)[:250]}
    st = s.settings
    res = {"spec": spec, "ok": True}

    st.file.read(file_type="case-data", file_name=CASE)

    if perf:
        try:
            s.scheme.string_eval("(rpsetvar 'gpuapp/performance-mode 1)")
            log("  performance-mode = 1")
        except Exception as e:
            log("  perf 设置失败: %s" % str(e)[:100])

    st.solution.run_calculation.iterate(iter_count=WARM)   # 抵消一次性开销
    log("  warm-up %d 步完成，开始计时 %d 步" % (WARM, NITER))
    t = time.time()
    st.solution.run_calculation.iterate(iter_count=NITER)
    dt = time.time() - t
    res["sec_per_iter"] = round(dt / NITER, 4)
    res["nproc"] = nproc
    log("  ★ %s 稳态 %.3f s/步" % (tag, dt / NITER))

    try:
        mem = s.scheme.string_eval("(%gpuapp-get-gpu-memory-usage)")
        res["gpu_mem_GB"] = round(float(mem.strip()), 3)
    except Exception:
        res["gpu_mem_GB"] = 0.0
    s.exit()
    return res


if __name__ == "__main__":
    specs = sys.argv[1:] or ["cpu:4", "gpu:4"]
    out = [run(x) for x in specs]
    print("\n=== 汇总 ===")
    print(json.dumps(out, indent=2, ensure_ascii=False))
    ok = [r for r in out if r.get("ok")]
    if len(ok) >= 2:
        base = next((r for r in ok if r["spec"].startswith("cpu")), ok[0])
        for r in ok:
            if r is not base:
                print("\n%s 相对 %s：加速 %.2f×" % (
                    r["spec"], base["spec"], base["sec_per_iter"] / r["sec_per_iter"]))
