"""Stage 2 - solve the UAV external aerodynamics over a range of angles of attack.

  * air  : ideal gas, 5 km ISA, Ma 0.187
  * outer: pressure-far-field  (AoA set through the flow direction)
  * model: k-omega SST, steady, coupled
  * reports: lift / drag / pitching moment about the quarter-MAC point

The airframe-interior cell zone produced by the boolean stays in the mesh; it is
sealed off by the airframe wall so it does not influence the external solution.
"""
import os, json, time, math
os.environ.setdefault("PYFLUENT_SHOW_SERVER_GUI", "0")
from ansys.fluent.core import launch_fluent

BASE = r"C:/Users/jianyuewushuang/document/model/ansys/UAVdesign20261004"
MSH = os.environ.get("MSH", BASE + "/aircraft_mesh.msh.h5")
NPROC = int(os.environ.get("NPROC", 4))
AOAS = [float(x) for x in os.environ.get("AOAS", "0,4,8,12").split(",")]
ITERS = int(os.environ.get("ITERS", "350"))

# ---------------- flight condition: 5 km ISA, V = 60 m/s ----------------
T_INF = 255.65          # K
P_INF = 54019.89        # Pa (gauge; operating pressure = 0)
RHO = 0.73612           # kg/m^3
MU = 1.628e-5           # Pa.s
V_INF = 60.0
A_INF = 320.529
MA = V_INF / A_INF
Q_INF = 0.5 * RHO * V_INF ** 2

# ---------------- reference values (wing) ----------------
SREF = 65.3375          # m^2  wing planform
LREF = 4.1996           # m    MAC
MOMENT_CENTRE = [7.9319, 0.0, 0.0]

t0 = time.time()


def log(*a):
    print(f"[{time.time()-t0:7.1f}s]", *a, flush=True)


s = launch_fluent(mode="solver", precision="double", processor_count=NPROC, cwd=BASE + "/mesh_work")
log(f"solver launched ({NPROC} cores)")
st = s.settings
st.file.read(file_type="mesh", file_name=MSH)
log("mesh read")


def tui(cmd):
    try:
        return s.execute_tui(cmd)
    except Exception:
        try:
            return s.scheme_eval.string_eval(f'(ti-menu-load-string "{cmd}")')
        except Exception:
            return None


def try_(label, fn):
    try:
        fn()
        log(f"   OK   {label}")
        return True
    except Exception as e:
        log(f"   FAIL {label}: {str(e)[:130]}")
        return False


# ---------------- physics ----------------
try_("energy on", lambda: setattr(st.setup.models.energy, "enabled", True))


def set_viscous():
    st.setup.models.viscous = {"model": "k-omega", "k_omega_model": "sst"}


try_("viscous k-omega SST", set_viscous)


def set_air():
    st.setup.materials.fluid["air"] = {
        "density": {"option": "ideal-gas"},
        "viscosity": {"option": "constant", "value": MU},
        "specific_heat": {"option": "constant", "value": 1006.43},
        "thermal_conductivity": {"option": "constant", "value": 0.0242}}


try_("air ideal-gas + constant mu", set_air)

# CRITICAL: Fluent's default operating pressure is 101325 Pa.  Far-field gauge
# pressure is relative to it, so leaving the default would give an absolute
# pressure of 155 kPa and a density ~2.9x too high.  Set it to 0 so that
# gauge == absolute.  Not on the settings tree in 26R1 -> use the TUI.
op_ok = False
for cmd in ("define/operating-conditions/operating-pressure 0",
            "define/operating-conditions/operating-pressure 0 () q"):
    try:
        s.execute_tui(cmd)
        log("   OK   operating pressure -> 0 Pa  (gauge = absolute)")
        op_ok = True
        break
    except Exception as e:
        log("   operating-pressure TUI: " + str(e)[:90])
if not op_ok:
    log("   !! could NOT set operating pressure - density would be ~2.9x wrong")

# ---------------- boundary zones ----------------
bcs = st.setup.boundary_conditions


def names_of(group):
    try:
        g = getattr(bcs, group)
        return list(g().keys()) if callable(g) else list(g.keys())
    except Exception:
        try:
            return g.get_object_names()
        except Exception:
            return []


walls = names_of("wall")
log(f"wall zones: {walls}")
# the mesher names the outer boundary "<fluid body>:n" and the airframe
# interface "aircraft-fluid_box" (+ a shadow).  Pick them apart explicitly.
outer = next((w for w in walls if "aircraft" not in w.lower()), None)
airframe = [w for w in walls if "aircraft" in w.lower()]
log(f"outer = {outer} | airframe = {airframe}")

try_(f"convert {outer} -> pressure-far-field",
     lambda: bcs.set_zone_type(zone_list=[outer], new_type="pressure-far-field"))
far = names_of("pressure_far_field")
log(f"pressure-far-field zones: {far}")

# ---------------- reference values ----------------
def set_ref():
    rv = st.setup.reference_values
    vals = {"area": SREF, "length": LREF, "density": RHO, "velocity": V_INF,
            "viscosity": MU, "temperature": T_INF, "pressure": P_INF}
    try:
        rv.set_state(vals)
    except Exception:
        for k, v in vals.items():
            try:
                setattr(rv, k, v)
            except Exception:
                pass


try_("reference values", set_ref)

# ---------------- solution methods ----------------
def set_methods():
    m = st.solution.methods
    try:
        m.p_v_coupling.set_state({"flow_scheme": "Coupled"})
    except Exception:
        try:
            m.p_v_coupling.flow_scheme = "Coupled"
        except Exception:
            pass
    try:
        m.discretization_scheme.set_state({
            "pressure": "second-order", "momentum": "second-order-upwind",
            "energy": "second-order-upwind"})
    except Exception:
        pass


try_("methods coupled + 2nd order", set_methods)

# ---------------- report definitions ----------------
def make_reports(aoa):
    a = math.radians(aoa)
    drag = [math.cos(a), 0.0, math.sin(a)]
    lift = [-math.sin(a), 0.0, math.cos(a)]
    rd = st.solution.report_definitions
    for nm, vec in (("rep-drag", drag), ("rep-lift", lift)):
        body = {"zones": airframe + ([outer] if outer else []),
                "force_vector": vec}
        # try several spellings for the moment reference
        for mc_key in ("moment_center", "moment_centre", "moment_origin"):
            try:
                rd.force[nm] = dict(body, **{mc_key: MOMENT_CENTRE,
                                             "moment_axis": [0.0, 1.0, 0.0]})
                log(f"   report {nm} (with {mc_key})")
                break
            except Exception:
                continue
        else:
            try:
                rd.force[nm] = body
                log(f"   report {nm} (no moment)")
            except Exception as e:
                log(f"   report {nm} failed: {str(e)[:120]}")
    return drag, lift


def read_forces():
    rd = st.solution.report_definitions
    out = {}
    for nm in ("rep-drag", "rep-lift"):
        v = None
        try:
            r = rd.compute(nm)          # <- the working call
            if r not in (None, {}, ""):
                v = r
        except Exception as e:
            log(f"   compute({nm}) failed: {str(e)[:110]}")
        out[nm] = v
    return out


def set_farfield(aoa):
    """pressure-far-field: settings live under .momentum / .turbulence / .thermal"""
    a = math.radians(aoa)
    d = [math.cos(a), 0.0, math.sin(a)]
    for z in far:
        zz = bcs.pressure_far_field[z]
        try:
            zz.momentum.gauge_pressure = {"option": "value", "value": P_INF}
            zz.momentum.mach_number = {"option": "value", "value": MA}
            zz.momentum.flow_direction = [{"option": "value", "value": float(v)} for v in d]
        except Exception as e:
            log(f"   farfield momentum {z}: {str(e)[:130]}")
        try:
            zz.turbulence.turbulent_intensity = 0.1
            zz.turbulence.turbulent_viscosity_ratio = 10.0
        except Exception as e:
            log(f"   farfield turbulence {z}: {str(e)[:120]}")
        told = False
        for path in (lambda: setattr(zz.thermal, "temperature",
                                     {"option": "value", "value": T_INF}),
                     lambda: setattr(zz, "temperature",
                                     {"option": "value", "value": T_INF})):
            try:
                path(); told = True; break
            except Exception:
                continue
        if not told:
            log(f"   !! could not set farfield temperature on {z}")
    return d


# ---------------- solve ----------------
results = []
for aoa in AOAS:
    log(f"\n############ AoA = {aoa} deg ############")
    set_farfield(aoa)
    make_reports(aoa)
    try_("hybrid init", lambda: st.solution.initialization.hybrid_initialize())
    try_("first-order 60 iters", lambda: st.solution.run_calculation.iterate(iter_count=60))

    def second_order():
        try:
            st.solution.methods.discretization_scheme.set_state({
                "k": "second-order-upwind", "omega": "second-order-upwind"})
        except Exception:
            pass


    try_("switch k/omega to 2nd order", second_order)
    try_(f"iterate {ITERS}", lambda: st.solution.run_calculation.iterate(iter_count=ITERS))
    f = read_forces()
    log(f"   forces: {f}")
    results.append({"aoa": aoa, "forces": f, "q_inf": Q_INF, "S_ref": SREF,
                    "L_ref": LREF, "mach": MA})
    try_("save case+data",
         lambda: st.file.write(file_type="case-data",
                               file_name=f"{BASE}/uav_aoa{int(aoa)}.cas.h5"))

json.dump(results, open(BASE + "/forces_raw.json", "w"), indent=2, default=str)
log("\n=== RAW RESULTS ===")
print(json.dumps(results, indent=2, default=str), flush=True)
s.exit()
log("DONE")
