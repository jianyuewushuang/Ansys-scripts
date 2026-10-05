"""Probe 16: use non_conformal=True instead of share topology."""
import os
os.environ.setdefault("PYFLUENT_SHOW_SERVER_GUI", "0")
from ansys.fluent.core import launch_fluent

BASE = r"C:/Users/jianyuewushuang/document/model/ansys/UAVdesign20261004"
DOM = BASE + "/fluid_domain.stl"
s = launch_fluent(mode="meshing", processor_count=2, precision="double", cwd=BASE + "/mesh_work")
print("LAUNCH OK", flush=True)
wtm = s.watertight()
WFO = wtm._workflow.task_object


def T(p, i=0):
    h = getattr(WFO, p)
    n = h.get_object_names()
    return h[n[i]]


ig = T("import_geometry")
ig.arguments.set_state({"length_unit": "m", "file_format": "Mesh", "mesh_file_name": DOM})
ig.execute()

als = T("add_local_sizing_wtm")
als.arguments.set_state({"boi_execution": "Body Size", "boi_size": 0.35,
                         "boi_growth_rate": 1.15, "boi_control_name": "airframe",
                         "boi_zoneor_label": "label",
                         "boi_face_label_list": ["aircraft"], "add_child": True})
als.execute()

T("create_surface_mesh").arguments.set_state({
    "length_unit": "m",
    "cfd_surface_mesh_controls": {"min_size": 0.12, "max_size": 2.0, "growth_rate": 1.2,
                                  "curvature_normal_angle": 12.0,
                                  "size_functions": "Curvature & Proximity",
                                  "scope_proximity_to": "edges", "cells_per_gap": 1.0,
                                  "use_size_files": "No"}})
T("create_surface_mesh").execute()
print("surface mesh done", flush=True)

dg = T("describe_geometry")
dg.arguments.set_state({"setup_type": "fluid", "capping_required": False,
                        "invoke_share_topology": "No", "non_conformal": True,
                        "wall_to_internal": False})
try:
    dg.execute()
    print(">>> describe_geometry OK (non_conformal)", flush=True)
    print("    args:", T("describe_geometry").arguments())
except Exception as e:
    print("describe FAIL", str(e)[:200], flush=True)

for p in ("create_regions", "update_regions"):
    try:
        T(p).execute()
        print(f">>> {p} executed", flush=True)
    except Exception as e:
        print(f"{p} FAIL {str(e)[:150]}", flush=True)

a = T("update_regions").arguments()
print("\nregion names:", a.get("region_name_list"), "| types:", a.get("region_type_list"))

bl = T("add_boundary_layers")
bl.arguments.set_state({"offset_method_type": "uniform", "number_of_layers": 8,
                        "rate": 1.2, "first_height": 0.0003, "add_child": "yes",
                        "local_prism_preferences": {"show_in_gui": False,
                                                    "modify_at_invalid_normals": True,
                                                    "ignore_boundary_layers": False,
                                                    "additional_ignored_layers": 0}})
try:
    bl.execute()
    print(">>> BL executed", flush=True)
except Exception as e:
    print("BL FAIL", str(e)[:150])

vm = T("create_volume_mesh_wtm")
vm.arguments.set_state({"volume_fill": "poly-hexcore"})
try:
    vm.execute()
    print(">>> volume mesh executed", flush=True)
except Exception as e:
    print("volume FAIL", str(e)[:200], flush=True)

print("\nzones:\n", s.execute_tui("boundary/manage/list"))
s.exit()
print("DONE")
