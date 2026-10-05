"""Dump FTM workflow task argument states (correct API)."""
import os, json
os.environ.setdefault("PYFLUENT_SHOW_SERVER_GUI", "0")
from ansys.fluent.core import launch_fluent

s = launch_fluent(mode="meshing", processor_count=2, precision="double",
                  cwd=r"C:/Users/jianyuewushuang/document/model/ansys/UAVdesign20261004/mesh_work")
print("LAUNCH OK", flush=True)
s.fault_tolerant()
wf = s.workflow

want = ["Import CAD and Part Management", "Describe Geometry and Flow",
        "Create External Flow Boundaries", "Add Local Sizing",
        "Generate the Surface Mesh", "Add Boundary Layers",
        "Generate the Volume Mesh", "Compute Size Field(s)"]

for n in wf.TaskObject.get_object_names():
    if n not in want:
        continue
    t = wf.TaskObject[n]
    print(f"\n########## {n}")
    try:
        st = t.Arguments.get_state()
        print(json.dumps(st, indent=2, default=str)[:4000])
    except Exception as e:
        print("  state fail:", type(e).__name__, e)
        try:
            print("  dir:", [a for a in dir(t.Arguments) if not a.startswith('_')])
        except Exception:
            pass

s.exit()
print("\nDONE")
