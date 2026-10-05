"""Probe 13: locate the pending Apply-Share-Topology task in the FULL task list and force it."""
import os
os.environ.setdefault("PYFLUENT_SHOW_SERVER_GUI", "0")
from ansys.fluent.core import launch_fluent

BASE = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))   # <project root>
DOM = BASE + "/artifacts/geometry/fluid_domain.stl"          # two-shell version
s = launch_fluent(mode="meshing", processor_count=2, precision="double", cwd=BASE + "/work")
print("LAUNCH OK", flush=True)
wtm = s.watertight()
WFO = wtm._workflow.task_object

print("\nFULL task_names():")
full = wtm.task_names()
print("  ", full)


def T(p, i=0):
    h = getattr(WFO, p)
    n = h.get_object_names()
    return h[n[i]]


def force(p):
    try:
        h = getattr(WFO, p)
        for dn in h.get_object_names():
            t = h[dn]
            st = getattr(t, "state", None)
            if st is None:
                continue
            try:
                allowed = st.allowed_values()
            except Exception:
                allowed = []
            cur = st()
            print(f"   [{p}/{dn}] state={cur} allowed={allowed}")
            if cur not in ("Up-to-date", "Forced-up-to-date") and "Forced-up-to-date" in allowed:
                st.set_state("Forced-up-to-date")
                print(f"      -> forced up-to-date")
    except Exception as e:
        print(f"   [{p}] fail {type(e).__name__} {e}")


ig = T("import_geometry")
ig.arguments.set_state({"length_unit": "m", "file_format": "Mesh", "mesh_file_name": DOM})
ig.execute()
print("imported", flush=True)

als = T("add_local_sizing_wtm")
als.arguments.set_state({"boi_execution": "Body Size", "boi_size": 0.35,
                         "boi_growth_rate": 1.15, "boi_control_name": "airframe",
                         "boi_zoneor_label": "label",
                         "boi_face_label_list": ["aircraft"], "add_child": True})
als.execute()
print("local sizing applied", flush=True)

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
                        "invoke_share_topology": "Yes", "wall_to_internal": False})
dg.execute()
print("describe_geometry executed", flush=True)

print("\n--- forcing any share-topology / pending task ---")
for p in full:
    if "share" in p.lower() or "topolog" in p.lower():
        force(p)

for step in ("update_regions",):
    try:
        T(step).execute()
        print(f"{step} OK", flush=True)
    except Exception as e:
        print(f"{step} FAIL {str(e)[:150]}", flush=True)
        print("  forcing again...")
        for p in full:
            force(p)
        try:
            T(step).execute()
            print(f"{step} OK (retry)", flush=True)
        except Exception as e2:
            print(f"{step} FAIL again {str(e2)[:150]}", flush=True)

bl = T("add_boundary_layers")
bl.arguments.set_state({"offset_method_type": "uniform", "number_of_layers": 8,
                        "rate": 1.2, "first_height": 0.0003, "add_child": "yes"})
try:
    bl.execute()
    print("BL done", flush=True)
except Exception as e:
    print("BL fail", str(e)[:150])

vm = T("create_volume_mesh_wtm")
vm.arguments.set_state({"volume_fill": "poly-hexcore"})
try:
    vm.execute()
    print("volume mesh done", flush=True)
except Exception as e:
    print("volume mesh FAIL", str(e)[:200], flush=True)

print("\nzones:\n", s.execute_tui("boundary/manage/list"))
print("\nsize:\n", s.execute_tui("mesh/size-info"))
s.exit()
print("DONE")
