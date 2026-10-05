"""Render all post-processing figures from results/*.npz + final*.log."""
import os
import re
import json
import struct
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.tri import Triangulation
import pyvista as pv

BASE = r"C:/Users/jianyuewushuang/document/model/ansys/UAVdesign20261004"
OUT = os.path.join(BASE, "results")
os.makedirs(OUT, exist_ok=True)

P_INF = 54019.89
Q_INF = 1325.016
V_INF = 60.0
SREF = 65.3375
LREF = 4.1996
AOAS = [0, 4, 8, 12]
STATIONS = [8, 15, 24, 34, 48]

CMP = "RdBu_r"      # pressure: red = high (stagnation), blue = low
CMV = "viridis"

plt.rcParams.update({"font.size": 10, "axes.titlesize": 11,
                     "figure.dpi": 110, "savefig.dpi": 110})


# --------------------------------------------------------------- helpers
def load_stl(path):
    with open(path, "rb") as f:
        d = f.read()
    n = struct.unpack("<I", d[80:84])[0]
    dt = np.dtype([("n", "<f4", 3), ("v0", "<f4", 3), ("v1", "<f4", 3),
                   ("v2", "<f4", 3), ("a", "<u2")])
    arr = np.frombuffer(d[84:84 + 50 * n], dtype=dt)
    tri = np.stack([arr["v0"], arr["v1"], arr["v2"]], axis=1).astype(np.float64)
    return tri


def slice_y0(tri, tol=0.12):
    """Upper / lower outline of the y=0 cross-section of a closed triangulated solid."""
    pts = []
    for t in tri:
        ys = t[:, 1]
        ins = ys <= tol
        if ins.sum() == 3:
            pts.append(t[:, [0, 2]])
        elif ins.sum() == 2:
            pts.append(t[ins][:, [0, 2]])
    if not pts:
        return np.zeros((0, 2)), np.zeros((0, 2))
    P = np.vstack(pts)
    P = P[np.isfinite(P).all(axis=1)]
    # P holds (x, z) pairs
    nb = 160
    edges = np.linspace(P[:, 0].min(), P[:, 0].max(), nb + 1)
    idx = np.clip(np.digitize(P[:, 0], edges) - 1, 0, nb - 1)
    up, lo = [], []
    for b in range(nb):
        m = idx == b
        if not m.any():
            continue
        z = P[m, 1]
        xc = 0.5 * (edges[b] + edges[b + 1])
        up.append((xc, z.max()))
        lo.append((xc, z.min()))
    return np.array(up), np.array(lo)


def vtkmesh(verts, conn):
    """Build a pyvista PolyData from Fluent vertices + face connectivity."""
    conn = [np.asarray(c, dtype=np.int64).ravel() for c in conn]
    faces = []
    for c in conn:
        if len(c) >= 3:
            faces.append(len(c))
            faces.extend(c.tolist())
    return pv.PolyData(np.asarray(verts, dtype=np.float64), np.array(faces))


def tri_from(verts, conn, values, axis=(0, 1)):
    """Matplotlib flat-shaded triangulation using face centroids."""
    verts = np.asarray(verts)
    cen = []
    val = []
    for i, c in enumerate(conn):
        c = np.asarray(c, dtype=np.int64).ravel()
        cen.append(verts[c].mean(axis=0))
        val.append(values[i])
    cen = np.asarray(cen)
    val = np.asarray(val)
    return Triangulation(cen[:, axis[0]], cen[:, axis[1]]), val


def plot_surface(verts, conn, vals, ax, axis=(0, 1), levels=40,
                 cmap=CMV, vmin=None, vmax=None):
    """Works whether `vals` are node values (len == nverts) or face values.

    Node values -> real triangulation with interpolated contours.
    Face values -> centroid triangulation with flat shading.
    """
    verts = np.asarray(verts)
    vals = np.asarray(vals).ravel()
    conn = [np.asarray(c, dtype=np.int64).ravel() for c in conn]
    if vals.size == verts.shape[0]:
        # fan-triangulate: Fluent plane surfaces are mostly quads
        tris = []
        for c in conn:
            for i in range(1, len(c) - 1):
                tris.append((c[0], c[i], c[i + 1]))
        tri = np.array(tris, dtype=np.int64)
        if not len(tri):
            raise ValueError("no faces to triangulate")
        tr = Triangulation(verts[:, axis[0]], verts[:, axis[1]], tri)
        v = vals
    elif vals.size == len(conn):
        tr, v = tri_from(verts, conn, vals, axis)
    else:
        raise ValueError("value count %d matches neither %d verts nor %d faces"
                         % (vals.size, verts.shape[0], len(conn)))
    # NOTE: tricontourf hangs (>30 min) on the fan-triangulated polyhedral
    # faces of these poly-hexcore planes.  tripcolor renders instantly and
    # looks essentially the same for smooth fields.
    m = ax.tripcolor(tr, v, cmap=cmap, vmin=vmin, vmax=vmax, shading="gouraud")
    ax.set_aspect("equal")
    return m


def cp_of(p):
    return (np.asarray(p) - P_INF) / Q_INF


# ---------------------------------------------------------- 3D surface Cp
def fig_cp_3d(bag, tag, aoa):
    verts = bag["wall_verts"]
    conn = list(bag["wall_conn"])
    cp = cp_of(bag.get("wall_pf", bag["wall_p"]))     # prefer face values
    mesh = vtkmesh(verts, conn)
    if cp.size == mesh.n_cells:
        mesh.cell_data["Cp"] = cp
    elif cp.size == mesh.n_points:
        mesh.point_data["Cp"] = cp
    else:
        mesh.cell_data["Cp"] = np.interp(
            np.linspace(0, cp.size - 1, mesh.n_cells), np.arange(cp.size), cp)
    clim = [-1.2, 1.0]

    views = [("planform (top)", (0, 0, 1), 150),
             ("side", (0, -1, 0), 150),
             ("front 3/4", (60, -60, 25), 150)]

    for label, vup, zoom in views:
        p = pv.Plotter(off_screen=True, window_size=(1500, 780))
        p.background_color = "white"
        p.add_mesh(mesh, scalars="Cp", cmap="coolwarm", clim=clim,
                   show_scalar_bar=True, scalar_bar_args={
                       "title": "Cp", "vertical": False,
                       "position_x": 0.30, "position_y": 0.06,
                       "width": 0.45, "height": 0.06})
        p.add_text("AoA = %g deg  -  %s" % (aoa, label), position="upper_left",
                   font_size=16, color="black")
        if label.startswith("planform"):
            p.camera_position = [(12, 0, 42), (12, 0, 0), (0, 1, 0)]
        elif label.startswith("side"):
            p.camera_position = [(12, -46, 0), (12, 0, 0), (0, 0, 1)]
        else:
            p.camera_position = [(42, -33, 14), (12, 0, 0), (0, 0, 1)]
        p.show()
        fn = os.path.join(OUT, "cp3d_%s_aoa%d_%s.png"
                          % (tag, int(aoa), label.split()[0]))
        p.screenshot(fn)
        p.close()
        print("saved", fn, flush=True)


# ------------------------------------------------- upper/lower Cp planform
def fig_cp_upper_lower(bag, aoa):
    verts = bag["wall_verts"]
    conn = list(bag["wall_conn"])
    cp = cp_of(bag.get("wall_pf", bag["wall_p"]))
    nrm = bag.get("wall_nrm")
    if nrm is not None and len(nrm) == len(conn):
        # Fluent returns area-weighted (unnormalised) normals
        L = np.linalg.norm(np.asarray(nrm, dtype=np.float64), axis=1)
        nrm = np.asarray(nrm, dtype=np.float64) / np.maximum(L, 1e-12)[:, None]
    if nrm is None:
        cen = bag.get("wall_cen")
        if cen is None:
            cen = np.array([np.asarray(verts)[np.asarray(c, dtype=np.int64)]
                            .mean(axis=0) for c in conn])
        nrm = np.zeros((len(conn), 3))
        nrm[:, 2] = np.sign(cen[:, 2] - np.median(cen[:, 2]))
    fig, ax = plt.subplots(1, 2, figsize=(13, 6.2))
    # Fluent wall normals point INTO the fluid, so the upper surface has nz < 0
    # (verified: faces with nz<0 sit at mean z = +0.64 and carry the suction).
    for k, (sel, ttl) in enumerate([(nrm[:, 2] < -0.15, "upper surface  Cp"),
                                    (nrm[:, 2] > 0.15, "lower surface  Cp")]):
        sub = [np.asarray(c) for c, s in zip(conn, sel) if s]
        val = cp[sel]
        m = plot_surface(verts, sub, val, ax[k], (0, 1), 45, "coolwarm",
                         -1.2, 1.0)
        ax[k].set_xlabel("x  [m]  (flight direction)")
        ax[k].set_ylabel("y  [m]  (span)")
        ax[k].set_title(ttl)
        plt.colorbar(m, ax=ax[k], fraction=0.046)
    fig.suptitle("Surface pressure coefficient - AoA = %g deg" % aoa)
    plt.tight_layout()
    fn = os.path.join(OUT, "cp_upper_lower_aoa%d.png" % int(aoa))
    plt.savefig(fn); plt.close()
    print("saved", fn, flush=True)


# ------------------------------------------------------ symmetry plane 2D
def fig_sym(bag, aoa, silh):
    verts = bag.get("sym_verts")
    conn = list(bag.get("sym_conn", []))
    if verts is None or not conn:
        print("   (no symmetry plane data)")
        return
    fig, ax = plt.subplots(2, 1, figsize=(14, 9))
    specs = [("sym_velocity_magnitude", "velocity magnitude [m/s]",
              "turbo", 45.0, 72.0),
             ("sym_pressure", "Cp  [-]", "coolwarm", -1.2, 1.0)]
    for k, (key, ttl, cmap, vmin, vmax) in enumerate(specs):
        vals = bag.get(key)
        if vals is None:
            continue
        v = cp_of(vals) if key.endswith("pressure") else vals
        m = plot_surface(verts, conn, v, ax[k], (0, 2), 60, cmap, vmin, vmax)
        if silh is not None:
            up, lo = silh
            if len(up):
                ax[k].plot(up[:, 0], up[:, 1], "k-", lw=1.3)
                ax[k].plot(lo[:, 0], lo[:, 1], "k-", lw=1.3)
        ax[k].set_xlim(-16, 46); ax[k].set_ylim(-12, 12)
        ax[k].set_xlabel("x  [m]  (flight direction)"); ax[k].set_ylabel("z  [m]")
        ax[k].set_title("symmetry plane y=0 - " + ttl)
        plt.colorbar(m, ax=ax[k], fraction=0.03)
    fig.suptitle("Symmetry plane fields - AoA = %g deg  (aircraft outline in black)"
                 % aoa)
    plt.tight_layout()
    fn = os.path.join(OUT, "sym_fields_aoa%d.png" % int(aoa))
    plt.savefig(fn); plt.close()
    print("saved", fn, flush=True)


# ------------------------------------------------------ symmetry streamlines
def fig_streamlines(bag, aoa, silh):
    from matplotlib.collections import LineCollection
    key = "pl_seed_line_verts"
    if key not in bag:
        print("   (no pathlines)")
        return
    V = np.asarray(bag[key])
    lines = list(bag["pl_seed_line_lines"])
    val = np.asarray(bag["pl_seed_line_val"]).ravel()
    segs, cvals = [], []
    for ln in lines:
        ln = np.asarray(ln, dtype=np.int64).ravel()
        if len(ln) < 2:
            continue
        pts = V[ln]
        if pts.shape[0] == 2:
            segs.append(pts[:, [0, 2]])
            cvals.append(float(val[ln].mean()))
        else:
            for i in range(len(pts) - 1):
                segs.append(pts[i:i + 2][:, [0, 2]])
                cvals.append(float(val[ln][i]))
    if not segs:
        print("   (empty pathlines)")
        return
    fig, ax = plt.subplots(figsize=(13, 7))
    lc = LineCollection(segs, cmap="turbo", linewidths=1.6,
                        norm=plt.Normalize(35, 80))
    lc.set_array(np.array(cvals))
    ax.add_collection(lc)
    cb = plt.colorbar(lc, ax=ax, fraction=0.03)
    cb.set_label("|V|  [m/s]")
    if silh is not None:
        up, lo = silh
        if len(up):
            ax.plot(up[:, 0], up[:, 1], "k-", lw=1.6)
            ax.plot(lo[:, 0], lo[:, 1], "k-", lw=1.6)
            ax.fill_between(up[:, 0], lo[:, 1], up[:, 1], color="0.25", alpha=0.9,
                            zorder=3)
    ax.set_xlim(-14, 50); ax.set_ylim(-10, 10)
    ax.set_aspect("equal")
    ax.set_xlabel("x  [m]  (flight direction)"); ax.set_ylabel("z  [m]")
    ax.set_title("Streamlines on the symmetry plane (coloured by |V|) - "
                 "AoA = %g deg" % aoa)
    plt.tight_layout()
    fn = os.path.join(OUT, "sym_streamlines_aoa%d.png" % int(aoa))
    plt.savefig(fn); plt.close()
    print("saved", fn, flush=True)


# ------------------------------------------------------ wake cross sections
def fig_wake(bag, aoa):
    have = [s for s in STATIONS if "xs%d_verts" % s in bag]
    if not have:
        print("   (no cross-section data)")
        return
    fig, ax = plt.subplots(1, len(have), figsize=(3.3 * len(have), 6.2))
    if len(have) == 1:
        ax = [ax]
    used = "velocity"
    for k, s in enumerate(have):
        verts = bag["xs%d_verts" % s]
        conn = list(bag["xs%d_conn" % s])
        key = "xs%d_vorticity_mag" % s
        if key not in bag:
            key = "xs%d_velocity_magnitude" % s
        used = "vorticity" if "vorticity" in key else "velocity"
        vals = bag[key]
        m = plot_surface(verts, conn, vals, ax[k], (1, 2), 40, "inferno",
                         0, 60 if used == "vorticity" else 90)
        ax[k].set_xlabel("y  [m]"); ax[k].set_ylabel("z  [m]")
        ax[k].set_title("x = %d m" % s)
        ax[k].set_xlim(-16, 16); ax[k].set_ylim(-9, 9)
        plt.colorbar(m, ax=ax[k], fraction=0.046)
    fig.suptitle("Wake cross-sections - %s  (AoA = %g deg)"
                 % ("vorticity magnitude [1/s]" if used == "vorticity"
                    else "|V| [m/s]", aoa))
    plt.tight_layout()
    fn = os.path.join(OUT, "wake_xsections_aoa%d.png" % int(aoa))
    plt.savefig(fn); plt.close()
    print("saved", fn, flush=True)


# ------------------------------------------ 3D tip-vortex streamlines
def fig_vortex3d(bag, aoa):
    seeds = [k.replace("_verts", "") for k in bag
             if k.startswith("pl_seed_tip") and k.endswith("_verts")]
    if not seeds:
        print("   (no tip-vortex pathlines)")
        return
    p = pv.Plotter(off_screen=True, window_size=(1600, 900))
    p.background_color = "white"
    mesh = vtkmesh(bag["wall_verts"], list(bag["wall_conn"]))
    p.add_mesh(mesh, color="#8d99a6", opacity=0.5, show_edges=False)
    for sname in seeds:
        V = np.asarray(bag[sname + "_verts"], dtype=np.float64)
        lines = [np.asarray(l, dtype=np.int64).ravel()
                 for l in bag[sname + "_lines"]]
        val = np.asarray(bag[sname + "_val"]).ravel()
        cell, idx = [], []
        for l in lines:
            # Fluent returns pathlines as independent 2-point segments that
            # are nevertheless consecutive - drawing them all reproduces the
            # continuous streamline.
            cell += [2, len(idx), len(idx) + 1]
            idx += [int(l[0]), int(l[1])]
        if not idx:
            continue
        idx = np.array(idx)
        # NOTE: pv.PolyData(points, cells) files 2-point cells under *polys*
        # and renders nothing - they must be assigned to `.lines`.
        poly = pv.PolyData()
        poly.points = V[idx]
        poly.lines = np.array(cell)
        poly["V"] = val[idx]
        p.add_mesh(poly, scalars="V", cmap="turbo", clim=[52, 72],
                   line_width=6, render_lines_as_tubes=True,
                   show_scalar_bar=(sname == seeds[0]),
                   scalar_bar_args={"title": "|V| [m/s]", "vertical": False,
                                    "position_x": 0.35, "position_y": 0.06,
                                    "width": 0.4, "height": 0.05})
    p.add_text("Wing-tip vortex streamlines - AoA = %g deg" % aoa,
               position="upper_left", font_size=16, color="black")
    p.camera_position = [(46, -30, 15), (16, 0, 0.0), (0, 0, 1)]
    p.show()
    fn = os.path.join(OUT, "vortex3d_aoa%d.png" % int(aoa))
    p.screenshot(fn); p.close()
    print("saved", fn, flush=True)


# ------------------------------------------ horizontal wake plane
def fig_hor(bag, aoa):
    if "hor_verts" not in bag:
        return
    verts = bag["hor_verts"]
    conn = list(bag["hor_conn"])
    key = "hor_vorticity_mag" if "hor_vorticity_mag" in bag \
        else "hor_velocity_magnitude"
    if key not in bag:
        return
    fig, ax = plt.subplots(figsize=(13, 7))
    m = plot_surface(verts, conn, bag[key], ax, (0, 1), 50, "inferno",
                     0, 60 if "vorticity" in key else 90)
    ax.set_xlabel("x  [m]"); ax.set_ylabel("y  [m]")
    ax.set_title("Horizontal plane z=0 - %s (AoA = %g deg)"
                 % ("vorticity magnitude [1/s]" if "vorticity" in key
                    else "|V| [m/s]", aoa))
    ax.set_xlim(-25, 65); ax.set_ylim(-20, 20)
    plt.colorbar(m, ax=ax, fraction=0.046)
    plt.tight_layout()
    fn = os.path.join(OUT, "wake_horizontal_aoa%d.png" % int(aoa))
    plt.savefig(fn); plt.close()
    print("saved", fn, flush=True)


# ------------------------------------------------------ coefficient curves
def fig_coeffs():
    src = os.path.join(OUT, "forces.json")
    if not os.path.exists(src):
        print("no forces.json")
        return None
    res = json.load(open(src))
    res = [r for r in res if r.get("CL") is not None]
    if not res:
        print("empty forces.json")
        return None
    a = [r["aoa"] for r in res]
    cl = [r["CL"] for r in res]
    cd = [r["CD"] for r in res]
    ld = [(x / y) if y else float("nan") for x, y in zip(cl, cd)]
    cm = [r.get("CM") for r in res]

    fig, ax = plt.subplots(2, 2, figsize=(12.5, 9))
    ax[0, 0].plot(a, cl, "o-", color="#d62728", lw=2, ms=8)
    ax[0, 0].set_xlabel("angle of attack  [deg]"); ax[0, 0].set_ylabel("CL")
    ax[0, 0].set_title("Lift coefficient  CL vs alpha"); ax[0, 0].grid(alpha=.35)

    ax[0, 1].plot(a, cd, "s-", color="#1f77b4", lw=2, ms=8)
    ax[0, 1].set_xlabel("angle of attack  [deg]"); ax[0, 1].set_ylabel("CD")
    ax[0, 1].set_title("Drag coefficient  CD vs alpha"); ax[0, 1].grid(alpha=.35)

    ax[1, 0].plot(a, ld, "^--", color="#2ca02c", lw=2, ms=8)
    ax[1, 0].set_xlabel("angle of attack  [deg]"); ax[1, 0].set_ylabel("L/D")
    ax[1, 0].set_title("Aerodynamic efficiency  L/D"); ax[1, 0].grid(alpha=.35)

    ax[1, 1].plot(cd, cl, "d-", color="#9467bd", lw=2, ms=8)
    for x, y, aa in zip(cd, cl, a):
        ax[1, 1].annotate("%g deg" % aa, (x, y), textcoords="offset points",
                          xytext=(7, 5), fontsize=9)
    ax[1, 1].set_xlabel("CD"); ax[1, 1].set_ylabel("CL")
    ax[1, 1].set_title("Drag polar"); ax[1, 1].grid(alpha=.35)

    plt.suptitle("UAV aerodynamics - 5 km ISA, V = 60 m/s, Ma = 0.187, "
                 "Re = 1.14e7, Sref = %.1f m2, MAC = %.2f m"
                 % (SREF, LREF), fontsize=12)
    plt.tight_layout()
    fn = os.path.join(OUT, "aero_coefficients.png")
    plt.savefig(fn); plt.close()
    print("saved", fn, flush=True)
    if all(c is not None for c in cm):
        fig, ax2 = plt.subplots(figsize=(7, 5))
        ax2.plot(a, cm, "o-", color="#ff7f0e", lw=2, ms=8)
        ax2.set_xlabel("angle of attack [deg]"); ax2.set_ylabel("CM")
        ax2.set_title("Pitching moment about y at quarter-chord")
        ax2.grid(alpha=.35); ax2.invert_yaxis()
        plt.tight_layout()
        fn = os.path.join(OUT, "pitch_moment.png")
        plt.savefig(fn); plt.close()
        print("saved", fn, flush=True)
    return dict(aoa=a, CL=cl, CD=cd, LD=ld, CM=cm)


# -------------------------------------------------------------- residuals
def fig_residuals(logfile=None):
    logfile = logfile or os.path.join(BASE, "final5.log")
    if not os.path.exists(logfile):
        return
    txt = open(logfile, errors="ignore").read()
    blocks = re.split(r"############ AoA = ([-\d.]+) deg", txt)
    fig, ax = plt.subplots(1, 2, figsize=(13, 5))
    for i in range(1, len(blocks), 2):
        aoa = float(blocks[i])
        body = blocks[i + 1]
        rows = re.findall(
            r"^\s*(\d+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s+"
            r"([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)",
            body, re.M)
        if not rows:
            continue
        arr = np.array([[float(x) for x in r] for r in rows])
        it, cont, vx, vy, vz, en, k, om = arr.T
        ax[0].semilogy(it, cont, lw=1.2, label="AoA %g: continuity" % aoa)
        ax[1].semilogy(it, np.maximum.reduce([vx, vy, vz]), lw=1.2,
                       label="AoA %g: velocity" % aoa)
    for a in ax:
        a.set_xlabel("iteration"); a.set_ylabel("scaled residual")
        a.grid(alpha=.35, which="both"); a.legend(fontsize=8)
    ax[0].set_title("continuity"); ax[1].set_title("velocity (max of x,y,z)")
    plt.suptitle("Convergence history")
    plt.tight_layout()
    fn = os.path.join(OUT, "residuals.png")
    plt.savefig(fn); plt.close()
    print("saved", fn, flush=True)


# ------------------------------------------------------------------- main
def main():
    silh = None
    stl = os.path.join(BASE, "aircraft_solid.stl")
    if os.path.exists(stl):
        silh = slice_y0(load_stl(stl))
        print("silhouette bins:", len(silh[0]), flush=True)
    for aoa in AOAS:
        fn = os.path.join(OUT, "fields_aoa%d.npz" % aoa)
        if not os.path.exists(fn):
            print("missing", fn)
            continue
        bag = dict(np.load(fn, allow_pickle=True))
        print("\n### rendering AoA %d" % aoa, flush=True)
        fig_cp_3d(bag, "surf", aoa)
        fig_cp_upper_lower(bag, aoa)
        fig_sym(bag, aoa, silh)
        fig_streamlines(bag, aoa, silh)
        fig_wake(bag, aoa)
        fig_vortex3d(bag, aoa)
        fig_hor(bag, aoa)
    fig_coeffs()
    fig_residuals()
    print("RENDER DONE")


if __name__ == "__main__":
    main()
