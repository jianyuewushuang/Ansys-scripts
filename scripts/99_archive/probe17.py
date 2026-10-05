import os
"""Probe 17: build the domain with both aircraft orientations, mesh, and check the
aircraft wall is actually referenced by the volume mesh (read back in a solver)."""
import numpy as np, re, os, subprocess, sys

os.environ.setdefault("PYFLUENT_SHOW_SERVER_GUI", "0")
from ansys.fluent.core import launch_fluent

BASE = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))   # <project root>
XMIN, XMAX, YMIN, YMAX, ZMIN, ZMAX = -36.0, 84.0, -33.0, 33.0, -20.0, 20.0

txt = open(BASE + "/data/1.stl", "r", errors="ignore").read()
V = np.array(re.findall(r"vertex\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)", txt), dtype=float)
tri = V.reshape(-1, 3, 3)
print("aircraft facets:", len(tri))

x0, x1, y0, y1, z0, z1 = XMIN, XMAX, YMIN, YMAX, ZMIN, ZMAX
P = np.array([[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],
              [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]], float)
QUADS = np.array([[4, 5, 6, 7], [1, 0, 3, 2], [0, 4, 7, 3],
                  [5, 1, 2, 6], [0, 1, 5, 4], [3, 7, 6, 2]])
box = []
for q in QUADS:
    box.append(P[q[[0, 1, 2]]]); box.append(P[q[[0, 2, 3]]])
box = np.array(box)


def write_stl(path, solids):
    with open(path, "w") as f:
        for name, fac in solids:
            a = fac[:, 1] - fac[:, 0]; b = fac[:, 2] - fac[:, 0]
            nv = np.cross(a, b)
            ln = np.linalg.norm(nv, axis=1, keepdims=True)
            nv = nv / np.where(ln == 0, 1, ln)
            f.write(f"solid {name}\n")
            for i in range(len(fac)):
                f.write(f"  facet normal {nv[i,0]:e} {nv[i,1]:e} {nv[i,2]:e}\n")
                f.write("    outer loop\n")
                for j in range(3):
                    f.write(f"      vertex {fac[i,j,0]:e} {fac[i,j,1]:e} {fac[i,j,2]:e}\n")
                f.write("    endloop\n  endfacet\n")
            f.write(f"endsolid {name}\n")


def pipeline(dom_path, msh_path):
    s = launch_fluent(mode="meshing", processor_count=2, precision="double", cwd=BASE + "/work")
    wtm = s.watertight(); WFO = wtm._workflow.task_object

    def T(p, i=0):
        h = getattr(WFO, p); n = h.get_object_names(); return h[n[i]]

    T("import_geometry").arguments.set_state({"length_unit": "m", "file_format": "Mesh",
                                              "mesh_file_name": dom_path})
    T("import_geometry").execute()
    try:
        als = T("add_local_sizing_wtm")
        als.arguments.set_state({"boi_execution": "Body Size", "boi_size": 0.35,
                                 "boi_growth_rate": 1.15, "boi_control_name": "airframe",
                                 "boi_zoneor_label": "label",
                                 "boi_face_label_list": ["aircraft"], "add_child": True})
        als.execute()
    except Exception as e:
        print("   sizing:", e)
    T("create_surface_mesh").arguments.set_state({
        "length_unit": "m",
        "cfd_surface_mesh_controls": {"min_size": 0.12, "max_size": 2.0, "growth_rate": 1.2,
                                      "curvature_normal_angle": 12.0,
                                      "size_functions": "Curvature & Proximity",
                                      "scope_proximity_to": "edges", "cells_per_gap": 1.0,
                                      "use_size_files": "No"}})
    T("create_surface_mesh").execute()
    dg = T("describe_geometry")
    dg.arguments.set_state({"setup_type": "fluid", "capping_required": False,
                            "invoke_share_topology": "No", "non_conformal": True,
                            "wall_to_internal": False})
    try:
        dg.execute()
    except Exception as e:
        print("   describe:", str(e)[:120])
    for p in ("create_regions", "update_regions"):
        try:
            T(p).execute()
        except Exception as e:
            print(f"   {p}: {str(e)[:120]}")
    bl = T("add_boundary_layers")
    bl.arguments.set_state({"offset_method_type": "uniform", "number_of_layers": 8,
                            "rate": 1.2, "first_height": 0.0003, "add_child": "yes",
                            "local_prism_preferences": {"show_in_gui": False,
                                                        "modify_at_invalid_normals": True,
                                                        "ignore_boundary_layers": False,
                                                        "additional_ignored_layers": 0}})
    try:
        bl.execute()
    except Exception as e:
        print("   BL:", str(e)[:120])
    vm = T("create_volume_mesh_wtm")
    vm.arguments.set_state({"volume_fill": "poly-hexcore"})
    try:
        vm.execute()
    except Exception as e:
        print("   volume:", str(e)[:150])
    try:
        s.execute_tui(f'file/write-mesh "{msh_path}"')
    except Exception as e:
        try:
            s.scheme_eval.string_eval(f'(ti-menu-load-string "file/write-mesh \\"{msh_path}\\"")')
        except Exception:
            pass
    s.exit()


def check(msh_path):
    s = launch_fluent(mode="solver", processor_count=2, precision="double", cwd=BASE + "/work")
    out = s.execute_tui(f'file/read-case "{msh_path}"')
    txtout = str(out)
    ok = "not referenced by grid" not in txtout
    z = s.execute_tui("define/boundary-conditions/list-zones")
    s.exit()
    return ok, txtout, str(z)


for tag, rev in (("REVERSED", True), ("ASIS", False)):
    dom = BASE + f"/dom_{tag}.stl"
    msh = BASE + f"/mesh_{tag}.msh.h5"
    ac = tri[:, ::-1].copy() if rev else tri.copy()
    write_stl(dom, [("farfield", box), ("aircraft", ac)])
    print(f"\n######## {tag} ########", flush=True)
    pipeline(dom, msh)
    if os.path.exists(msh):
        ok, txtout, z = check(msh)
        print(f"RESULT {tag}: aircraft referenced = {ok}")
        for line in txtout.splitlines():
            if "Skipping" in line or "cells," in line or "cell zone" in line or "Removing" in line:
                print("   ", line.strip())
        print("   zones:", [l.strip() for l in z.splitlines() if "wall" in l or "interior" in l][:8])
    else:
        print(f"RESULT {tag}: no mesh written")

print("\nALL DONE")
