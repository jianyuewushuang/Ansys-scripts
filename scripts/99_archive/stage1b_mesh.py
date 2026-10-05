"""Stage 1b - mesh the self-built fluid domain with the Watertight Geometry workflow."""
import os, time, sys

os.environ.setdefault("PYFLUENT_SHOW_SERVER_GUI", "0")
from ansys.fluent.core import launch_fluent

BASE = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))   # <project root>
DOM = BASE + "/artifacts/geometry/fluid_domain.stl"
MSH = BASE + "/artifacts/mesh/aircraft_mesh.msh.h5"

MIN_SIZE = float(os.environ.get("MIN_SIZE", 0.12))
MAX_SIZE = float(os.environ.get("MAX_SIZE", 2.0))
GROWTH = float(os.environ.get("GROWTH", 1.2))
CURV = float(os.environ.get("CURV", 12.0))
N_LAYERS = int(os.environ.get("N_LAYERS", 8))
FIRST_H = float(os.environ.get("FIRST_H", 0.0003))

t0 = time.time()


def log(*a):
    print(f"[{time.time()-t0:7.1f}s]", *a, flush=True)


s = launch_fluent(mode="meshing", processor_count=4, precision="double", cwd=BASE + "/work")
log("meshing session launched")
wtm = s.watertight()
WFO = wtm._workflow.task_object


def names():
    return [getattr(c, "_name", "?") for c in wtm.children()]


def T(p, i=0):
    h = getattr(WFO, p)
    n = h.get_object_names()
    if not n:
        raise LookupError(p)
    return h[n[i] if isinstance(i, int) else i]


def dump(p):
    try:
        t = T(p)
        log(f"---- {p} [{t.state()}]")
        for k, v in t.arguments().items():
            av = ""
            try:
                sub = getattr(t.arguments, k)
                if hasattr(sub, "allowed_values"):
                    a = sub.allowed_values()
                    if a:
                        av = f"   ALLOWED={a}"
            except Exception:
                pass
            log(f"     {k:30s} = {v!r}{av}")
    except Exception as e:
        log(f"---- {p} unavailable: {type(e).__name__} {e}")


def run(p, exec_after=True, **kw):
    t = T(p)
    if kw:
        try:
            t.arguments.set_state(kw)
            log(f"   set {p} -> ok")
        except Exception as e:
            log(f"   set_state failed ({type(e).__name__}); per-key")
            for k, v in kw.items():
                try:
                    setattr(t.arguments, k, v)
                except Exception as e2:
                    log(f"   !! {p}.{k}: {e2}")
    if not exec_after:
        return t
    try:
        t.execute()
        log(f"   >>> {p} executed")
    except Exception as e:
        log(f"   !! {p} FAILED: {type(e).__name__} {e}")
    return t


def tui(cmd):
    for m in (lambda: s.execute_tui(cmd),
              lambda: s.scheme_eval.string_eval(f'(ti-menu-load-string "{cmd}")')):
        try:
            return m()
        except Exception:
            continue


log("chain: " + str(names()))

# ---------- import ----------
ig = T("import_geometry")
ig.arguments.set_state({"length_unit": "m", "file_format": "Mesh",
                        "import_type": "Single File"})
avail = ig.arguments()
log("   import_geometry available keys: " + str(list(avail.keys())))
for key in ("file_names", "file_name", "mesh_file_name", "filename"):
    if key in avail:
        val = [DOM] if key.endswith("names") else DOM
        try:
            ig.arguments.set_state({key: val})
            log(f"   set {key} = {val}")
        except Exception as e:
            log(f"   !! {key}: {e}")
        break
try:
    a = T("import_geometry").arguments()
    log(f"   verify: file_names={a.get('file_names')} file_name={a.get('file_name')} "
        f"format={a.get('file_format')} unit={a.get('length_unit')}")
except Exception as e:
    log("   verify fail", e)
try:
    ig.execute()
    log("   >>> import_geometry executed")
except Exception as e:
    log("   !! import_geometry FAILED:", type(e).__name__, e)

# ---------- optional local sizing on the airframe (Body Size) ----------
try:
    als = T("add_local_sizing_wtm")
    lbl_ok = False
    try:
        av = getattr(als.arguments, "boi_face_label_list").allowed_values()
        log("   labels allowed: " + str(av))
        lbl_ok = bool(av)
    except Exception as e:
        log("   labels: " + str(e))
    if not lbl_ok:
        raise RuntimeError("no labels -> single solid, using global sizing only")
    als.arguments.set_state({"boi_execution": "Body Size",
                             "boi_size": 0.35,
                             "boi_growth_rate": 1.15,
                             "boi_control_name": "airframe_body",
                             "add_child": True,
                             "boi_zoneor_label": "label"})
    try:
        lbl = getattr(als.arguments, "boi_face_label_list")
        av = lbl.allowed_values()
        log("   label list allowed:", av)
        pick = [x for x in (av or []) if "aircraft" in str(x).lower()] or (av or [])
        if pick:
            als.arguments.set_state({"boi_face_label_list": pick})
            log(f"   labels = {pick}")
    except Exception as e:
        log("   label selection:", e)
    als.execute()
    log("   >>> add_local_sizing_wtm executed")
except Exception as e:
    log("   local sizing skipped:", type(e).__name__, e)

# ---------- surface mesh ----------
run("create_surface_mesh",
    length_unit="m",
    share_topology_preferences={"rename_internals_by_body_names": True,
                                "share_topology_angle": 40.0,
                                "join_tolerance_increment": 0.05,
                                "relative_share_topology_tolerance": 0.1,
                                "show_in_gui": False,
                                "operation": "Join-Intersect",
                                "execute_join_intersect": "Join Only",
                                "number_of_join_tries": 3},
    cfd_surface_mesh_controls={"min_size": MIN_SIZE,
                               "max_size": MAX_SIZE,
                               "growth_rate": GROWTH,
                               "curvature_normal_angle": CURV,
                               "size_functions": "Curvature & Proximity",
                               "scope_proximity_to": "edges",
                               "cells_per_gap": 1.0,
                               "use_size_files": "No",
                               "draw_size_control": False})

# ---------- describe geometry ----------
# Empirically (probe11) the only combination that succeeds for the two nested
# shells (outer box + inverted airframe) is:
#     setup_type = 'fluid_solid_voids',  invoke_share_topology = 'No'
# 'fluid' + 'No' -> "Either share topology needs to be applied, or non-conformal meshing"
# 'fluid' + 'Yes'-> "Apply Share Topology ... Intersect operation was not successful"
SETUP = os.environ.get("SETUP", "fluid")
SHARE = os.environ.get("SHARE", "No")
run("describe_geometry", setup_type=SETUP, capping_required=False,
    invoke_share_topology=SHARE, wall_to_internal=False)

# ---------- regions ----------
dump("update_regions")
try:
    T("update_regions").execute()
    log("   >>> update_regions executed")
except Exception as e:
    log("   update_regions:", e)

# ---------- boundary layers ----------
bl = T("add_boundary_layers")
try:
    bl.arguments.set_state({"offset_method_type": "uniform"})
    a = T("add_boundary_layers").arguments()
    log("   uniform mode keys: " + str(list(a.keys())))
    patch = {"number_of_layers": N_LAYERS, "rate": 1.2, "add_child": "yes"}
    if "first_height" in a:
        patch["first_height"] = FIRST_H
    bl.arguments.set_state(patch)
    log(f"   BL patch = {patch}")
    bl.execute()
    log("   >>> add_boundary_layers executed")
except Exception as e:
    log("   BL failed:", type(e).__name__, e)
    try:
        bl.arguments.set_state({"offset_method_type": "smooth-transition",
                                "number_of_layers": N_LAYERS,
                                "transition_ratio": 0.272,
                                "add_child": "yes"})
        bl.execute()
        log("   >>> add_boundary_layers executed (smooth-transition)")
    except Exception as e2:
        log("   BL fallback failed:", e2)

# ---------- volume mesh ----------
vm = T("create_volume_mesh_wtm")
try:
    vm.arguments.set_state({"volume_fill": "poly-hexcore"})
    log("   poly-hexcore keys: " + str(list(T("create_volume_mesh_wtm").arguments().keys())))
    log("   fill controls: " + str(T("create_volume_mesh_wtm").arguments().get("volume_fill_controls")))
except Exception as e:
    log("   volume_fill set:", e)

try:
    fc = T("create_volume_mesh_wtm").arguments().get("volume_fill_controls") or {}
    fc.update({"cell_sizing": "Geometric", "growth_rate": 1.2})
    for k in ("hex_max_cell_length", "polyhedral_max_cell_length", "tet_poly_max_cell_length"):
        if k in fc:
            fc[k] = MAX_SIZE
    log(f"   volume_fill_controls -> {fc}")
    vm.arguments.set_state({"volume_fill_controls": fc,
                            "volume_mesh_preferences": {"quality_method": "Orthogonal",
                                                        "use_size_field": False,
                                                        "quality_warning_limit": 0.05,
                                                        "poly_feature_angle": 30.0,
                                                        "check_self_proximity": False,
                                                        "show_in_gui": False}})
except Exception as e:
    log("   vc setup:", e)

try:
    vm.execute()
    log("   >>> create_volume_mesh_wtm executed")
except Exception as e:
    log("   !! volume mesh FAILED:", type(e).__name__, e)

# ---------- report + write ----------
log("=== boundary zones ===")
print(tui("boundary/manage/list"), flush=True)
log("=== mesh size ===")
print(tui("mesh/size-info"), flush=True)

for cmd in (f'file/write-mesh "{MSH}"',):
    tui(cmd)
log("mesh file exists:", os.path.exists(MSH))
s.exit()
log("DONE")
