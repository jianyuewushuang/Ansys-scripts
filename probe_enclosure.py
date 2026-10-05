"""Probe: import STL -> describe geometry (external flow) -> inspect enclosure task."""
import os, json
os.environ.setdefault("PYFLUENT_SHOW_SERVER_GUI", "0")
from ansys.fluent.core import launch_fluent

BASE = r"C:/Users/jianyuewushuang/document/model/ansys/UAVdesign20261004"
s = launch_fluent(mode="meshing", processor_count=2, precision="double", cwd=BASE + "/mesh_work")
print("LAUNCH OK", flush=True)
ftm = s.fault_tolerant()


def chain():
    return [(getattr(t, "_name", "?"), t._task_object.task_type()) for t in ftm.children()]


def dump(name):
    t = ftm.__getattr__(name)
    print(f"\n===== {name}  [{t._task_object.task_type()}]")
    for k, v in t._task_object.arguments().items():
        extra = ""
        try:
            av = getattr(t._task_object.arguments, k)
            allowed = av.allowed_values() if hasattr(av, "allowed_values") else None
            if allowed:
                extra = f"   ALLOWED={allowed}"
        except Exception:
            pass
        print(f"   {k:28s} = {v!r}{extra}")
    return t


print("\n--- step 1: import ---")
t = ftm.import_cad_and_part_management
t.fmd_file_name = BASE + "/1.stl"
t.length_unit = "m"
t.create_object_per = "One per part"
t.route = "Native"
print("set:", t.fmd_file_name, t.length_unit, t.create_object_per)
t()
print("import executed. chain:", chain())

print("\n--- step 2: describe geometry and flow ---")
t = ftm.describe_geometry_and_flow
dump("describe_geometry_and_flow")
t.add_enclosure = True
t.flow_type = "External flow around object"
t()
print("describe executed. chain:", chain())

print("\n--- step 3: enclosure task ---")
if "create_external_flow_boundaries" in [c[0] for c in chain()]:
    dump("create_external_flow_boundaries")
else:
    print("not in chain; available task_names:", ftm.task_names())

print("\n--- mesh objects ---")
try:
    print(s.meshing.get_object_names())
except Exception as e:
    print("objnames fail", e)

s.exit()
print("\nDONE")
