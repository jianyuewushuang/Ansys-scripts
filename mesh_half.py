"""Mesh the HALF-model fluid domain (genus-0, airframe on the symmetry plane)."""
import os, time, sys

os.environ.setdefault("PYFLUENT_SHOW_SERVER_GUI", "0")
from ansys.fluent.core import launch_fluent

BASE = r"C:/Users/jianyuewushuang/document/model/ansys/UAVdesign20261004"
DOM = os.environ.get("DOM", BASE + "/half_domain.stl")
MSH = os.environ.get("MSH", BASE + "/half_mesh.msh.h5")

MIN_SIZE = float(os.environ.get("MIN_SIZE", 0.12))
MAX_SIZE = float(os.environ.get("MAX_SIZE", 2.0))
GROWTH = float(os.environ.get("GROWTH", 1.2))
CURV = float(os.environ.get("CURV", 12.0))
BODY = float(os.environ.get("BODY", 0.35))
N_LAYERS = int(os.environ.get("N_LAYERS", 8))
FIRST_H = float(os.environ.get("FIRST_H", 0.0005))
RATE = float(os.environ.get("RATE", 1.3))
HEX_MAX = float(os.environ.get("HEX_MAX", 2.0))
NPROC = int(os.environ.get("NPROC", 4))
JOIN = os.environ.get("JOIN", "Join Only")     # <- no boolean, only weld seams
SHARE = os.environ.get("SHARE", "Yes")

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
                return True
    except Exception as e:
        log(f"   force({p}) {e}")
    return False


def run(p, **kw):
    t = T(p)
    if kw:
        try:
            t.arguments.set_state(kw)
        except Exception as e:
            log(f"   set_state({p}) {type(e).__name__}")
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


def tui(cmd):
    for m in (lambda: s.execute_tui(cmd),
              lambda: s.scheme_eval.string_eval(f'(ti-menu-load-string "{cmd}")')):
        try:
            r = m()
            if r is not None:
                return r
        except Exception:
            continue


# ---------------- import ----------------
run("import_geometry", length_unit="m", file_format="Mesh", mesh_file_name=DOM)

# ---------------- refinement on the airframe ----------------
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
        log(f"   >>> local sizing Body Size {BODY} m on {pick}")
except Exception as e:
    log("   local sizing skipped:", str(e)[:150])

# ---------------- surface mesh (seams welded with Join Only) ----------------
run("create_surface_mesh", length_unit="m",
    share_topology_preferences={"rename_internals_by_body_names": True,
                                "share_topology_angle": 40.0,
                                "join_tolerance_increment": 0.05,
                                "relative_share_topology_tolerance": 0.1,
                                "show_in_gui": False,
                                "operation": "Join-Intersect",
                                "execute_join_intersect": JOIN,
                                "number_of_join_tries": 3},
    cfd_surface_mesh_controls={"min_size": MIN_SIZE, "max_size": MAX_SIZE,
                               "growth_rate": GROWTH, "curvature_normal_angle": CURV,
                               "size_functions": "Curvature & Proximity",
                               "scope_proximity_to": "edges", "cells_per_gap": 1.0,
                               "use_size_files": "No", "draw_size_control": False})

# ---------------- describe geometry ----------------
SETUP = os.environ.get("SETUP", "fluid")
kw = dict(setup_type=SETUP, capping_required=False,
          invoke_share_topology=SHARE, wall_to_internal=False)
if os.environ.get("NONCONF", "0") == "1":
    kw["non_conformal"] = True
run("describe_geometry", **kw)
# actually RUN the seam welding now (Join Only = weld, no boolean)
try:
    ast = T("apply_share_topology")
    try:
        stp = ast.arguments().get("share_topology_preferences") or {}
        stp["execute_join_intersect"] = JOIN
        stp["operation"] = "Join-Intersect"
        stp["number_of_join_tries"] = 3
        ast.arguments.set_state({"share_topology_preferences": stp})
    except Exception as e:
        log("   share prefs:", str(e)[:120])
    ast.execute()
    log("   >>> apply_share_topology executed (seams welded)")
except Exception as e:
    log("   apply_share_topology FAILED:", str(e)[:200])
    force("apply_share_topology")

for p in ("create_regions", "update_regions"):
    try:
        T(p).execute()
        log(f"   >>> {p} executed")
    except Exception as e:
        log(f"   {p}: {str(e)[:170]}")

# --- try to type the airframe region as SOLID so its interior is not meshed.
# That halves the prism count (prisms grow on both sides of the shared wall)
# and removes the need to delete the interior cell zone in the solver.
try:
    ur = T("update_regions")
    log("   update_regions args: " + str(list(ur.arguments().keys())))
    for k in ur.arguments():
        try:
            log(f"     {k} = {ur.arguments().get(k)}")
        except Exception:
            pass
except Exception as e:
    log("   update_regions dump:", str(e)[:120])

typed_solid = False
# `region_name_list` / `region_type_list` are the ONLY real keys here - the
# `all_*` variants are silently ignored (execute() then "succeeds" doing
# nothing), which is how earlier runs kept meshing the airframe interior.
for keys in ({"region_name_list": ["fluid_box", "aircraft"],
              "region_type_list": ["fluid", "solid"]},
             {"region_name_list": ["aircraft"],
              "region_type_list": ["solid"]}):
    try:
        ur = T("update_regions")
        st = dict(ur.arguments())
        st.update(keys)
        ur.arguments.set_state(st)
        ur.execute()
        log("   >>> airframe region typed as SOLID via " + str(list(keys)))
        typed_solid = True
        break
    except Exception as e:
        log("   region type try %s: %s" % (list(keys), str(e)[:110]))
if not typed_solid:
    log("   (airframe region stayed fluid - interior will be meshed)")

# ---------------- boundary layers ----------------
bl = T("add_boundary_layers")
# offset_method_type must be set FIRST - only then does `first_height` appear.
try:
    bl.arguments.set_state({"offset_method_type": "uniform"})
    bl.arguments.set_state({
        "offset_method_type": "uniform",
        "number_of_layers": N_LAYERS,
        "first_height": FIRST_H,
        "rate": RATE,
        "control_name": os.environ.get("BLNAME", "smooth-transition_1"),
        # 'yes' CREATES a second control while the default one still carries
        # ignore_boundary_layers=True, which globally switches prisms off.
        # 'no' edits the existing control in place.
        "add_child": os.environ.get("BLADD", "no"),
        "local_prism_preferences": {"show_in_gui": False,
                                    "modify_at_invalid_normals": True,
                                    # default is True -> prisms are silently skipped
                                    "ignore_boundary_layers": False,
                                    "additional_ignored_layers": 0}})
    log("   BL args: " + str(bl.arguments()))
    bl.execute()
    log(f"   >>> boundary layers ({N_LAYERS} layers, h0={FIRST_H} m, rate={RATE})")
except Exception as e:
    log("   BL failed:", str(e)[:200])

# ---------------- volume mesh ----------------
vm = T("create_volume_mesh_wtm")
try:
    vm.arguments.set_state({"volume_fill": os.environ.get("VOLFILL", "poly-hexcore")})
    fc = T("create_volume_mesh_wtm").arguments().get("volume_fill_controls") or {}
    fc["cell_sizing"] = "Geometric"; fc["growth_rate"] = 1.2
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
    log("   volume mesh FAILED:", str(e)[:220])

log("=== boundary zones ===")
print(tui("boundary/manage/list"), flush=True)
tui(f'file/write-mesh "{MSH}"')
log("mesh written:", os.path.exists(MSH))
s.exit()
log("DONE")
