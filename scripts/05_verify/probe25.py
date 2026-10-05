"""Check near-wall resolution: does the fluid side actually have prisms / sane y+?"""
import os
import numpy as np

os.environ.setdefault("PYFLUENT_SHOW_SERVER_GUI", "0")
from ansys.fluent.core import launch_fluent
from ansys.fluent.core.fields.field_data_interfaces import (
    ScalarFieldDataRequest)

BASE = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))   # <project root>
MESH = os.environ.get("MSH", BASE + "/artifacts/mesh/aircraft_mesh.msh.h5")
MU, RHO, T, P = 1.628e-5, 0.73612, 255.65, 54019.89
V, MA = 60.0, 0.18719055

s = launch_fluent(mode="solver", precision="double", processor_count=2,
                  cwd=BASE + "/work")
st = s.settings
st.file.read(file_type="mesh", file_name=MESH)
st.mesh.modify_zones.delete_cell_zone(cell_zones=["aircraft"])
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
st.solution.initialization.hybrid_initialize()
st.solution.run_calculation.iterate(iter_count=30)

fd = getattr(s, "field_data", None) or s.fields.field_data
for fld in ("y-plus", "y-star", "pressure", "skin-friction-coef",
            "x-wall-shear", "z-wall-shear"):
    try:
        r = fd.get_field_data(ScalarFieldDataRequest(
            surfaces=["aircraft-fluid_box"], field_name=fld,
            node_value=True, boundary_value=True))
        v = np.asarray(r["aircraft-fluid_box"]).ravel()
        v = v[np.isfinite(v)]
        print("  %-20s min %10.3f  median %10.3f  max %10.3f"
              % (fld, v.min(), np.median(v), v.max()), flush=True)
    except Exception as e:
        print("  %-20s FAIL %s" % (fld, str(e)[:90]), flush=True)

print("\ncell counts:", flush=True)
print(s.execute_tui("report/summary-size-metrics"), flush=True)

s.exit()
print("PROBE25 DONE", flush=True)
