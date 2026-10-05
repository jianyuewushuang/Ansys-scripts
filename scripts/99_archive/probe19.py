"""Probe 19: FTM - let Fluent create the enclosure itself via add_enclosure=True."""
import os, time
os.environ.setdefault("PYFLUENT_SHOW_SERVER_GUI", "0")
from ansys.fluent.core import launch_fluent

BASE = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))   # <project root>
t0 = time.time()


def log(*a):
    print(f"[{time.time()-t0:6.1f}s]", *a, flush=True)


s = launch_fluent(mode="meshing", processor_count=2, precision="double", cwd=BASE + "/work")
ftm = s.fault_tolerant()
WFO = ftm._workflow.task_object


def T(p, i=0):
    h = getattr(WFO, p)
    n = h.get_object_names()
    return h[n[i]]


def ex(p):
    try:
        T(p).execute()
        log(f">>> {p} OK")
        return True
    except Exception as e:
        log(f"!! {p} {str(e)[:170]}")
        return False


def dump(p):
    try:
        log(f"--- {p} [{T(p).state()}]")
        for k, v in T(p).arguments().items():
            log(f"    {k:34s} = {v!r}")
    except Exception as e:
        log(f"--- {p} fail {e}")


T("import_cad_and_part_management").arguments.set_state({
    "fmd_file_name": BASE + "/data/1.stl", "length_unit": "m",
    "create_object_per": "One per part", "route": "Native"})
ex("import_cad_and_part_management")

T("describe_geometry_and_flow").arguments.set_state({
    "flow_type": "External flow around object", "add_enclosure": True})
ex("describe_geometry_and_flow")

# deliberately do NOT run create_external_flow_boundaries - see if Fluent does it
ex("generate_surface_mesh")
ex("compute_regions")
dump("update_region_settings")

# try to point the fluid region at the tunnel if one exists
urs = T("update_region_settings")
a = urs.arguments()
log(f"regions: {a.get('all_region_name_list')} types={a.get('all_region_type_list')} "
    f"fill={a.get('all_region_volume_fill_list')}")

bl = T("add_boundary_layers")
try:
    bl.arguments.set_state({"offset_method_type": "uniform", "number_of_layers": 8,
                            "rate": 1.2, "first_height": 0.0003, "add_child": "yes",
                            "local_prism_preferences": {"show_in_gui": False,
                                                        "modify_at_invalid_normals": True,
                                                        "ignore_boundary_layers": False,
                                                        "additional_ignored_layers": 0}})
    bl.execute()
    log(">>> BL OK")
except Exception as e:
    log("BL", str(e)[:120])

vm = T("create_volume_mesh_ftm")
try:
    vm.arguments.set_state({"fill_with_size_field": True, "quality_method": "Orthogonal"})
    vm.execute()
    log(">>> volume mesh OK")
except Exception as e:
    log("volume", str(e)[:170])

print("\nzones:\n", s.execute_tui("boundary/manage/list"), flush=True)
s.exit()
print("DONE")
