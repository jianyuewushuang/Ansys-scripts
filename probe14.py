"""Probe 14: run create_regions, then set region types in update_regions."""
import os
os.environ.setdefault("PYFLUENT_SHOW_SERVER_GUI", "0")
from ansys.fluent.core import launch_fluent

BASE = r"C:/Users/jianyuewushuang/document/model/ansys/UAVdesign20261004"
DOM = BASE + "/fluid_domain.stl"
s = launch_fluent(mode="meshing", processor_count=2, precision="double", cwd=BASE + "/mesh_work")
print("LAUNCH OK", flush=True)
wtm = s.watertight()
WFO = wtm._workflow.task_object
full = wtm.task_names()


def T(p, i=0):
    h = getattr(WFO, p)
    n = h.get_object_names()
    return h[n[i]]


def state_of(p):
    try:
        return T(p).state()
    except Exception as e:
        return f"<{type(e).__name__}>"


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
                cur = st()
            except Exception:
                continue
            if cur not in ("Up-to-date", "Forced-up-to-date") and "Forced-up-to-date" in allowed:
                st.set_state("Forced-up-to-date")
                print(f"   forced {p}/{dn}: {cur} -> Forced-up-to-date")
    except Exception as e:
        print("   force fail", p, e)


def dump(p):
    try:
        print(f"\n--- {p} [{state_of(p)}] ---")
        for k, v in T(p).arguments().items():
            print(f"   {k:28s} = {v!r}")
    except Exception as e:
        print(f"--- {p} fail {e}")


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
                        "invoke_share_topology": "Yes", "wall_to_internal": False})
dg.execute()
print("describe_geometry done", flush=True)
force("apply_share_topology")

# --- create regions (computes the region list) ---
for p in ("create_regions",):
    try:
        T(p).execute()
        print(f"{p} executed", flush=True)
    except Exception as e:
        print(f"{p} FAIL {str(e)[:160]}", flush=True)

dump("update_regions")
ur = T("update_regions")
a = ur.arguments()
names_ = a.get("region_name_list")
types_ = a.get("region_type_list")
print("\nregion names:", names_, "\nregion types:", types_)

if names_:
    try:
        print("allowed region types:",
              getattr(ur.arguments, "region_type_list").allowed_values())
    except Exception as e:
        print("types allowed fail", e)
    # mark everything fluid: the mesher fills fluid, dead/void stays empty
    new = []
    for n in names_:
        new.append("fluid" if str(n).startswith("fluid") else "fluid")
    try:
        ur.arguments.set_state({"region_type_list": new})
        print("set region_type_list =", new)
    except Exception as e:
        print("set types fail", e)
    try:
        ur.execute()
        print("update_regions executed", flush=True)
    except Exception as e:
        print("update_regions FAIL", str(e)[:200], flush=True)
else:
    print("!! region list still empty - cannot type regions")

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
s.exit()
print("DONE")
