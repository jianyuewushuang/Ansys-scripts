"""Probe 8: after surface mesh + compute regions, inspect the regions that exist."""
import os
os.environ.setdefault("PYFLUENT_SHOW_SERVER_GUI", "0")
from ansys.fluent.core import launch_fluent

BASE = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))   # <project root>
s = launch_fluent(mode="meshing", processor_count=2, precision="double", cwd=BASE + "/work")
print("LAUNCH OK", flush=True)
ftm = s.fault_tolerant()
WFO = ftm._workflow.task_object


def T(p, i=0):
    h = getattr(WFO, p)
    return h[h.get_object_names()[i]]


def dump(p, tag=""):
    try:
        t = T(p)
        print(f"\n---- {p} {tag} (state={t.state()}) ----")
        for k, v in t.arguments().items():
            print(f"    {k:36s} = {v!r}")
    except Exception as e:
        print(f"---- {p} fail {type(e).__name__} {e}")


def ex(p):
    try:
        T(p).execute()
        print(f"  >> {p} executed")
    except Exception as e:
        print(f"  !! {p} {type(e).__name__} {e}")


T("import_cad_and_part_management").arguments.set_state(
    {"fmd_file_name": BASE + "/data/1.stl", "length_unit": "m",
     "create_object_per": "One per part", "route": "Native"})
ex("import_cad_and_part_management")

T("describe_geometry_and_flow").arguments.set_state(
    {"flow_type": "External flow around object", "add_enclosure": True})
ex("describe_geometry_and_flow")

T("create_external_flow_boundaries").arguments.set_state({
    "creation_method": "Create new boundary", "selection_type": "object",
    "object_selection_list": ["object1"], "extraction_method": "surface mesh",
    "external_boundaries_name": "tunnel",
    "bounding_box_object": {"size_relative_length": "Ratio relative to geometry size",
                            "xmin_ratio": 1.5, "xmax_ratio": 2.5,
                            "ymin_ratio": 1.0, "ymax_ratio": 1.0,
                            "zmin_ratio": 6.0, "zmax_ratio": 6.0}})
ex("create_external_flow_boundaries")

T("identify_regions").arguments.set_state(
    {"new_region_type": "fluid", "selection_type": "object",
     "mpt_method_type": "Offset Method", "object_selection_list": ["tunnel"],
     "offset_x": 15.0, "offset_y": 0.0, "offset_z": 5.0})
ex("identify_regions")
dump("identify_regions", "[after exec]")

for p in ("update_region_settings",):
    dump(p, "[early]")

ex("generate_surface_mesh")
ex("compute_regions")

dump("update_region_settings", "[AFTER compute_regions]")
dump("compute_regions", "[after exec]")

print("\n=== listing boundary/face zones via TUI ===")
for cmd in ("boundary/manage/list", "define/boundary-conditions/list-zones",
            "mesh/modify-zones/list-zones"):
    try:
        out = s.execute_tui(cmd)
        print(f"--{cmd}--\n{out}")
    except Exception as e:
        print(f"--{cmd}-- fail {type(e).__name__} {e}")

s.exit()
print("\nDONE")
