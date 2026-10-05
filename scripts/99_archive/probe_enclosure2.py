"""Probe 2: how to activate the external-flow enclosure task."""
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

d = ftm.describe_geometry_and_flow
print("\ninsertable_tasks AFTER import:", [repr(x) for x in d.insertable_tasks()])

d.add_enclosure = True
d.flow_type = "External flow around object"
d()
print("described", flush=True)

print("\n--- task_list (raw) ---")
try:
    print(ftm._task_object.general.workflow.task_list())
except Exception as e:
    print("fail", e)

print("\n--- children() now ---")
for c in ftm.children():
    print("   ", getattr(c, "_name", "?"), c._task_object.task_type())

print("\n--- insertable_tasks after describe ---")
try:
    print([repr(x) for x in ftm.describe_geometry_and_flow.insertable_tasks()])
except Exception as e:
    print("fail", type(e).__name__, e)

# try the root command for enclosure
print("\n--- root command s.meshing.CreateExternalFlowBoundaries ---")
try:
    cmd = s.meshing.CreateExternalFlowBoundaries
    print("type:", type(cmd))
    args = cmd.arguments
    for k in dir(args):
        if k.startswith("_"):
            continue
        a = getattr(args, k)
        try:
            allowed = a.allowed_values() if hasattr(a, "allowed_values") else None
        except Exception:
            allowed = None
        print(f"   {k:26s} = {getattr(a,'get_state',lambda: '?')()!r}  ALLOWED={allowed}")
except Exception as e:
    print("cmd introspect fail:", type(e).__name__, e)

s.exit()
print("\nDONE")
