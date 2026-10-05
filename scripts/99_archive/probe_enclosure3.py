"""Probe 3: configure the Create External Flow Boundaries task."""
import os
os.environ.setdefault("PYFLUENT_SHOW_SERVER_GUI", "0")
from ansys.fluent.core import launch_fluent

BASE = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))   # <project root>
s = launch_fluent(mode="meshing", processor_count=2, precision="double", cwd=BASE + "/work")
print("LAUNCH OK", flush=True)
ftm = s.fault_tolerant()

t = ftm.import_cad_and_part_management
t.fmd_file_name = BASE + "/data/1.stl"
t.length_unit = "m"
t.create_object_per = "One per part"
t()
print("imported", flush=True)

ftm.describe_geometry_and_flow.add_enclosure = True
ftm.describe_geometry_and_flow.flow_type = "External flow around object"
ftm.describe_geometry_and_flow()

print("\n--- all tasks via ftm.tasks() ---")
try:
    for to in ftm.tasks():
        print("   ", to.name(), "|", to.task_type(), "| state=", to.state())
except Exception as e:
    print("tasks fail", type(e).__name__, e)

print("\n--- access create_external_flow_boundaries via attribute ---")
efb = None
try:
    efb = ftm.create_external_flow_boundaries
    print("got:", type(efb).__name__)
    a = efb._task_object.arguments
    for k in a():
        val = a[k]
        allowed = None
        try:
            sub = getattr(a, k)
            if hasattr(sub, "allowed_values"):
                allowed = sub.allowed_values()
        except Exception:
            pass
        print(f"   {k:28s} = {val!r}   ALLOWED={allowed}")
except Exception as e:
    print("attr fail:", type(e).__name__, e)

print("\n--- objects available ---")
for fn in ("GetObjects", "get_objects"):
    try:
        print(fn, getattr(s.meshing, fn)())
    except Exception as e:
        print(fn, "fail", type(e).__name__)

s.exit()
print("\nDONE")
