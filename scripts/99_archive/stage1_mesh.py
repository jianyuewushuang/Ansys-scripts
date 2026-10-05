"""Stage 1 v3 - external-flow mesh for the UAV (ANSYS Student <512k cells).

Fixes over v2:
  * material point coordinates go into `graphical_selection` (Numerical Inputs mode)
  * after adding a size-control child, the wrapper's global task lookup raises
    "Item not found </TaskObject:curvature-1>", so ALL tasks are addressed through
    the raw datamodel (`ftm._workflow.task_object.<type>[<display name>]`) instead.
"""
import os, time, sys

os.environ.setdefault("PYFLUENT_SHOW_SERVER_GUI", "0")
from ansys.fluent.core import launch_fluent

BASE = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))   # <project root>
MSH = BASE + "/artifacts/mesh/aircraft_mesh.msh.h5"

MIN_SIZE = float(os.environ.get("MIN_SIZE", 0.15))
MAX_SIZE = float(os.environ.get("MAX_SIZE", 2.0))
GROWTH = float(os.environ.get("GROWTH", 1.2))
N_LAYERS = int(os.environ.get("N_LAYERS", 8))
FIRST_H = float(os.environ.get("FIRST_H", 0.0003))
XMIN_R, XMAX_R = 1.5, 2.5
Y_R, Z_R = 1.0, 6.0

t0 = time.time()


def log(*a):
    print(f"[{time.time()-t0:7.1f}s]", *a, flush=True)


s = None
for attempt in (4, 2):
    try:
        s = launch_fluent(mode="meshing", processor_count=attempt, precision="double",
                          cwd=BASE + "/work")
        log(f"meshing session launched with {attempt} cores")
        break
    except Exception as e:
        log(f"launch with {attempt} cores failed: {type(e).__name__} {e}")
if s is None:
    sys.exit(1)

ftm = s.fault_tolerant()
WFO = ftm._workflow.task_object          # raw datamodel container


def T(pyname, idx=0):
    """Raw task PyMenu for a task type, bypassing the broken global state lookup."""
    holder = getattr(WFO, pyname)
    names = holder.get_object_names()
    if not names:
        raise LookupError(f"no instance for {pyname}")
    key = names[idx] if isinstance(idx, int) else idx
    return holder[key]


def show(pyname):
    t = T(pyname)
    try:
        log(f"   [{pyname}] state={t.state()}")
    except Exception:
        pass
    try:
        for k, v in t.arguments().items():
            log(f"      {k:32s} = {v!r}")
    except Exception as e:
        log(f"      args fail {type(e).__name__} {e}")
    return t


def run(pyname, exec_after=True, **kw):
    t = T(pyname)
    try:
        cur = t.arguments()
    except Exception:
        cur = {}
    patch = {}
    for k, v in kw.items():
        patch[k] = v
        log(f"   set {pyname}.{k} = {v}")
    if patch:
        try:
            t.arguments.set_state(patch)
        except Exception as e:
            log(f"   set_state failed ({type(e).__name__}); setting individually")
            for k, v in patch.items():
                try:
                    setattr(t.arguments, k, v)
                except Exception as e2:
                    log(f"   !! cannot set {k}: {e2}")
    if not exec_after:
        return t
    try:
        t.execute()
        log(f"   >>> {pyname} executed")
    except Exception as e:
        log(f"   !! {pyname} FAILED: {type(e).__name__} {e}")
    return t


def safe_exec(pyname):
    try:
        T(pyname).execute()
        log(f"   >>> {pyname} executed")
        return True
    except Exception as e:
        log(f"   !! {pyname} failed: {type(e).__name__} {e}")
        return False


# ---------------- 1. import ----------------
run("import_cad_and_part_management",
    fmd_file_name=BASE + "/data/1.stl", length_unit="m",
    create_object_per="One per part", route="Native")

# ---------------- 2. describe ----------------
run("describe_geometry_and_flow",
    flow_type="External flow around object", add_enclosure=True)

# ---------------- 3. tunnel ----------------
run("create_external_flow_boundaries",
    creation_method="Create new boundary",
    selection_type="object",
    object_selection_list=["object1"],
    extraction_method="surface mesh",
    external_boundaries_name="tunnel",
    bounding_box_object={"size_relative_length": "Ratio relative to geometry size",
                         "xmin_ratio": XMIN_R, "xmax_ratio": XMAX_R,
                         "ymin_ratio": Y_R, "ymax_ratio": Y_R,
                         "zmin_ratio": Z_R, "zmax_ratio": Z_R})

# ---------------- 4. fluid region (explicit material point) ----------------
# NOTE: mpt_method_type selects which extra arguments exist:
#   'Centroid of Objects' -> object_selection_list      (centroid may land inside the aircraft)
#   'Numerical Inputs'    -> graphical_selection (bool)  <- graphical picking only, NOT coordinates
#   'Offset Method'       -> object_selection_list + offset_x/offset_y/offset_z   <-- use this
ir = T("identify_regions")
ir.arguments.set_state({"new_region_type": "fluid",
                        "selection_type": "object",
                        "mpt_method_type": "Offset Method",
                        "object_selection_list": ["tunnel"],
                        "offset_x": 15.0,     # shift clear of the tail (tail tip at x=24.04)
                        "offset_y": 0.0,
                        "offset_z": 5.0})
log("   material point = centroid(tunnel) + [15, 0, 5]  -> in the fluid, clear of the airframe")
try:
    a = T("identify_regions").arguments()
    log("   verify: " + ", ".join(f"{k}={a[k]}" for k in
                                  ("mpt_method_type", "object_selection_list", "offset_x", "offset_z")))
except Exception as e:
    log("   verify fail:", e)
safe_exec("identify_regions")

# ---------------- 5. size controls ----------------
run("setup_size_controls", exec_after=True,
    object_selection_list=["object1", "tunnel"],
    local_size_control_parameters={
        "sizing_type": "curvature",
        "curvature_normal_angle": 18.0,
        "min_size": MIN_SIZE,
        "max_size": MAX_SIZE,
        "growth_rate": GROWTH,
        "scope_proximity_to": "faces-and-edges",
        "initial_size_control": False,
        "target_size_control": False,
    })
log(f"   size control configured: min={MIN_SIZE} max={MAX_SIZE} growth={GROWTH}")

# ---------------- 6.. ----------------
safe_exec("choose_mesh_control_options")
for n in ("compute_size_fields",):
    if safe_exec(n) is False:
        log("   (continuing without size field)")
safe_exec("generate_surface_mesh")
safe_exec("compute_regions")
safe_exec("update_boundaries")

# ---------------- boundary layers ----------------
show("add_boundary_layers")
bl = T("add_boundary_layers")
try:
    bl.arguments.set_state({"offset_method_type": "uniform"})
    log("   uniform mode args:", list(T("add_boundary_layers").arguments().keys()))
except Exception as e:
    log("   uniform not available:", e)
bargs = T("add_boundary_layers").arguments()
patch = {"number_of_layers": N_LAYERS, "rate": 1.2}
if "first_height" in bargs:
    patch["first_height"] = FIRST_H
elif "first_aspect_ratio" in bargs:
    patch["first_aspect_ratio"] = 50.0
try:
    bl.arguments.set_state(patch)
    log(f"   BL patch = {patch}")
except Exception as e:
    log("   BL patch fail:", e)
safe_exec("add_boundary_layers")

# ---------------- volume mesh ----------------
run("create_volume_mesh_ftm", exec_after=True,
    fill_with_size_field=True, quality_method="Orthogonal")


# ---------------- stats ----------------
def tui(cmd):
    for meth in (lambda: s.execute_tui(cmd),
                 lambda: s.scheme_eval.string_eval(f'(ti-menu-load-string "{cmd}")')):
        try:
            out = meth()
            if out is not None:
                return out
        except Exception:
            continue
    return None


for cmd in ("mesh/size-info", "mesh/quality traders-only"):
    res = tui(cmd)
    log(f"--- {cmd} ---")
    print(res if res else "(not available)", flush=True)

for cmd in (f'file/write-mesh "{MSH}"',):
    log(f"write-mesh -> {tui(cmd)!r}")
log("mesh file exists:", os.path.exists(MSH))
s.exit()
log("DONE")
