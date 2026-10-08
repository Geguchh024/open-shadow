# SPDX-License-Identifier: GPL-3.0-or-later
import random

import bpy

from . import presets, rig

PRESET_ENUM = [(p[0], p[1], "") for p in presets.PRESETS]


def _shadow(context):
    return rig.light_of(context.active_object)


class OS_OT_add(bpy.types.Operator):
    bl_idname = "open_shadow.add"
    bl_label = "Add Shadow Light"
    bl_description = "Add a lamp that casts the chosen pattern, aimed at the 3D cursor"
    bl_options = {"REGISTER", "UNDO"}

    light_type: bpy.props.EnumProperty(
        name="Type", items=[(t[0], t[1], t[2]) for t in
                            (("SPOT", "Spot", ""), ("AREA", "Area", ""),
                             ("SUN", "Sun", ""), ("POINT", "Point", ""))])
    preset: bpy.props.EnumProperty(name="Preset", items=PRESET_ENUM)

    def invoke(self, context, event):
        st = context.scene.open_shadow
        self.light_type = st.light_type
        if st.preset:
            self.preset = st.preset
        return self.execute(context)

    def execute(self, context):
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        ob = rig.create(context, self.light_type, presets.PRESET_BY_ID[self.preset][3])
        rig.apply_preset(ob, self.preset)
        for o in context.selected_objects:
            o.select_set(False)
        ob.select_set(True)
        context.view_layer.objects.active = ob
        return {"FINISHED"}


class OS_OT_attach(bpy.types.Operator):
    bl_idname = "open_shadow.attach"
    bl_label = "Add Pattern to Light"
    bl_description = "Give the selected lamps a shadow pattern"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return any(o.type == "LIGHT" for o in context.selected_objects)

    def execute(self, context):
        preset = context.scene.open_shadow.preset or presets.PRESETS[0][0]
        for ob in context.selected_objects:
            if ob.type == "LIGHT" and rig.plane_of(ob) is None:
                rig.attach(ob)
                rig.apply_preset(ob, preset)
        return {"FINISHED"}


class OS_OT_apply_preset(bpy.types.Operator):
    bl_idname = "open_shadow.apply_preset"
    bl_label = "Apply Preset"
    bl_description = "Set the active shadow light's pattern and settings to a preset"
    bl_options = {"REGISTER", "UNDO"}

    preset: bpy.props.EnumProperty(name="Preset", items=PRESET_ENUM)

    @classmethod
    def poll(cls, context):
        return _shadow(context) is not None

    def execute(self, context):
        rig.apply_preset(_shadow(context), self.preset)
        return {"FINISHED"}


class OS_OT_remove(bpy.types.Operator):
    bl_idname = "open_shadow.remove"
    bl_label = "Remove Pattern"
    bl_description = "Delete the shadow pattern and keep the lamp"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _shadow(context) is not None

    def execute(self, context):
        ob = _shadow(context)
        rig.detach(ob)
        context.view_layer.objects.active = ob
        ob.select_set(True)
        return {"FINISHED"}


class OS_OT_aim(bpy.types.Operator):
    bl_idname = "open_shadow.aim"
    bl_label = "Aim at Cursor"
    bl_description = "Point the shadow light at the 3D cursor"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _shadow(context) is not None

    def execute(self, context):
        rig.aim(_shadow(context), context.scene.cursor.location)
        return {"FINISHED"}


class OS_OT_random_seed(bpy.types.Operator):
    bl_idname = "open_shadow.random_seed"
    bl_label = "Random Seed"
    bl_description = "Pick a new random variation of the pattern"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        n = rig.node(_shadow(context), rig.N_PATTERN)
        return n is not None and not n.mute and "Seed" in n.inputs

    def execute(self, context):
        n = rig.node(_shadow(context), rig.N_PATTERN)
        n.inputs["Seed"].default_value = float(random.randint(0, 999))
        return {"FINISHED"}


class OS_OT_reset(bpy.types.Operator):
    bl_idname = "open_shadow.reset"
    bl_label = "Reset Pattern"
    bl_description = "Set the pattern, placement and look back to their defaults"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _shadow(context) is not None

    def execute(self, context):
        ob = _shadow(context)
        rig.set_pattern(ob, rig.current_pattern(ob))
        rig.reset_look(ob)
        return {"FINISHED"}


class OS_OT_make_unique(bpy.types.Operator):
    bl_idname = "open_shadow.make_unique"
    bl_label = "Make Unique"
    bl_description = ("This pattern is shared with other lights (e.g. after duplicating). "
                      "Give this light its own copy")
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _shadow(context) is not None

    def execute(self, context):
        rig.make_unique(_shadow(context))
        return {"FINISHED"}


class OS_OT_select_light(bpy.types.Operator):
    bl_idname = "open_shadow.select_light"
    bl_label = "Select Light"
    bl_description = "Select a shadow light"
    bl_options = {"REGISTER", "UNDO"}

    name: bpy.props.StringProperty()

    def execute(self, context):
        ob = context.scene.objects.get(self.name)
        if ob is None or context.view_layer.objects.get(ob.name) is None:
            return {"CANCELLED"}
        for o in context.selected_objects:
            o.select_set(False)
        ob.select_set(True)
        context.view_layer.objects.active = ob
        return {"FINISHED"}


CLASSES = (OS_OT_add, OS_OT_attach, OS_OT_apply_preset, OS_OT_remove, OS_OT_aim,
           OS_OT_random_seed, OS_OT_reset, OS_OT_make_unique, OS_OT_select_light)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
