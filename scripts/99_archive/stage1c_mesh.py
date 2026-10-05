"""Stage 1c - FINAL meshing of the UAV external-flow domain.

Two-shell STL (outer box + reversed airframe) -> Watertight workflow.
Sequence was determined empirically; see the memory note for the pitfalls.
"""
import os, time, sys

os.environ.setdefault("PYFLUENT_SHOW_SERVER_GUI", "0")
from ansys.fluent.core import launch_fluent

BASE = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))   # <project root>
DOM = BASE + "/artifacts/geometry/fluid_domain.stl"
MSH = BASE + "/artifacts/mesh/aircraft_mesh.msh.h5"

MIN_SIZE = float(os.environ.get("MIN_SIZE", 0.10))
MAX_SIZE = float(os.environ.get("MAX_SIZE", 1.0))
GROWTH = float(os.environ.get("GROWTH", 1.2))
CURV = float(os.environ.get("CURV", 10.0))
BODY = float(os.environ.get("BODY", 0.35))     # target size on the airframe
N_LAYERS = int(os.environ.get("N_LAYERS", 8))
FIRST_H = float(os.environ.get("FIRST_H", 0.0003))
HEX_MAX = float(os.environ.get("HEX_MAX", 1.5))
NPROC = int(os.environ.get("NPROC", 4))

t0 = time.time()


def log(*a):
    print(f"[{time.time()-t0:7.1f}s]", *a, flush=True)


s = launch_fluent(mode="meshing", processor_count=NPROC, precision="double",
                  cwd=BASE + "/work")
log(f"meshing session launched ({NPROC} cores)")
wtm = s.watertight()
WFO = wtm._workflow.task_object
full = wtm.task_names()


def T(p, i=0):
    h = getattr(WFO, p)
    n = h.get_object_names()
    if not n:
        raise LookupError(p)
    return h[n[i] if isinstance(i, int) else i]


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
                log(f"   forced {p}/{dn}: {cur} -> Forced-up-to-date")
    except Exception as e:
        log(f"   force({p}) fail {e}")


def run(p, **kw):
    t = T(p)
    if kw:
        try:
            t.arguments.set_state(kw)
        except Exception as e:
            log(f"   set_state({p}) {type(e).__name__}; per-key")
            for k, v in kw.items():
                try:
                    setattr(t.arguments, k, v)
                except Exception as e2:
                    log(f"   !! {p}.{k}: {e2}")
    try:
        t.execute()
        log(f"   >>> {p} executed")
        return True
    except Exception as e:
        log(f"   !! {p} FAILED: {str(e)[:180]}")
        return False


# ---------------- 1. import ----------------
run("import_geometry", length_unit="m", file_format="Mesh", mesh_file_name=DOM)

# ---------------- 2. refinement on the airframe only ----------------
try:
    als = T("add_local_sizing_wtm")
    av = getattr(als.arguments, "boi_face_label_list").allowed_values()
    log(f"   labels: {av}")
    pick = [x for x in (av or []) if "aircraft" in str(x).lower()]
    if pick:
        als.arguments.set_state({"boi_execution": "Body Size", "boi_size": BODY,
                                 "boi_growth_rate": 1.15, "boi_control_name": "airframe",
                                 "boi_zoneor_label": "label",
                                 "boi_face_label_list": pick, "add_child": True})
        als.execute()
        log(f"   >>> local sizing (Body Size {BODY} m) on {pick}")
except Exception as e:
    log("   local sizing skipped:", e)

# ---------------- 3. surface mesh ----------------
run("create_surface_mesh", length_unit="m",
    cfd_surface_mesh_controls={"min_size": MIN_SIZE, "max_size": MAX_SIZE,
                               "growth_rate": GROWTH, "curvature_normal_angle": CURV,
                               "size_functions": "Curvature & Proximity",
                               "scope_proximity_to": "edges", "cells_per_gap": 1.0,
                               "use_size_files": "No", "draw_size_control": False})

# ---------------- 4. describe geometry + skip the failing share topology ----------------
SETUP = os.environ.get("SETUP", "fluid")
SHARE = os.environ.get("SHARE", "Yes")
run("describe_geometry", setup_type=SETUP, capping_required=False,
    invoke_share_topology=SHARE, wall_to_internal=False)
force("apply_share_topology")

try:
    T("create_regions").execute()
    log("   >>> create_regions executed")
except Exception as e:
    log(f"   create_regions: {str(e)[:120]}")
try:
    ur = T("update_regions")
    a = ur.arguments()
    log(f"   region names = {a.get('region_name_list')}")
    if a.get("region_name_list"):
        n = len(a["region_name_list"])
        ur.arguments.set_state({"region_type_list": ["fluid"] * n})
    ur.execute()
    log("   >>> update_regions executed")
except Exception as e:
    log(f"   update_regions: {str(e)[:120]}")

# ---------------- 5. boundary layers ----------------
bl = T("add_boundary_layers")
try:
    bl.arguments.set_state({
        "offset_method_type": "uniform",
        "number_of_layers": N_LAYERS,
        "rate": 1.2,
        "first_height": FIRST_H,
        "add_child": "yes",
        "local_prism_preferences": {"show_in_gui": False,
                                    "modify_at_invalid_normals": True,
                                    "ignore_boundary_layers": False,
                                    "additional_ignored_layers": 0}})
    bl.execute()
    log(f"   >>> boundary layers: {N_LAYERS} layers, first height {FIRST_H} m")
except Exception as e:
    log("   BL failed:", str(e)[:150])

# ---------------- 6. volume mesh ----------------
vm = T("create_volume_mesh_wtm")
try:
    vm.arguments.set_state({"volume_fill": "poly-hexcore"})
    fc = T("create_volume_mesh_wtm").arguments().get("volume_fill_controls") or {}
    fc["cell_sizing"] = "Geometric"
    fc["growth_rate"] = 1.2
    for k in ("hex_max_cell_length", "hex_min_cell_length"):
        if k in fc:
            fc[k] = HEX_MAX if "max" in k else MIN_SIZE
    log(f"   volume_fill_controls = {fc}")
    vm.arguments.set_state({"volume_fill_controls": fc,
                            "volume_mesh_preferences": {"quality_method": "Orthogonal",
                                                        "use_size_field": False,
                                                        "quality_warning_limit": 0.05,
                                                        "poly_feature_angle": 30.0,
                                                        "check_self_proximity": False,
                                                        "show_in_gui": False}})
    vm.execute()
    log("   >>> create_volume_mesh_wtm executed")
except Exception as e:
    log("   volume mesh FAILED:", str(e)[:200])

# ---------------- 7. report ----------------
log("=== boundary zones ===")
print(s.execute_tui("boundary/manage/list"), flush=True)

def tui(cmd):
    for m in (lambda: s.execute_tui(cmd),
              lambda: s.scheme_eval.string_eval(f'(ti-menu-load-string "{cmd}")')):
        try:
            return m()
        except Exception:
            continue


tui(f'file/write-mesh "{MSH}"')
log("mesh written:", os.path.exists(MSH), MSH)
s.exit()
log("DONE")
