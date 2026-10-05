"""Probe 10: switch 'Object Based Regions' / inspect all region lists; try to expose the fluid region."""
import os
os.environ.setdefault("PYFLUENT_SHOW_SERVER_GUI", "0")
from ansys.fluent.core import launch_fluent

BASE = r"C:/Users/jianyuewushuang/document/model/ansys/UAVdesign20261004"
s = launch_fluent(mode="meshing", processor_count=2, precision="double", cwd=BASE + "/mesh_work")
print("LAUNCH OK", flush=True)
ftm = s.fault_tolerant()
WFO = ftm._workflow.task_object


def T(p, i=0):
    h = getattr(WFO, p)
    return h[h.get_object_names()[i]]


def ex(p):
    try:
        T(p).execute()
        print(f"  >> {p} executed")
    except Exception as e:
        print(f"  !! {p} {type(e).__name__} {e}")


T("import_cad_and_part_management").arguments.set_state(
    {"fmd_file_name": BASE + "/1.stl", "length_unit": "m",
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
ex("generate_surface_mesh")
ex("compute_regions")

urs = T("update_region_settings")
print("\n=== available filter categories ===")
try:
    print(urs.arguments.filter_category.allowed_values())
except Exception as e:
    print("fail", e)

for cat in ("All Regions", "Identified Regions", "Object Based Regions"):
    try:
        urs.arguments.set_state({"filter_category": cat})
        a = T("update_region_settings").arguments()
        print(f"\n=== filter_category = {cat} ===")
        for k in ("all_region_name_list", "all_region_type_list",
                  "all_region_source_list", "all_region_volume_fill_list",
                  "main_fluid_region"):
            print(f"   {k:32s} = {a.get(k)}")
    except Exception as e:
        print(f"   {cat} fail {type(e).__name__} {e}")

# try forcing: object1 -> void + no fill ; then re-run update regions / compute regions
print("\n=== attempt: object1 -> solid, no volume fill ===")
try:
    urs.arguments.set_state({"filter_category": "All Regions"})
    urs.arguments.set_state({"all_region_type_list": ["void"],
                             "all_region_volume_fill_list": ["none"]})
    ex("update_region_settings")
    a = T("update_region_settings").arguments()
    for k in ("all_region_name_list", "all_region_type_list", "all_region_volume_fill_list"):
        print(f"   {k} = {a.get(k)}")
except Exception as e:
    print("force fail", e)

ex("generate_the_volume_mesh") if False else None
s.exit()
print("\nDONE")
