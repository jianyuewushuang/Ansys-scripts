"""Find (a) how to type a region as solid and (b) how to make prisms appear."""
import os
import time

os.environ.setdefault("PYFLUENT_SHOW_SERVER_GUI", "0")
from ansys.fluent.core import launch_fluent

BASE = r"C:/Users/jianyuewushuang/document/model/ansys/UAVdesign20261004"
DOM = BASE + "/fluid_domain.stl"
t0 = time.time()
log = lambda *a: print(f"[{time.time()-t0:6.1f}s]", *a, flush=True)

m = launch_fluent(mode="meshing", processor_count=4, precision="double",
                  cwd=BASE + "/mesh_work")
WFO = m.watertight()._workflow.task_object


def T(p, i=0):
    h = getattr(WFO, p)
    return h[h.get_object_names()[i]]


T("import_geometry").arguments.set_state(
    {"length_unit": "m", "file_format": "Mesh", "mesh_file_name": DOM})
T("import_geometry").execute()
log("imported")
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
                                   "growth_rate": 1.2, "curvature_normal_angle": 20.0,
                                   "size_functions": "Curvature & Proximity",
                                   "scope_proximity_to": "edges", "cells_per_gap": 1.0,
                                   "use_size_files": "No", "draw_size_control": False}})
T("create_surface_mesh").execute()
log("surface mesh")
T("describe_geometry").arguments.set_state(
    {"setup_type": "fluid_solid_voids", "capping_required": False,
     "invoke_share_topology": "Yes", "wall_to_internal": False})
T("describe_geometry").execute()
T("apply_share_topology").execute()
log("share topology")
T("create_regions").execute()
T("update_regions").execute()

ur = T("update_regions")
print("\n=== update_regions state ===\n", ur.arguments(), flush=True)
for k in ("region_name_list", "region_type_list", "old_region_name_list",
          "old_region_type_list"):
    try:
        o = getattr(ur.arguments, k)
        try:
            av2 = o.allowed_values()
        except Exception:
            av2 = None
        print(f"  {k} = {ur.arguments().get(k)}  allowed={av2}", flush=True)
    except Exception as e:
        print("  ", k, str(e)[:80], flush=True)

for names, types in ((["fluid_box", "aircraft"], ["fluid", "solid"]),
                     (["aircraft"], ["solid"])):
    try:
        ur.arguments.set_state({"region_name_list": names,
                                "region_type_list": types})
        ur.execute()
        print("  -> typed", dict(zip(names, types)), "OK", flush=True)
        print("     now:", ur.arguments(), flush=True)
        break
    except Exception as e:
        print("  -> FAIL", str(e)[:120], flush=True)

bl = T("add_boundary_layers")
bl.arguments.set_state({"offset_method_type": "uniform"})
print("\n=== face_scope structure ===", flush=True)
try:
    print("  face_scope =", bl.arguments().get("face_scope"), flush=True)
    fs = getattr(bl.arguments, "face_scope", None)
    print("  dir:", [a for a in dir(fs) if not a.startswith("_")][:20], flush=True)
except Exception as e:
    print("  ", str(e)[:100], flush=True)

for fsval in ({"scope": "global"}, {"scope": "all"}, {"scope": "entire-domain"},
              {"selection_type": "global"}, {"zonelet_list": ["*"]},
              {"labels": ["aircraft"]}):
    try:
        bl.arguments.set_state({"offset_method_type": "uniform",
                                "face_scope": fsval})
        print("  face_scope %s -> OK" % fsval, flush=True)
    except Exception as e:
        print("  face_scope %s -> %s" % (fsval, str(e)[:90]), flush=True)

m.exit()
print("PROBE28 DONE", flush=True)
