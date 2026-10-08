# SPDX-License-Identifier: GPL-3.0-or-later
"""Render the preset gallery thumbnails.

    blender -b --factory-startup --python tools/render_thumbnails.py [-- [--size N] [--out DIR] PRESET_ID ...]

Writes open_shadow/thumbs/<ID>.png: the light that passes the pattern,
white = light, black = shadow. --size and --out render larger copies
elsewhere (the website uses docs/images/patterns at 512 px).
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import bpy  # noqa: E402

import open_shadow  # noqa: E402

open_shadow.register()
from open_shadow import presets, rig  # noqa: E402

OUT = os.path.join(ROOT, "open_shadow", "thumbs")
SIZE = 192


def setup(size=SIZE):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.taa_render_samples = 8
    scene.render.resolution_x = scene.render.resolution_y = size
    scene.view_settings.view_transform = "Standard"
    cam = bpy.data.cameras.new("Thumb")
    cam.type = "ORTHO"
    cam.ortho_scale = 1.0
    co = bpy.data.objects.new("Thumb", cam)
    co.location = (0.0, 0.0, 1.0)  # behind the lamp, looking along it
    scene.collection.objects.link(co)
    scene.camera = co
    ob = rig.create(bpy.context, "SUN", "WINDOW", target=(0.0, 0.0, -10.0))
    ob.location = (0.0, 0.0, 0.0)
    ob.rotation_euler = (0.0, 0.0, 0.0)
    ob.data.energy = 0.0
    ob["os_size"] = 1.0
    ob["os_distance"] = 0.5
    plane = rig.plane_of(ob)
    plane.visible_camera = True
    nt = rig.material_of(ob).node_tree
    em = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(nt.nodes[rig.N_FINISH].outputs["Light"], em.inputs["Color"])
    out = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeOutputMaterial")
    nt.links.new(em.outputs[0], out.inputs["Surface"])
    return scene, ob


def main():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    size, out = SIZE, OUT
    if "--size" in args:
        i = args.index("--size")
        size = int(args[i + 1])
        del args[i:i + 2]
    if "--out" in args:
        i = args.index("--out")
        out = os.path.join(ROOT, args[i + 1])
        del args[i:i + 2]
    ids = args or [p[0] for p in presets.PRESETS]
    os.makedirs(out, exist_ok=True)
    scene, ob = setup(size)
    for pid in ids:
        rig.apply_preset(ob, pid)
        scene.frame_set(1)
        scene.render.filepath = os.path.join(out, pid + ".png")
        bpy.ops.render.render(write_still=True)
        print("thumb", pid)


main()
