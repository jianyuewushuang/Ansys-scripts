"""Decisive test: incompressible (constant density) + pressure-far-field.

Compares against the diverged ideal-gas run. Prints the far-field parameter
set so we know which arguments actually exist, then runs a short solve and
reports wall-averaged pressure / forces / residuals.
"""
import os
import numpy as np

os.environ.setdefault("PYFLUENT_SHOW_SERVER_GUI", "0")
from ansys.fluent.core import launch_fluent

BASE = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))   # <project root>
RHO, MU, T, P = 0.73612, 1.628e-5, 255.65, 54019.89
V = 60.0
MA = 0.18719055
SREF, LREF = 65.3375, 4.1996
QINF = 0.5 * RHO * V * V

s = launch_fluent(mode="solver", precision="double", processor_count=4,
                  cwd=BASE + "/work")
st = s.settings
st.file.read(file_type="mesh", file_name=BASE + "/artifacts/mesh/aircraft_mesh.msh.h5")
st.mesh.modify_zones.delete_cell_zone(cell_zones=["aircraft"])
print("zones:\n", s.execute_tui("define/boundary-conditions/list-zones"), flush=True)

# ---- incompressible air ----
st.setup.materials.fluid["air"] = {
    "density": {"option": "constant", "value": RHO},
    "viscosity": {"option": "constant", "value": MU},
    "specific_heat": {"option": "constant", "value": 1006.43},
    "thermal_conductivity": {"option": "constant", "value": 0.0242}}
print("air rho:", st.setup.materials.fluid["air"].density.get_state(), flush=True)
st.setup.models.energy = {"enabled": False}
st.setup.models.viscous = {"model": "k-omega", "k_omega_model": "sst"}
s.execute_tui("define/operating-conditions/operating-pressure 0")

bcs = st.setup.boundary_conditions
bcs.set_zone_type(zone_list=["fluid_box:1"], new_type="pressure-far-field")
ff = bcs.pressure_far_field["fluid_box:1"]
print("\nfar-field state (incompressible):\n", ff.get_state(), flush=True)

# try both formulations
for label, setter in (
    ("mach", lambda: setattr(ff.momentum, "mach_number",
                             {"option": "value", "value": MA})),
    ("velocity-magnitude", lambda: setattr(ff.momentum, "velocity_magnitude",
                                           {"option": "value", "value": V})),
):
    try:
        setter()
        print("  set %s OK" % label, flush=True)
    except Exception as e:
        print("  set %s FAIL %s" % (label, str(e)[:100]), flush=True)

ff.momentum.gauge_pressure = {"option": "value", "value": P}
ff.momentum.flow_direction = [{"option": "value", "value": float(v)}
                              for v in (1.0, 0.0, 0.0)]
try:
    ff.turbulence.turbulent_intensity = 0.1
    ff.turbulence.turbulent_viscosity_ratio = 10.0
except Exception as e:
    print("  turb:", str(e)[:100], flush=True)
print("\nfar-field state after set:\n", ff.get_state(), flush=True)

st.setup.reference_values = {"area": SREF, "length": LREF, "density": RHO,
                             "velocity": V, "viscosity": MU, "pressure": P,
                             "temperature": T}

# ---- numerics: conservative ----
try:
    st.solution.methods.p_v_coupling.set_state({"flow_scheme": "Coupled"})
    st.solution.run_calculation.p_v_coupling.courant_number = 40.0
except Exception as e:
    print("courant:", str(e)[:100], flush=True)
try:
    st.solution.methods.spatial_discretization.discretization_scheme.set_state(
        {"pressure": "second-order", "momentum": "first-order-upwind",
         "k": "first-order-upwind", "omega": "first-order-upwind"})
except Exception as e:
    print("scheme:", str(e)[:100], flush=True)

st.solution.initialization.hybrid_initialize()
st.solution.run_calculation.iterate(iter_count=80)
print("\n=== after 80 iterations ===", flush=True)

rd = st.solution.report_definitions
rd.force["Fx"] = {"zones": ["aircraft-fluid_box"], "force_vector": [1, 0, 0]}
rd.force["Fy"] = {"zones": ["aircraft-fluid_box"], "force_vector": [0, 1, 0]}
rd.force["Fz"] = {"zones": ["aircraft-fluid_box"], "force_vector": [0, 0, 1]}
print(rd.compute(report_defs=["Fx", "Fy", "Fz"]), flush=True)

print("\nwall avg static pressure:", flush=True)
print(s.execute_tui("report/surface-integrals/area-weighted-avg "
                    "aircraft-fluid_box () pressure no no"), flush=True)

st.solution.run_calculation.iterate(iter_count=80)
print("\n=== after 160 iterations ===", flush=True)
print(rd.compute(report_defs=["Fx", "Fy", "Fz"]), flush=True)
print(s.execute_tui("report/surface-integrals/area-weighted-avg "
                    "aircraft-fluid_box () pressure no no"), flush=True)

s.exit()
print("PROBE22 DONE", flush=True)
