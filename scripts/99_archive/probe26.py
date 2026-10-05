"""Find the real boundary-layer argument set (depends on offset_method_type)."""
import os
import time

os.environ.setdefault("PYFLUENT_SHOW_SERVER_GUI", "0")
from ansys.fluent.core import launch_fluent

BASE = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))   # <project root>
DOM = BASE + "/artifacts/geometry/fluid_domain.stl"
t0 = time.time()
log = lambda *a: print(f"[{time.time()-t0:6.1f}s]", *a, flush=True)

m = launch_fluent(mode="meshing", precision="double", processor_count=4,
                  cwd=BASE + "/work")
WFO = m.watertight()._workflow.task_object
log("workflow ready")


def T(p, i=0):
    h = getattr(WFO, p)
    names = h.get_object_names()
    return h[names[i]]
T("import_geometry").arguments.set_state(
    {"length_unit": "m", "file_format": "Mesh", "mesh_file_name": DOM})
T("import_geometry").execute()
log("imported")
try:
    als = T("add_local_sizing_wtm")
    av = getattr(als.arguments, "boi_face_label_list").allowed_values()
    als.arguments.set_state({"boi_execution": "Body Size", "boi_size": 0.55,
                             "boi_growth_rate": 1.15, "boi_control_name": "airframe",
                             "boi_zoneor_label": "label",
                             "boi_face_label_list": [x for x in av
                                                     if "aircraft" in str(x).lower()],
                             "add_child": True})
    als.execute()
    log("local sizing")
except Exception as e:
    log("sizing:", str(e)[:120])

T("create_surface_mesh").arguments.set_state(
    {"length_unit": "m",
     "share_topology_preferences": {"rename_internals_by_body_names": True,
                                    "share_topology_angle": 40.0,
                                    "join_tolerance_increment": 0.05,
                                    "relative_share_topology_tolerance": 0.1,
                                    "show_in_gui": False,
                                    "operation": "Join-Intersect",
                                    "execute_join_intersect": "Yes",
                                    "number_of_join_tries": 3},
     "cfd_surface_mesh_controls": {"min_size": 0.20, "max_size": 2.5,
                                   "growth_rate": 1.2, "curvature_normal_angle": 12.0,
                                   "size_functions": "Curvature & Proximity",
                                   "scope_proximity_to": "edges", "cells_per_gap": 1.0,
                                   "use_size_files": "No", "draw_size_control": False}})
T("create_surface_mesh").execute()
log("surface mesh")
T("describe_geometry").arguments.set_state(
    {"setup_type": "fluid_solid_voids", "capping_required": False,
     "invoke_share_topology": "Yes", "wall_to_internal": False})
T("describe_geometry").execute()
log("describe done")

bl = T("add_boundary_layers")
a = bl.arguments
print("\n=== BL state ===\n", bl.arguments(), flush=True)
for k in ("offset_method_type", "face_scope", "control_name",
          "number_of_layers", "rate", "transition_ratio", "add_child"):
    try:
        o = getattr(a, k)
        try:
            av = o.allowed_values()
        except Exception:
            av = None
        print(f"  {k:22s} = {o() if callable(o) else o}   allowed={av}", flush=True)
    except Exception as e:
        print(f"  {k:22s} -> {str(e)[:80]}", flush=True)

for method in ("uniform", "aspect-ratio", "last-ratio", "user-defined",
               "smooth-transition", "expression"):
    try:
        bl.arguments.set_state({"offset_method_type": method})
        print(f"\n--- after offset_method_type={method} ---", flush=True)
        print("   ", list(bl.arguments().keys()), flush=True)
    except Exception as e:
        print(f"\n--- {method}: {str(e)[:90]}", flush=True)

for fs in ("global", "selected-zonelets", "selected-labels", "all"):
    try:
        bl.arguments.set_state({"face_scope": fs})
        print(f"\n--- after face_scope={fs} ---", flush=True)
        print("   ", bl.arguments(), flush=True)
    except Exception as e:
        print(f"\n--- face_scope {fs}: {str(e)[:90]}", flush=True)

m.exit()
print("PROBE26 DONE", flush=True)
