#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
==============================================================================
这是唯一需要手动运行的脚本
==============================================================================

只改 `config.py`，然后：

    python run_all.py

阶段顺序：
    ① geometry      体素求并修复 STL          scripts/01_geometry/voxel_union.py
    ② domain        生成外流场计算域           scripts/01_geometry/build_full_domain.py
    ③ mesh          Fluent Watertight 体网格   scripts/02_mesh/mesh_half.py
    ④ meshpreview   网格出图                   scripts/02_mesh/mesh_preview.py
    ⑤ solve         各攻角求解                 scripts/03_solve/final_solve.py
    ⑥ extract       抽取流场                   scripts/04_post/extract_post.py
    ⑦ render        渲染图片                   scripts/04_post/render_post.py
    ⑧ report        生成 HTML 报表             scripts/04_post/make_report.py

常用命令行覆盖（优先级高于 config.py）：

    # 只跑后处理（网格与 case 已存在）
    python run_all.py --only extract,render,report

    # 快速冒烟测试：单个攻角、极少迭代，结果写到临时目录
    python run_all.py --only solve,extract,render \
        --aoa 0 --warm 5 --iters 5 --results results_smoke

    # 跳过耗时最长的网格与求解
    python run_all.py --skip mesh,solve

    # 试用新参数但不动正式产物（几何/网格/case 全部写到临时目录）
    python run_all.py --voxel 0.08 --artifacts work/_trial

    # 只看参数，不实际执行
    python run_all.py --dry-run
==============================================================================
"""

import argparse
import os
import subprocess
import sys
import time

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SCRIPTS_DIR)  # <项目根>
sys.path.insert(0, SCRIPTS_DIR)

import config as C  # noqa: E402

PY = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
if not os.path.exists(PY):
    PY = sys.executable

STAGES = [
    "geometry",
    "domain",
    "mesh",
    "meshpreview",
    "solve",
    "extract",
    "render",
    "report",
]

ENABLED = {
    "geometry": C.RUN_GEOMETRY,
    "domain": C.RUN_DOMAIN,
    "mesh": C.RUN_MESH,
    "meshpreview": C.RUN_MESH_PREVIEW,
    "solve": C.RUN_SOLVE,
    "extract": C.RUN_EXTRACT,
    "render": C.RUN_RENDER,
    "report": C.RUN_REPORT,
}

# 每个阶段：(脚本相对路径, 人类可读说明)
SCRIPT = {
    "geometry": ("01_geometry/voxel_union.py", "体素求并修复几何"),
    "domain": ("01_geometry/build_full_domain.py", "生成外流场计算域"),
    "mesh": ("02_mesh/mesh_half.py", "Fluent WTM 体网格"),
    "meshpreview": ("02_mesh/mesh_preview.py", "网格出图"),
    "solve": ("03_solve/final_solve.py", "攻角扫描求解"),
    "extract": ("04_post/extract_post.py", "抽取流场"),
    "render": ("04_post/render_post.py", "渲染图片"),
    "report": ("04_post/make_report.py", "生成 HTML 报表"),
}


# ---------------------------------------------------------------- 环境构造
def build_env():
    """把 config.py 的参数翻译成各脚本读取的环境变量。"""
    e = dict(os.environ)
    e.update(
        {
            # 运行
            "PYFLUENT_SHOW_SERVER_GUI": C.PYFLUENT_SHOW_SERVER_GUI,
            "FLUENT_PRECISION": C.FLUENT_PRECISION,
            "RESULTS_DIR": C.RESULTS_DIR,
            "WORK_DIR": C.WORK_DIR,
            # 几何
            "VOXEL": str(C.VOXEL),
            "INPUT_STL": C.INPUT_STL,  # voxel_union 的输入
            "SRC": C.SOLID_STL,  # build_full_domain 的输入
            # 计算域
            "XMIN": str(C.DOMAIN_XMIN),
            "XMAX": str(C.DOMAIN_XMAX),
            "YMIN": str(C.DOMAIN_YMIN),
            "YMAX": str(C.DOMAIN_YMAX),
            "ZMIN": str(C.DOMAIN_ZMIN),
            "ZMAX": str(C.DOMAIN_ZMAX),
            "BOX_EDGE": str(C.BOX_EDGE),
            # 网格
            "DOM": C.DOMAIN_STL,
            "MSH": C.MESH_FILE,
            "MIN_SIZE": str(C.MIN_SIZE),
            "MAX_SIZE": str(C.MAX_SIZE),
            "GROWTH": str(C.GROWTH),
            "CURV": str(C.CURV),
            "BODY": str(C.BODY),
            "N_LAYERS": str(C.N_LAYERS),
            "FIRST_H": str(C.FIRST_H),
            "RATE": str(C.RATE),
            "HEX_MAX": str(C.HEX_MAX),
            "VOLFILL": C.VOLFILL,
            "SETUP": C.SETUP,
            "SHARE": C.SHARE,
            "JOIN": C.JOIN,
            "NPROC": str(C.MESH_NPROC),
            # 网格出图
            "MESH_SLICES": ",".join(C.MESH_PREVIEW_SLICES),
            "MESH_MAX_FACES": str(C.MESH_PREVIEW_MAX_FACES),
            "MESH_DPI": str(C.MESH_PREVIEW_DPI),
            # 来流与参考量
            "T_INF": str(C.T_INF),
            "P_INF": str(C.P_INF),
            "RHO": str(C.RHO),
            "MU": str(C.MU),
            "V_INF": str(C.V_INF),
            "A_INF": str(C.A_INF),
            "SREF": str(C.SREF),
            "LREF": str(C.LREF),
            "BREF": str(C.BREF),
            "Q_INF": str(C.Q_INF),
            "MC": ",".join(str(x) for x in C.MC),
            # 求解
            "AOAS": ",".join(str(a) for a in C.AOAS),
            "WARM": str(C.WARM),
            "ITERS": str(C.ITERS),
            "PRELAX": str(C.PRELAX),
            "MRELAX": str(C.MRELAX),
            "DELZONE": C.DELZONE,
            "CASE_FMT": C.CASE_FMT,
            # 后处理
            "STATIONS": ",".join(str(s) for s in C.STATIONS),
        }
    )
    return e


def run_stage(name, env, logf):
    rel, desc = SCRIPT[name]
    path = os.path.join(SCRIPTS_DIR, rel)
    print("\n" + "=" * 74, flush=True)
    print("阶段 %-12s %s" % (name.upper(), desc), flush=True)
    print("脚本 %s" % rel, flush=True)
    print("=" * 74, flush=True)

    env = dict(env)
    if name == "solve":
        env["NPROC"] = str(C.SOLVE_NPROC)
    if name in ("meshpreview", "extract", "render"):
        env["NPROC"] = str(C.POST_NPROC)
    # 几何两步共用 OUT 变量，按阶段分别指定
    if name == "geometry":
        env["OUT"] = C.SOLID_STL
    if name == "domain":
        env["OUT"] = C.DOMAIN_STL

    t = time.time()
    proc = subprocess.Popen(
        [PY, path],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    for line in proc.stdout:
        line = line.rstrip("\n")
        print(line, flush=True)
        if logf:
            logf.write(line + "\n")
            logf.flush()
    rc = proc.wait()
    dt = time.time() - t
    status = "OK " if rc == 0 else "FAIL"
    print("---- %s  %s  (%.1f s) ----" % (status, name, dt), flush=True)
    if logf:
        logf.write("---- %s %s (%.1f s) ----\n" % (status, name, dt))
        logf.flush()
    return rc


def main():
    ap = argparse.ArgumentParser(description="一键运行无人机 CFD 全流程")
    ap.add_argument("--only", help="只跑指定阶段，逗号分隔，如 mesh,solve")
    ap.add_argument("--skip", help="跳过指定阶段，逗号分隔")
    ap.add_argument("--aoa", help="覆盖 config.AOAS，如 0 或 0,4,8,12")
    ap.add_argument("--warm", type=int, help="覆盖 config.WARM")
    ap.add_argument("--iters", type=int, help="覆盖 config.ITERS")
    ap.add_argument("--voxel", type=float, help="覆盖 config.VOXEL")
    ap.add_argument("--results", help="覆盖 config.RESULTS_DIR")
    ap.add_argument(
        "--cases-dir",
        help="覆盖 case 输出目录（默认 artifacts/cases）；"
        "冒烟测试时指向临时目录可避免覆盖正式 case",
    )
    ap.add_argument(
        "--artifacts",
        help="覆盖全部生成物根目录（几何/网格/case 一起搬走）；"
        "适合在不影响正式产物的情况下试用新参数",
    )
    ap.add_argument("--nproc", type=int, help="覆盖所有阶段的并行核数")
    ap.add_argument(
        "--dry-run", action="store_true", help="只打印参数与将要执行的阶段，不实际运行"
    )
    args = ap.parse_args()

    # ---- 命令行覆盖 ----
    if args.aoa:
        C.AOAS = [float(x) for x in args.aoa.split(",")]
    if args.warm is not None:
        C.WARM = args.warm
    if args.iters is not None:
        C.ITERS = args.iters
    if args.voxel is not None:
        C.VOXEL = args.voxel
    if args.results:
        C.RESULTS_DIR = os.path.abspath(args.results)
    if args.artifacts:
        C.ARTIFACTS_DIR = os.path.abspath(args.artifacts)
        C.SOLID_STL = os.path.join(C.ARTIFACTS_DIR, "geometry", "aircraft_solid.stl")
        C.DOMAIN_STL = os.path.join(C.ARTIFACTS_DIR, "geometry", "fluid_domain.stl")
        C.MESH_FILE = os.path.join(C.ARTIFACTS_DIR, "mesh", "aircraft_mesh.msh.h5")
        C.CASE_FMT = os.path.join(C.ARTIFACTS_DIR, "cases", "final_aoa%d.cas.h5")
    if args.cases_dir:
        d = os.path.abspath(args.cases_dir)
        os.makedirs(d, exist_ok=True)
        C.CASE_FMT = os.path.join(d, "final_aoa%d.cas.h5")
    if args.nproc:
        C.MESH_NPROC = C.SOLVE_NPROC = C.POST_NPROC = args.nproc

    plan = list(STAGES)
    if args.only:
        want = [s.strip() for s in args.only.split(",")]
        plan = [s for s in plan if s in want]
    if args.skip:
        drop = [s.strip() for s in args.skip.split(",")]
        plan = [s for s in plan if s not in drop]
    plan = [s for s in plan if ENABLED.get(s, True)]

    print("=" * 74)
    print(" 无人机 CFD 全流程   ——   参数来自 config.py")
    print("=" * 74)
    print(C.summary())
    print("执行阶段 : " + (" → ".join(plan) if plan else "(无)"))
    print("预计耗时 : 含网格与 4 攻角 × 300 步约 60 分钟；仅后处理约 4 分钟")

    if args.dry_run:
        print("\n[dry-run] 不实际执行。")
        return 0

    os.makedirs(C.LOG_DIR, exist_ok=True)
    os.makedirs(C.RESULTS_DIR, exist_ok=True)
    os.makedirs(C.WORK_DIR, exist_ok=True)
    for sub in ("geometry", "mesh", "cases"):
        os.makedirs(os.path.join(C.ARTIFACTS_DIR, sub), exist_ok=True)

    env = build_env()
    stamp = time.strftime("%Y%m%d_%H%M%S")
    logpath = os.path.join(C.LOG_DIR, "run_all_%s.log" % stamp)
    t_all = time.time()
    failed = []

    with open(logpath, "w", encoding="utf-8") as logf:
        logf.write("run_all  %s\n" % stamp)
        logf.write(C.summary())
        for stage in plan:
            rc = run_stage(stage, env, logf)
            if rc != 0:
                failed.append(stage)
                if C.STOP_ON_ERROR:
                    print("\n!! 阶段 %s 失败，已停止。" % stage, flush=True)
                    break

    print("\n" + "=" * 74)
    print("总耗时 %.1f 分钟" % ((time.time() - t_all) / 60.0))
    print("日志   %s" % logpath)
    print("结果   %s" % C.RESULTS_DIR)
    if failed:
        print("失败阶段: " + ", ".join(failed))
        print("=" * 74)
        return 1
    print("全部阶段完成")
    print("  · 报表   : %s" % os.path.join(C.RESULTS_DIR, "report.html"))
    print("  · 系数   : %s" % os.path.join(C.RESULTS_DIR, "forces.json"))
    print("  · 网格图 : %s" % os.path.join(C.RESULTS_DIR, "mesh_surface.png"))
    print("=" * 74)
    return 0


if __name__ == "__main__":
    sys.exit(main())
