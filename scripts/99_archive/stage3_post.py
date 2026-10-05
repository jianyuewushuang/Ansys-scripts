"""Stage 3 - post-processing: coefficient curves + field visualisation."""
import os, json, math, time
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.tri import Triangulation

BASE = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))   # <project root>
OUT = os.path.join(BASE, "results")
os.makedirs(OUT, exist_ok=True)

SREF = 65.3375
LREF = 4.1996
QINF = 1325.016
P_INF = 54019.89
RHO = 0.73612
V_INF = 60.0


def first_number(obj):
    if obj is None:
        return None
    if isinstance(obj, (int, float)):
        return float(obj)
    if isinstance(obj, dict):
        for k in ("total_force", "total", "value", "force", "pressure_force"):
            if k in obj:
                r = first_number(obj[k])
                if r is not None:
                    return r
        for v in obj.values():
            r = first_number(v)
            if r is not None:
                return r
    if isinstance(obj, (list, tuple)):
        for v in obj:
            r = first_number(v)
            if r is not None:
                return r
    return None


# =============================== Part A ===============================
def part_a():
    p = os.path.join(BASE, "forces_raw.json")
    if not os.path.exists(p):
        print("forces_raw.json missing")
        return None
    res = json.load(open(p))
    aoa, CL, CD, LD = [], [], [], []
    for r in res:
        f = r.get("forces", {})
        d = first_number(f.get("rep-drag"))
        l = first_number(f.get("rep-lift"))
        if d is None or l is None:
            print("  no forces for AoA", r.get("aoa"), "->", f)
            continue
        a = float(r["aoa"])
        cd = d / (QINF * SREF); cl = l / (QINF * SREF)
        aoa.append(a); CL.append(cl); CD.append(cd)
        LD.append(cl / cd if cd else float("nan"))
    if not aoa:
        print("no usable force data")
        return None

    fig, ax = plt.subplots(2, 2, figsize=(12, 9))
    ax[0, 0].plot(aoa, CL, "o-", color="#c0392b", lw=2, ms=7)
    ax[0, 0].set_xlabel("angle of attack  [deg]"); ax[0, 0].set_ylabel("$C_L$")
    ax[0, 0].set_title("Lift coefficient"); ax[0, 0].grid(alpha=0.35)

    ax[0, 1].plot(aoa, CD, "s-", color="#2c6fbb", lw=2, ms=7)
    ax[0, 1].set_xlabel("angle of attack  [deg]"); ax[0, 1].set_ylabel("$C_D$")
    ax[0, 1].set_title("Drag coefficient"); ax[0, 1].grid(alpha=0.35)

    ax[1, 0].plot(aoa, LD, "^--", color="#27ae60", lw=2, ms=7)
    ax[1, 0].set_xlabel("angle of attack  [deg]"); ax[1, 0].set_ylabel("$L/D$")
    ax[1, 0].set_title("Lift-to-drag ratio"); ax[1, 0].grid(alpha=0.35)

    ax[1, 1].plot(CD, CL, "d-", color="#8e44ad", lw=2, ms=7)
    for x, y, a in zip(CD, CL, aoa):
        ax[1, 1].annotate(f"{a:.0f}$^\\circ$", (x, y), textcoords="offset points",
                          xytext=(6, 5), fontsize=9)
    ax[1, 1].set_xlabel("$C_D$"); ax[1, 1].set_ylabel("$C_L$")
    ax[1, 1].set_title("Drag polar"); ax[1, 1].grid(alpha=0.35)

    plt.suptitle("UAV aerodynamics - 5 km ISA, V = 60 m/s, Ma = 0.187, "
                 f"Re = 1.14e7, $S_{{ref}}$ = {SREF:.1f} m$^2$", fontsize=12)
    plt.tight_layout()
    f = os.path.join(OUT, "aero_coefficients.png")
    plt.savefig(f, dpi=130); plt.close()
    json.dump({"aoa": aoa, "CL": CL, "CD": CD, "LD": LD},
              open(os.path.join(OUT, "aero_coefficients.json"), "w"), indent=2)
    print("saved", f)
    for a, cl, cd, ld in zip(aoa, CL, CD, LD):
        print(f"  AoA {a:5.1f} deg :  CL {cl:8.4f}   CD {cd:8.4f}   L/D {ld:7.3f}")
    return dict(aoa=aoa, CL=CL, CD=CD, LD=LD)


# =============================== Part B ===============================
def plot_surface_tris(verts, conn, vals, title, fname, cmap="RdBu_r", clim=None):
    """Render a triangulated surface coloured by a scalar, one iso view."""
    v = np.asarray(verts)
    t = np.asarray(conn)
    s = np.asarray(vals).ravel()
    if v.ndim == 2 and v.shape[0] == 3:
        v = v.T
    x, y, z = v[:, 0], v[:, 1], v[:, 2]
    fig = plt.figure(figsize=(11, 5.5))
    for k, (name, (ua, va), az) in enumerate([
            ("planform (x-y)", (0, 1), None), ("side (x-z)", (0, 2), None)]):
        ax = fig.add_subplot(1, 2, k + 1)
        tri = Triangulation(x if ua == 0 else y, [x, y, z][va])
        m = ax.tripcolor(tri, s, cmap=cmap, shading="flat",
                         vmin=None if clim is None else clim[0],
                         vmax=None if clim is None else clim[1])
        ax.set_aspect("equal"); ax.set_title(name)
        ax.set_xlabel(["x", "x"][k]); ax.set_ylabel(["y", "z"][k])
        plt.colorbar(m, ax=ax, fraction=0.046)
    fig.suptitle(title, fontsize=12)
    plt.tight_layout(); plt.savefig(fname, dpi=125); plt.close()
    print("saved", fname)


def part_b(casefiles):
    os.environ.setdefault("PYFLUENT_SHOW_SERVER_GUI", "0")
    from ansys.fluent.core import launch_fluent
    for aoa, cf in casefiles:
        if not os.path.exists(cf):
            print("missing", cf); continue
        s = launch_fluent(mode="solver", precision="double", processor_count=2,
                          cwd=BASE + "/work")
        try:
            s.settings.file.read(file_type="case-data", file_name=cf)
            print(f"\n### AoA {aoa}: read {cf}")
            fd = s.field_data
            print("   field_data:", [a for a in dir(fd) if not a.startswith("_")][:24])

            # airframe wall: pressure coefficient
            walls = [w for w in s.settings.setup.boundary_conditions.wall()
                     if "aircraft" in w.lower()]
            print("   airframe wall zones:", walls)
            for field in ("pressure", "pressure-coefficient"):
                try:
                    d = fd.get_surfaces_data(field, surfaces=walls)
                    print(f"   got {field}: {type(d)} {list(d)[:3] if hasattr(d,'keys') else ''}")
                    break
                except Exception as e:
                    print(f"   {field}: {str(e)[:110]}")
        except Exception as e:
            print("   part_b error:", str(e)[:220])
        s.exit()


if __name__ == "__main__":
    part_a()
