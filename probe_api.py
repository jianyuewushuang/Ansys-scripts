"""Discover the exact settings keys for pressure-far-field and force reports."""
import os, json, math
os.environ.setdefault("PYFLUENT_SHOW_SERVER_GUI", "0")
from ansys.fluent.core import launch_fluent

BASE = r"C:/Users/jianyuewushuang/document/model/ansys/UAVdesign20261004"
s = launch_fluent(mode="solver", precision="double", processor_count=2, cwd=BASE + "/mesh_work")
st = s.settings
st.file.read(file_type="mesh", file_name=BASE + "/aircraft_mesh.msh.h5")
print("mesh read", flush=True)

bcs = st.setup.boundary_conditions
walls = list(bcs.wall().keys()) if callable(bcs.wall) else []
print("walls:", walls)
outer = next((w for w in walls if "aircraft" not in w.lower()), None)
try:
    bcs.set_zone_type(zone_list=[outer], new_type="pressure-far-field")
    print("converted", outer)
except Exception as e:
    print("convert fail", e)

pff = bcs.pressure_far_field
zones = list(pff().keys()) if callable(pff) else []
print("\npressure_far_field zones:", zones)
if zones:
    z = zones[0]
    print("\n--- pressure-far-field state ---")
    try:
        print(json.dumps(pff[z].get_state(), indent=2, default=str)[:2500])
    except Exception as e:
        print("state fail", e)

print("\n--- force report definition structure ---")
rd = st.solution.report_definitions
try:
    print("report_definitions children:", rd.get_object_names())
except Exception as e:
    print(e)
try:
    print(json.dumps(rd.force["probe"].get_state(), indent=2, default=str)[:2000])
except Exception as e:
    print("force probe:", e)

# how do we evaluate a report?
print("\n--- ways to get a computed value ---")
try:
    rd.force["probe"] = {"zones": [w for w in walls if "aircraft" in w.lower()],
                         "force_vector": [1, 0, 0]}
    print("created probe report")
except Exception as e:
    print("create:", str(e)[:200])

for desc, fn in (
    ("rd.compute_all()", lambda: rd.compute_all()),
    ("rd.force['probe'].compute()", lambda: rd.force["probe"].compute()),
    ("rd.force['probe'].value", lambda: rd.force["probe"].value),
    ("rd.force['probe']()", lambda: rd.force["probe"]()),
    ("getattr rd.force['probe'] dir", lambda: [a for a in dir(rd.force["probe"]) if not a.startswith("_")]),
):
    try:
        print(f"  {desc}: {fn()}")
    except Exception as e:
        print(f"  {desc}: FAIL {str(e)[:150]}")

print("\n--- TUI force report ---")
for cmd in ("/report/forces/force-coefficients", "/report/forces"):
    try:
        print(f"  {cmd} ->", str(s.execute_tui(cmd))[:400])
    except Exception as e:
        print(f"  {cmd} FAIL {str(e)[:120]}")

s.exit()
print("DONE")
