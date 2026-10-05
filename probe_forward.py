"""Drive FTM workflow forward step by step, dumping new tasks as they appear."""
import os
os.environ.setdefault("PYFLUENT_SHOW_SERVER_GUI", "0")
from ansys.fluent.core import launch_fluent

BASE = r"C:/Users/jianyuewushuang/document/model/ansys/UAVdesign20261004"
s = launch_fluent(mode="meshing", processor_count=2, precision="double", cwd=BASE + "/mesh_work")
print("LAUNCH OK", flush=True)
ftm = s.fault_tolerant()


def chain():
    return [getattr(c, "_name", "?") for c in ftm.children()]


def dump(name):
    t = ftm.__getattr__(name)
    print(f"\n>>>>> {name} [{t._task_object.task_type()}]")
    try:
        for k, v in t._task_object.arguments().items():
            allowed = ""
            try:
                a = getattr(t._task_object.arguments, k)
                if hasattr(a, "allowed_values"):
                    av = a.allowed_values()
                    if av:
                        allowed = f"  ALLOWED={av}"
            except Exception:
                pass
            print(f"     {k:34s} = {v!r}{allowed}")
    except Exception as e:
        print("     args fail:", e)
    return t


def run(name, **kw):
    t = ftm.__getattr__(name)
    for k, v in kw.items():
        setattr(t, k, v)
        print(f"   set {name}.{k} = {v}", flush=True)
    try:
        t()
    except Exception as e:
        print(f"   !! {name} execute failed: {type(e).__name__} {e}", flush=True)
        return False
    print(f"   >>> {name} OK. chain = {chain()}", flush=True)
    return True


print("chain0:", chain())

t = ftm.import_cad_and_part_management
t.fmd_file_name = BASE + "/1.stl"
t.length_unit = "m"
t.create_object_per = "One per part"
t()
print("imported. chain:", chain(), flush=True)

dump("describe_geometry_and_flow")
run("describe_geometry_and_flow", flow_type="External flow around object", add_enclosure=True)

# what appeared?
for n in chain():
    if n not in ("import_cad_and_part_management", "describe_geometry_and_flow"):
        dump(n)

run("choose_mesh_control_options")
print("\nAFTER choose_mesh_control_options chain:", chain(), flush=True)
for n in chain():
    if n in ("setup_size_controls", "mesh_controls_table", "create_external_flow_boundaries",
             "generate_surface_mesh", "compute_size_fields"):
        dump(n)

s.exit()
print("\nDONE")
