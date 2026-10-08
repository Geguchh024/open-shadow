# SPDX-License-Identifier: GPL-3.0-or-later
"""Shadow lights: a lamp with a hidden "gobo" plane in front of it.

The plane is parented to the lamp and placed along its -Z axis by drivers
(no Python in the expressions, so files work without the add-on). It is
invisible to the camera and to reflections; it only casts shadows, through
a material whose transparency is the pattern. This works in both Cycles
and EEVEE. Coloured patterns (stained glass) tint the light in Cycles.

Custom properties on the lamp object:
    os_distance  distance from the lamp to the plane (the "focus")
    os_size      plane width for Sun, Area and Point lamps
"""

import math

import bpy
from mathutils import Vector

from . import nodekit, patterns

PLANE_TAG = "os_shadow_plane"
MAT_TAG = "os_shadow_material"
DISTANCE = "os_distance"
SIZE = "os_size"
TYPE = "os_lamp_type"  # lamp type the plane drivers were built for
SPOT_MARGIN = 1.1   # the plane is a bit larger than the cone, so no light leaks
HAZE_NODE = "OS Haze"

N_TRANSFORM, N_PATTERN, N_IMAGE, N_FINISH = "Transform", "Pattern", "Image", "Finish"


# -- lookup ---------------------------------------------------------------------------


def plane_of(light_ob):
    if light_ob is None:
        return None
    for ch in light_ob.children:
        if ch.get(PLANE_TAG):
            return ch
    return None


def light_of(ob):
    """The shadow lamp for an object: the lamp itself or its gobo plane."""
    if ob is None:
        return None
    if ob.get(PLANE_TAG):
        return ob.parent if ob.parent and ob.parent.type == "LIGHT" else None
    if ob.type == "LIGHT" and plane_of(ob) is not None:
        return ob
    return None


def material_of(light_ob):
    plane = plane_of(light_ob)
    if plane is None or not plane.data.materials:
        return None
    return plane.data.materials[0]


def node(light_ob, name):
    mat = material_of(light_ob)
    return mat.node_tree.nodes.get(name) if mat else None


def current_pattern(light_ob):
    mat = material_of(light_ob)
    if mat is None:
        return None
    return mat.get("os_pattern")


# -- creation ---------------------------------------------------------------------------


def _new_plane_mesh(name):
    me = bpy.data.meshes.new(name)
    me.from_pydata([(-0.5, -0.5, 0.0), (0.5, -0.5, 0.0), (0.5, 0.5, 0.0), (-0.5, 0.5, 0.0)],
                   [], [(0, 1, 2, 3)])
    me.update()
    return me


def _driver(ob, path, index, expression, variables):
    ob.driver_remove(path, index)
    fc = ob.driver_add(path, index)
    drv = fc.driver
    drv.type = "SCRIPTED"
    for name, id_type, idb, data_path in variables:
        v = drv.variables.new()
        v.name = name
        v.type = "SINGLE_PROP"
        v.targets[0].id_type = id_type
        v.targets[0].id = idb
        v.targets[0].data_path = data_path
    drv.expression = expression
    return fc


def add_drivers(light_ob, plane):
    """Place and size the plane. Spot lamps fit the plane to the cone; other
    lamps use the os_size property. Only Spot lamps have a spot_size, so the
    drivers are rebuilt when the lamp type changes (see sync_types)."""
    lamp = light_ob.data
    _driver(plane, "location", 2, "-d", [("d", "OBJECT", light_ob, f'["{DISTANCE}"]')])
    if lamp.type == "SPOT":
        expr = f"2*d*tan(min(a,3.0)/2)*{SPOT_MARGIN}"
        variables = [("d", "OBJECT", light_ob, f'["{DISTANCE}"]'),
                     ("a", "LIGHT", lamp, "spot_size")]
    else:
        expr = "s"
        variables = [("s", "OBJECT", light_ob, f'["{SIZE}"]')]
    for i in (0, 1):
        _driver(plane, "scale", i, expr, variables)
    plane[TYPE] = lamp.type


def sync_types(*_args):
    """Rebuild the plane drivers of lamps whose type changed."""
    for ob in bpy.data.objects:
        if ob.type != "LIGHT":
            continue
        plane = plane_of(ob)
        if plane is not None and plane.get(TYPE) != ob.data.type:
            add_drivers(ob, plane)


def _build_material(name):
    mat = bpy.data.materials.new(name)
    mat[MAT_TAG] = True
    if hasattr(mat, "use_nodes") and not mat.use_nodes:
        mat.use_nodes = True
    # EEVEE: let the pattern's transparency through to shadows
    if hasattr(mat, "surface_render_method"):
        mat.surface_render_method = "DITHERED"
    if hasattr(mat, "use_transparent_shadow"):
        mat.use_transparent_shadow = True
    mat.diffuse_color = (0.1, 0.1, 0.1, 0.4)
    nt = mat.node_tree
    nt.nodes.clear()
    nb = nodekit.NB(nt)
    tc = nb.node("ShaderNodeTexCoord")
    tr = nodekit.group_node(nb, patterns.ensure_transform())
    tr.name = tr.label = N_TRANSFORM
    pat = nb.node("ShaderNodeGroup")
    pat.name = N_PATTERN
    img = nb.node("ShaderNodeTexImage", extension="CLIP")
    img.name = img.label = N_IMAGE
    fin = nodekit.group_node(nb, patterns.ensure_finish())
    fin.name = fin.label = N_FINISH
    bsdf = nb.node("ShaderNodeBsdfTransparent")
    out = nb.node("ShaderNodeOutputMaterial")
    nb.link(tc.outputs["Object"], tr.inputs["Vector"])
    nb.link(tc.outputs["Object"], fin.inputs["Vector"])
    nb.link(fin.outputs["Light"], bsdf.inputs["Color"])
    nb.link(bsdf.outputs[0], out.inputs["Surface"])
    # image coordinates: -0.5..0.5 -> 0..1
    mp = nb.node("ShaderNodeMapping")
    mp.name = "Image Mapping"
    nb.set(mp, "Location", (0.5, 0.5, 0.0))
    nb.link(tr.outputs["Vector"], mp.inputs["Vector"])
    nb.link(mp.outputs["Vector"], img.inputs["Vector"])
    for i, n in enumerate((tc, tr, pat, fin, bsdf, out)):
        n.location = (i * 220, 0)
    mp.location, img.location = (440, -260), (660, -260)
    return mat


def set_pattern(light_ob, pid, reset=True):
    """Switch the gobo to a pattern id (or patterns.IMAGE)."""
    mat = material_of(light_ob)
    nt = mat.node_tree
    pat, img, fin = nt.nodes[N_PATTERN], nt.nodes[N_IMAGE], nt.nodes[N_FINISH]
    tr = nt.nodes[N_TRANSFORM]
    if pid == patterns.IMAGE:
        nt.links.new(img.outputs["Color"], fin.inputs["Light"])
        pat.mute = True
    else:
        group = patterns.ensure(pid)
        same = pat.node_tree == group
        pat.node_tree = group
        pat.label = patterns.PATTERN_BY_ID[pid].label
        pat.mute = False
        nt.links.new(tr.outputs["Vector"], pat.inputs["Vector"])
        nt.links.new(pat.outputs["Light"], fin.inputs["Light"])
        # Swapping the tree keeps the old values by socket index, so always
        # write the new pattern's defaults.
        if reset or not same:
            for name, v in patterns.default_inputs(pid).items():
                pat.inputs[name].default_value = v
    mat["os_pattern"] = pid


def reset_look(light_ob):
    for name in (N_TRANSFORM, N_FINISH):
        n = node(light_ob, name)
        if n is None:
            continue
        for item in n.node_tree.interface.items_tree:
            if item.item_type == "SOCKET" and item.in_out == "INPUT" and hasattr(item, "default_value"):
                if not n.inputs[item.name].is_linked:
                    n.inputs[item.name].default_value = item.default_value


def attach(light_ob, pid="WINDOW"):
    """Give a lamp a shadow plane (or return the existing one)."""
    plane = plane_of(light_ob)
    if plane is not None:
        return plane
    lamp = light_ob.data
    if DISTANCE not in light_ob:
        light_ob[DISTANCE] = 1.0
    if SIZE not in light_ob:
        light_ob[SIZE] = 2.0
    ui = light_ob.id_properties_ui(DISTANCE)
    ui.update(min=0.001, soft_max=20.0, subtype="DISTANCE",
              description="Distance from the lamp to the shadow pattern")
    ui = light_ob.id_properties_ui(SIZE)
    ui.update(min=0.001, soft_max=100.0, subtype="DISTANCE",
              description="Width of the shadow pattern (Sun, Area and Point lamps)")
    name = light_ob.name + " Shadow"
    plane = bpy.data.objects.new(name, _new_plane_mesh(name))
    plane[PLANE_TAG] = True
    for coll in light_ob.users_collection:
        coll.objects.link(plane)
    plane.parent = light_ob
    plane.matrix_parent_inverse.identity()
    for attr in ("visible_camera", "visible_diffuse", "visible_glossy",
                 "visible_transmission"):
        setattr(plane, attr, False)
    plane.visible_shadow = True
    plane.display_type = "WIRE"
    plane.hide_select = True
    mat = _build_material(name)
    plane.data.materials.append(mat)
    add_drivers(light_ob, plane)
    set_pattern(light_ob, pid)
    # sharper shadows read better with a gobo
    if lamp.type in {"SPOT", "POINT"} and lamp.shadow_soft_size > 0.05:
        lamp.shadow_soft_size = 0.01
    if lamp.type == "SPOT":
        lamp.spot_blend = min(lamp.spot_blend, 0.1)
    return plane


def detach(light_ob):
    plane = plane_of(light_ob)
    if plane is None:
        return
    mesh = plane.data
    mats = list(mesh.materials)
    bpy.data.objects.remove(plane)
    if mesh.users == 0:
        bpy.data.meshes.remove(mesh)
    for m in mats:
        if m is not None and m.users == 0:
            bpy.data.materials.remove(m)
    for key in (DISTANCE, SIZE):
        if key in light_ob:
            del light_ob[key]


def make_unique(light_ob):
    plane = plane_of(light_ob)
    mat = material_of(light_ob)
    if mat is None or mat.users <= 1:
        return
    plane.data = plane.data.copy()
    plane.data.materials[0] = mat.copy()


def aim(light_ob, target):
    direction = Vector(target) - light_ob.matrix_world.translation
    if direction.length < 1e-6:
        return
    light_ob.rotation_mode = "XYZ"
    light_ob.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def create(context, light_type="SPOT", pid="WINDOW", target=None):
    """New shadow lamp aimed at target (default: the 3D cursor)."""
    scene = context.scene
    target = Vector(target if target is not None else scene.cursor.location)
    lamp = bpy.data.lights.new("Shadow Light", light_type)
    if light_type == "SPOT":
        lamp.energy = 1500.0
        lamp.spot_size = math.radians(45.0)
        lamp.spot_blend = 0.05
    elif light_type == "AREA":
        lamp.energy = 800.0
        lamp.size = 0.25
        if hasattr(lamp, "spread"):
            lamp.spread = math.radians(60.0)
    elif light_type == "SUN":
        lamp.energy = 4.0
        lamp.angle = math.radians(0.6)
    else:
        lamp.energy = 1500.0
    if light_type in {"SPOT", "POINT"}:
        lamp.shadow_soft_size = 0.0  # sharp, like a gobo projector; raise for softer shadows
    ob = bpy.data.objects.new("Shadow Light", lamp)
    coll = context.collection or scene.collection
    coll.objects.link(ob)
    ob.location = target + Vector((1.5, -2.5, 3.5))
    context.view_layer.update()
    aim(ob, target)
    if light_type == "SUN":
        ob[SIZE] = 3.0
        ob[DISTANCE] = 1.0
    elif light_type == "AREA":
        ob[SIZE] = 2.5
        ob[DISTANCE] = 1.0
    else:
        ob[DISTANCE] = 1.0
    attach(ob, pid)
    return ob


def apply_values(light_ob, values):
    """Set pattern / placement / finish inputs by name (unknown names raise).

    "Transform.Scale" or "Finish.Invert" pick a node explicitly; plain names
    are looked up in the pattern, then the transform, then the finish.
    """
    for key, v in values.items():
        node_name, _, name = key.rpartition(".")
        names = (node_name,) if node_name else (N_PATTERN, N_TRANSFORM, N_FINISH)
        targets = [node(light_ob, n) for n in names]
        for n in targets:
            if n is not None and not n.mute and name in n.inputs and name != "Vector":
                sock = n.inputs[name]
                if sock.type == "RGBA" and len(v) == 3:
                    v = (*v, 1.0)
                sock.default_value = v
                break
        else:
            raise KeyError(f"no input named {name!r}")


# -- haze ------------------------------------------------------------------------------------


def haze_node(world):
    if world is None or world.node_tree is None:
        return None
    return world.node_tree.nodes.get(HAZE_NODE)


def set_haze(scene, enable, density=0.03):
    """Thin volume in the world so shadow lights draw visible beams."""
    world = scene.world
    if enable:
        if world is None:
            world = scene.world = bpy.data.worlds.new("World")
        if hasattr(world, "use_nodes") and not world.use_nodes:
            world.use_nodes = True
        nt = world.node_tree
        if nt.nodes.get(HAZE_NODE):
            return
        out = next((n for n in nt.nodes if n.bl_idname == "ShaderNodeOutputWorld"
                    and n.is_active_output), None)
        if out is None:
            out = nt.nodes.new("ShaderNodeOutputWorld")
        if out.inputs["Volume"].is_linked:
            return  # keep the user's own volume
        vol = nt.nodes.new("ShaderNodeVolumeScatter")
        vol.name = vol.label = HAZE_NODE
        vol.inputs["Density"].default_value = density
        vol.location = out.location + Vector((-220.0, -200.0))
        nt.links.new(vol.outputs[0], out.inputs["Volume"])
    else:
        n = haze_node(world)
        if n is not None:
            world.node_tree.nodes.remove(n)


# -- file upgrades ----------------------------------------------------------------------------


def shadow_materials():
    return [m for m in bpy.data.materials if m.get(MAT_TAG) and m.node_tree]


def upgrade_file():
    """Rebuild node groups saved by another add-on version, keeping values."""
    stale = [g for g in patterns.all_groups() if not patterns.is_current(g)]
    if not stale:
        return
    saved = []
    for mat in shadow_materials():
        for n in mat.node_tree.nodes:
            if n.bl_idname == "ShaderNodeGroup" and n.node_tree in stale:
                vals = {s.name: _copy(s.default_value) for s in n.inputs
                        if hasattr(s, "default_value") and not s.is_linked}
                saved.append((mat, n.name, vals))
    for g in stale:
        pid = g.get("os_pattern")
        if pid in patterns.PATTERN_BY_ID:
            patterns.ensure(pid)
        elif g.name == patterns.TRANSFORM:
            patterns.ensure_transform()
        elif g.name == patterns.FINISH:
            patterns.ensure_finish()
    for mat, name, vals in saved:
        n = mat.node_tree.nodes.get(name)
        for k, v in vals.items():
            if n is not None and k in n.inputs and hasattr(n.inputs[k], "default_value"):
                try:
                    n.inputs[k].default_value = v
                except (TypeError, ValueError):
                    pass


def _copy(v):
    try:
        return tuple(v)
    except TypeError:
        return v


def apply_preset(light_ob, preset_id):
    from . import presets
    _, _, _, pid, values = presets.PRESET_BY_ID[preset_id]
    set_pattern(light_ob, pid)
    reset_look(light_ob)
    apply_values(light_ob, presets.converted(pid, values))
    material_of(light_ob)["os_preset"] = preset_id
