"""Probe 20: build the two-shell domain with BOTH aircraft orientations, mesh it,
then read the mesh back in a solver and check whether the aircraft wall survives."""
import numpy as np, re, os

os.environ.setdefault("PYFLUENT_SHOW_SERVER_GUI", "0")
from ansys.fluent.core import launch_fluent

BASE = r"C:/Users/jianyuewushuang/document/model/ansys/UAVdesign20261004"
XMIN, XMAX, YMIN, YMAX, ZMIN, ZMAX = -36.0, 84.0, -33.0, 33.0, -20.0, 20.0

txt = open(BASE + "/1.stl", "r", errors="ignore").read()
V = np.array(re.findall(r"vertex\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)", txt), dtype=float)
tri = V.reshape(-1, 3, 3)
print("aircraft facets:", len(tri), flush=True)

x0, x1, y0, y1, z0, z1 = XMIN, XMAX, YMIN, YMAX, ZMIN, ZMAX
C = np.array([[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],
              [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]], float)
QUADS = [(C[4], C[5], C[6], C[7]), (C[1], C[0], C[3], C[2]), (C[0], C[4], C[7], C[3]),
         (C[5], C[1], C[2], C[6]), (C[0], C[1], C[5], C[4]), (C[3], C[7], C[6], C[2])]


def quad_grid(p00, p10, p11, p01, n=10):
    out = []
    for i in range(n):
        for j in range(n):
            u0, u1, v0, v1 = i / n, (i + 1) / n, j / n, (j + 1) / n
            P = lambda u, v: (p00 * (1 - u) * (1 - v) + p10 * u * (1 - v)
                              + p11 * u * v + p01 * (1 - u) * v)
            a, b, c, d = P(u0, v0), P(u1, v0), P(u1, v1), P(u0, v1)
            out.append([a, b, c]); out.append([a, c, d])
    return out


box = np.array([t for q in QUADS for t in quad_grid(*q, n=10)])


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


def pipeline(dom, msh):
    s = launch_fluent(mode="meshing", processor_count=2, precision="double", cwd=BASE + "/mesh_work")
    wtm = s.watertight(); WFO = wtm._workflow.task_object

    def T(p, i=0):
        h = getattr(WFO, p); n = h.get_object_names(); return h[n[i]]

    T("import_geometry").arguments.set_state({"length_unit": "m", "file_format": "Mesh",
                                              "mesh_file_name": dom})
    T("import_geometry").execute()
    als = T("add_local_sizing_wtm")
    try:
        av = getattr(als.arguments, "boi_face_label_list").allowed_values()
        pick = [x for x in (av or []) if "aircraft" in str(x).lower()]
        if pick:
            als.arguments.set_state({"boi_execution": "Body Size", "boi_size": 0.35,
                                     "boi_growth_rate": 1.15, "boi_control_name": "airframe",
                                     "boi_zoneor_label": "label",
                                     "boi_face_label_list": pick, "add_child": True})
            als.execute()
    except Exception as e:
        print("   sizing:", e, flush=True)
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
        print("   describe:", str(e)[:130], flush=True)
    for p in ("create_regions", "update_regions"):
        try:
            T(p).execute()
        except Exception as e:
            print(f"   {p}: {str(e)[:130]}", flush=True)
    bl = T("add_boundary_layers")
    try:
        bl.arguments.set_state({"offset_method_type": "uniform", "number_of_layers": 8,
                                "rate": 1.2, "first_height": 0.0003, "add_child": "yes",
                                "local_prism_preferences": {"show_in_gui": False,
                                                            "modify_at_invalid_normals": True,
                                                            "ignore_boundary_layers": False,
                                                            "additional_ignored_layers": 0}})
        bl.execute()
    except Exception as e:
        print("   BL:", str(e)[:130], flush=True)
    vm = T("create_volume_mesh_wtm")
    try:
        vm.arguments.set_state({"volume_fill": "poly-hexcore"})
        vm.execute()
    except Exception as e:
        print("   volume:", str(e)[:150], flush=True)
    try:
        s.execute_tui(f'file/write-mesh "{msh}"')
    except Exception:
        try:
            s.scheme_eval.string_eval(f'(ti-menu-load-string "file/write-mesh \\"{msh}\\"")')
        except Exception:
            pass
    s.exit()


def check(msh):
    s = launch_fluent(mode="solver", processor_count=2, precision="double", cwd=BASE + "/mesh_work")
    out = str(s.execute_tui(f'file/read-case "{msh}"'))
    bad = "not referenced by grid" in out
    ncell = None
    for line in out.splitlines():
        if "cells," in line:
            ncell = line.strip()
    s.exit()
    return (not bad), ncell


for tag, rev in (("REVERSED", True), ("ASIS", False)):
    dom = BASE + f"/dom_{tag}.stl"
    msh = BASE + f"/mesh_{tag}.msh.h5"
    ac = tri[:, ::-1].copy() if rev else tri.copy()
    write_stl(dom, [("farfield", box), ("aircraft", ac)])
    print(f"\n######## {tag} ########", flush=True)
    pipeline(dom, msh)
    if os.path.exists(msh):
        ok, ncell = check(msh)
        print(f"RESULT {tag}: aircraft kept = {ok} | {ncell}", flush=True)

print("\nDONE")
