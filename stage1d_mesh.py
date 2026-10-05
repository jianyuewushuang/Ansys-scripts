"""Stage 1d - mesh the single closed shell (box + airframe cavity) with the
Watertight workflow, using non_conformal=True (the alternative to share topology)."""
import os, time, sys

os.environ.setdefault("PYFLUENT_SHOW_SERVER_GUI", "0")
from ansys.fluent.core import launch_fluent

BASE = r"C:/Users/jianyuewushuang/document/model/ansys/UAVdesign20261004"
DOM = BASE + "/fluid_domain.stl"
MSH = BASE + "/aircraft_mesh.msh.h5"

MIN_SIZE = float(os.environ.get("MIN_SIZE", 0.12))
MAX_SIZE = float(os.environ.get("MAX_SIZE", 1.5))
GROWTH = float(os.environ.get("GROWTH", 1.2))
CURV = float(os.environ.get("CURV", 10.0))
N_LAYERS = int(os.environ.get("N_LAYERS", 8))
FIRST_H = float(os.environ.get("FIRST_H", 0.0003))
HEX_MAX = float(os.environ.get("HEX_MAX", 2.0))
NPROC = int(os.environ.get("NPROC", 4))

t0 = time.time()


def log(*a):
    print(f"[{time.time()-t0:7.1f}s]", *a, flush=True)


s = launch_fluent(mode="meshing", processor_count=NPROC, precision="double",
                  cwd=BASE + "/mesh_work")
log(f"meshing session launched ({NPROC} cores)")
wtm = s.watertight()
WFO = wtm._workflow.task_object


def T(p, i=0):
    h = getattr(WFO, p)
    n = h.get_object_names()
    if not n:
        raise LookupError(p)
    return h[n[i]]


def run(p, **kw):
    t = T(p)
    if kw:
        try:
            t.arguments.set_state(kw)
        except Exception as e:
            log(f"   set_state({p}) fail {type(e).__name__}")
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
        log(f"   !! {p} FAILED: {str(e)[:200]}")
        return False


run("import_geometry", length_unit="m", file_format="Mesh", mesh_file_name=DOM)

# optional airframe refinement if labels exist (single shell -> usually none)
try:
    als = T("add_local_sizing_wtm")
    av = getattr(als.arguments, "boi_face_label_list").allowed_values()
    log(f"   labels: {av}")
except Exception as e:
    log("   labels n/a:", e)

run("create_surface_mesh", length_unit="m",
    cfd_surface_mesh_controls={"min_size": MIN_SIZE, "max_size": MAX_SIZE,
                               "growth_rate": GROWTH, "curvature_normal_angle": CURV,
                               "size_functions": "Curvature & Proximity",
                               "scope_proximity_to": "edges", "cells_per_gap": 1.0,
                               "use_size_files": "No", "draw_size_control": False},
    surface_mesh_preferences={"thin_volume_meshing_auto_control_creation": False,
                              "remove_steps": False,
                              "quality_improve_skewness_limit": 0.8,
                              "quality_improve_collapase_skewness_limit": 0.95,
                              "quality_improve_max_angle": 80.0,
                              "auto_surface_remesh": "auto", "improve_quality": True,
                              "show_in_gui": False, "fold_face_limit": 10.0,
                              "auto_assign_zone_types": True,
                              "self_intersect_check": False,
                              "parallel_region_compute": "no"})

SETUP = os.environ.get("SETUP", "fluid")
SHARE = os.environ.get("SHARE", "Yes")
NONCONF = os.environ.get("NONCONF", "0") == "1"
kw = dict(setup_type=SETUP, capping_required=False,
          invoke_share_topology=SHARE, wall_to_internal=False)
if NONCONF:
    kw["non_conformal"] = True
run("describe_geometry", **kw)

# this is the step whose failure blocks the volume mesh; skip it if needed
def force(p):
    try:
        h = getattr(WFO, p)
        for dn in h.get_object_names():
            t = h[dn]
            st = getattr(t, "state", None)
            if st is None:
                continue
            try:
                allowed = st.allowed_values(); cur = st()
            except Exception:
                continue
            if cur not in ("Up-to-date", "Forced-up-to-date") and "Forced-up-to-date" in allowed:
                st.set_state("Forced-up-to-date")
                log(f"   forced {p}/{dn}: {cur} -> Forced-up-to-date")
    except Exception as e:
        log(f"   force({p}) {e}")


force("apply_share_topology")

for p in ("create_regions", "update_regions"):
    try:
        T(p).execute()
        log(f"   >>> {p} executed")
    except Exception as e:
        log(f"   {p}: {str(e)[:150]}")

bl = T("add_boundary_layers")
try:
    bl.arguments.set_state({"offset_method_type": "uniform", "number_of_layers": N_LAYERS,
                            "rate": 1.2, "first_height": FIRST_H, "add_child": "yes",
                            "local_prism_preferences": {"show_in_gui": False,
                                                        "modify_at_invalid_normals": True,
                                                        "ignore_boundary_layers": False,
                                                        "additional_ignored_layers": 0}})
    bl.execute()
    log(f"   >>> boundary layers ({N_LAYERS} layers, h0={FIRST_H} m)")
except Exception as e:
    log("   BL failed:", str(e)[:180])

vm = T("create_volume_mesh_wtm")
try:
    vm.arguments.set_state({"volume_fill": "poly-hexcore"})
    fc = T("create_volume_mesh_wtm").arguments().get("volume_fill_controls") or {}
    fc["cell_sizing"] = "Geometric"; fc["growth_rate"] = 1.2
    for k in ("hex_max_cell_length", "hex_min_cell_length"):
        if k in fc:
            fc[k] = HEX_MAX if "max" in k else MIN_SIZE
    log(f"   volume_fill_controls = {fc}")
    vm.arguments.set_state({"volume_fill_controls": fc})
    vm.execute()
    log("   >>> create_volume_mesh_wtm executed")
except Exception as e:
    log("   volume mesh FAILED:", str(e)[:220])

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
log("mesh written:", os.path.exists(MSH))
s.exit()
log("DONE")
