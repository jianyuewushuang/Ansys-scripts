"""Find a working way to evaluate Fluent force report definitions."""
import os, json, math, sys
os.environ.setdefault("PYFLUENT_SHOW_SERVER_GUI", "0")
from ansys.fluent.core import launch_fluent

BASE = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))   # <project root>
CASE = sys.argv[1] if len(sys.argv) > 1 else os.path.join(BASE, "artifacts/cases/uav_aoa0.cas.h5")

s = launch_fluent(mode="solver", precision="double", processor_count=2, cwd=BASE + "/work")
st = s.settings
st.file.read(file_type="case-data", file_name=CASE)
print("read", CASE, flush=True)

bcs = st.setup.boundary_conditions
walls = list(bcs.wall().keys()) if callable(bcs.wall) else []
airframe = [w for w in walls if "aircraft" in w.lower()]
print("airframe zones:", airframe, flush=True)

rd = st.solution.report_definitions
a = math.radians(4.0)
lift = [-math.sin(a), 0.0, math.cos(a)]
drag = [math.cos(a), 0.0, math.sin(a)]

for nm, vec in (("lift", lift), ("drag", drag)):
    try:
        rd.force[nm] = {"zones": airframe, "force_vector": vec,
                        "moment_center": [7.9319, 0.0, 0.0],
                        "moment_axis": [0.0, 1.0, 0.0]}
        print(f"created {nm} (with moment)")
    except Exception as e:
        print(f"create {nm}: {str(e)[:150]}")

print("\n--- container-level API ---")
print("rd attrs:", [x for x in dir(rd) if not x.startswith("_")][:30])

def t(label, fn):
    try:
        print(f"  {label}: {fn()}")
    except Exception as e:
        print(f"  {label}: FAIL {str(e)[:150]}")

t("rd.compute('lift')", lambda: rd.compute("lift"))
t("rd.compute(['lift'])", lambda: rd.compute(["lift"]))
t("rd.compute()", lambda: rd.compute())
t("rd()", lambda: rd())
try:
    print("  rd.compute signature:", rd.compute.__doc__)
except Exception:
    pass

print("\n--- TUI attempts ---")
for cmd in ("report/forces/compute-force",
            "report/forces/wall-forces",
            "report/report-definitions/compute lift",
            "report/report-definitions/list"):
    try:
        r = s.execute_tui(cmd)
        print(f"  {cmd} -> {str(r)[:600]}")
    except Exception as e:
        print(f"  {cmd}: FAIL {str(e)[:120]}")

print("\n--- transcript of a force report ---")
try:
    s.execute_tui("report/forces")
except Exception as e:
    print(e)

s.exit()
print("DONE")
