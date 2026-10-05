"""Diagnose the AoA=0 case: mass balance, field extrema, force breakdown."""
import os
import numpy as np

os.environ.setdefault("PYFLUENT_SHOW_SERVER_GUI", "0")
from ansys.fluent.core import launch_fluent

BASE = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))   # <project root>
s = launch_fluent(mode="solver", precision="double", processor_count=2,
                  cwd=BASE + "/work")
st = s.settings
st.file.read(file_type="case-data", file_name=BASE + "/artifacts/cases/final_aoa0.cas.h5")
print("=== case read ===", flush=True)

print("\n--- zones ---", flush=True)
print(s.execute_tui("define/boundary-conditions/list-zones"), flush=True)

print("\n--- BC types ---", flush=True)
bcs = st.setup.boundary_conditions
for grp in ("pressure_far_field", "velocity_inlet", "pressure_outlet", "wall"):
    o = getattr(bcs, grp, None)
    if o is None:
        continue
    try:
        print(" ", grp, list(o().keys()) if callable(o) else o.get_object_names(),
              flush=True)
    except Exception as e:
        print(" ", grp, "?", str(e)[:80], flush=True)

print("\n--- farfield state ---", flush=True)
try:
    print(bcs.pressure_far_field["fluid_box:1"].get_state(), flush=True)
except Exception as e:
    print(str(e)[:200], flush=True)

print("\n--- mass flow balance ---", flush=True)
try:
    print(s.execute_tui("report/fluxes/mass-flow-rate no"), flush=True)
except Exception as e:
    print("flux fail", str(e)[:200], flush=True)

print("\n--- field limits (volume) ---", flush=True)
for cmd in ("report/reference-values", "solve/initialize/set-defaults"):
    pass
try:
    print(s.execute_tui("report/volume-integrals/min static-pressure () () no"),
          flush=True)
    print(s.execute_tui("report/volume-integrals/max static-pressure () () no"),
          flush=True)
    print(s.execute_tui("report/volume-integrals/min velocity-magnitude () () no"),
          flush=True)
    print(s.execute_tui("report/volume-integrals/max velocity-magnitude () () no"),
          flush=True)
except Exception as e:
    print("limits fail", str(e)[:200], flush=True)

print("\n--- force breakdown on aircraft wall ---", flush=True)
rd = st.solution.report_definitions
af = ["aircraft-fluid_box"]
for nm, vec in (("Fx", [1, 0, 0]), ("Fz", [0, 0, 1]), ("Fy", [0, 1, 0])):
    try:
        rd.force[nm] = {"zones": af, "force_vector": vec}
    except Exception as e:
        print("  def", nm, str(e)[:100], flush=True)
try:
    out = rd.compute(report_defs=["Fx", "Fz", "Fy"])
    print(out, flush=True)
except Exception as e:
    print("compute fail", str(e)[:200], flush=True)

print("\n--- surface integrals on aircraft wall ---", flush=True)
for f in ("pressure", "x-wall-shear-stress", "y-wall-shear-stress"):
    try:
        r = s.execute_tui(
            "report/surface-integrals/area-weighted-avg aircraft-fluid_box () %s no no"
            % f)
        print(f, "->", r, flush=True)
    except Exception as e:
        print(f, "fail", str(e)[:100], flush=True)

s.exit()
print("DIAG DONE", flush=True)
