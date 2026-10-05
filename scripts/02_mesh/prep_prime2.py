"""Pick the fluid cell zone out of the exported Prime mesh and verify y+."""
import os
import numpy as np

os.environ.setdefault("PYFLUENT_SHOW_SERVER_GUI", "0")
from ansys.fluent.core import launch_fluent
from ansys.fluent.core.fields.field_data_interfaces import ScalarFieldDataRequest

BASE = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))   # <project root>
MESH = os.environ.get("MSH", BASE + "/artifacts/mesh/aircraft_mesh_prime.msh.h5")
DROP = os.environ.get("DROP", "model.1")
MU, RHO, T, P = 1.628e-5, 0.73612, 255.65, 54019.89
V, MA = 60.0, 0.18719055

s = launch_fluent(mode="solver", precision="double", processor_count=2,
                  cwd=BASE + "/work")
st = s.settings
st.file.read(file_type="mesh", file_name=MESH)

cz = st.setup.cell_zone_conditions
names = []
for g in ("fluid", "solid"):
    o = getattr(cz, g, None)
    if o is None:
        continue
    try:
        names += list(o().keys()) if callable(o) else []
    except Exception:
        pass
print("cell zones:", names, flush=True)
bcs = st.setup.boundary_conditions
print("walls:", list(bcs.wall().keys()) if callable(bcs.wall) else None, flush=True)

# physics FIRST: the exported Prime zones are typed solid, and a
# pressure-far-field cannot be created until an ideal-gas fluid exists.
st.setup.models.energy = {"enabled": True}
st.setup.models.viscous = {"model": "k-omega", "k_omega_model": "sst"}
st.setup.materials.fluid["air"] = {
    "density": {"option": "ideal-gas"},
    "viscosity": {"option": "constant", "value": MU}}
print("air rho:", st.setup.materials.fluid["air"].density.get_state(), flush=True)

st.mesh.modify_zones.delete_cell_zone(cell_zones=[DROP])
print("deleted", DROP, flush=True)
left = [n for n in names if n != DROP]
print("remaining:", left, flush=True)
for n in left:
    try:
        st.setup.boundary_conditions.set_zone_type(zone_list=[n],
                                                   new_type="fluid")
        print("  -> %s set to fluid" % n, flush=True)
    except Exception as e:
        print("  set fluid %s: %s" % (n, str(e)[:110]), flush=True)
try:
    print("fluid zones now:", list(st.setup.cell_zone_conditions.fluid().keys()),
          flush=True)
except Exception as e:
    print("fluid list:", str(e)[:90], flush=True)

print("walls now:", list(bcs.wall().keys()) if callable(bcs.wall) else None,
      flush=True)

s.execute_tui("define/operating-conditions/operating-pressure 0")
walls = list(bcs.wall().keys()) if callable(bcs.wall) else []
outer = min(walls, key=lambda w: len(w)) if len(walls) > 1 else walls[0]
af = [w for w in walls if w != outer]
print("outer=%s  airframe=%s" % (outer, af), flush=True)
bcs.set_zone_type(zone_list=[outer], new_type="pressure-far-field")
ff = bcs.pressure_far_field[outer]
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
for w in af:
    for fld in ("y-plus", "pressure", "skin-friction-coef"):
        try:
            r = fd.get_field_data(ScalarFieldDataRequest(
                surfaces=[w], field_name=fld, node_value=True,
                boundary_value=True))
            v = np.asarray(r[w]).ravel()
            v = v[np.isfinite(v)]
            print("  %-22s min %10.3f  median %10.3f  max %10.3f"
                  % (fld, v.min(), np.median(v), v.max()), flush=True)
        except Exception as e:
            print("  %s %s" % (fld, str(e)[:90]), flush=True)

s.exit()
print("PREP2 DONE", flush=True)
