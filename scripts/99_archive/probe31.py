"""For each candidate face_scope value: run the volume mesh and count cells."""
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
T("update_regions").arguments.set_state(
    {"region_name_list": ["fluid_box", "aircraft"],
     "region_type_list": ["fluid", "solid"]})
T("update_regions").execute()
log("prep ready")

CANDIDATES = [
    ("(empty)", None),
    ("mesh-object fluid_box", "origin-fluid_box"),
    ("mesh-object list", ["origin-fluid_box", "origin-aircraft"]),
]

for tag, val in CANDIDATES:
    bl = T("add_boundary_layers")
    bl.arguments.set_state({"offset_method_type": "uniform"})
    st = {"offset_method_type": "uniform", "number_of_layers": 10,
          "first_height": 5e-4, "rate": 1.3, "add_child": "yes",
          "control_name": "bl",
          "local_prism_preferences": {"show_in_gui": False,
                                      "modify_at_invalid_normals": True,
                                      "ignore_boundary_layers": False,
                                      "additional_ignored_layers": 0}}
    if val is not None:
        st["face_scope"] = {"face_scope_mesh_object": val}
    try:
        bl.arguments.set_state(st)
        bl.execute()
    except Exception as e:
        log("[%s] BL FAIL %s" % (tag, str(e)[:130]))
        continue
    log("[%s] face_scope after = %s" % (tag, bl.arguments().get("face_scope")))
    vm = T("create_volume_mesh_wtm")
    try:
        vm.arguments.set_state({"volume_fill": "poly-hexcore"})
        fc = vm.arguments().get("volume_fill_controls") or {}
        fc["cell_sizing"] = "Geometric"
        fc["growth_rate"] = 1.2
        for k in ("hex_max_cell_length", "hex_min_cell_length"):
            if k in fc:
                fc[k] = 2.5 if "max" in k else 0.30
        vm.arguments.set_state({"volume_fill_controls": fc})
        vm.execute()
        log("[%s] volume mesh OK" % tag)
    except Exception as e:
        log("[%s] volume mesh FAIL %s" % (tag, str(e)[:130]))

m.exit()
print("PROBE31 DONE", flush=True)
