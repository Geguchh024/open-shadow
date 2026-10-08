# SPDX-License-Identifier: GPL-3.0-or-later
"""Settings. Per-light settings are views onto the rig (custom properties and
material nodes), so nothing here has to be kept in sync."""

import bpy

from . import patterns, presets, rig, thumbs

LIGHT_TYPES = [
    ("SPOT", "Spot", "Cone of light; the pattern fills the cone", "LIGHT_SPOT", 0),
    ("AREA", "Area", "Soft panel light", "LIGHT_AREA", 1),
    ("SUN", "Sun", "Parallel sunlight through a pattern of a set size", "LIGHT_SUN", 2),
    ("POINT", "Point", "Omni light; only the side facing the pattern is shaped", "LIGHT_POINT", 3),
]

PATTERN_ITEMS = [(p.id, p.label, p.description, p.icon, i)
                 for i, p in enumerate(patterns.PATTERNS)]
PATTERN_ITEMS.append((patterns.IMAGE, "Image", "Use your own black and white image",
                      "IMAGE_DATA", len(PATTERN_ITEMS)))
PATTERN_IDS = [it[0] for it in PATTERN_ITEMS]

_preset_items = []  # Blender needs references to dynamic enum items kept alive


def preset_items(self, context):
    cat = self.category if self else "ALL"
    _preset_items.clear()
    for i, (pid, label, pcat, pattern, _) in enumerate(presets.PRESETS):
        if cat != "ALL" and pcat != cat:
            continue
        desc = patterns.PATTERN_BY_ID[pattern].description
        _preset_items.append((pid, label, desc, thumbs.icon(pid), i))
    return _preset_items


def _active_shadow(context):
    return rig.light_of(context.active_object) if context else None


def _preset_changed(self, context):
    if _active_shadow(context) is not None:
        bpy.ops.open_shadow.apply_preset(preset=self.preset)


def _category_changed(self, context):
    items = preset_items(self, context)
    if items and self.get("preset") not in {it[4] for it in items}:
        self["preset"] = items[0][4]  # skip the update: browsing must not apply


def _get_haze(self):
    return rig.haze_node(self.id_data.world) is not None


def _set_haze(self, value):
    rig.set_haze(self.id_data, value)


def _get_haze_density(self):
    n = rig.haze_node(self.id_data.world)
    return n.inputs["Density"].default_value if n else 0.03


def _set_haze_density(self, value):
    n = rig.haze_node(self.id_data.world)
    if n:
        n.inputs["Density"].default_value = value


class OS_SceneSettings(bpy.types.PropertyGroup):
    category: bpy.props.EnumProperty(
        name="Category", items=presets.CATEGORIES, update=_category_changed)
    preset: bpy.props.EnumProperty(
        name="Preset", items=preset_items, update=_preset_changed,
        description="Shadow pattern. Picking one changes the active shadow light")
    light_type: bpy.props.EnumProperty(
        name="Light Type", items=LIGHT_TYPES, default="SPOT",
        description="Type of lamp for new shadow lights")
    haze: bpy.props.BoolProperty(
        name="Haze", get=_get_haze, set=_set_haze,
        description="Fill the world with a thin volume so the light draws visible beams "
                    "(slower to render)")
    haze_density: bpy.props.FloatProperty(
        name="Density", min=0.0, soft_max=0.5, precision=3, step=0.1,
        get=_get_haze_density, set=_set_haze_density)


def _light(self):
    return rig.light_of(self.id_data)


def _get_pattern(self):
    pid = rig.current_pattern(_light(self))
    return PATTERN_IDS.index(pid) if pid in PATTERN_IDS else 0


def _set_pattern(self, value):
    ob = _light(self)
    if ob is not None:
        rig.set_pattern(ob, PATTERN_IDS[value])


def _custom_getter(key, default):
    def get(self):
        ob = _light(self)
        return float(ob.get(key, default)) if ob else default

    def set(self, value):
        ob = _light(self)
        if ob is not None:
            ob[key] = value
            ob.update_tag()  # re-evaluate the plane drivers

    return get, set


_get_dist, _set_dist = _custom_getter(rig.DISTANCE, 1.0)
_get_size, _set_size = _custom_getter(rig.SIZE, 2.0)


class OS_ObjectSettings(bpy.types.PropertyGroup):
    pattern: bpy.props.EnumProperty(
        name="Pattern", items=PATTERN_ITEMS, get=_get_pattern, set=_set_pattern,
        description="Procedural pattern (resets its settings)")
    distance: bpy.props.FloatProperty(
        name="Focus Distance", subtype="DISTANCE", min=0.001, soft_max=10.0,
        get=_get_dist, set=_set_dist,
        description="Distance from the lamp to the pattern. Further away gives sharper "
                    "shadows (and, for Sun and Area lamps, moves the pattern)")
    size: bpy.props.FloatProperty(
        name="Pattern Size", subtype="DISTANCE", min=0.001, soft_max=50.0,
        get=_get_size, set=_set_size,
        description="Width of the pattern plane (Sun, Area and Point lamps; Spot "
                    "lamps fit the cone automatically)")


def register():
    bpy.utils.register_class(OS_SceneSettings)
    bpy.utils.register_class(OS_ObjectSettings)
    bpy.types.Scene.open_shadow = bpy.props.PointerProperty(type=OS_SceneSettings)
    bpy.types.Object.open_shadow = bpy.props.PointerProperty(type=OS_ObjectSettings)


def unregister():
    del bpy.types.Object.open_shadow
    del bpy.types.Scene.open_shadow
    bpy.utils.unregister_class(OS_ObjectSettings)
    bpy.utils.unregister_class(OS_SceneSettings)
