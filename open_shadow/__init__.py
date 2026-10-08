# SPDX-License-Identifier: GPL-3.0-or-later
"""Open Shadow: open source procedural gobo lights for Blender."""

import bpy
from bpy.app.handlers import persistent

from . import ops, props, rig, thumbs, ui

_owner = object()


def _subscribe():
    bpy.msgbus.clear_by_owner(_owner)
    bpy.msgbus.subscribe_rna(key=(bpy.types.Light, "type"), owner=_owner, args=(),
                             notify=rig.sync_types)


@persistent
def _on_load(*_args):
    """Rebuild node groups saved with an older add-on version, and watch lamp
    type changes (subscriptions are cleared when a file loads)."""
    try:
        rig.upgrade_file()
        rig.sync_types()
    except Exception as e:  # never block file loading
        print("Open Shadow: upgrade failed:", e)
    _subscribe()


def register():
    props.register()
    ops.register()
    ui.register()
    bpy.app.handlers.load_post.append(_on_load)
    _subscribe()


def unregister():
    bpy.msgbus.clear_by_owner(_owner)
    if _on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load)
    ui.unregister()
    ops.unregister()
    props.unregister()
    thumbs.clear()
