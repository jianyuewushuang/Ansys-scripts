"""网格出图：在求解之前先看清网格长什么样。

产出（写到 <项目根>/results/）：
    mesh_slice_y0.png      y = 0    对称面剖切（体网格线框）
    mesh_slice_z0.png      z = 0    水平面剖切
    mesh_slice_x12.png     x = 12 m 横向站位剖切
    mesh_surface.png       机体表面网格的三视图线框
    mesh_stats.json        单元数 / 各分区面数 / 网格质量

用法：
    ./.venv/Scripts/python.exe scripts/02_mesh/mesh_preview.py
    MSH=<其它网格> ./.venv/Scripts/python.exe scripts/02_mesh/mesh_preview.py
"""

import os
import json
import time

os.environ.setdefault("PYFLUENT_SHOW_SERVER_GUI", "0")

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection

BASE = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))   # <project root>

MESH = os.environ.get("MSH", os.path.join(BASE, "artifacts", "mesh",
                                          "aircraft_mesh.msh.h5"))
OUT = os.environ.get("RESULTS_DIR", os.path.join(BASE, "results"))
os.makedirs(OUT, exist_ok=True)

WORK = os.environ.get("WORK_DIR", os.path.join(BASE, "work"))
NPROC = int(os.environ.get("NPROC", 4))
MAX_FACES = int(os.environ.get("MESH_MAX_FACES", 60000))
DPI = int(os.environ.get("MESH_DPI", 130))
SLICES = [s.strip() for s in os.environ.get("MESH_SLICES", "y0,z0,x12").split(",")]

# 切面定义：名字 -> (Fluent 平面类型, 坐标名, 坐标值)
#   yz-plane -> x 常数 ; zx-plane -> y 常数 ; xy-plane -> z 常数
SLICE_DEF = {
    "y0": ("zx-plane", "y", 0.0),
    "z0": ("xy-plane", "z", 0.0),
    "x12": ("yz-plane", "x", 12.0),
    "x24": ("yz-plane", "x", 24.0),
}

t0 = time.time()


def log(*a):
    print("[%7.1fs]" % (time.time() - t0), *a, flush=True)


def edges_of(verts, conn, limit, seed=0):
    """把多边形连接表转成线段数组 (nseg, 2, 3)；超过 limit 张面就随机抽稀。"""
    rng = np.random.default_rng(seed)
    idx = np.arange(len(conn))
    if len(conn) > limit:
        idx = rng.choice(idx, size=limit, replace=False)
    seg = []
    for i in idx:
        c = np.asarray(conn[i], dtype=np.int64).ravel()
        n = len(c)
        for k in range(n):
            seg.append([verts[c[k]], verts[c[(k + 1) % n]]])
    return np.array(seg, dtype=np.float64)


def draw(ax, segs, proj, title, color="#1f3d6b"):
    """proj = 两个轴索引，例如 (0,1) = x-y 平面"""
    if segs is None or not len(segs):
        ax.text(0.5, 0.5, "no data", ha="center", va="center",
                transform=ax.transAxes)
        return
    s = segs[:, :, proj]          # (nseg, 2, 2)
    lc = LineCollection(s, colors=color, linewidths=0.28, alpha=0.75)
    ax.add_collection(lc)
    ax.autoscale()
    ax.set_aspect("equal")
    ax.set_title(title, fontsize=10)
    ax.margins(0.02)


def main():
    from ansys.fluent.core import launch_fluent
    from ansys.fluent.core.fields.field_data_interfaces import (
        SurfaceFieldDataRequest, SurfaceDataType)

    log("launching Fluent ...")
    s = launch_fluent(mode="solver",
                      precision=os.environ.get("FLUENT_PRECISION", "double"),
                      processor_count=NPROC,
                      cwd=WORK)
    st = s.settings
    fd = getattr(s, "field_data", None) or s.fields.field_data

    log("reading mesh:", MESH)
    st.file.read(file_type="mesh", file_name=MESH)

    # ---------------- 统计信息 ----------------
    info = {"mesh": MESH}
    try:
        bcs = st.setup.boundary_conditions
        walls = list(bcs.wall().keys()) if callable(bcs.wall) else []
        info["wall_zones"] = walls
    except Exception as e:
        walls, info["wall_zones_err"] = [], str(e)[:120]

    try:
        cz = st.setup.cell_zone_conditions
        names = []
        for g in ("fluid", "solid"):
            o = getattr(cz, g, None)
            if o is None:
                continue
            try:
                names += list(o().keys()) if callable(o) else o.get_object_names()
            except Exception:
                pass
        info["cell_zones"] = names
    except Exception as e:
        info["cell_zones_err"] = str(e)[:120]

    # 单元数 / 网格检查 / 质量。
    # PyFluent 的 execute_tui 对这些命令返回 None，文本只写进 transcript 文件，
    # 所以这里执行后去读 work/*.trn 的新增内容。
    import glob

    def tui_capture(cmd):
        trn = glob.glob(os.path.join(WORK, "*.trn"))
        before = {f: os.path.getsize(f) for f in trn}
        try:
            s.execute_tui("/" + cmd)
        except Exception:
            pass
        time.sleep(0.4)
        chunks = []
        for f in glob.glob(os.path.join(WORK, "*.trn")):
            sz = os.path.getsize(f)
            if sz > before.get(f, 0):
                with open(f, errors="ignore") as fh:
                    fh.seek(before.get(f, 0))
                    chunks.append(fh.read())
        return "\n".join(chunks).strip()

    for key, cmd, fn in (("size_info", "mesh/size-info", None),
                         ("check", "mesh/check", lambda: st.mesh.check()),
                         ("quality", "mesh/quality", lambda: st.mesh.quality())):
        txt = tui_capture(cmd)
        if not txt:
            try:
                txt = str((fn() if fn else "") or "")
            except Exception as e:
                txt = "unavailable: " + str(e)[:120]
        info[key] = txt.strip()[:4000] if txt.strip() else "(not reported)"
        log("   %-9s -> %s" % (key, info[key].replace("\n", " | ")[:100]))

    # ---------------- 机体壁面表面网格 ----------------
    # 面数最多的 wall 就是机体（远场盒子只有几千面）
    wall = None
    if walls:
        counts = {}
        for w in walls:
            try:
                sd = fd.get_field_data(SurfaceFieldDataRequest(
                    surfaces=[w], data_types=[SurfaceDataType.FacesConnectivity]))
                counts[w] = len(list(sd[w].connectivity))   # 面数（不是连接表长度）
            except Exception:
                counts[w] = -1
        info["wall_face_counts"] = counts
        wall = max(counts, key=lambda k: counts[k]) if counts else None
    log("airframe wall zone:", wall)

    surf = None
    if wall:
        try:
            sd = fd.get_field_data(SurfaceFieldDataRequest(
                surfaces=[wall],
                data_types=[SurfaceDataType.Vertices,
                            SurfaceDataType.FacesConnectivity]))
            surf = (np.asarray(sd[wall].vertices),
                    [np.asarray(c) for c in sd[wall].connectivity])
            info["airframe_faces"] = len(surf[1])
            log("airframe surface mesh: %d faces" % len(surf[1]))
        except Exception as e:
            log("wall mesh fail:", str(e)[:120])

    # ---------------- 切面 ----------------
    slices = {}
    surfapi = s.settings.results.surfaces
    for name in SLICES:
        if name not in SLICE_DEF:
            continue
        method, coord, val = SLICE_DEF[name]
        try:
            surfapi.plane_surface.__setitem__(
                name, {"method": method, coord: val})
            log("+ plane", name)
        except Exception as e:
            log("! plane %s: %s" % (name, str(e)[:110]))
            continue
        try:
            sd = fd.get_field_data(SurfaceFieldDataRequest(
                surfaces=[name],
                data_types=[SurfaceDataType.Vertices,
                            SurfaceDataType.FacesConnectivity]))
            conn = [np.asarray(c) for c in sd[name].connectivity]
            slices[name] = (np.asarray(sd[name].vertices), conn)
            log("   %-4s : %d faces" % (name, len(conn)))
        except Exception as e:
            log("! slice %s: %s" % (name, str(e)[:110]))

    # ---------------- 画图 ----------------
    # 1) 每个切面单独一张图（沿其自然平面）
    proj_of = {"y0": (0, 2), "z0": (0, 1), "x12": (1, 2), "x24": (1, 2)}
    axislab = {0: "x  [m]", 1: "y  [m]", 2: "z  [m]"}
    for name, data in slices.items():
        verts, conn = data
        per = max(1, MAX_FACES)
        segs = edges_of(verts, conn, per, seed=1)
        fig, ax = plt.subplots(figsize=(13, 7))
        p = proj_of.get(name, (0, 1))
        draw(ax, segs, p, "%s  slice — %d faces (showing %d)" %
             (name, len(conn), min(len(conn), per)))
        ax.set_xlabel(axislab[p[0]])
        ax.set_ylabel(axislab[p[1]])
        fig.suptitle("Volume mesh — %s cut" % name, fontsize=12)
        fig.tight_layout()
        fn = os.path.join(OUT, "mesh_slice_%s.png" % name)
        fig.savefig(fn, dpi=DPI)
        plt.close(fig)
        log("saved", fn)

    # 2) 机体表面网格三视图
    if surf is not None:
        verts, conn = surf
        per = max(1, MAX_FACES // 3)
        fig, ax = plt.subplots(1, 3, figsize=(16, 5.2))
        for k, (p, ttl) in enumerate([((0, 1), "planform  (x-y)"),
                                      ((0, 2), "side  (x-z)"),
                                      ((1, 2), "front  (y-z)")]):
            segs = edges_of(verts, conn, per, seed=2 + k)
            draw(ax[k], segs, p, "%s — %d faces total" % (ttl, len(conn)),
                 color="#2c3e50")
            ax[k].set_xlabel(axislab[p[0]])
            ax[k].set_ylabel(axislab[p[1]])
        fig.suptitle("Airframe surface mesh (%s)" % wall, fontsize=12)
        fig.tight_layout()
        fn = os.path.join(OUT, "mesh_surface.png")
        fig.savefig(fn, dpi=DPI)
        plt.close(fig)
        log("saved", fn)

    # 3) 统计
    fn = os.path.join(OUT, "mesh_stats.json")
    json.dump(info, open(fn, "w"), indent=2, default=str)
    log("saved", fn)

    s.exit()
    log("MESH PREVIEW DONE")


if __name__ == "__main__":
    main()
