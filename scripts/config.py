# -*- coding: utf-8 -*-
"""
这是唯一需要你修改的文件。改完运行：

    python run_all.py

所有下游脚本（几何修复 / 计算域 / 网格 / 求解 / 后处理 / 出图）都会从本文件
读取参数。`run_all.py` 会把它们转成环境变量再调用各脚本。

参数分组：
    §1  路径与目录
    §2  流水线阶段开关
    §3  几何修复（体素求并）
    §4  外流场计算域（远场盒子）
    §5  网格生成（Fluent Watertight）
    §6  飞行状态与参考量（含 ISA 大气自动计算）
    §7  求解器设置（湍流、松弛、迭代）
    §8  后处理（切面、流线、色标）
    §9  网格出图
    §10 并行与运行

单位约定：长度 m，速度 m/s，温度 K，压强 Pa，密度 kg/m3，粘度 Pa·s，角度 deg。
==============================================================================
"""

import math
import os

# ==============================================================================
# §1 路径与目录
# ==============================================================================

# 项目根目录。本文件位于 <项目根>/scripts/ 下，上溯两级即项目根，一般不需要改。这样从任意工作目录运行脚本都能正确定位产物。
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 输入几何 —— 唯一不可再生的文件。若换成其它飞机，只改这一行。
INPUT_STL = os.path.join(PROJECT_ROOT, "data", "1.stl")

# 生成物根目录（网格 / 计算域 / case），默认在 .gitignore 中，不入库
ARTIFACTS_DIR = os.path.join(PROJECT_ROOT, "artifacts")

# 交付结果目录（图片 / 报表 / 系数），入库
# 做快速冒烟测试时可改成 results_smoke 之类的临时目录，避免覆盖正式结果
RESULTS_DIR = os.path.join(PROJECT_ROOT, "results")

# PyFluent 启动工作目录（Fluent 会在此生成 FM_* 临时目录），运行残留，不入库
WORK_DIR = os.path.join(PROJECT_ROOT, "work")

# 日志目录
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")


# ==============================================================================
# §2 流水线阶段开关  (True = 执行, False = 跳过)
# ==============================================================================
# 典型用法：
#   · 只重跑后处理（网格和 case 已存在）→ 把前四项设为 False
#   · 只想看一下网格长什么样       → 只开 RUN_MESH_PREVIEW

RUN_GEOMETRY = True  # ① 体素求并修复 STL → aircraft_solid.stl
RUN_DOMAIN = True  # ② 生成外流场计算域 → fluid_domain.stl
RUN_MESH = True  # ③ Fluent Watertight 体网格 → aircraft_mesh.msh.h5
RUN_MESH_PREVIEW = True  # ④ 网格出图（切面线框 + 机体表面网格 + 统计）
RUN_SOLVE = True  # ⑤ 各攻角求解 → final_aoa*.cas.h5 / .dat.h5 + forces.json
RUN_EXTRACT = True  # ⑥ 从 case 抽取流场 → results/fields_aoa*.npz
RUN_RENDER = True  # ⑦ 渲染图片 → results/*.png
RUN_REPORT = True  # ⑧ 生成 HTML 报表 → results/report.html

# 若某个阶段出错就立即停止（False = 出错也继续跑下一阶段）
STOP_ON_ERROR = True


# ==============================================================================
# §3 几何修复（voxel_union.py：体素求并 + Marching Cubes）
# ==============================================================================
# 原始 1.stl 是 4 个互相穿插的独立封闭壳体，无法直接做布尔运算。
# 本步把它们合并成一个单一水密实体。

# 体素边长 [m] —— 最重要的几何参数，直接决定表面分辨率与后续网格规模
#   0.06 → 261 956 面（**交付结果用的就是 0.06**）
#   0.12 →  63 620 面（第二轮粗化版，腾预算给棱柱时用）
# 越小越精细但面数∝1/h²、体素内存∝1/h³。低于 0.04 在本机会很慢。
VOXEL = 0.06


# ==============================================================================
# §4 外流场计算域（build_full_domain.py：远场盒子）
# ==============================================================================
# 机体位于 x∈[0, 24.04]、y∈[−11.82, 11.82]、z∈[−1.79, 1.79]。
# 推荐阻塞度 < 1%：上游 1.5 倍机长、下游 2.5 倍机长、上下 5.5 倍机高。
DOMAIN_XMIN = -36.0  # 上游边界 [m]（机头前 36 m ≈ 1.5 L）
DOMAIN_XMAX = 84.0  # 下游边界 [m]（机尾后 60 m ≈ 2.5 L，留给尾流发展）
DOMAIN_YMIN = -33.0  # 侧向 [m]（±33 m ≈ 1.4 倍翼展）
DOMAIN_YMAX = 33.0
DOMAIN_ZMIN = -20.0  # 垂向 [m]（±20 m ≈ 5.6 倍机高）
DOMAIN_ZMAX = 20.0

# 盒子每个面的细分边长 [m]。盒子只是远场边界，不需要细；
# 但太粗（>10）会让体网格在盒子附近产生超大单元。
BOX_EDGE = 8.0


# ==============================================================================
# §5 网格生成（mesh_half.py：Fluent Watertight 工作流）
# ==============================================================================
#  当前参数下约 50 万格（含机体内腔 18 万，求解时删除后流体区约 32 万）。

MIN_SIZE = 0.12  # 全局最小面尺寸 [m]。机体前缘、尾撑等细节由此控制
MAX_SIZE = 2.5  # 全局最大面尺寸 [m]。远场粗化上限，越大越省单元
GROWTH = 1.2  # 面网格增长率（1.1~1.3，越小过渡越平缓、单元越多）
CURV = 12.0  # 曲率法向角 [deg]。越小越贴合曲面（8 精细 / 20 粗糙）
BODY = 0.35  # 机体局部 Body Size [m] —— 控制飞机表面网格疏密的关键

N_LAYERS = 8  # 边界层棱柱层数
FIRST_H = 0.0003  # 棱柱第一层高度 [m]（y+≈1 需 ~1.3e-5 m，本预算做不到）
RATE = 1.3  # 棱柱层间增长率

HEX_MAX = 2.5  # poly-hexcore 中六面体核心的最大尺寸 [m]
VOLFILL = "poly-hexcore"  # 体填充：poly-hexcore（默认）/ poly / tetrahedral
SETUP = "fluid_solid_voids"  # describe_geometry 类型，**必须**是这个值才能成功
SHARE = "Yes"  # 是否调用 share topology（Yes / No）
JOIN = "Join Only"  # 接缝处理方式（不做布尔，只焊接）

MESH_NPROC = 4  # 网格阶段并行核数


# ==============================================================================
# §6 飞行状态与参考量
# ==============================================================================

# ---- 6.1 大气：给高度即可，其余自动按 ISA 计算 ----
ALTITUDE_M = 5000.0  # 飞行高度 [m]（ISA 对流层，0~11 km 内有效）
USE_ISA = True  # True = 由 ALTITUDE_M 自动算 T/p/rho/mu/a
# False = 直接用下面 MANUAL_* 手动指定的值

# ---- 6.2 手动大气参数（仅当 USE_ISA = False 时生效）----
MANUAL_T = 255.65  # 静温 [K]
MANUAL_P = 54019.89  # 静压 [Pa]
MANUAL_RHO = 0.73612  # 密度 [kg/m3]
MANUAL_MU = 1.628e-5  # 动力粘度 [Pa·s]
MANUAL_A = 320.529  # 声速 [m/s]

# ---- 6.3 来流 ----
V_INF = 60.0  # 来流速度 [m/s]（Ma ≈ 0.187 @ 5 km）

# ---- 6.4 参考量（必须与几何一致；改几何后需重跑 refgeom.py 更新）----
SREF = 65.3375  # 机翼参考面积 [m²]
LREF = 4.1996  # 参考长度 = 平均气动弦长 MAC [m]（力矩用）
BREF = 23.6443  # 翼展 [m]
MC = (7.9319, 0.0, 0.0)  # 俯仰力矩取矩中心（1/4 弦点）[m]


def isa(h_m):
    """国际标准大气（ISA）对流层模型，返回 (T, p, rho, a, mu)。

    T = T0 - Λh                       Λ = 6.5 K/km
    p = p0 (1 - Λh/T0)^(g/(RΛ))       由静力平衡 dp = -ρg dh 积分得到
    ρ = p/(RT)                        理想气体
    a = sqrt(γRT)                     等熵声速
    μ = μ0 (T/T0)^1.5 (T0+S)/(T+S)    Sutherland 公式
    """
    T0, p0 = 288.15, 101325.0
    LAP = 0.0065  # 温度递减率 [K/m]
    R, GAMMA, G = 287.05, 1.4, 9.80665
    MU0, S = 1.716e-5, 110.4  # Sutherland 常数

    T = T0 - LAP * h_m
    p = p0 * (1.0 - LAP * h_m / T0) ** (G / (R * LAP))
    rho = p / (R * T)
    a = math.sqrt(GAMMA * R * T)
    mu = MU0 * (T / 273.15) ** 1.5 * (273.15 + S) / (T + S)
    return T, p, rho, a, mu


if USE_ISA:
    T_INF, P_INF, RHO, A_INF, MU = isa(ALTITUDE_M)
else:
    T_INF, P_INF, RHO, A_INF, MU = MANUAL_T, MANUAL_P, MANUAL_RHO, MANUAL_A, MANUAL_MU

# 派生量（只读，供报告与日志使用）
MA_INF = V_INF / A_INF  # 马赫数
Q_INF = 0.5 * RHO * V_INF**2  # 动压 [Pa]
RE_MAC = RHO * V_INF * LREF / MU  # 基于 MAC 的雷诺数


# ==============================================================================
# §7 求解器设置
# ==============================================================================

# ---- 7.1 攻角扫描 ----
AOAS = [0.0, 4.0, 8.0, 12.0]  # 要算的攻角列表 [deg]
# 冒烟测试用 [0.0]，正式跑用 [0, 4, 8, 12]

# ---- 7.2 迭代步数 ----
WARM = 100  # 一阶迎风预热步数（先用一阶稳住流场再切二阶）
ITERS = 300  # 二阶主迭代步数
# 参考耗时：32 万格 / 4 核 ≈ 2.5 s/步 → 300 步 ≈ 12 min/工况
# 冒烟测试可设 WARM=5, ITERS=5

# ---- 7.3 显式松弛（★ 本项目的收敛关键，不要轻易改大）----
# Fluent 耦合求解器默认 0.75。对 Ma=0.187 的低马赫可压外流场会**发散**：
# 曾出现壁面平均压力 59 936 Pa（远高于远场总压 55 355）、C_D 到 1e140。
# 降到 0.4 / 0.5 后域内压力回到 54 025 Pa（远场 54 019.9），侧向力≈0。
PRELAX = 0.4  # 压力显式松弛（0.2~0.5，越小越稳但越慢）
MRELAX = 0.5  # 动量显式松弛（0.3~0.6）

# ---- 7.4 物理模型（改这里需要同步改 final_solve.py 里的代码）----
# 当前固定：压力基耦合求解器 + 理想气体 + k-ω SST + 压力远场边界
# 备注：pressure-far-field 边界**不支持不可压**，所以必须保留理想气体。

# ---- 7.5 要删除的机体内腔 cell zone ----
# 布尔运算会在机体内部留下一个封闭的 cell zone，必须删除，否则会被当流体求解
# 导致压力崩塌、阻力为负。
#   WTM 网格（mesh_half.py 产出）: 内腔叫 "aircraft"，机体壁面叫 "aircraft-fluid_box"
#   Prime 网格（prime_mesh.py 产出）: 内腔叫 "model.1"
DELZONE = "aircraft"

SOLVE_NPROC = 4  # 求解阶段并行核数


# ==============================================================================
# §8 后处理
# ==============================================================================

# ---- 8.1 流向站位（尾涡横截面）----
# 机体 x 范围 0 → 24.04 m，建议既有翼上站位也有下游站位
STATIONS = [8, 15, 24, 34, 48]  # [m]

# ---- 8.2 流线种子（上游播种，让流线自然卷起）----
# 格式：(名字, 起点(x,y,z), 终点(x,y,z))
# 翼尖 y = ±11.82 m，故 tip 种子放在 9.4~12.8 之间
PATHLINE_SEEDS = [
    ("seed_line", (-12, 0, -7), (-12, 0, 7)),  # 对称面全域
    ("seed_line_hi", (-12, 0, -4), (-12, 0, 4)),  # 对称面近场
    ("seed_tip", (-6, 9.4, 0.0), (-6, 11.9, 0.0)),  # 翼尖涡
    ("seed_tip2", (-6, 11.9, 0.6), (-6, 12.8, 0.6)),  # 翼尖外侧
    ("seed_mid", (-6, 3.0, 0.2), (-6, 7.0, 0.2)),  # 中段翼展
]
PATHLINE_STEPS = 230  # 积分步数
PATHLINE_STEP_SIZE = 0.35  # 每步长度 [m]（230 × 0.35 ≈ 80 m，覆盖整个域）
PATHLINE_TOL = 0.001  # 积分精度容差

POST_NPROC = 4  # 后处理阶段并行核数


# ==============================================================================
# §9 网格出图（mesh_preview.py）
# ==============================================================================
# 在网格生成之后立即产出 3~4 张图，便于在花时间求解之前先确认网格质量。

MESH_PREVIEW_SLICES = ["y0", "z0", "x12"]
#   可选切面（同时决定画几张切面图）：
#     "y0"  → y = 0   对称面剖切（看机翼剖面处的体网格）
#     "z0"  → z = 0   水平面剖切
#     "x12" → x = 12  横向站位剖切
MESH_PREVIEW_MAX_FACES = 60000  # 线框最大面数，超过则随机抽稀（防止画图卡死）
MESH_PREVIEW_DPI = 130  # 图片分辨率


# ==============================================================================
# §10 并行与运行
# ==============================================================================

# 求解精度：Fluent 的 precision 参数。"double" 更稳（推荐），"single" 省内存
FLUENT_PRECISION = "double"

# Fluent 是否显示 GUI（无头运行必须为 0）
PYFLUENT_SHOW_SERVER_GUI = "0"


# ==============================================================================
# 以下为派生量，一般不用改
# ==============================================================================

SOLID_STL = os.path.join(ARTIFACTS_DIR, "geometry", "aircraft_solid.stl")
DOMAIN_STL = os.path.join(ARTIFACTS_DIR, "geometry", "fluid_domain.stl")
MESH_FILE = os.path.join(ARTIFACTS_DIR, "mesh", "aircraft_mesh.msh.h5")
CASE_FMT = os.path.join(ARTIFACTS_DIR, "cases", "final_aoa%d.cas.h5")


def summary():
    """打印一份参数摘要（run_all.py 启动时会调用）。"""
    return f"""\
  输入几何   : {INPUT_STL}
  体素尺寸   : {VOXEL} m
  计算域     : x[{DOMAIN_XMIN}, {DOMAIN_XMAX}]  y[{DOMAIN_YMIN}, {DOMAIN_YMAX}]  z[{DOMAIN_ZMIN}, {DOMAIN_ZMAX}]
  网格       : min={MIN_SIZE}  max={MAX_SIZE}  body={BODY}  curv={CURV}  fill={VOLFILL}
  高度/速度  : {ALTITUDE_M / 1000:g} km ISA,  V = {V_INF} m/s,  Ma = {MA_INF:.4f}
  大气       : T={T_INF:.2f} K, p={P_INF:.1f} Pa, rho={RHO:.5f} kg/m3, mu={MU:.4e}
  动压/雷诺  : q = {Q_INF:.2f} Pa,  Re_MAC = {RE_MAC:.3e}
  参考量     : S={SREF} m2, MAC={LREF} m, b={BREF} m
  攻角       : {AOAS}
  迭代       : warm={WARM} + main={ITERS}   松弛: p={PRELAX}, mom={MRELAX}
  删除内腔   : {DELZONE}
  站位       : {STATIONS}
  结果目录   : {RESULTS_DIR}
"""
