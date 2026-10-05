"""Enumerate the face_scope sub-structure of the boundary-layer task."""
import os
import time

os.environ.setdefault("PYFLUENT_SHOW_SERVER_GUI", "0")
from ansys.fluent.core import launch_fluent

BASE = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))   # <project root>
DOM = BASE + "/artifacts/geometry/fluid_domain.stl"
t0 = time.time()
log = lambda *a: print(f"[{time.time()-t0:6.1f}s]", *a, flush=True)

m = launch_fluent(mode="meshing", processor_count=4, precision="double",
                  cwd=BASE + "/work")
WFO = m.watertight()._workflow.task_object


def T(p, i=0):
    h = getattr(WFO, p)
    return h[h.get_object_names()[i]]


T("import_geometry").arguments.set_state(
    {"length_unit": "m", "file_format": "Mesh", "mesh_file_name": DOM})
T("import_geometry").execute()
als = T("add_local_sizing_wtm")
av = getattr(als.arguments, "boi_face_label_list").allowed_values()
als.arguments.set_state({"boi_execution": "Body Size", "boi_size": 0.6,
                         "boi_growth_rate": 1.15, "boi_control_name": "af",
                         "boi_zoneor_label": "label",
                         "boi_face_label_list": [x for x in av
                                                 if "aircraft" in str(x).lower()],
                         "add_child": True})
als.execute()
T("create_surface_mesh").arguments.set_state(
    {"length_unit": "m",
     "share_topology_preferences": {"rename_internals_by_body_names": True,
                                    "share_topology_angle": 40.0,
                                    "join_tolerance_increment": 0.05,
                                    "relative_share_topology_tolerance": 0.1,
                                    "show_in_gui": False,
                                    "operation": "Join-Intersect",
                                    "execute_join_intersect": "Join Only",
                                    "number_of_join_tries": 3},
     "cfd_surface_mesh_controls": {"min_size": 0.30, "max_size": 2.5,
                                   "growth_rate": 1.2,
                                   "curvature_normal_angle": 20.0,
                                   "size_functions": "Curvature & Proximity",
                                   "scope_proximity_to": "edges",
                                   "cells_per_gap": 1.0,
                                   "use_size_files": "No",
                                   "draw_size_control": False}})
T("create_surface_mesh").execute()
T("describe_geometry").arguments.set_state(
    {"setup_type": "fluid_solid_voids", "capping_required": False,
     "invoke_share_topology": "Yes", "wall_to_internal": False})
T("describe_geometry").execute()
T("apply_share_topology").execute()
T("create_regions").execute()
ur = T("update_regions")
ur.arguments.set_state({"region_name_list": ["fluid_box", "aircraft"],
                        "region_type_list": ["fluid", "solid"]})
ur.execute()
log("ready")

bl = T("add_boundary_layers")
bl.arguments.set_state({"offset_method_type": "uniform"})

fs = getattr(bl.arguments, "face_scope")
print("face_scope type:", type(fs).__name__, flush=True)
for attr in ("child_names", "command_names", "query_names", "python_name",
             "fluent_name"):
    try:
        print("  ", attr, "=", getattr(fs, attr), flush=True)
    except Exception as e:
        print("  ", attr, str(e)[:60], flush=True)
try:
    print("  getState:", fs.getState(), flush=True)
except Exception as e:
    print("  getState:", str(e)[:90], flush=True)
try:
    print("  child_object_type:", fs.child_object_type.allowed_values()
          if hasattr(fs, "child_object_type") else None, flush=True)
except Exception as e:
    print("  cot:", str(e)[:90], flush=True)

for nm in ("face_scope_mesh_object", "mesh_object", "object", "zonelet",
           "selection", "selection_type", "label", "face_zone"):
    try:
        o = getattr(fs, nm)
        try:
            av = o.allowed_values()
        except Exception:
            av = None
        print("  child %-24s allowed=%s" % (nm, av), flush=True)
    except Exception as e:
        print("  child %-24s -> %s" % (nm, str(e)[:70]), flush=True)

m.exit()
print("PROBE30 DONE", flush=True)
