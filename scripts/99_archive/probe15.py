"""Probe 15: dump create_regions / update_regions and try to define the fluid region."""
import os
os.environ.setdefault("PYFLUENT_SHOW_SERVER_GUI", "0")
from ansys.fluent.core import launch_fluent

BASE = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))   # <project root>
DOM = BASE + "/artifacts/geometry/fluid_domain.stl"
s = launch_fluent(mode="meshing", processor_count=2, precision="double", cwd=BASE + "/work")
print("LAUNCH OK", flush=True)
wtm = s.watertight()
WFO = wtm._workflow.task_object


def T(p, i=0):
    h = getattr(WFO, p)
    n = h.get_object_names()
    return h[n[i]]


def dump(p):
    try:
        print(f"\n===== {p} [{T(p).state()}]")
        for k, v in T(p).arguments().items():
            av = ""
            try:
                sub = getattr(T(p).arguments, k)
                if hasattr(sub, "allowed_values"):
                    a = sub.allowed_values()
                    if a:
                        av = f"   ALLOWED={a}"
            except Exception:
                pass
            print(f"   {k:34s} = {v!r}{av}")
    except Exception as e:
        print(f"===== {p} fail {type(e).__name__} {e}")


ig = T("import_geometry")
ig.arguments.set_state({"length_unit": "m", "file_format": "Mesh", "mesh_file_name": DOM})
ig.execute()
T("create_surface_mesh").arguments.set_state({
    "length_unit": "m",
    "cfd_surface_mesh_controls": {"min_size": 0.12, "max_size": 2.0, "growth_rate": 1.2,
                                  "curvature_normal_angle": 12.0,
                                  "size_functions": "Curvature & Proximity",
                                  "scope_proximity_to": "edges", "cells_per_gap": 1.0,
                                  "use_size_files": "No"}})
T("create_surface_mesh").execute()
print("surface mesh done", flush=True)

for p in ("create_regions", "update_regions", "apply_share_topology", "describe_geometry"):
    dump(p)

# execute describe geometry with fluid + no share, then see what create_regions reports
dg = T("describe_geometry")
for setup, share in (("fluid", "No"), ("fluid_solid_voids", "No")):
    try:
        dg.arguments.set_state({"setup_type": setup, "capping_required": False,
                                "invoke_share_topology": share, "wall_to_internal": False})
        dg.execute()
        print(f"\n>>> describe({setup},{share}) OK", flush=True)
        break
    except Exception as e:
        print(f"\n>>> describe({setup},{share}) FAIL {str(e)[:120]}", flush=True)

dump("create_regions")
try:
    T("create_regions").execute()
    print("create_regions executed", flush=True)
except Exception as e:
    print("create_regions FAIL", str(e)[:200], flush=True)
dump("update_regions")
dump("create_regions")

s.exit()
print("DONE")
