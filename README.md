# Ansys Scripts to Make CFD Very Simple

用python脚本无痛跑Ansys Fluent CFD仿真。

> 测试求解器：ANSYS Fluent 2026 R1 + PyFluent 0.42.1

## 快速开始

```bash
# 进入项目根目录
cd path/to/your/project
# 输出参数
python scripts/run_all.py --dry-run
# 跑完整流程
python scripts/run_all.py
```

结果在 `results/`中。

只想重跑后处理（已有网格和 case ）：

```bash
python scripts/run_all.py --only extract,render,report
```

## 目录结构

```
UAVdesign20261004/
├── README.md
├── LICENSE.md
├── .gitignore
│
├── docs/
│   └── 后处理结果与气动分析详解.md
│
├── scripts/                    全部源码
│   ├── config.py               参数配置入口
│   ├── run_all.py              全流程脚本
│   ├── 01_geometry/  (9)       几何解析 · 体素修复 · 计算域构建
│   ├── 02_mesh/      (4)       Fluent 网格生成 · 网格出图
│   ├── 03_solve/     (1)       多攻角求解
│   ├── 04_post/      (3)       抽取流场 · 渲染图片 · 生成报表
│   └── 05_verify/    (6)       校验与体检（MCP / 网格 / 流场 / y⁺）
│
├── data/                       输入
│   └── 1.stl                   .stl几何文件
│
├── artifacts/                   生成物
│   ├── geometry/               aircraft_solid.stl、fluid_domain.stl
│   ├── mesh/                   aircraft_mesh.msh.h5（网格）
│   └── cases/                  final_aoa{0,4,8,12}.cas.h5 + .dat.h5
│
├── results/                    交付结果
│   ├── *.png                   后处理图 + 网格图
│   ├── report.html             单页 HTML 报表
│   ├── forces.json              力系数与收敛史
│   ├── refgeom.json / refvalues.json / forces_raw.json
│   ├── mesh_stats.json          网格统计
│   └── fields_aoa*.npz         中间流场数据
│
├── work/                        PyFluent 启动工作目录
└── logs/                        运行日志
```

### 各目录作用

| 目录 | 作用 |
| --- | --- |
| **`docs/`** | 文档 |
| **`scripts/`** | 全部 Python 源码，按流水线阶段分级命名 |
| **`scripts/config.py`** | 所有可调参数的唯一来源 |
| **`scripts/run_all.py`** | 8 阶段总控，把 config 翻成环境变量后逐阶段调用子脚本 |
| **`scripts/common.py`** | 各阶段共用的小工具：PyFluent 已知缺陷绕行、连接表格式转换、TUI 转义 |
| **`scripts/01_geometry`** | STL 度量、连通分量诊断、体素求并修复、外流场域构建、参考量计算、三视图 |
| **`scripts/02_mesh`** | Fluent Watertight 网格 + 网格出图 |
| **`scripts/03_solve`** | 删内腔 → 物理模型 → 显式松弛 → 预热+主迭代 → 每 50 步报系数 → 存 case |
| **`scripts/04_post`** | 抽流场到 npz、npz 渲染成图、生成 HTML 报表 |
| **`scripts/05_verify`** | 体检脚本：MCP 握手、网格分区、流场压力/马赫、发散诊断、y⁺ 测量 |
| **`data/`** | .stl几何文件 |
| **`artifacts/`** | 生成的几何 / 网格 / case |
| **`results/`** | 图片、报表、系数 |
| **`work/`** | Fluent 启动时的 cwd |
| **`logs/`** | 每次运行的完整日志 |

## 使用方法

### 一键运行

```bash
python scripts/run_all.py
```

依次执行 8 个阶段：

| | 阶段 | 脚本 | 主要产物 | 耗时估计 |
| ---: | --- | --- | --- | ---: |
| 1 | `geometry` | `scripts/01_geometry/voxel_union.py` | `artifacts/geometry/aircraft_solid.stl` | 2–8 min |
| 2 | `domain` | `scripts/01_geometry/build_full_domain.py` | `artifacts/geometry/fluid_domain.stl` | < 1 min |
| 3 | `mesh` | `scripts/02_mesh/mesh_half.py` | `artifacts/mesh/aircraft_mesh.msh.h5` | 2–6 min |
| 4 | `meshpreview` | `scripts/02_mesh/mesh_preview.py` | `results/mesh_*.png` + `mesh_stats.json` | 1.5–3 min |
| 5 | `solve` | `scripts/03_solve/final_solve.py` | `artifacts/cases/final_aoa*.cas.h5` + `results/forces.json` | ~12 min/工况 |
| 6 | `extract` | `scripts/04_post/extract_post.py` | `results/fields_aoa*.npz` | ~2.5 min |
| 7 | `render` | `scripts/04_post/render_post.py` | `results/*.png` | ~30 s |
| 8 | `report` | `scripts/04_post/make_report.py` | `results/report.html` | < 1 s |

日志同时打印到屏幕并写入 `logs/run_all_<时间戳>.log`。

### 常用命令行覆盖

> 优先级高于 `scripts/config.py`

```bash
# 只看参数，不执行
python scripts/run_all.py --dry-run

# 只跑指定阶段
python scripts/run_all.py --only meshpreview
python scripts/run_all.py --only extract,render,report

# 跳过耗时阶段
python scripts/run_all.py --skip mesh,solve

# 快速冒烟测试（单攻角、5 步迭代，写入临时目录，不碰正式结果）
python scripts/run_all.py --only solve,extract,render,report \
    --aoa 0 --warm 5 --iters 5 \
    --results work/_smoke_results --cases-dir work/_smoke_cases

# 试用新参数但不动正式产物（几何/网格/case 全部写到临时目录）
python scripts/run_all.py --voxel 0.08 --artifacts work/_trial

# 其它
python scripts/run_all.py --nproc 8        # 并行核数
python scripts/run_all.py --iters 500      # 主迭代步数
```

完整参数列表见 `run_all.py --help`。

### 调参

**只改 `scripts/config.py`**

| 组 | 关键参数 | 说明 |
| --- | --- | --- |
| §1 路径 | `INPUT_STL`、`RESULTS_DIR`、`ARTIFACTS_DIR` | 换模型只改 `INPUT_STL` |
| §2 开关 | `RUN_GEOMETRY` … `RUN_REPORT` | 8 个阶段各一个 True/False |
| §3 几何 | `VOXEL` | 体素边长；0.06 精细（26 万面）/ 0.12 粗化（6.4 万面） |
| §4 计算域 | `DOMAIN_XMIN` … `ZMAX`、`BOX_EDGE` | 远场盒子范围 |
| §5 网格 | `MIN_SIZE`、`MAX_SIZE`、`CURV`、`BODY`、`VOLFILL`、`SETUP` | `BODY` 控制机体表面疏密 |
| §6 飞行状态 | `ALTITUDE_M`、`V_INF`、`SREF`、`LREF`、`BREF`、`MC` | 只给高度和速度，大气按 ISA 自动算 |
| §7 求解 | `AOAS`、`WARM`、`ITERS`、`PRELAX`、`MRELAX`、`DELZONE` | 松弛 0.4/0.5 是本项目收敛关键 |
| §8 后处理 | `STATIONS`、`PATHLINE_SEEDS` | 尾涡站位与流线种子 |
| §9 网格出图 | `MESH_PREVIEW_SLICES`、`MESH_PREVIEW_MAX_FACES` | 切面选择与抽稀上限 |
| §10 并行 | `MESH_NPROC`、`SOLVE_NPROC`、`POST_NPROC` | 各阶段核数 |

### 单独出网格图

在花时间求解之前先确认网格质量：

```bash
python scripts/run_all.py --only meshpreview
```

产出：

- `results/mesh_slice_y0.png` / `mesh_slice_z0.png` / `mesh_slice_x12.png` —— 体网格切面线框
- `results/mesh_surface.png` —— 机体表面网格三视图
- `results/mesh_stats.json` —— 单元数、分区面数、网格质量

### 体检

```bash
python scripts/05_verify/probe25.py        # 近壁 y⁺
python scripts/05_verify/check_fields.py   # 远场压力/马赫、质量流平衡
python scripts/05_verify/check_mcp.py      # MCP 服务器握手
```

## 环境要求

| 组件 | 版本 |
| --- | --- |
| 操作系统 | Windows |
| ANSYS | 2026 R1（v261），含 Fluent |
| Python | 3.14.7 |
| 关键包 | `ansys-fluent-core` 0.42.1、`ansys-fluent-mcp` 0.5.0、`ansys-meshing-prime` 0.10.4、 `pyvista` 0.49、`matplotlib` 3.11、`numpy` 2.5、`scikit-image` 0.26、`pymeshlab`、`mapbox_earcut` |
