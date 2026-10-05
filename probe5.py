"""Probe 5: create enclosure, then dump size-control tasks."""
import os
os.environ.setdefault("PYFLUENT_SHOW_SERVER_GUI", "0")
from ansys.fluent.core import launch_fluent

BASE = r"C:/Users/jianyuewushuang/document/model/ansys/UAVdesign20261004"
s = launch_fluent(mode="meshing", processor_count=2, precision="double", cwd=BASE + "/mesh_work")
print("LAUNCH OK", flush=True)
ftm = s.fault_tolerant()


def dump(name):
    try:
        t = ftm.__getattr__(name)
    except Exception as e:
        print(f"\n>>>>> {name}: unavailable ({type(e).__name__})")
        return None
    print(f"\n>>>>> {name} [{t._task_object.task_type()}] state={t._task_object.state()}")
    try:
        for k, v in t._task_object.arguments().items():
            allowed = ""
            try:
                sub = getattr(t._task_object.arguments, k)
                if hasattr(sub, "allowed_values"):
                    av = sub.allowed_values()
                    if av:
                        allowed = f"  ALLOWED={av}"
            except Exception:
                pass
            print(f"   {k:30s} = {v!r}{allowed}")
    except Exception as e:
        print("   args fail:", e)
    return t


icpm = ftm.import_cad_and_part_management
icpm.fmd_file_name = BASE + "/1.stl"
icpm.length_unit = "m"
icpm.create_object_per = "One per part"
icpm()
print("imported", flush=True)

d = ftm.describe_geometry_and_flow
d.add_enclosure = True
d.flow_type = "External flow around object"
d()
print("described", flush=True)

efb = ftm.create_external_flow_boundaries
try:
    print("   ", efb._task_object.arguments()["bounding_box_object"])
except Exception as e:
    print("   fail", e)

efb.creation_method = "Create new boundary"
efb.selection_type = "object"
efb.object_selection_list = ["object1"]
efb.extraction_method = "surface mesh"
efb.external_boundaries_name = "tunnel"
efb.bounding_box_object = {
    "size_relative_length": "Ratio relative to geometry size",
    "xmin_ratio": 1.5, "xmax_ratio": 2.5,
    "ymin_ratio": 1.0, "ymax_ratio": 1.0,
    "zmin_ratio": 6.0, "zmax_ratio": 6.0,
}
print("\nset bbox:", efb._task_object.arguments()["bounding_box_object"], flush=True)
try:
    efb()
    print(">>> enclosure created OK", flush=True)
except Exception as e:
    print(">>> enclosure FAILED:", type(e).__name__, e, flush=True)

for n in ["create_external_flow_boundaries", "choose_mesh_control_options",
          "size_controls_table", "add_local_sizing", "setup_size_controls",
          "generate_surface_mesh", "compute_size_fields"]:
    dump(n)

s.exit()
print("\nDONE")
