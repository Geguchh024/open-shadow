# SPDX-License-Identifier: GPL-3.0-or-later
"""Headless test suite.

    blender -b --factory-startup --python tests/run_tests.py

Exits with a non-zero status when any test fails.
"""

import math
import os
import sys
import tempfile
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import bpy  # noqa: E402

import open_shadow  # noqa: E402

open_shadow.register()
from open_shadow import patterns, presets, rig  # noqa: E402

TMP = tempfile.mkdtemp(prefix="osh_tests_")
results = []


def test(fn):
    results.append(fn)
    return fn


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def new_light(kind="SPOT", pid="WINDOW"):
    reset()
    ob = rig.create(bpy.context, kind, pid, target=(0.0, 0.0, 0.0))
    bpy.context.scene.frame_set(1)
    return ob


def evaluated(ob):
    bpy.context.view_layer.update()
    return ob.evaluated_get(bpy.context.evaluated_depsgraph_get())


def refresh(*changed):
    for idb in changed:
        idb.update_tag()
    bpy.context.scene.frame_set(bpy.context.scene.frame_current)


# -- patterns and presets ---------------------------------------------------------------


@test
def every_pattern_builds():
    reset()
    for p in patterns.PATTERNS:
        ng = patterns.ensure(p.id)
        assert ng.get("os_version") == patterns.GROUP_VERSION
        names = {i.name for i in ng.interface.items_tree if i.item_type == "SOCKET"}
        assert {"Vector", "Light"} <= names, p.id
        for spec in p.inputs:
            assert spec[0] in names, (p.id, spec[0])
        # every link must be valid (no type mismatches left dangling)
        assert all(l.is_valid for l in ng.links), p.id


@test
def ensure_is_cached():
    reset()
    a = patterns.ensure("FOLIAGE")
    n = len(a.nodes)
    b = patterns.ensure("FOLIAGE")
    assert a == b and len(b.nodes) == n


@test
def every_preset_applies():
    ob = new_light()
    for p in presets.PRESETS:
        rig.apply_preset(ob, p[0])  # raises KeyError on an unknown input name
        assert rig.current_pattern(ob) == p[3]


@test
def preset_ids_unique_and_thumbnailed():
    ids = [p[0] for p in presets.PRESETS]
    assert len(ids) == len(set(ids))
    cats = {c[0] for c in presets.CATEGORIES}
    missing = []
    for p in presets.PRESETS:
        assert p[2] in cats, p
        if not os.path.exists(os.path.join(ROOT, "open_shadow", "thumbs", p[0] + ".png")):
            missing.append(p[0])
    assert not missing, f"no thumbnail for {missing} (run tools/render_thumbnails.py)"


@test
def switching_pattern_resets_inputs():
    ob = new_light(pid="WINDOW")
    pat = rig.node(ob, rig.N_PATTERN)
    pat.inputs["Columns"].default_value = 9.0
    rig.set_pattern(ob, "BLINDS")
    for name, v in patterns.default_inputs("BLINDS").items():
        assert math.isclose(pat.inputs[name].default_value, v, abs_tol=1e-5), name


@test
def angle_presets_in_radians():
    ob = new_light()
    rig.apply_preset(ob, "LATTICE")
    a = rig.node(ob, rig.N_PATTERN).inputs["Angle"].default_value
    assert math.isclose(a, math.radians(45.0), abs_tol=1e-5), a


@test
def explicit_node_names():
    ob = new_light()
    rig.apply_preset(ob, "COBWEB_GLOW")
    assert rig.node(ob, rig.N_FINISH).inputs["Invert"].default_value == 1.0
    rig.apply_preset(ob, "COBWEB")
    assert rig.node(ob, rig.N_FINISH).inputs["Invert"].default_value == 0.0


@test
def image_pattern():
    ob = new_light()
    img = bpy.data.images.new("gobo", 8, 8)
    rig.node(ob, rig.N_IMAGE).image = img
    rig.set_pattern(ob, patterns.IMAGE)
    fin = rig.node(ob, rig.N_FINISH)
    assert fin.inputs["Light"].links[0].from_node.name == rig.N_IMAGE
    rig.set_pattern(ob, "HEX")
    assert fin.inputs["Light"].links[0].from_node.name == rig.N_PATTERN


# -- rig ------------------------------------------------------------------------------------


@test
def drivers_need_no_python():
    for kind in ("SPOT", "SUN", "AREA", "POINT"):
        ob = new_light(kind)
        plane = rig.plane_of(ob)
        fcs = list(plane.animation_data.drivers)
        assert len(fcs) == 3
        for fc in fcs:
            assert fc.driver.is_valid, (kind, fc.data_path)
            assert fc.driver.is_simple_expression, fc.driver.expression


@test
def plane_fits_spot_cone():
    ob = new_light("SPOT")
    ob.data.spot_size = math.radians(40.0)
    ob[rig.DISTANCE] = 2.0
    refresh(ob)
    ev = evaluated(rig.plane_of(ob))
    want = 2 * 2.0 * math.tan(math.radians(20.0)) * rig.SPOT_MARGIN
    assert math.isclose(ev.scale.x, want, rel_tol=1e-4), (ev.scale.x, want)
    assert math.isclose(ev.location.z, -2.0, abs_tol=1e-5)


@test
def other_lamps_use_size():
    for kind in ("SUN", "AREA", "POINT"):
        ob = new_light(kind)
        ob[rig.SIZE] = 3.25
        refresh(ob)
        assert math.isclose(evaluated(rig.plane_of(ob)).scale.x, 3.25, rel_tol=1e-5), kind


@test
def changing_lamp_type_follows():
    ob = new_light("SPOT")
    ob[rig.SIZE] = 5.0
    ob.data.type = "SUN"
    rig.sync_types()  # the add-on runs this from a message bus subscription
    refresh(ob, ob.data)
    assert math.isclose(evaluated(rig.plane_of(ob)).scale.x, 5.0, rel_tol=1e-5)
    assert all(fc.driver.is_valid for fc in rig.plane_of(ob).animation_data.drivers)
    ob[rig.SIZE] = 6.0
    refresh(ob)
    assert math.isclose(evaluated(rig.plane_of(ob)).scale.x, 6.0, rel_tol=1e-5)
    ob.data.type = "SPOT"
    rig.sync_types()
    refresh(ob, ob.data)
    assert all(fc.driver.is_valid for fc in rig.plane_of(ob).animation_data.drivers)


@test
def plane_only_casts_shadows():
    ob = new_light()
    plane = rig.plane_of(ob)
    assert not plane.visible_camera and not plane.visible_glossy
    assert not plane.visible_diffuse and plane.visible_shadow
    mat = rig.material_of(ob)
    assert mat.use_transparent_shadow


@test
def light_of_and_plane_of():
    ob = new_light()
    plane = rig.plane_of(ob)
    assert rig.light_of(ob) == ob and rig.light_of(plane) == ob
    lamp = bpy.data.objects.new("plain", bpy.data.lights.new("plain", "POINT"))
    assert rig.light_of(lamp) is None and rig.light_of(None) is None


@test
def aim_points_minus_z_at_target():
    ob = new_light()
    ob.location = (3.0, -2.0, 5.0)
    bpy.context.view_layer.update()
    rig.aim(ob, (0.0, 1.0, 0.0))
    bpy.context.view_layer.update()
    fwd = ob.matrix_world.to_3x3() @ __import__("mathutils").Vector((0, 0, -1))
    want = (__import__("mathutils").Vector((0, 1, 0)) - ob.location).normalized()
    assert fwd.dot(want) > 0.9999


@test
def detach_cleans_up():
    ob = new_light()
    mat = rig.material_of(ob)
    name = mat.name
    rig.detach(ob)
    assert rig.plane_of(ob) is None
    assert bpy.data.materials.get(name) is None
    assert rig.DISTANCE not in ob


@test
def duplicate_and_make_unique():
    ob = new_light()
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    rig.plane_of(ob).hide_select = False
    rig.plane_of(ob).select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.duplicate()
    dup = next(o for o in bpy.context.selected_objects if o.type == "LIGHT")
    assert dup != ob and rig.plane_of(dup) is not None
    # duplicated drivers must follow the new lamp, not the original
    for fc in rig.plane_of(dup).animation_data.drivers:
        for v in fc.driver.variables:
            assert v.targets[0].id in (dup, dup.data), (fc.data_path, v.targets[0].id)
    rig.make_unique(dup)
    assert rig.material_of(dup) != rig.material_of(ob)


@test
def object_settings():
    ob = new_light("SUN")
    ob.open_shadow.distance = 3.0
    ob.open_shadow.size = 4.0
    assert ob[rig.DISTANCE] == 3.0 and ob[rig.SIZE] == 4.0
    ob.open_shadow.pattern = "HEX"
    assert rig.current_pattern(ob) == "HEX"
    assert rig.plane_of(ob).open_shadow.pattern == "HEX"  # the plane is a view too


@test
def haze_toggle():
    reset()
    scene = bpy.context.scene
    st = scene.open_shadow
    assert not st.haze
    st.haze = True
    assert st.haze and rig.haze_node(scene.world) is not None
    st.haze_density = 0.1
    assert math.isclose(rig.haze_node(scene.world).inputs["Density"].default_value, 0.1, rel_tol=1e-6)
    st.haze = False
    assert not st.haze


@test
def operators():
    reset()
    bpy.ops.open_shadow.add(light_type="AREA", preset="FERN")
    ob = bpy.context.active_object
    assert rig.light_of(ob) == ob and ob.data.type == "AREA"
    assert rig.current_pattern(ob) == "FERN"
    bpy.ops.open_shadow.apply_preset(preset="HONEYCOMB")
    assert rig.current_pattern(ob) == "HEX"
    bpy.ops.open_shadow.random_seed()
    bpy.ops.open_shadow.reset()
    bpy.ops.open_shadow.aim()
    bpy.ops.open_shadow.remove()
    assert rig.plane_of(ob) is None
    lamp = bpy.data.objects.new("L", bpy.data.lights.new("L", "SPOT"))
    bpy.context.scene.collection.objects.link(lamp)
    bpy.ops.object.select_all(action="DESELECT")
    lamp.select_set(True)
    bpy.context.view_layer.objects.active = lamp
    bpy.ops.open_shadow.attach()
    assert rig.plane_of(lamp) is not None


@test
def picking_a_preset_changes_active_light():
    reset()
    bpy.ops.open_shadow.add(light_type="SPOT", preset="WINDOW_4")
    ob = bpy.context.active_object
    bpy.context.scene.open_shadow.preset = "PALM"
    assert rig.current_pattern(ob) == "PALM"


# -- files --------------------------------------------------------------------------------------


@test
def file_works_without_addon():
    ob = new_light()
    rig.apply_preset(ob, "FERN")
    path = os.path.join(TMP, "noaddon.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path)
    open_shadow.unregister()
    try:
        bpy.ops.wm.open_mainfile(filepath=path)
        lamp = bpy.data.objects["Shadow Light"]
        plane = next(c for c in lamp.children if c.get(rig.PLANE_TAG))
        for fc in plane.animation_data.drivers:
            assert fc.driver.is_valid and fc.driver.is_simple_expression
        lamp[rig.DISTANCE] = 2.5
        refresh(lamp)
        assert math.isclose(evaluated(plane).location.z, -2.5, abs_tol=1e-5)
    finally:
        open_shadow.register()


@test
def upgrade_keeps_values():
    ob = new_light()
    rig.apply_preset(ob, "LEAVES")
    pat = rig.node(ob, rig.N_PATTERN)
    pat.inputs["Density"].default_value = 13.0
    rig.node(ob, rig.N_TRANSFORM).inputs["Scale"].default_value = 2.5
    for g in patterns.all_groups():
        g["os_version"] = 0
    rig.upgrade_file()
    assert all(patterns.is_current(g) for g in patterns.all_groups())
    assert rig.node(ob, rig.N_PATTERN).inputs["Density"].default_value == 13.0
    assert rig.node(ob, rig.N_TRANSFORM).inputs["Scale"].default_value == 2.5


# -- renders -------------------------------------------------------------------------------------


def floor_brightness(engine, values):
    """Mean brightness of a floor lit straight down through a pattern."""
    reset()
    scene = bpy.context.scene
    scene.render.engine = engine
    if engine == "CYCLES":
        scene.cycles.samples = 8
        scene.cycles.device = "CPU"
    else:
        scene.eevee.taa_render_samples = 4
    scene.render.resolution_x = scene.render.resolution_y = 32
    bpy.ops.mesh.primitive_plane_add(size=4.0)
    cam = bpy.data.cameras.new("c")
    cam.type = "ORTHO"
    cam.ortho_scale = 1.0
    co = bpy.data.objects.new("c", cam)
    co.location = (0.0, 0.0, 6.0)
    scene.collection.objects.link(co)
    scene.camera = co
    ob = rig.create(bpy.context, "SPOT", "GRID", target=(0.0, 0.0, 0.0))
    ob.location = (0.0, 0.0, 3.0)
    ob.rotation_euler = (0.0, 0.0, 0.0)
    ob.data.energy = 500.0
    rig.apply_values(ob, values)
    path = os.path.join(TMP, "r.png")
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    img = bpy.data.images.load(path)
    px = list(img.pixels)
    return sum(px[0::4]) / (len(px) // 4)


@test
def shadows_render_in_both_engines():
    for engine in ("CYCLES", "BLENDER_EEVEE"):
        open_ = floor_brightness(engine, {"Hole Size": 1.0, "Cells": 1.0})
        closed = floor_brightness(engine, {"Hole Size": 0.0, "Cells": 1.0})
        assert open_ > 0.2, (engine, open_)
        assert closed < open_ * 0.1, (engine, open_, closed)


def main():
    failed = 0
    for fn in results:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except Exception:
            failed += 1
            print(f"FAIL {fn.__name__}")
            traceback.print_exc()
    print(f"\n{len(results) - failed}/{len(results)} passed")
    sys.exit(1 if failed else 0)


main()
