"""Extract post-processing field data from the solved cases into npz files."""
import os
import sys

import numpy as np

os.environ.setdefault("PYFLUENT_SHOW_SERVER_GUI", "0")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import common  # noqa: E402

common.quiet_pyfluent()

from ansys.fluent.core import launch_fluent  # noqa: E402
from ansys.fluent.core.fields.field_data_interfaces import (  # noqa: E402
    ScalarFieldDataRequest,
    PathlinesFieldDataRequest,
)

BASE = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))   # <project root>
OUT = os.environ.get("RESULTS_DIR", os.path.join(BASE, "results"))
os.makedirs(OUT, exist_ok=True)

AOAS = [float(a) for a in os.environ.get("AOAS", "0,4,8,12").split(",")]
CASE_FMT = os.environ.get("CASE_FMT",
                          os.path.join(BASE, "artifacts/cases/final_aoa%d.cas.h5"))
WALL = "aircraft-fluid_box"
STATIONS = [float(x) for x in
            os.environ.get("STATIONS", "8,15,24,34,48").split(",")]


def make_planes(s):
    """Create planes / seed lines through the settings API.

    NOTE: the TUI form `point-and-normal 0 0 0 0 1 0` is ambiguous - it
    silently produced an x=0 plane instead of y=0.  The settings API with an
    explicit `method` is unambiguous.
    """
    made = []
    surf = s.settings.results.surfaces
    ps = surf.plane_surface
    tui = s.execute_tui

    def mkplane(name, method, coord):
        """method must be one of yz-plane (x=c) / zx-plane (y=c) / xy-plane (z=c)."""
        try:
            try:
                ps.__setitem__(name, {"method": method})
            except Exception:
                ps.create(name=name)
            o = ps[name]
            try:
                o.method = method
            except Exception as e:
                print("   ! %s method: %s" % (name, str(e)[:90]), flush=True)
            k, val = coord
            try:
                setattr(o, k, val)
            except Exception as e:
                print("   ! %s %s: %s" % (name, k, str(e)[:90]), flush=True)
            made.append(name)
        except Exception as e:
            print("   ! plane %s: %s" % (name, str(e)[:120]), flush=True)

    # yz-plane -> constant x ; zx-plane -> constant y ; xy-plane -> constant z
    mkplane("sym_y0", "zx-plane", ("y", 0.0))
    mkplane("hor_z0", "xy-plane", ("z", 0.0))
    for x in STATIONS:
        mkplane("xs_%d" % int(x), "yz-plane", ("x", float(x)))

    # tip-vortex seeds are placed upstream so the lines roll up over the tip
    seeds = [("seed_line", (-12, 0, -7), (-12, 0, 7)),
             ("seed_line_hi", (-12, 0, -4), (-12, 0, 4)),
             ("seed_tip", (-6, 9.4, 0.0), (-6, 11.9, 0.0)),
             ("seed_tip2", (-6, 11.9, 0.6), (-6, 12.8, 0.6)),
             ("seed_mid", (-6, 3.0, 0.2), (-6, 7.0, 0.2))]
    for name, p0, p1 in seeds:
        cmd = ("/surface/line-surface %s %g %g %g %g %g %g"
               % (name, p0[0], p0[1], p0[2], p1[0], p1[1], p1[2]))
        try:
            tui(cmd)
            made.append(name)
            print("   + line " + name, flush=True)
        except Exception as e:
            print("   ! line %s: %s" % (name, str(e)[:130]), flush=True)

    # report the actual extents so orientation mistakes are obvious
    for nm in ("sym_y0", "hor_z0", "xs_24"):
        if nm not in made:
            continue
        try:
            fd_tmp = getattr(s, "field_data", None) or s.fields.field_data
            sd = common.surface(fd_tmp, nm)
            v = np.asarray(sd.vertices)
            print("   %-8s x[%7.2f,%7.2f] y[%7.2f,%7.2f] z[%7.2f,%7.2f]"
                  % (nm, v[:, 0].min(), v[:, 0].max(), v[:, 1].min(),
                     v[:, 1].max(), v[:, 2].min(), v[:, 2].max()), flush=True)
        except Exception as e:
            print("   bounds %s: %s" % (nm, str(e)[:100]), flush=True)
    return made


def surf_geom(fd, name):
    """取一个面的顶点 / 连接表 / 面心 / 法向。

    走 common.surface()：带 flatten_connectivity=True，不再触发
    PyFluentDeprecationWarning，且 .faces 恒为逐面索引列表。
    """
    return common.surface(fd, name, with_normals=True)


def conn_list(c):
    """兼容旧调用：既能吃逐面 list，也能吃扁平 ndarray。"""
    return common.faces_of(c)


def scalar(fd, name, field):
    """Node values (good for point_data / smooth rendering)."""
    try:
        r = fd.get_field_data(ScalarFieldDataRequest(
            surfaces=[name], field_name=field, node_value=True,
            boundary_value=True))
        return np.asarray(r[name]).ravel()
    except Exception as e:
        print("   ! scalar %s on %s: %s" % (field, name, str(e)[:110]), flush=True)
        return None


def scalar_face(fd, name, field):
    """Per-face values (needed for flat cell_data + matplotlib shading)."""
    try:
        r = fd.get_field_data(ScalarFieldDataRequest(
            surfaces=[name], field_name=field, node_value=False,
            boundary_value=True))
        return np.asarray(r[name]).ravel()
    except Exception as e:
        print("   ! face scalar %s on %s: %s" % (field, name, str(e)[:110]),
              flush=True)
        return None


def main():
    s = launch_fluent(mode="solver", precision="double", processor_count=4,
                      cwd=BASE + "/work")
    st = s.settings
    fd = getattr(s, "field_data", None)
    if fd is None:
        fd = s.fields.field_data

    for aoa in AOAS:
        cf = CASE_FMT % int(aoa)
        if not os.path.exists(cf):
            print("missing " + cf)
            continue
        print("\n########## AoA %g : %s" % (aoa, cf), flush=True)
        st.file.read(file_type="case-data", file_name=cf)
        names = make_planes(s)
        bag = {"aoa": aoa}

        try:
            sd = surf_geom(fd, WALL)
            bag["wall_verts"] = np.asarray(sd.vertices)
            bag["wall_conn"] = np.array(sd.faces, dtype=object)
            bag["wall_nrm"] = np.asarray(sd.normals)
            bag["wall_cen"] = np.asarray(sd.centroids)
            bag["wall_p"] = scalar(fd, WALL, "pressure")
            pf = scalar_face(fd, WALL, "pressure")
            if pf is not None and len(pf) == len(sd.faces):
                bag["wall_pf"] = pf
            print("   wall: %d verts, %d face entries"
                  % (bag["wall_verts"].shape[0],
                     sum(len(c) for c in sd.faces)), flush=True)
        except Exception as e:
            print("   ! wall: " + str(e)[:160], flush=True)

        try:
            sd = surf_geom(fd, "sym_y0")
            bag["sym_verts"] = np.asarray(sd.vertices)
            bag["sym_conn"] = np.array(sd.faces, dtype=object)
            for fld in ("velocity-magnitude", "pressure",
                        "vorticity-mag", "turb-kinetic-energy", "q-criterion"):
                v = scalar(fd, "sym_y0", fld)
                if v is not None:
                    bag["sym_" + fld.replace("-", "_")] = v
            print("   sym_y0: %d verts" % bag["sym_verts"].shape[0], flush=True)
        except Exception as e:
            print("   ! sym_y0: " + str(e)[:160], flush=True)

        try:
            sd = surf_geom(fd, "hor_z0")
            bag["hor_verts"] = np.asarray(sd.vertices)
            bag["hor_conn"] = np.array(sd.faces, dtype=object)
            for fld in ("velocity-magnitude", "vorticity-mag", "q-criterion"):
                v = scalar(fd, "hor_z0", fld)
                if v is not None:
                    bag["hor_" + fld.replace("-", "_")] = v
            print("   hor_z0: ok", flush=True)
        except Exception as e:
            print("   ! hor_z0: " + str(e)[:160], flush=True)

        for x in STATIONS:
            nm = "xs_%d" % int(x)
            if nm not in names:
                continue
            try:
                sd = surf_geom(fd, nm)
                bag["xs%d_verts" % int(x)] = np.asarray(sd.vertices)
                bag["xs%d_conn" % int(x)] = np.array(sd.faces, dtype=object)
                for fld in ("velocity-magnitude", "vorticity-mag",
                            "q-criterion"):
                    v = scalar(fd, nm, fld)
                    if v is not None:
                        bag["xs%d_%s" % (int(x), fld.replace("-", "_"))] = v
                print("   " + nm + ": ok", flush=True)
            except Exception as e:
                print("   ! %s: %s" % (nm, str(e)[:140]), flush=True)

        for seed in ("seed_line", "seed_line_hi", "seed_tip", "seed_tip2",
                     "seed_mid"):
            if seed not in names:
                continue
            try:
                # flatten_connectivity=True：避免 PyFluentDeprecationWarning，
                # 同时 lines 变成扁平数组，交给 common.lines_of 统一展开
                try:
                    req = PathlinesFieldDataRequest(
                        surfaces=[seed], field_name="velocity-magnitude",
                        steps=230, step_size=0.35, skip=1,
                        reverse=False, accuracy_control_on=True, tolerance=0.001,
                        coarsen=1, velocity_domain="all-phases",
                        flatten_connectivity=True)
                except TypeError:                 # 旧版 PyFluent 没有该参数
                    req = PathlinesFieldDataRequest(
                        surfaces=[seed], field_name="velocity-magnitude",
                        steps=230, step_size=0.35, skip=1,
                        reverse=False, accuracy_control_on=True, tolerance=0.001,
                        coarsen=1, velocity_domain="all-phases")
                r = fd.get_field_data(req)
                d = r[seed]
                bag["pl_%s_verts" % seed] = np.asarray(d.vertices)
                lines = common.lines_of(d.lines)
                bag["pl_%s_lines" % seed] = np.array(lines, dtype=object)
                bag["pl_%s_val" % seed] = np.asarray(d.scalar_field).ravel()
                print("   pathlines %s: %d pts, %d lines"
                      % (seed, len(d.vertices), len(lines)), flush=True)
            except Exception as e:
                print("   ! pathlines %s: %s" % (seed, str(e)[:140]), flush=True)

        fn = os.path.join(OUT, "fields_aoa%d.npz" % int(aoa))
        np.savez_compressed(fn, **bag)
        print("   saved " + fn, flush=True)

    s.exit()
    print("EXTRACT DONE")


if __name__ == "__main__":
    main()
