"""Mesh the fluid domain with ANSYS Prime Mesh, including boundary-layer prisms.

Fluent's watertight workflow silently ignores every boundary-layer setting in
this build (verified: 11 parameter combinations all produce the identical
prism-free mesh).  Prime has a real PrismControl, so we mesh there instead and
hand the .msh to Fluent's solver.
"""
import os
import time

os.environ.setdefault("PYFLUENT_SHOW_SERVER_GUI", "0")
import ansys.meshing.prime as prime
from ansys.meshing.prime import launch_prime

BASE = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))   # <project root>
DOM = os.environ.get("DOM", BASE + "/artifacts/geometry/fluid_domain.stl")
OUT = os.environ.get("OUT", BASE + "/artifacts/mesh/aircraft_mesh_prime.msh.h5")
MINS = float(os.environ.get("MINS", 0.25))
MAXS = float(os.environ.get("MAXS", 2.5))
BODY = float(os.environ.get("BODY", 0.5))
NL = int(os.environ.get("NL", 10))
H0 = float(os.environ.get("H0", 5e-4))
RATE = float(os.environ.get("RATE", 1.3))
GROW = float(os.environ.get("GROW", 1.2))
CURV = float(os.environ.get("CURV", 18.0))
FILL = os.environ.get("FILL", "POLY")          # POLY / HEXCOREPOLY / TET
ONLY = os.environ.get("ONLY", "introspect")    # introspect / mesh

t0 = time.time()
log = lambda *a: print(f"[{time.time()-t0:6.1f}s]", *a, flush=True)

with launch_prime() as client:
    model = client.model
    log("prime launched")
    io = prime.FileIO(model)
    io.import_cad(
        file_name=DOM,
        params=prime.ImportCadParams(
            model=model, length_unit=prime.LengthUnit.M,
            part_creation_type=prime.PartCreationType.MODEL,
            cad_reader_route=prime.CadReaderRoute.PROGRAMCONTROLLED,
            validate_shared_topology=False, refacet=False,
            stitch_tolerance=0.05))
    part = model.parts[0]
    log("imported: %d face zonelets" % len(part.get_face_zonelets()))

    part.compute_closed_volumes(
        params=prime.ComputeVolumesParams(model=model))
    vols = part.get_volumes()
    log("closed volumes: %d -> %s" % (len(vols), vols))

    # The fluid volume is bounded by BOTH shells (box + airframe); the airframe
    # interior is bounded only by the airframe shell.  Deleting the interior
    # stops prisms being extruded into the solid as well (that doubled the
    # cell count on the first attempt).
    if len(vols) >= 2:
        for v in vols:
            log("   volume %s boundary zonelets: %s"
                % (v, part.get_face_zonelets_of_volumes([v])))
        keep, drop = [], []
        for v in vols:
            zs = part.get_face_zonelets_of_volumes([v])
            (keep if len(zs) >= 2 else drop).append(v)
        log("   fluid volume(s): %s   dropping: %s" % (keep, drop))
        if keep and drop:
            # deleting by id silently does nothing; the size-threshold form works
            part.delete_volumes(vols, params=prime.DeleteVolumesParams(
                model=model, delete_small_volumes=True, volume_limit=300.0))
            log("   after delete, volumes: %s" % part.get_volumes())

    fz = part.get_face_zonelets()
    for z in fz:
        try:
            labs = part.get_labels_on_zonelet(z)
        except Exception:
            labs = []
        try:
            cnt = part.get_face_zonelet_face_count(z)
        except Exception:
            cnt = -1
        log("  zonelet %-8s faces=%-7d labels=%s" % (z, cnt, labs))
    try:
        log("  face zones: %s" % part.get_face_zones())
    except Exception as e:
        log("  face zones err", str(e)[:80])

    if ONLY == "introspect":
        log("introspect only")
        raise SystemExit(0)

    # ---------------- global sizing ----------------
    model.set_global_sizing_params(
        prime.GlobalSizingParams(model=model, min=MINS, max=MAXS,
                                 growth_rate=GROW))
    # curvature sizing on the whole model
    sc = model.control_data.create_size_control(
        prime.SizingType.CURVATURE)
    sc.set_curvature_sizing_params(
        prime.CurvatureSizingParams(model=model, min=MINS, max=MAXS,
                                    growth_rate=GROW, normal_angle=CURV))
    sc.set_scope(prime.ScopeDefinition(
        model=model, entity_type=prime.ScopeEntity.FACEANDEDGEZONELETS,
        evaluation_type=prime.ScopeEvaluationType.ZONES,
        part_expression="*", zone_expression="*"))
    sc.set_suggested_name("curv")

    # finer sizing on the airframe
    # No labels survive the STL import.  The airframe shell is the face
    # zonelet SHARED by both volumes (it bounds the fluid region and the
    # airframe interior); the far-field box bounds only the fluid region.
    ac_zonelets = []
    try:
        from collections import Counter
        bnd = {v: part.get_face_zonelets_of_volumes([v]) for v in part.get_volumes()}
        cnt = Counter(z for zs in bnd.values() for z in zs)
        nv = len(bnd)
        ac_zonelets = [z for z, n in cnt.items() if n >= 2]
        box_zonelets = [z for z, n in cnt.items() if n == 1]
        log("   shared(airframe)=%s  box=%s" % (ac_zonelets, box_zonelets))
    except Exception as e:
        log("   zonelet id err %s" % str(e)[:90])
    # scope by LABEL: a bare zonelet id is not a valid zone expression
    for z in ac_zonelets:
        try:
            part.add_labels_on_zonelets([z], ["airframe"])
        except Exception as e:
            log("   label err %s" % str(e)[:90])
    log("airframe zonelets: %s" % ac_zonelets)
    if ac_zonelets:
        sc2 = model.control_data.create_size_control(
            prime.SizingType.SOFT)
        sc2.set_soft_sizing_params(
            prime.SoftSizingParams(model=model, max=BODY, growth_rate=GROW))
        sc2.set_scope(prime.ScopeDefinition(
            model=model, entity_type=prime.ScopeEntity.FACEANDEDGEZONELETS,
            evaluation_type=prime.ScopeEvaluationType.LABELS,
            label_expression="airframe"))
        sc2.set_suggested_name("airframe")

    # ---------------- boundary-layer prisms ----------------
    pc = model.control_data.create_prism_control()
    pc.set_growth_params(prime.PrismControlGrowthParams(
        model=model,
        offset_type=prime.PrismControlOffsetType.UNIFORM,
        n_layers=NL, growth_rate=RATE, first_height=H0))
    # SCOPE=all is the only expression that actually resolves; scoping by
    # label/zonelet silently yields an empty scope and no prisms at all.
    # The far-field box has ~600 faces so "*" costs almost nothing extra.
    if ac_zonelets and os.environ.get("SCOPE", "label") == "label":
        pc.set_surface_scope(prime.ScopeDefinition(
            model=model, entity_type=prime.ScopeEntity.FACEZONELETS,
            evaluation_type=prime.ScopeEvaluationType.LABELS,
            part_expression="*", label_expression="airframe"))
    else:
        pc.set_surface_scope(prime.ScopeDefinition(
            model=model, entity_type=prime.ScopeEntity.FACEZONELETS,
            evaluation_type=prime.ScopeEvaluationType.ZONES,
            part_expression="*", zone_expression="*"))
    pc.set_volume_scope(prime.ScopeDefinition(
        model=model, entity_type=prime.ScopeEntity.VOLUME,
        evaluation_type=prime.ScopeEvaluationType.ZONES,
        part_expression="*", zone_expression="*"))
    log("prism control created: %s" % pc)

    # Make sure the exported cell zones are FLUID, not SOLID - Fluent refuses
    # to convert a solid cell zone afterwards.
    vc = model.control_data.create_volume_control()
    vc.set_params(prime.VolumeControlParams(
        model=model, cell_zonelet_type=prime.CellZoneletType.FLUID))
    vc.set_scope(prime.ScopeDefinition(
        model=model, entity_type=prime.ScopeEntity.VOLUME,
        evaluation_type=prime.ScopeEvaluationType.ZONES,
        part_expression="*", zone_expression="*"))
    vc.set_suggested_name("fluid")
    log("volume control (fluid) created")

    # ---------------- volume mesh ----------------
    fill = getattr(prime.VolumeFillType, FILL)
    am = prime.AutoMesh(model)
    res = am.mesh(
        part_id=part.id,
        automesh_params=prime.AutoMeshParams(
            model=model,
            size_field_type=prime.SizeFieldType.GEOMETRIC,
            max_size=MAXS,
            volume_fill_type=fill,
            prism_control_ids=[pc.id],
            volume_control_ids=[vc.id],
            prism=prime.PrismParams(model=model)))
    log("automesh done: %s" % str(res)[:200])
    try:
        log("cell zonelets: %s" % part.get_cell_zonelets())
        for cz in part.get_cell_zonelets():
            log("   %s cells = %s" % (cz, part.get_cell_zonelet_cell_count(cz)))
    except Exception as e:
        log("cell count err %s" % str(e)[:100])
    try:
        log("volume zones: %s" % part.get_volume_zones())
    except Exception as e:
        log("vz err %s" % str(e)[:80])

    io.export_fluent_meshing_mesh(
        file_name=OUT,
        export_fluent_mesh_params=prime.ExportFluentMeshingMeshParams(
            model=model, cff_format=True))
    log("wrote %s (%.1f MB)" % (OUT, os.path.getsize(OUT) / 1e6))

log("PRIME DONE")
