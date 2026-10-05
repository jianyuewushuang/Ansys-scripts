"""Smoke test: can PyFluent launch a local Fluent solver?"""
import os, sys, traceback

print("AWP_ROOT261 =", os.environ.get("AWP_ROOT261"))
try:
    import ansys.fluent.core as pyfluent
    print("pyfluent version:", pyfluent.__version__)
except Exception as e:
    print("IMPORT FAIL:", e); traceback.print_exc(); sys.exit(1)

try:
    from ansys.fluent.core import launch_fluent
    import ansys.fluent.core as pyfluent
    print("EXE detected :", pyfluent.EXE_PATH)
    print("launcher     :", pyfluent.launcher.LAUNCHER)
except Exception as e:
    print("introspection fail:", e)

try:
    print("\n>>> launching fluent (meshing, 2 cores) ...")
    s = launch_fluent(mode="meshing", precision="double", processor_count=2,
                      cwd=r"C:/Users/jianyuewushuang/document/model/ansys/UAVdesign20261004")
    print("LAUNCH OK")
    print(s.health_check_service.get_server_status() if hasattr(s, "health_check_service") else "")
    print("scheme version:", s.version)
    s.exit()
    print("EXIT OK")
except Exception as e:
    print("LAUNCH FAIL:", type(e).__name__, e)
    traceback.print_exc()
    sys.exit(2)
