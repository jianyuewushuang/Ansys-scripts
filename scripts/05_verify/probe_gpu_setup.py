# -*- coding: utf-8 -*-
"""GPU 求解器冷启动策略对比：hybrid / standard / FMG / 由已收敛解续算。

发散判据 = 跑完后能否算出量级合理的升力系数。

用法：
    ./.venv/Scripts/python.exe scripts/05_verify/probe_gpu_setup.py
"""
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
CASE0 = os.path.join(BASE, "artifacts", "cases", "final_aoa0.cas.h5")
Q, S = 1325.016, 65.3375
t0 = time.time()


def log(*a):
    print("[%6.1fs]" % (time.time() - t0), *a, flush=True)


def setup_physics(st, aoa=0.0):
    import math as m
    a = m.radians(aoa)
    bcs = st.setup.boundary_conditions
    ff = bcs.pressure_far_field["fluid_box:1"]
    ff.momentum.gauge_pressure = {"option": "value", "value": 54019.89}
    ff.momentum.mach_number = {"option": "value", "value": 60.0 / 320.529}
    ff.momentum.flow_direction = [
        {"option": "value", "value": v} for v in (m.cos(a), 0.0, m.sin(a))]
    ff.turbulence.turbulent_intensity = 0.1
    ff.turbulence.turbulent_viscosity_ratio = 10.0
    ff.thermal.temperature = {"option": "value", "value": 255.65}


def build(report_aoa=0.0):
    s, dev = common.launch_solver(prefer="gpu", gpu_nproc=1, cpu_nproc=4,
                                  cwd=os.path.join(BASE, "work"))
    st = s.settings
    st.file.read(file_type="mesh", file_name=MSH)
    st.mesh.modify_zones.delete_cell_zone(cell_zones=["aircraft"])
    st.setup.models.energy.enabled = True
    st.setup.models.viscous = {"model": "k-omega", "k_omega_model": "sst"}
    st.setup.materials.fluid["air"] = {
        "density": {"option": "ideal-gas"},
        "viscosity": {"option": "constant", "value": 1.628e-5},
        "specific_heat": {"option": "constant", "value": 1006.43},
        "thermal_conductivity": {"option": "constant", "value": 0.0242}}
    common.tui(s, "define/operating-conditions/operating-pressure 0")
    bcs = st.setup.boundary_conditions
    bcs.set_zone_type(zone_list=["fluid_box:1"], new_type="pressure-far-field")
    st.setup.reference_values.set_state({"area": S, "length": 4.1996,
                                         "density": 0.73612, "velocity": 60.0,
                                         "viscosity": 1.628e-5, "temperature": 255.65})
    st.solution.methods.p_v_coupling.set_state({"flow_scheme": "Coupled"})
    pc = st.solution.controls.p_v_controls
    pc.explicit_pressure_under_relaxation = 0.4
    pc.explicit_momentum_under_relaxation = 0.5
    setup_physics(st, 0.0)
    import math as m
    aa = m.radians(report_aoa)
    rd = st.solution.report_definitions
    rd.force["L"] = {"zones": ["aircraft-fluid_box"],
                     "force_vector": [-m.sin(aa), 0.0, m.cos(aa)]}
    return s, st, rd


def cl_of(rd):
    try:
        out = rd.compute(report_defs=["L"])
        v = out[0]["L"]
        v = float(v[0]) if isinstance(v, (list, tuple)) else float(v)
        return v / (Q * S)
    except Exception:
        return None


def verdict(tag, cl, lo=-1.0, hi=3.0):
    if cl is None:
        log("  ❌ %-40s 发散/无解" % tag)
        return False
    ok = math.isfinite(cl) and lo < cl < hi
    log("  %s %-40s CL=%+.4f" % ("✅" if ok else "❌", tag, cl))
    return ok


# ---- 1) hybrid init（当前做法，已在完整跑里确认发散）----
s, st, rd = build()
st.solution.initialization.hybrid_initialize()
st.solution.run_calculation.iterate(iter_count=80)
verdict("hybrid init + 80 步", cl_of(rd))
s.exit()

# ---- 2) standard init ----
s, st, rd = build()
try:
    st.solution.initialization.standard_initialize()
    log("  (standard_initialize 已执行)")
except Exception as e:
    log("  standard_initialize 不可用: " + str(e)[:100])
try:
    st.solution.run_calculation.iterate(iter_count=80)
    verdict("standard init + 80 步", cl_of(rd))
except Exception as e:
    log("  ❌ standard init + 80 步 中断: " + str(e)[:100])
s.exit()

# ---- 3) FMG init ----
s, st, rd = build()
try:
    common.tui(s, "solve/initialize/fmg-initialization")
    log("  (FMG 已执行)")
except Exception as e:
    log("  FMG 不可用: " + str(e)[:100])
try:
    st.solution.run_calculation.iterate(iter_count=80)
    verdict("FMG init + 80 步", cl_of(rd))
except Exception as e:
    log("  ❌ FMG + 80 步 中断: " + str(e)[:100])
s.exit()

# ---- 4) 由已收敛的 α=0 解续算到 α=4（GPU 只做续算）----
s, dev = common.launch_solver(prefer="gpu", gpu_nproc=1, cpu_nproc=4,
                              cwd=os.path.join(BASE, "work"))
st = s.settings
st.file.read(file_type="case-data", file_name=CASE0)
import math as m
aa = m.radians(4.0)
rd = st.solution.report_definitions
rd.force["L"] = {"zones": ["aircraft-fluid_box"],
                 "force_vector": [-m.sin(aa), 0.0, m.cos(aa)]}
setup_physics(st, 4.0)
st.solution.run_calculation.iterate(iter_count=150)
verdict("α0 收敛解 → α=4，150 步（GPU 续算）", cl_of(rd), lo=0.2, hi=0.6)
log("  参考：CPU 全量跑 α=4 的 CL = 0.3454")
s.exit()

log("PROBE DONE")
