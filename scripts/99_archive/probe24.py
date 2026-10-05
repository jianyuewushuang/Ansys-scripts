"""Find how to set the coupled-solver Courant number in 26R1."""
import os
os.environ.setdefault("PYFLUENT_SHOW_SERVER_GUI", "0")
from ansys.fluent.core import launch_fluent

BASE = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))   # <project root>
s = launch_fluent(mode="solver", precision="double", processor_count=2,
                  cwd=BASE + "/work")
st = s.settings
st.file.read(file_type="mesh", file_name=BASE + "/artifacts/mesh/aircraft_mesh.msh.h5")
st.mesh.modify_zones.delete_cell_zone(cell_zones=["aircraft"])
st.setup.models.energy = {"enabled": True}
st.setup.models.viscous = {"model": "k-omega", "k_omega_model": "sst"}
try:
    st.solution.methods.p_v_coupling.set_state({"flow_scheme": "Coupled"})
except Exception as e:
    print("coupling", str(e)[:100])

print("--- TUI methods ---")
print("p_v_coupling state:", st.solution.methods.p_v_coupling.get_state(), flush=True)

print("\n--- try TUI /solve/set/p-v-controls ---", flush=True)
for cmd in ("solve/set/p-v-controls 20", "solve/set/courant-number 20"):
    try:
        r = s.execute_tui(cmd)
        print(cmd, "->", r, flush=True)
    except Exception as e:
        print(cmd, "-> FAIL", str(e)[:120], flush=True)

pc = st.solution.controls.p_v_controls
for nm in ("flow_courant_number", "explicit_pressure_under_relaxation",
           "explicit_momentum_under_relaxation"):
    for cb in ("report Beispiel",):
        pass
    try:
        cur = getattr(pc, nm)()
        print(nm, "current =", cur, flush=True)
    except Exception as e:
        print(nm, "read fail", str(e)[:100], flush=True)

print("\n--- try direct assignment after scheme set ---", flush=True)
try:
    st.solution.methods.pseudo_time_method.set_state(
        {"formulation": "global-time-step"})
except Exception as e:
    print("pseudo:", str(e)[:100], flush=True)
try:
    pc.flow_courant_number = 20.0
    print("OK set flow_courant_number ->", pc.flow_courant_number(), flush=True)
except Exception as e:
    print("still fail:", str(e)[:150], flush=True)

print("\n--- children of p_v_controls ---", flush=True)
print(pc.child_names if hasattr(pc, "child_names") else dir(pc), flush=True)
print("\n--- list active sub-objects ---", flush=True)
for n in ("flow_courant_number", "residual_smoothing_factor",
          "pseudo_time_method", "pseudo_time_courant_number"):
    o = getattr(pc, n, None)
    try:
        print(" ", n, "is_active =", o.is_active(), flush=True)
    except Exception as e:
        print(" ", n, str(e)[:80], flush=True)

s.exit()
print("PROBE24 DONE", flush=True)
