# SPDX-License-Identifier: GPL-3.0-or-later
"""Built-in looks: a pattern plus input values.

Values are node input names. Plain names are looked up in the pattern,
then the placement ("Transform") and finish groups; use "Transform.Scale"
or "Finish.Invert" to be explicit. Angles are in degrees here.
"""

import math

from . import patterns

# (id, label, category, pattern id, values)
PRESETS = [
    # -- windows -----------------------------------------------------------------
    ("WINDOW_4", "Four-Pane Window", "WINDOWS", "WINDOW", {"Columns": 2.0, "Rows": 2.0}),
    ("WINDOW_6", "Six-Pane Window", "WINDOWS", "WINDOW", {}),
    ("WINDOW_TUDOR", "Tudor Window", "WINDOWS", "WINDOW",
     {"Columns": 4.0, "Rows": 4.0, "Diagonals": 1.0, "Width": 0.9, "Height": 0.95,
      "Bars": 0.03}),
    ("WINDOW_TALL", "Tall Window", "WINDOWS", "WINDOW",
     {"Columns": 3.0, "Rows": 5.0, "Width": 0.62, "Height": 0.96, "Bars": 0.015}),
    ("WINDOW_LEAVES", "Window and Leaves", "WINDOWS", "WINDOW", {"Leaves": 0.7}),
    ("BLINDS", "Blinds", "WINDOWS", "BLINDS", {}),
    ("BLINDS_PALM", "Blinds and Palm", "WINDOWS", "BLINDS", {"Plants": 0.85, "Openness": 0.6}),
    ("BLINDS_NARROW", "Half-Closed Blinds", "WINDOWS", "BLINDS",
     {"Slats": 24.0, "Openness": 0.3, "Mullion": 0.0, "Width": 0.95}),
    ("ROSE", "Rose Window", "WINDOWS", "ROSE", {}),
    ("ROSE_COLOUR", "Stained Rose", "WINDOWS", "ROSE",
     {"Segments": 16.0, "Colour": 0.9, "Leading": 0.4}),
    ("ROSE_8", "Eight-Petal Rose", "WINDOWS", "ROSE",
     {"Segments": 8.0, "Hub": 0.24, "Petal": 1.1, "Leading": 0.0}),
    ("GOTHIC", "Gothic Window", "WINDOWS", "GOTHIC", {}),
    ("GOTHIC_COLOUR", "Stained Lancets", "WINDOWS", "GOTHIC",
     {"Lancets": 4.0, "Colour": 0.9, "Quarries": 12.0}),
    ("BROKEN_GLASS", "Broken Glass", "WINDOWS", "GLASS", {}),
    ("SHATTERED", "Shattered Pane", "WINDOWS", "GLASS",
     {"Missing": 0.35, "Shards": 22.0, "Fine Cracks": 1.0, "Impact X": -0.15}),
    # -- screens and metal -------------------------------------------------------
    ("LATTICE", "Garden Lattice", "SCREENS", "GRID",
     {"Angle": 45.0, "Cells": 7.0, "Hole Size": 0.72}),
    ("LATTICE_FINE", "Fine Trellis", "SCREENS", "GRID",
     {"Angle": 45.0, "Cells": 12.0, "Hole Size": 0.62, "Aspect": 1.5}),
    ("GRATE", "Industrial Grate", "SCREENS", "GRID",
     {"Cells": 9.0, "Aspect": 0.7, "Hole Size": 0.62, "Roundness": 0.35}),
    ("PERFORATED", "Perforated Metal", "SCREENS", "GRID",
     {"Cells": 12.0, "Hole Size": 0.62, "Roundness": 1.0, "Stagger": 1.0}),
    ("HONEYCOMB", "Honeycomb", "SCREENS", "HEX", {}),
    ("HEX_TILES", "Hexagon Tiles", "SCREENS", "HEX", {"Cells": 5.0, "Closed": 0.45, "Bar": 0.12}),
    ("MOROCCAN", "Moroccan Screen", "SCREENS", "MOROCCAN", {}),
    ("MOROCCAN_STARS", "Star Lattice", "SCREENS", "MOROCCAN",
     {"Cells": 6.0, "Star": 0.27, "Bar": 0.09, "Rosette": 0.0}),
    ("BIRDCAGE", "Birdcage", "SCREENS", "GATE", {"Leaves": 0.85}),
    ("IRON_GATE", "Iron Gate", "SCREENS", "GATE", {"Bars": 12.0}),
    ("PIPES", "Industrial Pipes", "SCREENS", "PIPES", {}),
    ("BARBED_WIRE", "Barbed Wire", "SCREENS", "BARBED", {}),
    # -- plants ------------------------------------------------------------------------
    ("LEAVES", "Leaves", "PLANTS", "FOLIAGE", {}),
    ("LEAVES_DENSE", "Dense Leaves", "PLANTS", "FOLIAGE",
     {"Density": 9.0, "Coverage": 1.0, "Depth": 0.8}),
    ("IVY", "Ivy", "PLANTS", "FOLIAGE",
     {"Leaf Width": 0.75, "Leaf Size": 0.7, "Stems": 1.0, "Density": 8.0}),
    ("LEAF_FRAME", "Leafy Frame", "PLANTS", "FOLIAGE", {"Frame": 1.0, "Coverage": 1.0}),
    ("PETALS", "Petals", "PLANTS", "FOLIAGE",
     {"Density": 3.5, "Leaf Size": 1.2, "Leaf Width": 0.55, "Stems": 0.0, "Depth": 0.0,
      "Coverage": 0.9}),
    ("FERN", "Ferns", "PLANTS", "FERN", {}),
    ("FERN_DENSE", "Fern Thicket", "PLANTS", "FERN", {"Count": 11.0, "Length": 0.85}),
    ("PALM", "Palm", "PLANTS", "PALM", {}),
    ("SPIDER_PLANT", "Spider Plant", "PLANTS", "BLADES", {}),
    ("GRASS", "Tall Grass", "PLANTS", "BLADES",
     {"Layout": 1.0, "Origin Y": -0.75, "Count": 14.0, "Blade Width": 0.02, "Length": 0.85,
      "Spread": 100.0, "Bend": 0.8}),
    ("BAMBOO", "Bamboo", "PLANTS", "BAMBOO", {}),
    ("BAMBOO_LEAVES", "Bamboo Leaves", "PLANTS", "BAMBOO",
     {"Leaves": 1.0, "Stalks": 3.0, "Leaf Density": 5.0}),
    ("BRANCHES", "Branches", "PLANTS", "BRANCHES", {}),
    ("BARE_TREE", "Bare Tree", "PLANTS", "BRANCHES",
     {"Layout": 1.0, "Count": 4.0, "Twigs": 14.0, "Thickness": 0.03, "Length": 1.3,
      "Network": 0.2}),
    ("TWIG_NET", "Twig Tangle", "PLANTS", "BRANCHES",
     {"Count": 2.0, "Network": 1.0, "Scale": 3.0, "Twig Width": 0.006}),
    ("CANOPY", "Forest Canopy", "PLANTS", "BRANCHES",
     {"Leaves": 1.0, "Frame": 0.6, "Thickness": 0.025}),
    ("PINE", "Pine", "PLANTS", "PINE", {}),
    ("VINES", "Hanging Vines", "PLANTS", "VINES", {}),
    ("JUNGLE", "Jungle Vines", "PLANTS", "VINES",
     {"Frame": 1.0, "Strands": 16.0, "Length": 0.9, "Leaf Size": 0.04}),
    ("CACTI", "Cacti", "PLANTS", "CACTI", {}),
    ("CACTI_TALL", "Saguaros", "PLANTS", "CACTI", {"Height": 0.8, "Count": 3.5, "Width": 0.045}),
    # -- other ---------------------------------------------------------------------------
    ("COBWEB", "Cobweb", "OTHER", "COBWEB", {}),
    ("COBWEB_SPARSE", "Thin Cobweb", "OTHER", "COBWEB",
     {"Detail": 0.25, "Clumps": 0.2, "Haze": 0.0, "Strands": 0.002}),
    ("COBWEB_GLOW", "Glowing Web", "OTHER", "COBWEB", {"Finish.Invert": 1.0, "Strands": 0.004}),
    ("SPIDER_WEB", "Spider Web", "OTHER", "ORBWEB", {}),
    ("SPIDER_WEB_CORNER", "Corner Web", "OTHER", "ORBWEB",
     {"Center X": 0.35, "Center Y": 0.35, "Broken": 0.25}),
    ("SHEER", "Sheer Curtain", "OTHER", "CURTAIN", {}),
    ("SWAG", "Draped Curtain", "OTHER", "CURTAIN", {"Swag": 1.0, "Folds": 4.0}),
    ("LACE", "Lace Curtain", "OTHER", "CURTAIN", {"Lace": 0.9, "Opacity": 0.35, "Lace Scale": 3.0}),
    ("CAUSTICS", "Water Caustics", "OTHER", "CAUSTICS", {}),
    ("POOL", "Pool Light", "OTHER", "CAUSTICS",
     {"Scale": 7.0, "Sharpness": 0.03, "Darkness": 0.4, "Finish.Tint": (0.75, 0.92, 1.0)}),
    ("BREAKUP", "Breakup", "OTHER", "BREAKUP", {}),
    ("DAPPLE", "Soft Dapple", "OTHER", "BREAKUP",
     {"Scale": 6.0, "Coverage": 0.45, "Softness": 0.15}),
]

CATEGORIES = [
    ("ALL", "All", "Every preset"),
    ("WINDOWS", "Windows", "Window frames, blinds, stained and broken glass"),
    ("SCREENS", "Screens", "Lattices, grilles, metalwork"),
    ("PLANTS", "Plants", "Leaves, ferns, palms, trees and vines"),
    ("OTHER", "Other", "Webs, curtains, water and breakup"),
]

PRESET_BY_ID = {p[0]: p for p in PRESETS}


def converted(pid, values):
    """Degrees -> radians for ANGLE inputs."""
    angle_names = {spec[0] for spec in patterns.PATTERN_BY_ID[pid].inputs
                   if len(spec) > 5 and spec[5] == "ANGLE"}
    angle_names |= {"Transform.Rotation", "Rotation"} - {spec[0] for spec in
                                                        patterns.PATTERN_BY_ID[pid].inputs}
    out = {}
    for k, v in values.items():
        out[k] = math.radians(v) if k in angle_names else v
    return out
