"""Extract lift / drag / pitching moment from every solved case.

Important: the airframe wall is a two-sided baffle
('aircraft-fluid_box' + '...-shadow').  Only the side seen from the fluid box is
the real wetted surface - including the shadow adds the (stagnant) pressure
inside the airframe and gives nonsense such as negative drag.
"""
import os, json, math
os.environ.setdefault("PYFLUENT_SHOW_SERVER_GUI", "0")
from ansys.fluent.core import launch_fluent

BASE = r"C:/Users/jianyuewushuang/document/model/ansys/UAVdesign20261004"
OUT = os.path.join(BASE, "results")
os.makedirs(OUT, exist_ok=True)

SREF = 65.3375
LREF = 4.1996
QINF = 1325.016
MOMENT_CENTRE = [7.9319, 0.0, 0.0]
AOAS = [0.0, 4.0, 8.0, 12.0]

s = launch_fluent(mode="solver", precision="double", processor_count=2, cwd=BASE + "/mesh_work")
st = s.settings
results = []

for aoa in AOAS:
    case = os.path.join(BASE, f"uav_aoa{int(aoa)}.cas.h5")
    if not os.path.exists(case):
        print("missing", case)
        continue
    st.file.read(file_type="case-data", file_name=case)
    bcs = st.setup.boundary_conditions
    walls = list(bcs.wall().keys()) if callable(bcs.wall) else []
    outer_side = [w for w in walls if "aircraft" in w.lower() and "shadow" not in w.lower()]
    print(f"\n### AoA {aoa}: airframe side = {outer_side}")

    a = math.radians(aoa)
    lift = [-math.sin(a), 0.0, math.cos(a)]
    drag = [math.cos(a), 0.0, math.sin(a)]
    rd = st.solution.report_definitions
    rd.force["L"] = {"zones": outer_side, "force_vector": lift}
    rd.force["D"] = {"zones": outer_side, "force_vector": drag}
    mom = None
    try:
        rd.moment["M"] = {"zones": outer_side, "moment_axis": [0.0, 1.0, 0.0],
                          "moment_center": MOMENT_CENTRE}
        mom = True
    except Exception as e:
        print("   moment report:", str(e)[:110])

    names = ["L", "D"] + (["M"] if mom else [])
    out = rd.compute(report_defs=names)
    vals = {}
    for item in out:
        for k, v in item.items():
            vals[k] = float(v[0]) if isinstance(v, (list, tuple)) else float(v)

    L = vals.get("L"); D = vals.get("D"); M = vals.get("M")
    cl = L / (QINF * SREF) if L is not None else None
    cd = D / (QINF * SREF) if D is not None else None
    cm = M / (QINF * SREF * LREF) if M is not None else None
    print(f"   L = {L} N   D = {D} N   M = {M} N.m")
    print(f"   CL = {cl:.4f}   CD = {cd:.4f}   CM = {cm}")
    results.append({"aoa": aoa, "L_N": L, "D_N": D, "M_Nm": M,
                    "CL": cl, "CD": cd, "CM": cm,
                    "L_over_D": (cl / cd) if (cl is not None and cd) else None})

json.dump(results, open(os.path.join(OUT, "forces.json"), "w"), indent=2, default=str)
# also refresh forces_raw.json so stage3_post can read it
json.dump([{"aoa": r["aoa"],
            "forces": {"rep-drag": r["D_N"], "rep-lift": r["L_N"]}}
           for r in results],
          open(os.path.join(BASE, "forces_raw.json"), "w"), indent=2, default=str)
print("\n=== SUMMARY ===")
for r in results:
    print(f"  AoA {r['aoa']:5.1f} deg :  CL {r['CL']:8.4f}   CD {r['CD']:8.4f}   "
          f"L/D {r['L_over_D']:7.3f}   CM {r['CM']}")
s.exit()
print("DONE")
