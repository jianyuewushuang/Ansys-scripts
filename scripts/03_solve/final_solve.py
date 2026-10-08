"""FINAL run: delete the spurious airframe-interior cell zone, then solve AoA sweep.

Why: the boolean leaves a sealed `aircraft` cell zone inside the airframe wall.
It is solved as fluid, its pressure collapses ("absolute pressure limited ... on
zone 230789"), the continuity residual never drops and the forces are garbage.
Removing it leaves a clean single fluid region.
"""

import os, json, math, sys, time

os.environ.setdefault("PYFLUENT_SHOW_SERVER_GUI", "0")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import common  # noqa: E402

common.quiet_pyfluent()

from ansys.fluent.core import launch_fluent  # noqa: E402

BASE = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)  # <project root>
OUT = os.environ.get("RESULTS_DIR", os.path.join(BASE, "results"))
os.makedirs(OUT, exist_ok=True)
MSH = os.environ.get("MSH", os.path.join(BASE, "artifacts/mesh/aircraft_mesh.msh.h5"))
CASE_FMT = os.environ.get(
    "CASE_FMT", os.path.join(BASE, "artifacts/cases/final_aoa%d.cas.h5")
)


def _f(key, default):
    return float(os.environ.get(key, default))


# ---- 来流状态（5 km ISA 默认值，可由 config.py / 环境变量覆盖）----
T_INF = _f("T_INF", 255.65)  # 静温 [K]
P_INF = _f("P_INF", 54019.89)  # 静压 [Pa]
RHO = _f("RHO", 0.73612)  # 密度 [kg/m3]
MU = _f("MU", 1.628e-5)  # 动力粘度 [Pa.s]
V_INF = _f("V_INF", 60.0)  # 来流速度 [m/s]
A_INF = _f("A_INF", 320.529)  # 声速 [m/s]
MA = V_INF / A_INF

# ---- 参考量（由 config.py 传入，保证与几何脚本一致）----
SREF = _f("SREF", 65.3375)  # 参考面积 [m2]
LREF = _f("LREF", 4.1996)  # 参考长度 = MAC [m]
BREF = _f("BREF", 23.6443)  # 翼展 [m]
QINF = 0.5 * RHO * V_INF**2  # 动压 [Pa]
MC = [float(x) for x in os.environ.get("MC", "7.9319,0,0").split(",")]  # 取矩中心

AOAS = [float(x) for x in os.environ.get("AOAS", "0,4,8,12").split(",")]
NPROC = int(os.environ.get("NPROC", 4))  # CPU 回退时的进程数
NPROC_GPU = int(os.environ.get("SOLVE_NPROC_GPU", 1))  # GPU 时的进程数（单卡 1 最快）
DEVICE = os.environ.get("SOLVE_DEVICE", "auto")  # auto / gpu / cpu
FALLBACK = os.environ.get("GPU_FALLBACK", "1") not in ("0", "false", "no", "False")
GPU_PERF = int(os.environ.get("GPU_PERF", 0))
WARM = int(os.environ.get("WARM", 50))
ITERS = int(os.environ.get("ITERS", 150))

t0 = time.time()


def log(*a):
    print(f"[{time.time() - t0:7.1f}s]", *a, flush=True)


# --------------------------------------------------------------------------
# GPU 冷启动自检
# --------------------------------------------------------------------------
def gpu_coldstart_ok(iters=None):
    """返回 (是否可用, 说明)。"""
    iters = int(iters or os.environ.get("GPU_SELFTEST_ITERS", 15))
    try:
        s2, dev2 = common.launch_solver(
            prefer="gpu",
            gpu_nproc=NPROC_GPU,
            cpu_nproc=NPROC,
            cwd=BASE + "/work",
            fallback=False,
            log=lambda *a: None,
        )
    except Exception as e:
        return False, "GPU 会话启动失败：%s" % str(e)[:100]
    if dev2 != "gpu":
        s2.exit()
        return False, "未建立 GPU 会话"
    try:
        st2 = s2.settings
        st2.file.read(file_type="mesh", file_name=MSH)
        st2.mesh.modify_zones.delete_cell_zone(cell_zones=[DELZONE])
        st2.setup.models.energy.enabled = True
        st2.setup.models.viscous = {"model": "k-omega", "k_omega_model": "sst"}
        st2.setup.materials.fluid["air"] = {
            "density": {"option": "ideal-gas"},
            "viscosity": {"option": "constant", "value": MU},
            "specific_heat": {"option": "constant", "value": 1006.43},
            "thermal_conductivity": {"option": "constant", "value": 0.0242},
        }
        common.tui(s2, "define/operating-conditions/operating-pressure 0")
        b2 = st2.setup.boundary_conditions
        w2 = list(b2.wall().keys()) if callable(b2.wall) else []
        air2 = [w for w in w2 if "aircraft" in w.lower()] or w2[:1]
        out2 = next((w for w in w2 if w not in air2), None)
        b2.set_zone_type(zone_list=[out2], new_type="pressure-far-field")
        f2 = b2.pressure_far_field[out2]
        f2.momentum.gauge_pressure = {"option": "value", "value": P_INF}
        f2.momentum.mach_number = {"option": "value", "value": MA}
        f2.momentum.flow_direction = [
            {"option": "value", "value": v} for v in (math.cos(0.0), 0.0, math.sin(0.0))
        ]
        f2.turbulence.turbulent_intensity = 0.1
        f2.turbulence.turbulent_viscosity_ratio = 10.0
        f2.thermal.temperature = {"option": "value", "value": T_INF}
        st2.solution.methods.p_v_coupling.set_state({"flow_scheme": "Coupled"})
        p2 = st2.solution.controls.p_v_controls
        p2.explicit_pressure_under_relaxation = PR
        p2.explicit_momentum_under_relaxation = MR
        rd2 = st2.solution.report_definitions
        rd2.force["L"] = {"zones": air2, "force_vector": [0.0, 0.0, 1.0]}
        st2.solution.initialization.hybrid_initialize()
        st2.solution.run_calculation.iterate(iter_count=iters)
        v = rd2.compute(report_defs=["L"])
        val = v[0]["L"]
        F = float(val[0]) if isinstance(val, (list, tuple)) else float(val)
        CL = F / (QINF * SREF)
        if not math.isfinite(CL) or abs(CL) > 5.0:
            return False, "冷启动 %d 步后 CL=%.3g（发散）" % (iters, CL)
        return True, "冷启动 %d 步 CL=%.4f，正常" % (iters, CL)
    except Exception as e:
        return False, "自检中断：%s" % str(e)[:110]
    finally:
        try:
            s2.exit()
        except Exception:
            pass


PR = float(os.environ.get("PRELAX", 0.4))
MR = float(os.environ.get("MRELAX", 0.5))
GPU_SELFTEST = os.environ.get("GPU_SELFTEST", "1") not in ("0", "false", "no", "False")
DELZONE = os.environ.get("DELZONE", "aircraft")
# hybrid 模式：CPU 冷启动跑多少步再把解交给 GPU（实测 20 步就够，再多只是浪费）
GPU_SEED = int(os.environ.get("GPU_SEED", 20))
# 每个攻角一个种子文件（hybrid 阶段① 写、阶段② 读）
SEED_FMT = os.path.join(os.path.dirname(CASE_FMT), "_gpu_seed_aoa%d.cas.h5")

if DEVICE in ("auto", "gpu") and GPU_SELFTEST:
    log("GPU 冷启动自检中（约 1 分钟）...")
    good, why = gpu_coldstart_ok()
    log("   -> " + why)
    if not good:
        log("!! GPU 冷启动不稳定，本轮回退 CPU")
        DEVICE = "cpu"

# GPU 优先、无 GPU 自动回退 CPU（详见 scripts/common.py 的 launch_solver）
s, DEV = common.launch_solver(
    prefer=DEVICE,
    gpu_nproc=NPROC_GPU,
    cpu_nproc=NPROC,
    precision="double",
    cwd=BASE + "/work",
    fallback=FALLBACK,
    performance_mode=GPU_PERF,
    log=log,
)
st = s.settings
st.file.read(file_type="mesh", file_name=MSH)
log("mesh read")

# ---------- 1. delete the airframe-interior cell zone ----------
# Correct keyword is `cell_zones` (not `zone_names`, which is silently ignored).
deleted = False
try:
    st.mesh.modify_zones.delete_cell_zone(cell_zones=[DELZONE])
    deleted = True
except Exception as e:
    log(f"!! delete_cell_zone failed: {str(e)[:120]}")
log(f"OK  delete cell zone {DELZONE} -> {deleted}")
log("zones now: " + str(s.execute_tui("define/boundary-conditions/list-zones")))


# ---------- 2. physics ----------
def ok(label, fn):
    try:
        fn()
        log(f"OK   {label}")
    except Exception as e:
        log(f"FAIL {label}: {str(e)[:120]}")


ok("energy on", lambda: setattr(st.setup.models.energy, "enabled", True))


def set_viscous():
    st.setup.models.viscous = {"model": "k-omega", "k_omega_model": "sst"}


def set_air():
    st.setup.materials.fluid["air"] = {
        "density": {"option": "ideal-gas"},
        "viscosity": {"option": "constant", "value": MU},
        "specific_heat": {"option": "constant", "value": 1006.43},
        "thermal_conductivity": {"option": "constant", "value": 0.0242},
    }


ok("k-omega SST", set_viscous)
ok("air ideal gas", set_air)
log("   check viscous: " + str(st.setup.models.viscous.get_state()))
log("   check air rho: " + str(st.setup.materials.fluid["air"].density.get_state()))
ok(
    "operating pressure 0",
    lambda: s.execute_tui("define/operating-conditions/operating-pressure 0"),
)

bcs = st.setup.boundary_conditions
walls = list(bcs.wall().keys()) if callable(bcs.wall) else []
log(f"walls: {walls}")
# With a two-sided wall the airframe fluid side is the "-shadow" zone;
# with a plain Fluent-Meshing mesh it is the zone named "*aircraft*".
shadow = [w for w in walls if "shadow" in w.lower()]
if shadow:
    airframe = shadow
    outer = next((w for w in walls if w not in shadow), None)
else:
    airframe = [w for w in walls if "aircraft" in w.lower()]
    outer = next((w for w in walls if w not in airframe), None)
log(f"outer={outer}  airframe={airframe}")
ok(
    f"convert {outer} -> pressure-far-field",
    lambda: bcs.set_zone_type(zone_list=[outer], new_type="pressure-far-field"),
)
far = list(bcs.pressure_far_field().keys()) if callable(bcs.pressure_far_field) else []
log(f"far field zones: {far}")
ok(
    "reference values",
    lambda: st.setup.reference_values.set_state(
        {
            "area": SREF,
            "length": LREF,
            "density": RHO,
            "velocity": V_INF,
            "viscosity": MU,
            "temperature": T_INF,
        }
    ),
)


try:
    st.solution.methods.p_v_coupling.set_state({"flow_scheme": "Coupled"})
except Exception as e:
    log("   coupling: " + str(e)[:100])
# IMPORTANT: the default explicit relaxation (0.75) makes this low-Mach
# ideal-gas case diverge (verified: mean wall pressure drifted to 60 kPa,
# Mach up to 1.17).  0.4 / 0.5 keeps it stable and physically sane.
pc = st.solution.controls.p_v_controls
for nm, val in (
    ("explicit_pressure_under_relaxation", PR),
    ("explicit_momentum_under_relaxation", MR),
):
    try:
        setattr(pc, nm, val)
        log(f"OK   {nm} = {val}")
    except Exception as e:
        log(f"FAIL {nm}: {str(e)[:100]}")


def methods(order1, stx=None):
    # 2026 R1 把离散格式挪到了 spatial_discretization 下面，旧路径虽然还能用，
    # 但每次调用都会刷一屏 DeprecatedSettingWarning 与新语法提示。
    # 注意：新路径的键名是 `mom` / `temperature`，不是 `momentum` / `energy`。
    # GPU 求解器下这些子项不存在，两步都会静默失败 —— 属正常，GPU 用自己的默认值。
    stx = stx or st
    up = "first-order-upwind" if order1 else "second-order-upwind"
    sch = {
        "pressure": "standard" if order1 else "second-order",
        "mom": up,
        "temperature": up,
        "k": up,
        "omega": up,
    }
    try:
        stx.solution.methods.spatial_discretization.discretization_scheme.set_state(sch)
        return
    except Exception:
        pass
    sch = {
        "pressure": "standard" if order1 else "second-order",
        "momentum": up,
        "energy": up,
        "k": up,
        "omega": up,
    }
    try:
        stx.solution.methods.discretization_scheme.set_state(sch)
    except Exception:
        pass


ok("methods 1st order", lambda: methods(True))


def set_ff(aoa):
    a = math.radians(aoa)
    d = [math.cos(a), 0.0, math.sin(a)]
    for z in far:
        zz = bcs.pressure_far_field[z]
        zz.momentum.gauge_pressure = {"option": "value", "value": P_INF}
        zz.momentum.mach_number = {"option": "value", "value": MA}
        zz.momentum.flow_direction = [{"option": "value", "value": float(v)} for v in d]
        zz.turbulence.turbulent_intensity = 0.1
        zz.turbulence.turbulent_viscosity_ratio = 10.0
        try:
            zz.thermal.temperature = {"option": "value", "value": T_INF}
        except Exception:
            log("   (could not set farfield temperature)")
    return d


rd = st.solution.report_definitions
HAS_MZ = False  # 力矩报告是否创建成功（创建失败时不要把它塞进 compute）


def reports(aoa, rdx=None):
    global HAS_MZ
    rdx = rdx or rd
    a = math.radians(aoa)
    lift = [-math.sin(a), 0.0, math.cos(a)]
    drag = [math.cos(a), 0.0, math.sin(a)]
    rdx.force["L"] = {"zones": airframe, "force_vector": lift}
    rdx.force["D"] = {"zones": airframe, "force_vector": drag}
    # 2026 R1 的键名是 `mom_axis` / `mom_center`，写 `moment_axis` 会被拒
    # （Key 'moment_axis' is invalid），于是俯仰力矩一直是 None、pitch_moment.png
    # 也一直画不出来。report_output_type 选 "Moment" 拿到的是 N·m 原始力矩，
    # 由本脚本自己除 q·S·MAC 得 Cm，避免依赖参考值的设置顺序。
    try:
        rdx.moment["Mz"] = {
            "zones": airframe,
            "mom_axis": [0.0, 1.0, 0.0],
            "mom_center": MC,
            "report_output_type": "Moment",
        }
        HAS_MZ = True
    except Exception as e:
        HAS_MZ = False
        log("   (moment report unavailable: %s)" % str(e)[:80])


def values(names=None, rdx=None):
    rdx = rdx or rd
    if names is None:
        names = ("L", "D") + (("Mz",) if HAS_MZ else ())
    out = rdx.compute(report_defs=list(names))
    v = {}
    for item in out:
        for k, val in item.items():
            try:
                v[k] = float(val[0]) if isinstance(val, (list, tuple)) else float(val)
            except Exception:
                v[k] = None
    return v


# 记录本轮实际用的设备，写进 forces.json 便于事后核对
hw = {"device": DEV, "gpu_performance_mode": GPU_PERF}

results = []

# --------------------------------------------------------------------------
# hybrid 模式：CPU 冷启动播种 → GPU 跑主迭代
# --------------------------------------------------------------------------

HYBRID = DEVICE == "hybrid"
if HYBRID:
    os.makedirs(os.path.dirname(SEED_CASE), exist_ok=True)
hw["device"] = ("hybrid(cpu%d+gpu)" % GPU_SEED) if HYBRID else DEV

if HYBRID:
    log("=" * 60)
    log("hybrid 阶段①：CPU 播种 %d 步 × %d 个攻角" % (GPU_SEED, len(AOAS)))
    ok("methods 1st order", lambda: methods(True))
    for aoa in AOAS:
        log(f"\n############ AoA = {aoa} deg（CPU 播种）############")
        set_ff(aoa)
        reports(aoa)
        st.solution.initialization.hybrid_initialize()
        st.solution.run_calculation.iterate(iter_count=GPU_SEED)
        st.file.write(file_type="case-data", file_name=SEED_FMT % int(aoa))
        log("   种子已写入 %s" % (SEED_FMT % int(aoa)))
    s.exit()
    log("CPU 会话已退出，准备启动 GPU 会话")

    gs, gdev = common.launch_solver(
        prefer="gpu",
        gpu_nproc=NPROC_GPU,
        cpu_nproc=NPROC,
        precision="double",
        cwd=BASE + "/work",
        fallback=FALLBACK,
        performance_mode=GPU_PERF,
        log=log,
    )
    gst = gs.settings
    grd = gst.solution.report_definitions
    if gdev != "gpu":
        log("!! GPU 不可用，改用 CPU 跑主迭代")
    rest = max(0, WARM + ITERS - GPU_SEED)
    log("hybrid 阶段②：%s 跑剩余 %d 步 × %d 个攻角" % (gdev.upper(), rest, len(AOAS)))
    for aoa in AOAS:
        log(f"\n############ AoA = {aoa} deg（{gdev.upper()} 主迭代）############")
        gst.file.read(file_type="case-data", file_name=SEED_FMT % int(aoa))
        reports(aoa, rdx=grd)
        methods(False, stx=gst)
        hist = []
        for done in range(0, rest, 50):
            n = min(50, rest - done)
            gst.solution.run_calculation.iterate(iter_count=n)
            v = values(rdx=grd)
            if v.get("L") is not None and v.get("D") is not None:
                hist.append(
                    [
                        GPU_SEED + done + n,
                        v["D"] / (QINF * SREF),
                        v["L"] / (QINF * SREF),
                    ]
                )
                log(
                    f"   it {GPU_SEED + done + n:4d}  CD={hist[-1][1]:+.4f}  CL={hist[-1][2]:+.4f}"
                )
        v = values(rdx=grd)
        L, D = v.get("L"), v.get("D")
        cl = L / (QINF * SREF) if L is not None else None
        cd = D / (QINF * SREF) if D is not None else None
        log(f"   CL = {cl:.4f}   CD = {cd:.4f}   Mz = {v.get('Mz')}")
        results.append(
            {
                "aoa": aoa,
                "L_N": L,
                "D_N": D,
                "CL": cl,
                "CD": cd,
                "Mz_N_m": v.get("Mz"),
                "CM": (v.get("Mz") / (QINF * SREF * LREF)) if v.get("Mz") else None,
                "L_over_D": (cl / cd) if cd else None,
                "history": hist,
            }
        )
        ok(
            "save",
            lambda a=aoa: gst.file.write(
                file_type="case-data", file_name=CASE_FMT % int(a)
            ),
        )
    if gdev == "gpu":
        hw["gpu_mem_gb"] = common.gpu_memory_gb(gs)
        log("   GPU 显存占用 %.2f GB" % hw["gpu_mem_gb"])
    gs.exit()
    hw["device"] = "hybrid(cpu%d+%s)" % (GPU_SEED, gdev)
    hw["n_aoa"] = len(results)
    hw["total_solve_s"] = round(time.time() - t0, 1)
    hw["seconds_per_iter"] = round(
        (time.time() - t0) / max(1, len(results) * (WARM + ITERS)), 4
    )
    json.dump(
        results, open(os.path.join(OUT, "forces.json"), "w"), indent=2, default=str
    )
    try:
        json.dump(
            hw, open(os.path.join(OUT, "run_hardware.json"), "w"), indent=2, default=str
        )
    except Exception:
        pass
    log("\n=== SUMMARY (hybrid) ===")
    for r in results:
        log(
            f"  AoA {r['aoa']:5.1f}: CL {r['CL']:8.4f}  CD {r['CD']:8.4f}  L/D {r['L_over_D']:7.3f}"
        )
    log(f"  设备 {hw['device']}  |  总求解 {hw['total_solve_s'] / 60:.1f} min")
    raise SystemExit(0)

_t_all = time.time()
for aoa in AOAS:
    log(f"\n############ AoA = {aoa} deg ############")
    set_ff(aoa)
    reports(aoa)
    ok("hybrid init", lambda: st.solution.initialization.hybrid_initialize())
    ok(f"warm-up {WARM}", lambda: st.solution.run_calculation.iterate(iter_count=WARM))
    ok("2nd order", lambda: methods(False))
    # 第一个攻角跑完预热后确认 GPU 求解器确实在工作（显存占用 > 0）
    if aoa == AOAS[0] and DEV == "gpu":
        gb = common.gpu_memory_gb(s)
        log(f"   GPU 显存占用 {gb:.2f} GB" + ("" if gb > 0 else "  ⚠️ 为 0，GPU 未生效"))
        hw["gpu_mem_gb"] = gb
    # iterate in chunks so we can watch convergence
    hist = []
    for chunk in range(0, ITERS, 50):
        n = min(50, ITERS - chunk)
        st.solution.run_calculation.iterate(iter_count=n)
        v = values()
        if v.get("L") is not None and v.get("D") is not None:
            hist.append(
                [WARM + chunk + n, v["D"] / (QINF * SREF), v["L"] / (QINF * SREF)]
            )
            log(
                f"   it {WARM + chunk + n:4d}  CD={hist[-1][1]:+.4f}  CL={hist[-1][2]:+.4f}"
            )
    v = values()
    L, D = v.get("L"), v.get("D")
    cl = L / (QINF * SREF) if L is not None else None
    cd = D / (QINF * SREF) if D is not None else None
    log(f"   L = {L}  D = {D}  Mz = {v.get('Mz')}")
    log(
        f"   CL = {cl:.4f}   CD = {cd:.4f}   L/D = {cl / cd if cd else float('nan'):.3f}"
    )
    results.append(
        {
            "aoa": aoa,
            "L_N": L,
            "D_N": D,
            "CL": cl,
            "CD": cd,
            "Mz_N_m": v.get("Mz"),
            "CM": (v.get("Mz") / (QINF * SREF * LREF)) if v.get("Mz") else None,
            "L_over_D": (cl / cd) if cd else None,
            "history": hist,
        }
    )
    ok(
        "save",
        lambda a=aoa: st.file.write(file_type="case-data", file_name=CASE_FMT % int(a)),
    )
    json.dump(
        results, open(os.path.join(OUT, "forces.json"), "w"), indent=2, default=str
    )

json.dump(results, open(os.path.join(OUT, "forces.json"), "w"), indent=2, default=str)

hw["n_aoa"] = len(results)
hw["total_solve_s"] = round(time.time() - _t_all, 1)
hw["seconds_per_iter"] = round(
    (time.time() - _t_all) / max(1, len(results) * (WARM + ITERS)), 4
)
try:
    json.dump(
        hw, open(os.path.join(OUT, "run_hardware.json"), "w"), indent=2, default=str
    )
except Exception:
    pass

log("\n=== SUMMARY ===")
for r in results:
    log(
        f"  AoA {r['aoa']:5.1f}: CL {r['CL']:8.4f}  CD {r['CD']:8.4f}  L/D {r['L_over_D']:7.3f}"
    )
log(
    f"  设备 {DEV}  |  总求解 {hw['total_solve_s'] / 60:.1f} min  "
    f"|  平均 {hw['seconds_per_iter']:.3f} s/步"
)
s.exit()
log("DONE")
