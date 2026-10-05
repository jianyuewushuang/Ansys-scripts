"""Decisive probe: remove the aircraft interior cell zone, then determine
which wall zone carries the real aerodynamic force."""
import os
import json
import math

os.environ.setdefault("PYFLUENT_SHOW_SERVER_GUI", "0")
from ansys.fluent.core import launch_fluent

BASE = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))   # <project root>
MESH = BASE + "/artifacts/mesh/aircraft_mesh.msh.h5"

RHO, V, MU, T = 0.73612, 60.0, 1.6282e-5, 255.65
P = 54019.9
MA = 0.187
SREF, LREF = 65.34, 4.20


def zones_txt(s):
    return s.scheme.eval("(format #f \"~a\" (list-zones))") if False else None


s = launch_fluent(mode="solver", precision="double", processor_count=2,
                  cwd=BASE + "/work")
st = s.settings
st.file.read(file_type="mesh", file_name=MESH)
print("=== mesh read ===", flush=True)

mz = st.mesh.modify_zones

# --- try DELETE first (cleanest) ---
for name, kw in (("delete", {"cell_zones": ["aircraft"]}),
                 ("deactivate", {"cell_deactivate_list": ["aircraft"]})):
    fn = getattr(mz, name + "_cell_zone")
    try:
        fn(**kw)
        print(f"{name}_cell_zone({kw}) -> OK", flush=True)
    except Exception as e:
        print(f"{name}_cell_zone({kw}) -> FAIL {str(e)[:150]}", flush=True)

print(s.execute_tui("define/boundary-conditions/list-zones"), flush=True)

# --- minimal setup ---
ok = lambda t, f: print(f"OK   {t}" if (f() or True) else "", flush=True)
st.setup.models.energy = {"enabled": True}
print("energy", st.setup.models.energy.enabled(), flush=True)
st.setup.models.viscous = {"model": "k-omega", "k_omega_model": "sst"}
st.setup.materials.fluid["air"] = {
    "density": {"option": "ideal-gas"},
    "viscosity": {"option": "constant", "value": MU},
    "specific_heat": {"option": "constant", "value": 1006.43},
    "thermal_conductivity": {"option": "constant", "value": 0.0242}}

bcs = st.setup.boundary_conditions
walls = [n for n in (bcs.wall() if callable(bcs.wall) else {}) ]
print("wall zones:", walls, flush=True)
try:
    bcs.set_zone_type(zone_list=["fluid_box:1"], new_type="pressure-far-field")
except Exception as e:
    print("farfield conv:", str(e)[:120], flush=True)
ff = bcs.pressure_far_field["fluid_box:1"]
ff.momentum.gauge_pressure = {"option": "value", "value": P}
ff.momentum.mach_number = {"option": "value", "value": MA}
ff.momentum.flow_direction = [{"option": "value", "value": 1.0},
                              {"option": "value", "value": 0.0},
                              {"option": "value", "value": 0.0}]
ff.turbulence.turbulent_intensity = 0.1
ff.turbulence.turbulent_viscosity_ratio = 10.0
try:
    ff.thermal.temperature = {"option": "value", "value": T}
    print("   farfield T set", flush=True)
except Exception as e:
    print("   farfield T FAIL", str(e)[:100], flush=True)
print("farfield state:\n", ff.get_state(), flush=True)
s.tui.define.operating_conditions.operating_pressure("0")
st.setup.reference_values = {"area": SREF, "length": LREF, "density": RHO,
                             "velocity": V, "viscosity": MU,
                             "temperature": T, "pressure": P}
st.solution.initialization.hybrid_initialize()
st.solution.run_calculation.iterate(iter_count=30)
print("=== iterated 30 ===", flush=True)

# --- forces on each candidate wall zone ---
rd = st.solution.report_definitions
qS = 0.5 * RHO * V * V * SREF
for zn in walls:
    if "fluid_box:1" in zn:
        continue
    rd.force["Fx"] = {"zones": [zn], "force_vector": [1, 0, 0]}
    rd.force["Fz"] = {"zones": [zn], "force_vector": [0, 0, 1]}
    try:
        out = rd.compute(report_defs=["Fx", "Fz"])
        fx = out["Fx"][0]["Fx"][0] if isinstance(out, dict) else None
        fz = out["Fz"][0]["Fz"][0] if isinstance(out, dict) else None
        print(f"  {zn:32s}  Fx={fx:12.1f} N (CD={fx/qS:+.4f})   "
              f"Fz={fz:12.1f} N (CL={fz/qS:+.4f})", flush=True)
    except Exception as e:
        print(f"  {zn}: FAIL {str(e)[:120]}", flush=True)

rd.force["Fxb"] = {"zones": [w for w in walls if "fluid_box:1" not in w],
                   "force_vector": [1, 0, 0]}
try:
    out = rd.compute(report_defs=["Fxb"])
    print("  BOTH sides Fx =", out, flush=True)
except Exception as e:
    print("  both:", str(e)[:120], flush=True)

s.exit()
print("=== done ===", flush=True)
