"""Does an explicit face_scope make the boundary-layer prisms appear?"""
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


def prep():
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
    log("prep done; regions:", ur.arguments())


prep()

bl = T("add_boundary_layers")
bl.arguments.set_state({"offset_method_type": "uniform"})
try:
    fsmo = getattr(bl.arguments, "face_scope").face_scope_mesh_object
    print("face_scope_mesh_object allowed:", fsmo.allowed_values(), flush=True)
except Exception as e:
    print("fsmo:", str(e)[:120], flush=True)


def volmesh():
    vm = T("create_volume_mesh_wtm")
    vm.arguments.set_state({"volume_fill": "poly-hexcore"})
    fc = vm.arguments().get("volume_fill_controls") or {}
    fc["cell_sizing"] = "Geometric"
    fc["growth_rate"] = 1.2
    for k in ("hex_max_cell_length", "hex_min_cell_length"):
        if k in fc:
            fc[k] = 2.5 if "max" in k else 0.30
    vm.arguments.set_state({"volume_fill_controls": fc})
    vm.execute()
    return vm


for tag, extra in (
        ("no-scope", {}),
        ("mesh-objects", {"face_scope": {"face_scope_mesh_object":
                                         ["origin-fluid_box", "origin-aircraft"]}}),
        ("mesh-objects-str", {"face_scope": {"face_scope_mesh_object": "*"}}),
):
    prep()
    bl = T("add_boundary_layers")
    bl.arguments.set_state({"offset_method_type": "uniform"})
    st = {"offset_method_type": "uniform", "number_of_layers": 10,
          "first_height": 5e-4, "rate": 1.3, "add_child": "yes",
          "control_name": "bl_" + tag,
          "local_prism_preferences": {"show_in_gui": False,
                                      "modify_at_invalid_normals": True,
                                      "ignore_boundary_layers": False,
                                      "additional_ignored_layers": 0}}
    st.update(extra)
    try:
        bl.arguments.set_state(st)
        bl.execute()
        log("[%s] BL args after exec: %s" % (tag, bl.arguments()))
    except Exception as e:
        log("[%s] BL FAIL %s" % (tag, str(e)[:130]))
    try:
        volmesh()
        log("[%s] volume mesh OK" % tag)
    except Exception as e:
        log("[%s] volume mesh FAIL %s" % (tag, str(e)[:130]))
    print(m.tui.__class__ and "", flush=True)
    try:
        out = m.execute_tui("report/summary-size-metrics")
        log("[%s] size: %s" % (tag, str(out)[:300]))
    except Exception as e:
        log("[%s] size report FAIL %s" % (tag, str(e)[:100]))

m.exit()
print("PROBE29 DONE", flush=True)
