"""Probe 4: dump + configure + execute Create External Flow Boundaries."""
import os, json
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
print("described", flush=True)

efb = ftm.create_external_flow_boundaries
print("task obj:", type(efb).__name__)
a = efb._task_object.arguments
print("\n--- arguments ---")
state = a()
for k, v in state.items():
    allowed = None
    try:
        sub = getattr(a, k)
        if hasattr(sub, "allowed_values"):
            allowed = sub.allowed_values()
    except Exception as e:
        allowed = f"<{type(e).__name__}>"
    print(f"   {k:26s} = {v!r}")
    if allowed:
        print(f"   {'':26s}   ALLOWED={allowed}")

print("\n--- objects in meshing model ---")
for probe in ("objects", "Objects"):
    try:
        print(probe, getattr(a, probe).allowed_values())
    except Exception as e:
        print(probe, "fail", type(e).__name__, e)

s.exit()
print("\nDONE")
