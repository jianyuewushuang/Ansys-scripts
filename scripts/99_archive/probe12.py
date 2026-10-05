"""Probe 12: force-skip the failing Apply Share Topology task, then mesh."""
import os, time
os.environ.setdefault("PYFLUENT_SHOW_SERVER_GUI", "0")
from ansys.fluent.core import launch_fluent

BASE = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))   # <project root>
DOM = BASE + "/artifacts/geometry/fluid_domain.stl"
s = launch_fluent(mode="meshing", processor_count=2, precision="double", cwd=BASE + "/work")
print("LAUNCH OK", flush=True)
wtm = s.watertight()
WFO = wtm._workflow.task_object


def names():
    return [getattr(c, "_name", "?") for c in wtm.children()]


def T(p, i=0):
    h = getattr(WFO, p)
    n = h.get_object_names()
    return h[n[i]]


def force_updated(p):
    """Mark a task Forced-up-to-date so downstream tasks stop waiting on it."""
    try:
        t = T(p)
        st = getattr(t, "state", None)
        if st is None:
            return False
        allowed = st.allowed_values() if hasattr(st, "allowed_values") else []
        print(f"   [{p}] state={st()} allowed={allowed}")
        if "Forced-up-to-date" in allowed:
            st.set_state("Forced-up-to-date")
            print(f"   [{p}] -> Forced-up-to-date")
            return True
    except Exception as e:
        print(f"   [{p}] force fail {type(e).__name__} {e}")
    return False


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
print("describe_geometry executed; chain =", names(), flush=True)

# force-skip anything share-topology related
for n in names():
    if "share" in n.lower():
        force_updated(n)

try:
    T("update_regions").execute()
    print("update_regions OK", flush=True)
except Exception as e:
    print("update_regions FAIL:", str(e)[:200], flush=True)
    for n in names():
        if "share" in n.lower():
            force_updated(n)
    try:
        T("update_regions").execute()
        print("update_regions OK (retry)", flush=True)
    except Exception as e2:
        print("update_regions FAIL again:", str(e2)[:200])

bl = T("add_boundary_layers")
try:
    bl.arguments.set_state({"offset_method_type": "uniform", "number_of_layers": 8,
                            "rate": 1.2, "first_height": 0.0003, "add_child": "yes"})
    bl.execute()
    print("BL done", flush=True)
except Exception as e:
    print("BL fail", e)

vm = T("create_volume_mesh_wtm")
try:
    vm.arguments.set_state({"volume_fill": "poly-hexcore"})
    vm.execute()
    print("volume mesh done", flush=True)
except Exception as e:
    print("volume mesh FAIL:", str(e)[:300], flush=True)

print("\nzones:\n", s.execute_tui("boundary/manage/list"))
s.exit()
print("DONE")
