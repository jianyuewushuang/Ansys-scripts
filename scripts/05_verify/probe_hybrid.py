# -*- coding: utf-8 -*-
"""CPU 冷启动 → GPU 主迭代：找到最少需要多少步 CPU 才能安全交给 GPU。

背景：GPU 求解器冷启动必发散，但接手"已经跑起来"的解完全正常且快 8 倍。
所以思路是：用 CPU 跑掉最危险的那几十步瞬变，再交给 GPU 跑剩下的几百步。

用法：
    ./.venv/Scripts/python.exe scripts/05_verify/probe_hybrid.py
"""
import json
import math
import os
import sys
import time

os.environ.setdefault("PYFLUENT_SHOW_SERVER_GUI", "0")
BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(BASE, "scripts"))
import common  # noqa: E402

common.quiet_pyfluent()

MSH = os.path.join(BASE, "artifacts", "mesh", "aircraft_mesh.msh.h5")
TMP = os.path.join(BASE, "work", "_hybrid_seed.cas.h5")
Q, S = 1325.016, 65.3375
REF = 0.0227          # CPU 全量跑 α=0 的 C_L
t0 = time.time()


def log(*a):
    print("[%6.1fs]" % (time.time() - t0), *a, flush=True)


def setup(st):
    st.setup.models.energy.enabled = True
    st.setup.models.viscous = {"model": "k-omega", "k_omega_model": "sst"}
    st.setup.materials.fluid["air"] = {
        "density": {"option": "ideal-gas"},
        "viscosity": {"option": "constant", "value": 1.628e-5},
        "specific_heat": {"option": "constant", "value": 1006.43},
        "thermal_conductivity": {"option": "constant", "value": 0.0242}}
    bcs = st.setup.boundary_conditions
    bcs.set_zone_type(zone_list=["fluid_box:1"], new_type="pressure-far-field")
    ff = bcs.pressure_far_field["fluid_box:1"]
    ff.momentum.gauge_pressure = {"option": "value", "value": 54019.89}
    ff.momentum.mach_number = {"option": "value", "value": 60.0 / 320.529}
    ff.momentum.flow_direction = [{"option": "value", "value": v} for v in (1.0, 0.0, 0.0)]
    ff.turbulence.turbulent_intensity = 0.1
    ff.turbulence.turbulent_viscosity_ratio = 10.0
    ff.thermal.temperature = {"option": "value", "value": 255.65}
    st.setup.reference_values.set_state({"area": S, "length": 4.1996,
                                         "density": 0.73612, "velocity": 60.0,
                                         "viscosity": 1.628e-5, "temperature": 255.65})
    st.solution.methods.p_v_coupling.set_state({"flow_scheme": "Coupled"})
    pc = st.solution.controls.p_v_controls
    pc.explicit_pressure_under_relaxation = 0.4
    pc.explicit_momentum_under_relaxation = 0.5


def cl_of(rd):
    try:
        out = rd.compute(report_defs=["L"])
        v = out[0]["L"]
        v = float(v[0]) if isinstance(v, (list, tuple)) else float(v)
        return v / (Q * S)
    except Exception:
        return None


def trial(seed_iters, main_iters=380):
    tag = "CPU %d 步 → GPU %d 步" % (seed_iters, main_iters)
    # ---- 阶段 1：CPU 冷启动 ----
    from ansys.fluent.core import launch_fluent
    s = launch_fluent(mode="solver", precision="double", processor_count=4,
                      cwd=os.path.join(BASE, "work"))
    st = s.settings
    st.file.read(file_type="mesh", file_name=MSH)
    st.mesh.modify_zones.delete_cell_zone(cell_zones=["aircraft"])
    common.tui(s, "define/operating-conditions/operating-pressure 0")
    setup(st)
    st.solution.initialization.hybrid_initialize()
    t1 = time.time()
    st.solution.run_calculation.iterate(iter_count=seed_iters)
    t_cpu = time.time() - t1
    st.file.write(file_type="case-data", file_name=TMP)
    s.exit()

    # ---- 阶段 2：GPU 接手 ----
    s2, dev = common.launch_solver(prefer="gpu", gpu_nproc=1, cpu_nproc=4,
                                   cwd=os.path.join(BASE, "work"),
                                   log=lambda *a: None)
    st2 = s2.settings
    st2.file.read(file_type="case-data", file_name=TMP)
    rd2 = st2.solution.report_definitions
    rd2.force["L"] = {"zones": ["aircraft-fluid_box"], "force_vector": [0.0, 0.0, 1.0]}
    t2 = time.time()
    try:
        st2.solution.run_calculation.iterate(iter_count=main_iters)
    except Exception as e:
        log("  ❌ %-26s GPU 阶段中断: %s" % (tag, str(e)[:90]))
        s2.exit()
        return None
    t_gpu = time.time() - t2
    cl = cl_of(rd2)
    s2.exit()

    if cl is None or not math.isfinite(cl) or abs(cl) > 5:
        log("  ❌ %-26s 发散（CL=%s）" % (tag, cl))
        return None
    total = t_cpu + t_gpu
    log("  ✅ %-26s CL=%+.4f (参考 %.4f, 偏差 %+.4f) | CPU %.0fs + GPU %.0fs = %.0fs"
        % (tag, cl, REF, cl - REF, t_cpu, t_gpu, total))
    return {"seed": seed_iters, "cl": cl, "cpu_s": t_cpu, "gpu_s": t_gpu,
            "total_s": total}


out = []
for n in (20, 40, 80):
    r = trial(n)
    if r:
        out.append(r)

log("参考：纯 CPU 全量 400 步约 %.0f s" % (400 * 1.593))
print("\n=== 汇总 ===")
print(json.dumps(out, indent=2))
for r in out:
    print("seed %3d 步：总 %.0f s，相对纯 CPU 加速 %.2f×"
          % (r["seed"], r["total_s"], 400 * 1.593 / r["total_s"]))
log("PROBE DONE")
