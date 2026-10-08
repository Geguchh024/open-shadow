# SPDX-License-Identifier: GPL-3.0-or-later
"""Render shadow previews of presets in a small room, plus a contact sheet.

    blender -b --factory-startup --python tools/render_previews.py [-- [--eevee] PRESET_ID ...]

Writes docs/images/previews/<ID>.png and docs/images/previews.png.
"""

import math
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import bpy  # noqa: E402

import open_shadow  # noqa: E402

open_shadow.register()
from open_shadow import rig  # noqa: E402

OUT = os.path.join(ROOT, "docs", "images")
SHEET = ("WINDOW_TUDOR", "BLINDS_PALM", "ROSE_COLOUR", "GOTHIC_COLOUR",
         "LEAVES", "FERN", "PALM", "BAMBOO",
         "MOROCCAN", "LATTICE", "SPIDER_WEB", "BRANCHES")
WIDTH, HEIGHT = 480, 320


def setup(eevee=False):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    if eevee:
        scene.render.engine = "BLENDER_EEVEE"
        scene.eevee.taa_render_samples = 64
    else:
        scene.render.engine = "CYCLES"
        scene.cycles.samples = 48
        scene.cycles.use_denoising = True
        scene.cycles.device = "CPU"
    scene.render.resolution_x, scene.render.resolution_y = WIDTH, HEIGHT
    scene.view_settings.view_transform = "AgX"
    world = bpy.data.worlds.new("World")
    world.color = (0.012, 0.012, 0.014)
    scene.world = world
    mat = bpy.data.materials.new("Plaster")
    mat.diffuse_color = (0.8, 0.78, 0.74, 1.0)
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (0.8, 0.78, 0.74, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.9
    for name, loc, rot in (("Floor", (0, 0, 0), (0, 0, 0)),
                           ("Wall", (0, 2.0, 2.5), (math.pi / 2, 0, 0))):
        bpy.ops.mesh.primitive_plane_add(size=10.0, location=loc, rotation=rot)
        ob = bpy.context.active_object
        ob.name = name
        ob.data.materials.append(mat)
    cam = bpy.data.cameras.new("Camera")
    cam.lens = 30
    co = bpy.data.objects.new("Camera", cam)
    scene.collection.objects.link(co)
    co.location = (0.0, -5.2, 1.6)
    co.rotation_euler = (math.radians(84), 0.0, 0.0)
    scene.camera = co
    ob = rig.create(bpy.context, "SPOT", "WINDOW", target=(0.0, 2.0, 1.4))
    ob.location = (-1.6, -2.4, 3.0)
    bpy.context.view_layer.update()
    rig.aim(ob, (0.2, 1.8, 1.1))
    ob.data.energy = 2600.0
    ob.data.spot_size = math.radians(62)
    ob.data.shadow_soft_size = 0.004
    ob["os_distance"] = 1.2
    fill = bpy.data.lights.new("Fill", "AREA")
    fill.energy = 12.0
    fill.size = 6.0
    fo = bpy.data.objects.new("Fill", fill)
    fo.location = (0.0, -4.0, 4.0)
    fo.rotation_euler = (math.radians(30), 0.0, 0.0)
    scene.collection.objects.link(fo)
    return scene, ob


def contact_sheet(paths, out, cols=4):
    imgs = []
    for p in paths:
        im = bpy.data.images.load(p)
        a = np.array(im.pixels[:], dtype=np.float32).reshape(im.size[1], im.size[0], 4)
        imgs.append(a)
        bpy.data.images.remove(im)
    h, w = imgs[0].shape[:2]
    rows = (len(imgs) + cols - 1) // cols
    gap = 6
    sheet = np.ones(((h + gap) * rows - gap, (w + gap) * cols - gap, 4), dtype=np.float32)
    for i, a in enumerate(imgs):
        r, c = divmod(i, cols)
        y0 = (rows - 1 - r) * (h + gap)  # Blender images start at the bottom
        sheet[y0:y0 + h, c * (w + gap):c * (w + gap) + w] = a
    img = bpy.data.images.new("sheet", sheet.shape[1], sheet.shape[0], alpha=True)
    img.pixels[:] = sheet.ravel()
    img.filepath_raw = out
    img.file_format = "PNG"
    img.save()


def main():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    eevee = "--eevee" in args
    ids = [a for a in args if not a.startswith("--")] or list(SHEET)
    folder = os.path.join(OUT, "previews_eevee" if eevee else "previews")
    os.makedirs(folder, exist_ok=True)
    scene, ob = setup(eevee)
    paths = []
    for pid in ids:
        rig.apply_preset(ob, pid)
        scene.frame_set(1)
        scene.render.filepath = os.path.join(folder, pid + ".png")
        bpy.ops.render.render(write_still=True)
        paths.append(scene.render.filepath)
        print("preview", pid)
    if not [a for a in args if not a.startswith("--")] and not eevee:
        contact_sheet(paths, os.path.join(OUT, "previews.png"))


main()
