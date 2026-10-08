# SPDX-License-Identifier: GPL-3.0-or-later
"""Render showcase artwork: small scenes lit by shadow lights.

    blender -b --factory-startup --python tools/render_showcase.py -- [SCENE ...] [--samples N] [--scale F] [--plain]

Writes docs/images/showcase/<scene>.png (1600 x 900, the hero 2400 x 1200).
--plain renders the same lamps without their patterns, as <scene>_plain.png.
Renders on the GPU when one is available.
"""

import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import open_shadow  # noqa: E402

open_shadow.register()
from open_shadow import nodekit, rig  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
SAMPLES = int(argv[argv.index("--samples") + 1]) if "--samples" in argv else 256
SCALE = float(argv[argv.index("--scale") + 1]) if "--scale" in argv else 1.0
PLAIN = "--plain" in argv
OUT = os.path.join(ROOT, "docs", "images", "showcase")


# -- scene helpers ----------------------------------------------------------------------


def reset(world_color=(0.01, 0.011, 0.014), exposure=0.0, look="AgX - Medium High Contrast"):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    prefs = bpy.context.preferences.addons["cycles"].preferences
    for kind in ("OPTIX", "CUDA", "HIP", "METAL", "ONEAPI"):
        try:
            prefs.compute_device_type = kind
            prefs.get_devices()
            for d in prefs.devices:
                d.use = d.type != "CPU"
            break
        except TypeError:
            continue
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "GPU"
    sc.cycles.samples = SAMPLES
    sc.cycles.use_denoising = True
    sc.cycles.max_bounces = 8
    sc.view_settings.view_transform = "AgX"
    try:
        sc.view_settings.look = look
    except TypeError:
        pass
    sc.view_settings.exposure = exposure
    world = bpy.data.worlds.new("World")
    world.color = world_color
    nt = world.node_tree
    bg = nt.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = (*world_color, 1.0)
    sc.world = world
    return sc


def material(name, color, rough=0.8, bump=0.0, bump_scale=40.0, metal=0.0, coat=0.0,
             sss=0.0, variation=0.0):
    """Principled material with an optional fine noise bump and colour variation."""
    mat = bpy.data.materials.new(name)
    nt = mat.node_tree
    nb = nodekit.NB(nt)
    bsdf = nt.nodes["Principled BSDF"]
    col = nodekit.hex_color(color) if isinstance(color, str) else (*color, 1.0)
    bsdf.inputs["Base Color"].default_value = col
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    bsdf.inputs["Coat Weight"].default_value = coat
    if sss:
        bsdf.inputs["Subsurface Weight"].default_value = sss
    tc = nb.node("ShaderNodeTexCoord")
    if variation:
        n = nb.noise(tc.outputs["Object"], 3.0, 4.0, 0.6)
        c = nb.mix(col, nb.mul(n.outputs["Fac"], 1.0), variation, blend="MULTIPLY")
        nb.link(nb.mix(col, c, 1.0), bsdf.inputs["Base Color"])
    if bump:
        n = nb.noise(tc.outputs["Object"], bump_scale, 8.0, 0.65)
        b = nb.node("ShaderNodeBump")
        nb.set(b, "Strength", bump)
        nb.set(b, "Distance", 0.01)
        nb.link(n.outputs["Fac"], b.inputs["Height"])
        nb.link(b.outputs["Normal"], bsdf.inputs["Normal"])
    mat.diffuse_color = col
    return mat


def plank_floor(name, color, plank=0.18, rough=0.45):
    """Wooden boards: wave-texture grain with per-board colour."""
    mat = material(name, color, rough)
    nt = mat.node_tree
    nb = nodekit.NB(nt)
    bsdf = nt.nodes["Principled BSDF"]
    tc = nb.node("ShaderNodeTexCoord")
    x, y, _ = nb.sep(tc.outputs["Object"])
    row = nb.math("FLOOR", nb.div(y, plank))
    wn = nb.node("ShaderNodeTexWhiteNoise", noise_dimensions="1D")
    nb.set(wn, "W", row)
    grain = nb.node("ShaderNodeTexWave", wave_type="BANDS", bands_direction="X")
    nb.set(grain, "Vector", nb.comb(nb.mul(y, 6.0), nb.add(x, nb.mul(wn.outputs["Value"], 9.0)), 0.0))
    nb.set(grain, "Scale", 2.0)
    nb.set(grain, "Distortion", 6.0)
    nb.set(grain, "Detail", 3.0)
    base = nodekit.hex_color(color)
    dark = tuple(c * 0.55 for c in base[:3])
    tone = nb.mix(base, dark, nb.mul(grain.outputs["Fac"], 0.5))
    tone = nb.mix(tone, nb.mul(tone, 0.75), nb.mul(wn.outputs["Value"], 0.8))
    nb.link(tone, bsdf.inputs["Base Color"])
    seam = nb.math("FRACT", nb.div(y, plank))
    gap = nb.smooth(nb.min(seam, nb.one_minus(seam)), 0.0, 0.02)
    b = nb.node("ShaderNodeBump")
    nb.set(b, "Strength", 0.4)
    nb.set(b, "Distance", 0.003)
    nb.link(gap, b.inputs["Height"])
    nb.link(b.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def tiles(name, color, grout="#3a332c", size=0.3, rough=0.55):
    mat = material(name, color, rough, variation=0.25)
    nt = mat.node_tree
    nb = nodekit.NB(nt)
    bsdf = nt.nodes["Principled BSDF"]
    tc = nb.node("ShaderNodeTexCoord")
    br = nb.node("ShaderNodeTexBrick", offset=0.0)
    nb.set(br, "Vector", tc.outputs["Object"])
    nb.set(br, "Scale", 1.0 / size)
    nb.set(br, "Mortar Size", 0.012)
    nb.set(br, "Brick Width", 1.0)
    nb.set(br, "Row Height", 1.0)
    nb.set(br, "Color1", color)
    nb.set(br, "Color2", tuple(c * 0.85 for c in nodekit.hex_color(color)[:3]))
    nb.set(br, "Mortar", grout)
    nb.link(br.outputs["Color"], bsdf.inputs["Base Color"])
    b = nb.node("ShaderNodeBump")
    nb.set(b, "Strength", 0.5)
    nb.set(b, "Distance", 0.004)
    nb.link(nb.one_minus(br.outputs["Fac"]), b.inputs["Height"])
    nb.link(b.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def obj(op, name, mat, bevel=0.0, smooth=False, subsurf=0, **kw):
    op(**kw)
    ob = bpy.context.active_object
    ob.name = name
    if mat:
        ob.data.materials.append(mat)
    if bevel:
        m = ob.modifiers.new("Bevel", "BEVEL")
        m.width = bevel
        m.segments = 3
        m.limit_method = "ANGLE"
    if subsurf:
        m = ob.modifiers.new("Subsurf", "SUBSURF")
        m.levels = m.render_levels = subsurf
    if smooth or bevel or subsurf:
        bpy.ops.object.shade_smooth()
    return ob


def box(name, size, loc, mat, bevel=0.01, rot=(0, 0, 0)):
    ob = obj(bpy.ops.mesh.primitive_cube_add, name, mat, bevel, size=1.0, location=loc, rotation=rot)
    ob.scale = size
    bpy.ops.object.transform_apply(scale=True)
    return ob


def cylinder(name, r, h, loc, mat, bevel=0.005, verts=64):
    ob = obj(bpy.ops.mesh.primitive_cylinder_add, name, mat, bevel, radius=r, depth=h,
             location=(loc[0], loc[1], loc[2] + h / 2), vertices=verts)
    return ob


def lathe(name, profile, loc, mat, subsurf=2):
    """Vase/bowl from a (radius, height) profile, spun around Z."""
    me = bpy.data.meshes.new(name)
    n = 48
    verts, faces = [], []
    for j in range(n):
        a = 2 * math.pi * j / n
        for r, z in profile:
            verts.append((r * math.cos(a), r * math.sin(a), z))
    m = len(profile)
    for j in range(n):
        for i in range(m - 1):
            a, b = j * m + i, ((j + 1) % n) * m + i
            faces.append((a, b, b + 1, a + 1))
    me.from_pydata(verts, [], faces)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = loc
    me.materials.append(mat)
    if subsurf:
        s = ob.modifiers.new("Subsurf", "SUBSURF")
        s.levels = s.render_levels = subsurf
    sol = ob.modifiers.new("Solidify", "SOLIDIFY")
    sol.thickness = 0.01
    for p in me.polygons:
        p.use_smooth = True
    return ob


def plane(name, size, loc, mat, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_plane_add(size=1.0, location=loc, rotation=rot)
    ob = bpy.context.active_object
    ob.name = name
    ob.scale = (size[0], size[1], 1.0)
    bpy.ops.object.transform_apply(scale=True)
    ob.data.materials.append(mat)
    return ob


def camera(loc, look_at, lens=35.0, shift_y=0.0):
    cam = bpy.data.cameras.new("Camera")
    cam.lens = lens
    cam.shift_y = shift_y
    co = bpy.data.objects.new("Camera", cam)
    bpy.context.scene.collection.objects.link(co)
    co.location = loc
    d = Vector(look_at) - Vector(loc)
    co.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.camera = co
    return co


def shadow_light(preset, loc, target, energy, cone=40.0, color=(1, 1, 1), soft=0.0,
                 distance=1.0, values=None, kind="SPOT"):
    ob = rig.create(bpy.context, kind, "WINDOW", target=target)
    rig.apply_preset(ob, preset)
    if values:
        rig.apply_values(ob, values)
    if PLAIN:
        rig.apply_values(ob, {"Finish.Strength": 0.0})
    ob.location = loc
    bpy.context.view_layer.update()
    rig.aim(ob, target)
    lamp = ob.data
    lamp.energy = energy
    lamp.color = color
    if kind == "SPOT":
        lamp.spot_size = math.radians(cone)
        lamp.spot_blend = 0.08
        lamp.shadow_soft_size = soft
    elif kind == "SUN":
        lamp.angle = math.radians(soft)
    ob[rig.DISTANCE] = distance
    ob.update_tag()
    return ob


def fill_light(loc, target, energy, size=4.0, color=(1, 1, 1)):
    lamp = bpy.data.lights.new("Fill", "AREA")
    lamp.energy = energy
    lamp.size = size
    lamp.color = color
    ob = bpy.data.objects.new("Fill", lamp)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = loc
    ob.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    return ob


def haze(density, anisotropy=0.4):
    rig.set_haze(bpy.context.scene, True, density)
    n = rig.haze_node(bpy.context.scene.world)
    n.inputs["Anisotropy"].default_value = anisotropy


def warm(k):
    """Rough blackbody colour for a temperature in kelvin (for lamp colours)."""
    t = k / 100.0
    r = 1.0 if t <= 66 else min(1.0, 1.292936 * (t - 60) ** -0.1332)
    g = (0.39008 * math.log(t) - 0.6318) if t <= 66 else 1.1298 * (t - 60) ** -0.0755
    b = 1.0 if t >= 66 else (0.0 if t <= 19 else 0.5432 * math.log(t - 10) - 1.1963)
    return tuple(max(0.0, min(1.0, c)) ** 2.2 for c in (r, g, b))


# -- scenes -----------------------------------------------------------------------------------


def scene_sunroom():
    """Golden hour through a window, leaves outside, dust in the air."""
    reset((0.012, 0.014, 0.02), exposure=-0.2)
    plaster = material("Plaster", "#d9cbb8", 0.9, bump=0.08, bump_scale=60)
    plane("Floor", (12, 12), (0, 0, 0), plank_floor("Oak", "#9c6b43"))
    plane("Wall", (12, 6), (0, 2.2, 3), plaster, rot=(math.pi / 2, 0, 0))
    # sofa
    fabric = material("Linen", "#b9a58c", 0.95, bump=0.15, bump_scale=300)
    box("Sofa Base", (2.2, 0.9, 0.42), (1.2, 1.55, 0.25), fabric, 0.04)
    box("Sofa Back", (2.2, 0.25, 0.55), (1.2, 1.95, 0.68), fabric, 0.06)
    for x in (0.18, 2.22):
        box("Arm", (0.22, 0.9, 0.62), (x, 1.55, 0.35), fabric, 0.06)
    for i, x in enumerate((0.72, 1.68)):
        box("Cushion", (0.9, 0.7, 0.16), (x, 1.5, 0.54), fabric, 0.06)
    # side table, vase, branch
    wood = material("Walnut", "#4a2f1e", 0.4, variation=0.2)
    cylinder("Table Top", 0.32, 0.04, (-0.55, 1.4, 0.55), wood)
    cylinder("Table Leg", 0.035, 0.55, (-0.55, 1.4, 0.0), wood)
    ceramic = material("Ceramic", "#e8e1d6", 0.25, coat=0.3)
    lathe("Vase", [(0.0, 0.0), (0.09, 0.0), (0.12, 0.08), (0.11, 0.2), (0.05, 0.3), (0.045, 0.36),
                   (0.06, 0.4)], (-0.55, 1.4, 0.59), ceramic)
    rug = material("Rug", "#7d5a46", 1.0, bump=0.3, bump_scale=500, variation=0.3)
    box("Rug", (3.4, 2.2, 0.015), (0.7, 0.6, 0.008), rug, 0.004)
    shadow_light("WINDOW_LEAVES", (-3.2, -3.0, 3.6), (0.5, 1.9, 1.0), 9000.0, cone=55,
                 color=warm(3300), soft=0.005, distance=1.6,
                 values={"Columns": 3.0, "Rows": 2.0, "Leaves": 0.55, "Width": 0.9, "Height": 0.75,
                         "Transform.Rotation": math.radians(8)})
    fill_light((2.0, -5.0, 3.0), (0.5, 1.5, 0.8), 140.0, 6.0, (0.6, 0.72, 1.0))
    haze(0.012)
    camera((2.9, -4.6, 1.45), (0.3, 1.5, 0.95), lens=30)
    return "sunroom", (2400, 1200)


def scene_noir():
    """A bust behind venetian blinds, cold night light."""
    reset((0.004, 0.005, 0.008), exposure=0.2)
    wall = material("Wall", "#5e6670", 0.85, bump=0.1, bump_scale=80)
    plane("Floor", (10, 10), (0, 0, 0), material("Floor", "#26272a", 0.6, bump=0.05))
    plane("Wall", (10, 6), (0, 1.0, 3), wall, rot=(math.pi / 2, 0, 0))
    stone = material("Plinth", "#3c3d40", 0.5, bump=0.1)
    box("Plinth", (0.6, 0.6, 1.0), (0.1, 0.2, 0.5), stone, 0.01)
    bpy.ops.mesh.primitive_monkey_add(location=(0.1, 0.2, 1.38), rotation=(math.radians(-10), 0, math.radians(-25)))
    head = bpy.context.active_object
    head.scale = (0.42, 0.42, 0.42)
    head.data.materials.append(material("Plaster Bust", "#d9d6cf", 0.55, sss=0.15))
    m = head.modifiers.new("Subsurf", "SUBSURF")
    m.levels = m.render_levels = 3
    bpy.ops.object.shade_smooth()
    shadow_light("BLINDS_NARROW", (-3.0, -4.0, 3.2), (0.1, 0.5, 1.3), 12000.0, cone=26,
                 color=(0.62, 0.74, 1.0), soft=0.01, distance=2.0,
                 values={"Slats": 18.0, "Openness": 0.45, "Transform.Rotation": math.radians(-14)})
    fill_light((2.5, -2.5, 2.0), (0.1, 0.2, 1.3), 12.0, 2.0, (1.0, 0.55, 0.3))
    haze(0.02)
    camera((1.05, -2.6, 1.55), (0.0, 0.5, 1.35), lens=45)
    return "noir", (1600, 900)


def scene_cathedral():
    """Coloured light from a rose window across a stone nave."""
    reset((0.006, 0.006, 0.008), exposure=0.3)
    stone = material("Limestone", "#b7ab98", 0.8, bump=0.25, bump_scale=25, variation=0.25)
    plane("Floor", (16, 30), (0, 6, 0), tiles("Flagstones", "#8f8576", size=0.8, rough=0.7))
    plane("Back Wall", (16, 14), (0, 14, 7), stone, rot=(math.pi / 2, 0, 0))
    for side in (-1, 1):
        for i in range(4):
            cylinder(f"Column {side} {i}", 0.42, 9.0, (side * 2.6, 1.5 + i * 3.4, 0), stone, 0.02)
            box("Base", (1.1, 1.1, 0.3), (side * 2.6, 1.5 + i * 3.4, 0.15), stone, 0.02)
    shadow_light("ROSE_COLOUR", (0.4, 13.0, 13.5), (0.0, 2.5, 0.0), 80000.0, cone=34,
                 soft=0.0, distance=2.0, values={"Colour": 1.0})
    fill_light((0, -6, 5), (0, 6, 2), 300.0, 10.0, (0.55, 0.62, 0.8))
    haze(0.012, 0.3)
    camera((0.5, -5.5, 1.6), (0.0, 6.0, 0.9), lens=24, shift_y=0.1)
    return "cathedral", (1600, 900)


def scene_palm():
    """Palm fronds on a sun-baked terracotta wall."""
    reset((0.03, 0.035, 0.05), exposure=-1.0)
    wall = material("Stucco", "#c9775a", 0.9, bump=0.35, bump_scale=30, variation=0.15)
    plane("Wall", (10, 6), (0, 1.0, 3), wall, rot=(math.pi / 2, 0, 0))
    plane("Floor", (10, 10), (0, -4, 0), tiles("Terracotta", "#b5694a", size=0.35))
    jar = material("Glazed Jar", "#2f5a5c", 0.25, coat=0.6)
    lathe("Jar", [(0.0, 0.0), (0.16, 0.0), (0.28, 0.25), (0.3, 0.45), (0.2, 0.7), (0.14, 0.78),
                  (0.17, 0.82)], (0.9, 0.55, 0.0), jar)
    bench = material("Bench", "#e9e2d4", 0.7, bump=0.1)
    box("Bench", (1.6, 0.45, 0.42), (-0.8, 0.7, 0.21), bench, 0.03)
    shadow_light("PALM", (-3.0, -6.0, 5.5), (0.0, 1.0, 1.6), 30000.0, cone=52,
                 color=warm(4300), soft=0.006, distance=3.5,
                 values={"Count": 7.0, "Origin X": 0.55, "Origin Y": -0.75, "Transform.Scale": 0.75})
    fill_light((0, -6, 2), (0, 1, 1), 160.0, 8.0, (0.55, 0.7, 1.0))
    camera((0.6, -4.2, 1.2), (0.1, 1.0, 1.45), lens=32)
    return "palm", (1600, 900)


def scene_moroccan():
    """A carved screen throwing stars across a riad floor."""
    reset((0.01, 0.009, 0.008), exposure=0.0)
    plaster = material("Tadelakt", "#d8b48a", 0.55, bump=0.12, bump_scale=20, variation=0.2)
    plane("Wall", (12, 6), (0, 2.5, 3), plaster, rot=(math.pi / 2, 0, 0))
    plane("Floor", (12, 12), (0, 0, 0), tiles("Zellige", "#d9d2c3", grout="#8d806e", size=0.2, rough=0.3))
    brass = material("Brass", "#c9a45c", 0.3, metal=1.0)
    lathe("Lantern", [(0.0, 0.0), (0.12, 0.0), (0.18, 0.15), (0.12, 0.38), (0.04, 0.5), (0.0, 0.52)],
          (1.0, 1.6, 0.0), brass)
    cushion = material("Velvet", "#7a2a28", 0.9, bump=0.2, bump_scale=300)
    box("Pouf", (0.7, 0.7, 0.38), (-1.2, 1.4, 0.2), cushion, 0.12)
    shadow_light("MOROCCAN", (-1.0, -5.0, 6.0), (0.0, 1.0, 0.0), 30000.0, cone=62,
                 color=warm(3600), soft=0.0, distance=2.5,
                 values={"Cells": 7.0, "Bar": 0.06})
    fill_light((3, -4, 3), (0, 1, 0.5), 60.0, 5.0, (0.7, 0.8, 1.0))
    haze(0.008)
    camera((0.2, -3.6, 2.4), (0.0, 1.1, 0.25), lens=28)
    return "moroccan", (1600, 900)


def scene_zen():
    """Bamboo moving on paper walls, a tea table."""
    reset((0.02, 0.022, 0.02), exposure=-0.8)
    paper = material("Washi", "#ece4d2", 0.95, bump=0.15, bump_scale=200, sss=0.05)
    plane("Wall", (10, 6), (0, 1.0, 3), paper, rot=(math.pi / 2, 0, 0))
    wood = material("Hinoki", "#c9a47a", 0.5, variation=0.2)
    for x in (-2.4, -0.8, 0.8, 2.4):
        box("Frame", (0.06, 0.06, 6.0), (x, 0.96, 3.0), material("Dark Wood", "#2c2018", 0.5), 0.005)
    box("Rail", (10, 0.06, 0.06), (0, 0.96, 2.2), material("Dark Wood", "#2c2018", 0.5), 0.005)
    plane("Tatami", (10, 10), (0, -4, 0), material("Tatami", "#b8ad7a", 0.9, bump=0.3, bump_scale=400,
                                                  variation=0.15))
    box("Table", (1.2, 0.7, 0.06), (0.0, 0.0, 0.33), wood, 0.01)
    for x in (-0.5, 0.5):
        for y in (-0.28, 0.28):
            box("Leg", (0.06, 0.06, 0.3), (x, y, 0.15), wood, 0.005)
    bowl = material("Raku", "#2b2724", 0.35, coat=0.4)
    lathe("Bowl", [(0.0, 0.0), (0.04, 0.0), (0.06, 0.02), (0.075, 0.07), (0.072, 0.08)],
          (0.25, 0.05, 0.36), bowl)
    shadow_light("BAMBOO", (-2.0, -6.0, 3.5), (0.0, 1.0, 1.5), 24000.0, cone=58,
                 color=warm(5200), soft=0.008, distance=3.0,
                 values={"Stalks": 6.0, "Leaves": 0.9, "Back Layer": 0.7,
                         "Transform.Scale": 0.6})
    fill_light((0, -6, 2), (0, 1, 1), 80.0, 8.0, (0.8, 0.85, 1.0))
    camera((0.4, -3.4, 0.95), (0.0, 1.0, 1.0), lens=30)
    return "zen", (1600, 900)


SCENES = {"sunroom": scene_sunroom, "noir": scene_noir, "cathedral": scene_cathedral,
          "palm": scene_palm, "moroccan": scene_moroccan, "zen": scene_zen}


def main():
    names = [a for a in argv if a in SCENES] or list(SCENES)
    os.makedirs(OUT, exist_ok=True)
    for name in names:
        key, (w, h) = SCENES[name]()
        sc = bpy.context.scene
        sc.render.resolution_x, sc.render.resolution_y = int(w * SCALE), int(h * SCALE)
        sc.frame_set(1)
        sc.render.filepath = os.path.join(OUT, key + ("_plain" if PLAIN else "") + ".png")
        bpy.ops.render.render(write_still=True)
        print("showcase", key)


main()
