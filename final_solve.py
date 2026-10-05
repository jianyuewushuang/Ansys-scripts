"""FINAL run: delete the spurious airframe-interior cell zone, then solve AoA sweep.

Why: the boolean leaves a sealed `aircraft` cell zone inside the airframe wall.
It is solved as fluid, its pressure collapses ("absolute pressure limited ... on
zone 230789"), the continuity residual never drops and the forces are garbage.
Removing it leaves a clean single fluid region.
"""
import os, json, math, time
os.environ.setdefault("PYFLUENT_SHOW_SERVER_GUI", "0")
from ansys.fluent.core import launch_fluent

BASE = r"C:/Users/jianyuewushuang/document/model/ansys/UAVdesign20261004"
OUT = os.path.join(BASE, "results"); os.makedirs(OUT, exist_ok=True)
MSH = os.environ.get("MSH", os.path.join(BASE, "aircraft_mesh.msh.h5"))
CASE_FMT = os.environ.get("CASE_FMT", os.path.join(BASE, "final_aoa%d.cas.h5"))

T_INF = 255.65; P_INF = 54019.89; RHO = 0.73612; MU = 1.628e-5
V_INF = 60.0; A_INF = 320.529; MA = V_INF / A_INF
SREF = 65.3375; LREF = 4.1996; BREF = 23.6443
QINF = 0.5 * RHO * V_INF ** 2
MC = [7.9319, 0.0, 0.0]

AOAS = [float(x) for x in os.environ.get("AOAS", "0,4,8,12").split(",")]
NPROC = int(os.environ.get("NPROC", 4))
WARM = int(os.environ.get("WARM", 50))
ITERS = int(os.environ.get("ITERS", 150))

t0 = time.time()


def log(*a):
    print(f"[{time.time()-t0:7.1f}s]", *a, flush=True)


s = launch_fluent(mode="solver", precision="double", processor_count=NPROC, cwd=BASE + "/mesh_work")
st = s.settings
st.file.read(file_type="mesh", file_name=MSH)
log("mesh read")

# ---------- 1. delete the airframe-interior cell zone ----------
# Correct keyword is `cell_zones` (not `zone_names`, which is silently ignored).
DELZONE = os.environ.get("DELZONE", "aircraft")
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
        fn(); log(f"OK   {label}")
    except Exception as e:
        log(f"FAIL {label}: {str(e)[:120]}")


ok("energy on", lambda: setattr(st.setup.models.energy, "enabled", True))
def set_viscous():
    st.setup.models.viscous = {"model": "k-omega", "k_omega_model": "sst"}


def set_air():
    st.setup.materials.fluid["air"] = {"density": {"option": "ideal-gas"},
                                       "viscosity": {"option": "constant", "value": MU},
                                       "specific_heat": {"option": "constant", "value": 1006.43},
                                       "thermal_conductivity": {"option": "constant", "value": 0.0242}}


ok("k-omega SST", set_viscous)
ok("air ideal gas", set_air)
log("   check viscous: " + str(st.setup.models.viscous.get_state()))
log("   check air rho: " + str(st.setup.materials.fluid["air"].density.get_state()))
ok("operating pressure 0", lambda: s.execute_tui(
    "define/operating-conditions/operating-pressure 0"))

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
ok(f"convert {outer} -> pressure-far-field",
   lambda: bcs.set_zone_type(zone_list=[outer], new_type="pressure-far-field"))
far = list(bcs.pressure_far_field().keys()) if callable(bcs.pressure_far_field) else []
log(f"far field zones: {far}")
ok("reference values", lambda: st.setup.reference_values.set_state(
    {"area": SREF, "length": LREF, "density": RHO, "velocity": V_INF,
     "viscosity": MU, "temperature": T_INF}))


try:
    st.solution.methods.p_v_coupling.set_state({"flow_scheme": "Coupled"})
except Exception as e:
    log("   coupling: " + str(e)[:100])
# IMPORTANT: the default explicit relaxation (0.75) makes this low-Mach
# ideal-gas case diverge (verified: mean wall pressure drifted to 60 kPa,
# Mach up to 1.17).  0.4 / 0.5 keeps it stable and physically sane.
pc = st.solution.controls.p_v_controls
PR = float(os.environ.get("PRELAX", 0.4))
MR = float(os.environ.get("MRELAX", 0.5))
for nm, val in (("explicit_pressure_under_relaxation", PR),
                ("explicit_momentum_under_relaxation", MR)):
    try:
        setattr(pc, nm, val)
        log(f"OK   {nm} = {val}")
    except Exception as e:
        log(f"FAIL {nm}: {str(e)[:100]}")


def methods(order1):
    sch = {"pressure": "second-order", "momentum": "second-order-upwind",
           "energy": "second-order-upwind"}
    sch["k"] = "first-order-upwind" if order1 else "second-order-upwind"
    sch["omega"] = "first-order-upwind" if order1 else "second-order-upwind"
    if order1:
        sch["pressure"] = "standard"
    try:
        st.solution.methods.discretization_scheme.set_state(sch)
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


def reports(aoa):
    a = math.radians(aoa)
    lift = [-math.sin(a), 0.0, math.cos(a)]
    drag = [math.cos(a), 0.0, math.sin(a)]
    rd.force["L"] = {"zones": airframe, "force_vector": lift}
    rd.force["D"] = {"zones": airframe, "force_vector": drag}
    try:
        rd.moment["Mz"] = {"zones": airframe, "moment_axis": [0.0, 1.0, 0.0],
                           "moment_center": MC}
    except Exception as e:
        log("   (moment report unavailable: %s)" % str(e)[:80])


def values(names=("L", "D")):
    out = rd.compute(report_defs=list(names))
    v = {}
    for item in out:
        for k, val in item.items():
            try:
                v[k] = float(val[0]) if isinstance(val, (list, tuple)) else float(val)
            except Exception:
                v[k] = None
    return v


results = []
for aoa in AOAS:
    log(f"\n############ AoA = {aoa} deg ############")
    set_ff(aoa); reports(aoa)
    ok("hybrid init", lambda: st.solution.initialization.hybrid_initialize())
    ok(f"warm-up {WARM}", lambda: st.solution.run_calculation.iterate(iter_count=WARM))
    ok("2nd order", lambda: methods(False))
    # iterate in chunks so we can watch convergence
    hist = []
    for chunk in range(0, ITERS, 50):
        n = min(50, ITERS - chunk)
        st.solution.run_calculation.iterate(iter_count=n)
        v = values()
        if v.get("L") is not None and v.get("D") is not None:
            hist.append([WARM + chunk + n, v["D"] / (QINF * SREF),
                         v["L"] / (QINF * SREF)])
            log(f"   it {WARM+chunk+n:4d}  CD={hist[-1][1]:+.4f}  CL={hist[-1][2]:+.4f}")
    v = values()
    L, D = v.get("L"), v.get("D")
    cl = L / (QINF * SREF) if L is not None else None
    cd = D / (QINF * SREF) if D is not None else None
    log(f"   L = {L}  D = {D}  Mz = {v.get('Mz')}")
    log(f"   CL = {cl:.4f}   CD = {cd:.4f}   L/D = {cl/cd if cd else float('nan'):.3f}")
    results.append({"aoa": aoa, "L_N": L, "D_N": D, "CL": cl, "CD": cd,
                    "Mz_N_m": v.get("Mz"),
                    "CM": (v.get("Mz") / (QINF * SREF * LREF)) if v.get("Mz") else None,
                    "L_over_D": (cl / cd) if cd else None,
                    "history": hist})
    ok("save", lambda a=aoa: st.file.write(file_type="case-data",
                                           file_name=CASE_FMT % int(a)))
    json.dump(results, open(os.path.join(OUT, "forces.json"), "w"), indent=2,
              default=str)

json.dump(results, open(os.path.join(OUT, "forces.json"), "w"), indent=2, default=str)
log("\n=== SUMMARY ===")
for r in results:
    log(f"  AoA {r['aoa']:5.1f}: CL {r['CL']:8.4f}  CD {r['CD']:8.4f}  L/D {r['L_over_D']:7.3f}")
s.exit()
log("DONE")
