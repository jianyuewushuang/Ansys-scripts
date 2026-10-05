"""Probe 11: find a working describe_geometry combination for the two-shell domain."""
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
ig.arguments.set_state({"length_unit": "m", "file_format": "Mesh",
                        "mesh_file_name": DOM})
ig.execute()
print("imported", flush=True)

sm = T("create_surface_mesh")
print("\nshare_topology_preferences:", sm.arguments().get("share_topology_preferences"))
for sub in ("operation", "execute_join_intersect"):
    try:
        print(f"  {sub} ALLOWED =",
              getattr(sm.arguments.share_topology_preferences, sub).allowed_values())
    except Exception as e:
        print("  ", sub, "fail", e)

als = T("add_local_sizing_wtm")
try:
    als.arguments.set_state({"boi_execution": "Body Size", "boi_size": 0.35,
                             "boi_growth_rate": 1.15, "boi_control_name": "airframe",
                             "boi_zoneor_label": "label",
                             "boi_face_label_list": ["aircraft"], "add_child": True})
    als.execute()
    print("local sizing on 'aircraft' applied", flush=True)
except Exception as e:
    print("local sizing fail", e)

sm.arguments.set_state({"length_unit": "m",
                        "cfd_surface_mesh_controls": {"min_size": 0.12, "max_size": 2.0,
                                                      "growth_rate": 1.2,
                                                      "curvature_normal_angle": 12.0,
                                                      "size_functions": "Curvature & Proximity",
                                                      "scope_proximity_to": "edges",
                                                      "cells_per_gap": 1.0,
                                                      "use_size_files": "No"}})
sm.execute()
print("surface mesh done", flush=True)

dg = T("describe_geometry")
for setup in ("fluid", "fluid_solid_voids", "solid"):
    for share in ("No", "Yes"):
        try:
            dg.arguments.set_state({"setup_type": setup,
                                    "capping_required": False,
                                    "invoke_share_topology": share,
                                    "wall_to_internal": False})
            dg.execute()
            st = dg.state()
            print(f"\nRESULT setup_type={setup:20s} share={share:4s} -> EXECUTED, state={st}", flush=True)
            ur = T("update_regions")
            try:
                ur.execute()
                a = ur.arguments()
                print("   update_regions OK:", a.get("region_name_list"), a.get("region_type_list"))
            except Exception as e:
                print("   update_regions fail:", str(e)[:160])
        except Exception as e:
            print(f"\nRESULT setup_type={setup:20s} share={share:4s} -> FAIL: {str(e)[:120]}", flush=True)

s.exit()
print("\nDONE")
