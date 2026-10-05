"""Conservative re-solve test for AoA=0 with a low Courant number.

Prints the area-averaged wall pressure and forces every few iterations so we
can see immediately whether the low-Mach compressible run is healthy
(target: mean wall pressure ~ 54020 Pa, |Fy| ~ 0, drag > 0).
"""
import os

os.environ.setdefault("PYFLUENT_SHOW_SERVER_GUI", "0")
from ansys.fluent.core import launch_fluent

BASE = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))   # <project root>
RHO, MU, T, P = 0.73612, 1.628e-5, 255.65, 54019.89
V, MA = 60.0, 0.18719055
SREF, LREF = 65.3375, 4.1996
QINF = 0.5 * RHO * V * V
COURANT = float(os.environ.get("COURANT", 20))

s = launch_fluent(mode="solver", precision="double", processor_count=4,
                  cwd=BASE + "/work")
st = s.settings
st.file.read(file_type="mesh", file_name=BASE + "/artifacts/mesh/aircraft_mesh.msh.h5")
st.mesh.modify_zones.delete_cell_zone(cell_zones=["aircraft"])
print("=== mesh ready ===", flush=True)

st.setup.models.energy = {"enabled": True}
st.setup.models.viscous = {"model": "k-omega", "k_omega_model": "sst"}
st.setup.materials.fluid["air"] = {
    "density": {"option": "ideal-gas"},
    "viscosity": {"option": "constant", "value": MU}}
s.execute_tui("define/operating-conditions/operating-pressure 0")

bcs = st.setup.boundary_conditions
bcs.set_zone_type(zone_list=["fluid_box:1"], new_type="pressure-far-field")
ff = bcs.pressure_far_field["fluid_box:1"]
ff.momentum.gauge_pressure = {"option": "value", "value": P}
ff.momentum.mach_number = {"option": "value", "value": MA}
ff.momentum.flow_direction = [{"option": "value", "value": float(v)}
                              for v in (1.0, 0.0, 0.0)]
ff.turbulence.turbulent_intensity = 0.1
ff.turbulence.turbulent_viscosity_ratio = 10.0
ff.thermal.temperature = {"option": "value", "value": T}
st.setup.reference_values = {"area": SREF, "length": LREF, "density": RHO,
                             "velocity": V, "viscosity": MU, "pressure": P,
                             "temperature": T}

try:
    st.solution.methods.p_v_coupling.set_state({"flow_scheme": "Coupled"})
except Exception as e:
    print("coupling:", str(e)[:100], flush=True)
pc = st.solution.controls.p_v_controls
try:
    pc.flow_courant_number = COURANT
    print("Courant =", pc.flow_courant_number(), flush=True)
except Exception as e:
    print("courant fail:", str(e)[:120], flush=True)
for nm, val in (("explicit_pressure_under_relaxation", 0.4),
                ("explicit_momentum_under_relaxation", 0.5)):
    try:
        setattr(pc, nm, val)
        print(nm, "=", getattr(pc, nm)(), flush=True)
    except Exception as e:
        print(nm, "fail", str(e)[:100], flush=True)

st.solution.methods.discretization_scheme.set_state(
    {"pressure": "standard", "momentum": "first-order-upwind",
     "k": "first-order-upwind", "omega": "first-order-upwind"})

rd = st.solution.report_definitions
rd.force["Fx"] = {"zones": ["aircraft-fluid_box"], "force_vector": [1, 0, 0]}
rd.force["Fy"] = {"zones": ["aircraft-fluid_box"], "force_vector": [0, 1, 0]}
rd.force["Fz"] = {"zones": ["aircraft-fluid_box"], "force_vector": [0, 0, 1]}


def diag(tag):
    out = rd.compute(report_defs=["Fx", "Fy", "Fz"])
    d = {}
    for item in out:
        for k, v in item.items():
            d[k] = float(v[0])
    pw = s.execute_tui("report/surface-integrals/area-weighted-avg "
                       "aircraft-fluid_box () pressure no no")
    print("[%s] Fx=%9.1f  Fy=%9.1f  Fz=%9.1f   CD=%+.4f CL=%+.4f"
          % (tag, d["Fx"], d["Fy"], d["Fz"], d["Fx"] / (QINF * SREF),
             d["Fz"] / (QINF * SREF)), flush=True)
    return d


st.solution.initialization.hybrid_initialize()
for i in range(8):
    st.solution.run_calculation.iterate(iter_count=25)
    diag("its %3d" % (25 * (i + 1)))

s.exit()
print("PROBE23 DONE", flush=True)
