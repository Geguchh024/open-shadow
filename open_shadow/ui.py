# SPDX-License-Identifier: GPL-3.0-or-later
"""Sidebar panels (View3D > Sidebar > Shadow)."""

import bpy

from . import patterns, presets, rig


def _shadow(context):
    return rig.light_of(context.active_object)


def draw_inputs(layout, node, skip=("Vector",)):
    col = layout.column(align=True)
    for s in node.inputs:
        if s.name in skip or s.is_linked or not hasattr(s, "default_value"):
            continue
        if s.name == "Seed":
            row = col.row(align=True)
            row.prop(s, "default_value", text="Seed")
            row.operator("open_shadow.random_seed", text="", icon="FILE_REFRESH")
        else:
            col.prop(s, "default_value", text=s.name)


class OS_PT_base:
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Shadow"


class OS_PT_library(OS_PT_base, bpy.types.Panel):
    bl_label = "Open Shadow"
    bl_idname = "OS_PT_library"

    def draw(self, context):
        st = context.scene.open_shadow
        col = self.layout.column()
        col.prop(st, "category", text="")
        col.template_icon_view(st, "preset", show_labels=True, scale=7.0, scale_popup=5.0)
        p = presets.PRESET_BY_ID.get(st.preset)
        if p:
            col.label(text=p[1], icon=patterns.PATTERN_BY_ID[p[3]].icon)
        col.separator()
        col.row(align=True).prop(st, "light_type", expand=True)
        row = col.row()
        row.scale_y = 1.4
        row.operator("open_shadow.add", icon="ADD")
        ob = context.active_object
        if ob is not None and ob.type == "LIGHT" and rig.plane_of(ob) is None:
            col.operator("open_shadow.attach", icon="LIGHT")


class OS_PT_light(OS_PT_base, bpy.types.Panel):
    bl_label = "Shadow Light"
    bl_idname = "OS_PT_light"

    @classmethod
    def poll(cls, context):
        return _shadow(context) is not None

    def draw_header(self, context):
        self.layout.label(text="", icon="LIGHT_" + _shadow(context).data.type)

    def draw(self, context):
        ob = _shadow(context)
        layout = self.layout
        layout.label(text=ob.name)
        mat = rig.material_of(ob)
        if mat.users > 1:
            box = layout.box()
            box.label(text="Pattern shared with other lights", icon="LINKED")
            box.operator("open_shadow.make_unique")
        layout.prop(ob.open_shadow, "pattern")
        pid = rig.current_pattern(ob)
        if pid == patterns.IMAGE:
            img = rig.node(ob, rig.N_IMAGE)
            layout.template_ID(img, "image", new="image.new", open="image.open")
            layout.label(text="White lets light through, black blocks it", icon="INFO")
        else:
            draw_inputs(layout, rig.node(ob, rig.N_PATTERN))
        row = layout.row(align=True)
        row.operator("open_shadow.reset", icon="LOOP_BACK")
        row.operator("open_shadow.remove", icon="X")


class OS_PT_placement(OS_PT_base, bpy.types.Panel):
    bl_label = "Placement"
    bl_parent_id = "OS_PT_light"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        ob = _shadow(context)
        col = self.layout.column()
        col.prop(ob.open_shadow, "distance")
        if ob.data.type != "SPOT":
            col.prop(ob.open_shadow, "size")
        draw_inputs(col, rig.node(ob, rig.N_TRANSFORM))


class OS_PT_look(OS_PT_base, bpy.types.Panel):
    bl_label = "Look"
    bl_parent_id = "OS_PT_light"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        ob = _shadow(context)
        draw_inputs(self.layout, rig.node(ob, rig.N_FINISH))
        if context.scene.render.engine != "CYCLES":
            self.layout.label(text="Coloured light needs Cycles", icon="INFO")


class OS_PT_lamp(OS_PT_base, bpy.types.Panel):
    bl_label = "Lamp"
    bl_parent_id = "OS_PT_light"

    def draw(self, context):
        ob = _shadow(context)
        lamp = ob.data
        col = self.layout.column()
        col.prop(lamp, "type", expand=False)
        col.prop(lamp, "color")
        col.prop(lamp, "energy")
        if lamp.type == "SPOT":
            col.prop(lamp, "spot_size", text="Cone")
            col.prop(lamp, "spot_blend", text="Edge Blend")
        if lamp.type == "SUN":
            col.prop(lamp, "angle", text="Softness")
        elif lamp.type == "AREA":
            col.prop(lamp, "size", text="Softness")
            if hasattr(lamp, "spread"):
                col.prop(lamp, "spread")
        else:
            col.prop(lamp, "shadow_soft_size", text="Softness")
        if context.scene.render.engine != "CYCLES" and hasattr(lamp, "use_shadow_jitter"):
            col.prop(lamp, "use_shadow_jitter", text="Accurate Soft Shadows")
        col.operator("open_shadow.aim", icon="PIVOT_CURSOR")


class OS_PT_scene(OS_PT_base, bpy.types.Panel):
    bl_label = "Scene"
    bl_idname = "OS_PT_scene"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        st = context.scene.open_shadow
        col = self.layout.column()
        row = col.row(align=True)
        row.prop(st, "haze", toggle=True, icon="OUTLINER_DATA_VOLUME")
        sub = row.row(align=True)
        sub.active = st.haze
        sub.prop(st, "haze_density")
        lights = [o for o in context.scene.objects if o.type == "LIGHT" and rig.plane_of(o)]
        if lights:
            col.separator()
            col.label(text="Shadow Lights")
            for o in lights:
                r = col.row(align=True)
                op = r.operator("open_shadow.select_light", text=o.name,
                                icon="LIGHT_" + o.data.type,
                                depress=o == context.active_object)
                op.name = o.name
                r.prop(o, "hide_viewport", text="", emboss=False)


CLASSES = (OS_PT_library, OS_PT_light, OS_PT_placement, OS_PT_look, OS_PT_lamp, OS_PT_scene)


def draw_add_menu(self, context):
    self.layout.operator("open_shadow.add", icon="LIGHT_SPOT")


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)
    bpy.types.VIEW3D_MT_light_add.append(draw_add_menu)


def unregister():
    bpy.types.VIEW3D_MT_light_add.remove(draw_add_menu)
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
