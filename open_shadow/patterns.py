# SPDX-License-Identifier: GPL-3.0-or-later
"""Procedural shadow patterns.

Every pattern is a shader node group with a "Vector" input (pattern space:
the shadow plane spans -0.5..0.5 in X and Y) and a "Light" colour output:
how much light passes at that point (1 = open, 0 = blocked). Coloured
values tint the light, as stained glass does (Cycles only).
"""

import math
from collections import namedtuple

import bpy

from . import nodekit

GROUP_VERSION = 1
PREFIX = "OS "
AA = 0.0015  # anti-aliasing width, in plane units
TAU = 2 * math.pi

Pattern = namedtuple("Pattern", "id label icon description inputs build")


class PB(nodekit.NB):
    """Node builder with 2D helpers. Points are passed as (x, y) sockets."""

    def fract(self, a):
        return self.math("FRACT", a)

    def floor(self, a):
        return self.math("FLOOR", a)

    def sin(self, a):
        return self.math("SINE", a)

    def atan2(self, y, x):
        return self.math("ARCTAN2", y, x)

    def mod(self, a, b):
        return self.math("FLOORED_MODULO", a, b)

    def gt(self, a, b):
        return self.math("GREATER_THAN", a, b)

    def lt(self, a, b):
        return self.math("LESS_THAN", a, b)

    def sq(self, a):
        return self.mul(a, a)

    def neg(self, a):
        return self.mul(a, -1.0)

    def len2(self, x, y):
        return self.length(self.comb(x, y))

    def rot(self, x, y, angle):
        """Rotate (x, y) counter-clockwise by angle (float or socket)."""
        if isinstance(angle, (int, float)):
            c, s = math.cos(angle), math.sin(angle)
        else:
            c, s = self.cos(angle), self.sin(angle)
        return (self.sub(self.mul(x, c), self.mul(y, s)),
                self.add(self.mul(x, s), self.mul(y, c)))

    def fill(self, d, aa=AA):
        """1 where the signed distance d < 0, with a soft edge of width aa."""
        neg = -aa if isinstance(aa, (int, float)) else self.neg(aa)
        return self.smooth(d, aa, neg)

    def band(self, d, width, aa=AA):
        """1 within width/2 of the line d = 0."""
        return self.fill(self.sub(self.abs(d), self.mul(width, 0.5)), aa)

    def union(self, *masks):
        out = masks[0]
        for m in masks[1:]:
            out = self.max(out, m)
        return out

    def cut(self, a, b):
        """a minus b."""
        return self.mul(a, self.one_minus(b))

    def hash(self, a, b=0.0, c=0.0):
        """Random numbers for an id: returns (value, r, g, b) sockets in 0..1."""
        n = self.node("ShaderNodeTexWhiteNoise", noise_dimensions="3D")
        self.set(n, "Vector", self.comb(a, b, c))
        r, g, bl = self.sep(n.outputs["Color"])
        return n.outputs["Value"], r, g, bl

    def vor(self, x, y, feature="F1", rand=1.0, ox=0.0, oy=0.0):
        """2D Voronoi at scale 1 on (x + ox, y + oy). Returns the node."""
        v = self.comb(self.add(x, ox), self.add(y, oy))
        return self.voronoi(v, 1.0, feature, rand, "2D")

    def noise2(self, x, y, scale=1.0, detail=2.0, rough=0.5, w=0.0):
        # the seed moves along Z, so different seeds give different 2D slices
        n = self.noise(self.comb(x, y, w), scale, detail, rough, 0.0, "3D")
        return n.outputs["Fac"]

    def vesica(self, lx, ly, a, b):
        """Pointed leaf along X from -a to a, half width b. Signed distance."""
        r = self.div(self.add(self.sq(a), self.sq(b)), self.mul(b, 2.0))
        off = self.sub(r, b)
        d1 = self.sub(self.len2(lx, self.sub(ly, off)), r)
        d2 = self.sub(self.len2(lx, self.add(ly, off)), r)
        return self.max(d1, d2)

    def capsule_v(self, x, y, y0, y1, r):
        """Vertical capsule from (0, y0) to (0, y1), radius r."""
        cy = self.min(self.max(y, y0), y1)
        return self.sub(self.len2(x, self.sub(y, cy)), r)

    def capsule_h(self, x, y, x0, x1, r):
        cx = self.min(self.max(x, x0), x1)
        return self.sub(self.len2(self.sub(x, cx), y), r)

    def hsv(self, h, s, v):
        n = self.node("ShaderNodeCombineColor", mode="HSV")
        for i, val in enumerate((h, s, v)):
            self.set(n, i, val)
        return n.outputs[0]

    def rgb(self, value):
        """Grey colour from a float socket."""
        return self.comb(value, value, value)

    def radius(self, x, y):
        """Distance from the centre: 0 at the centre, 1 at the plane edge."""
        return self.mul(self.len2(x, y), 2.0)

    def frame_mask(self, x, y, amount):
        """Probability multiplier that keeps things away from the centre."""
        edge = self.smooth(self.radius(x, y), 0.25, 0.95)
        return self.lerp(1.0, edge, amount)


# -- shared building blocks ------------------------------------------------------


def leaf_layer(pb, x, y, density, size, width, keep, seed, offset=0.0,
               angle=None, spread=1.0, base=0.45):
    """Scattered pointed leaves, one per Voronoi cell (F1 and F2, so leaves
    reaching into the next cell are not cut off). Returns a 0..1 mask.

    size: leaf length in cell units; width: width / length;
    keep: probability (socket or float) that a cell carries a leaf;
    angle: leaf direction in radians (None = random), spread: random range
    around it, as a fraction of a full turn.
    """
    px = pb.add(pb.mul(x, density), pb.mul(seed, 7.31))
    py = pb.add(pb.mul(y, density), offset)
    masks = []
    for feature in ("F1", "F2"):
        v = pb.vor(px, py, feature)
        cx, cy, _ = pb.sep(v.outputs["Position"])
        h1, h2, h3 = pb.sep(v.outputs["Color"])
        lx, ly = pb.sub(px, cx), pb.sub(py, cy)
        turn = pb.mul(pb.sub(h1, 0.5), TAU * spread)
        if angle is not None:
            turn = pb.add(turn, angle)
        lx, ly = pb.rot(lx, ly, pb.neg(turn))
        a = pb.mul(size, pb.madd(h2, 0.6, 0.7))
        a = pb.mul(a, 0.5)
        d = pb.vesica(pb.sub(lx, pb.mul(a, base)), ly, a, pb.mul(a, width))
        aa = pb.mul(density, AA)
        masks.append(pb.mul(pb.fill(d, aa), pb.lt(h3, keep)))
    return pb.union(*masks)


def frond(pb, x, y, ox, oy, angle, length, bend, I, kind, seed=0.0):
    """One frond / blade / branch growing from (ox, oy) in direction angle.

    kind: "FERN" (lobed pinnae), "PALM" (long thin leaflets), "BLADE"
    (one long tapering leaf) or "BRANCH" (a limb with scattered twigs).
    Returns a 0..1 mask.
    """
    dx, dy = pb.sub(x, ox), pb.sub(y, oy)
    u, v = pb.rot(dx, dy, pb.neg(angle))
    v = pb.sub(v, pb.mul(bend, pb.sq(u)))
    t = pb.div(u, length)
    inside = pb.mul(pb.gt(t, 0.0), pb.lt(t, 1.0))
    b = pb.abs(v)
    if kind == "BLADE":
        # widest a third of the way along, pointed tip
        prof = pb.mul(pb.sqrt(pb.clamp01(pb.mul(t, 3.0))), pb.pow(pb.clamp01(pb.one_minus(t)), 0.8))
        w = pb.mul(I["Blade Width"], prof)
        return pb.mul(pb.fill(pb.sub(b, w)), inside)
    if kind == "BRANCH":
        stem = pb.fill(pb.sub(b, pb.mul(I["Thickness"], pb.madd(t, -0.85, 1.0))))
    else:
        stem = pb.fill(pb.sub(b, pb.mul(I["Stem"], pb.madd(t, -0.7, 1.0))))
    taper = pb.sqrt(pb.clamp01(pb.mul(pb.mul(t, pb.one_minus(t)), 4.0)))
    if kind == "FERN":
        taper = pb.mul(taper, pb.madd(t, -0.5, 1.0))
    plen = pb.mul(pb.mul(I["Leaflet Length"], length), taper)
    # slanted repetition along the stem: one leaflet per cell on each side
    u2 = pb.sub(u, pb.mul(b, I["Slant"]))
    step = pb.div(length, I["Leaflets"])
    a = pb.mul(pb.sub(pb.fract(pb.div(u2, step)), 0.5), step)
    rel = pb.clamp01(pb.div(b, pb.max(plen, 1e-4)))
    if kind == "BRANCH":
        # twigs: thin, curling, and only on some of the slots
        cell = pb.floor(pb.div(u2, step))
        keep, _, _, _ = pb.hash(cell, pb.gt(v, 0.0), seed)
        w = pb.mul(I["Twig Width"], pb.madd(rel, -0.7, 1.0))
        a = pb.sub(a, pb.mul(pb.sq(b), I["Curl"]))
        twig = pb.mul(pb.fill(pb.sub(pb.abs(a), w)), pb.lt(b, plen))
        return pb.mul(pb.union(stem, pb.mul(twig, pb.lt(keep, 0.55))), inside)
    if kind == "NEEDLE":
        w = I["Needle Width"]
        leaflet = pb.mul(pb.fill(pb.sub(pb.abs(a), w)), pb.lt(b, plen))
        return pb.mul(pb.union(stem, leaflet), inside)
    hw = pb.mul(pb.mul(step, 0.5), I["Leaflet Width"])
    if kind == "FERN":
        # narrow at the stem and the tip, with small rounded lobes
        lobes = pb.abs(pb.sin(pb.mul(rel, pb.mul(I["Lobes"], math.pi))))
        hw = pb.mul(hw, pb.madd(lobes, 0.3, 0.7))
        w = pb.mul(hw, pb.mul(pb.sqrt(pb.mul(rel, pb.one_minus(rel))), 2.0))
        w = pb.max(w, pb.mul(hw, 0.25))
    else:
        w = pb.mul(hw, pb.pow(pb.one_minus(rel), 0.7))
    leaflet = pb.mul(pb.fill(pb.sub(pb.abs(a), w)), pb.lt(b, plen))
    return pb.mul(pb.union(stem, leaflet), inside)


def fronds(pb, x, y, I, kind, count_max):
    """Several fronds, either around the edges pointing in (Layout 0) or
    fanning out from one point (Layout 1)."""
    masks = []
    n = I["Count"]
    for k in range(count_max):
        h0, h1, h2, h3 = pb.hash(k, I["Seed"], 3.7)
        # around the edges
        phi = pb.add(pb.mul(pb.div(k, n), TAU), pb.mul(pb.sub(h1, 0.5), 1.2))
        rr = pb.madd(h2, 0.2, 0.55)
        ex, ey = pb.mul(pb.cos(phi), rr), pb.mul(pb.sin(phi), rr)
        e_ang = pb.add(phi, pb.madd(h3, 0.9, math.pi - 0.45))
        # from one point
        frac = pb.div(pb.add(k, 0.5), n)
        f_ang = pb.add(pb.add(I["Direction"], pb.mul(pb.sub(frac, 0.5), I["Spread"])),
                       pb.mul(pb.sub(h1, 0.5), 0.25))
        lay = I["Layout"]
        ox = pb.lerp(ex, I["Origin X"], lay)
        oy = pb.lerp(ey, I["Origin Y"], lay)
        ang = pb.lerp(e_ang, f_ang, lay)
        length = pb.mul(I["Length"], pb.madd(h2, 0.5, 0.75))
        bend = pb.mul(I["Bend"], pb.sub(pb.mul(h3, 2.0), 1.0))
        bend = pb.lerp(bend, pb.mul(I["Bend"], pb.sub(pb.mul(frac, 2.0), 1.0)), lay)
        m = frond(pb, x, y, ox, oy, ang, length, bend, I, kind, pb.add(h0, k))
        masks.append(pb.mul(m, pb.lt(k, n)))
    return pb.union(*masks)


def window_box(pb, x, y, I):
    """Open area of a rectangular window with an outer frame."""
    hw = pb.sub(pb.mul(I["Width"], 0.5), I["Frame"])
    hh = pb.sub(pb.mul(I["Height"], 0.5), I["Frame"])
    d = pb.max(pb.sub(pb.abs(x), hw), pb.sub(pb.abs(y), hh))
    return pb.fill(d), hw, hh


def overlay(pb, light, pid, x, y, amount, scale, seed=0.0):
    """Multiply light by another pattern (e.g. plants outside the window)."""
    g = nodekit.group_node(pb, ensure(pid))
    pb.set(g, "Vector", pb.comb(pb.mul(x, scale), pb.mul(y, scale)))
    if "Seed" in g.inputs:
        pb.set(g, "Seed", seed)
    o = pb.luminance(g.outputs["Light"])
    return pb.mul(light, pb.lerp(1.0, o, amount))


# -- architecture ------------------------------------------------------------------


def build_grid(pb, x, y, I):
    x, y = pb.rot(x, y, pb.neg(I["Angle"]))
    gy = pb.mul(y, pb.mul(I["Cells"], I["Aspect"]))
    gx = pb.add(pb.mul(x, I["Cells"]), pb.mul(pb.floor(gy), pb.mul(I["Stagger"], 0.5)))
    fx, fy = pb.sub(pb.fract(gx), 0.5), pb.sub(pb.fract(gy), 0.5)
    h = pb.mul(I["Hole Size"], 0.5)
    r = pb.mul(I["Roundness"], h)
    qx, qy = pb.sub(pb.abs(fx), pb.sub(h, r)), pb.sub(pb.abs(fy), pb.sub(h, r))
    outside = pb.len2(pb.max(qx, 0.0), pb.max(qy, 0.0))
    d = pb.sub(pb.add(outside, pb.min(pb.max(qx, qy), 0.0)), r)
    return pb.fill(d, pb.mul(I["Cells"], AA * 1.5))


def build_window(pb, x, y, I):
    opening, hw, hh = window_box(pb, x, y, I)
    cw = pb.div(pb.mul(hw, 2.0), I["Columns"])
    ch = pb.div(pb.mul(hh, 2.0), I["Rows"])
    fu = pb.fract(pb.div(pb.add(x, hw), cw))
    fv = pb.fract(pb.div(pb.add(y, hh), ch))
    du = pb.mul(pb.min(fu, pb.one_minus(fu)), cw)
    dv = pb.mul(pb.min(fv, pb.one_minus(fv)), ch)
    bars = pb.fill(pb.sub(pb.min(du, dv), pb.mul(I["Bars"], 0.5)))
    hyp = pb.len2(cw, ch)
    k = pb.div(pb.mul(cw, ch), hyp)
    d1 = pb.mul(pb.abs(pb.sub(fu, fv)), k)
    d2 = pb.mul(pb.abs(pb.sub(pb.add(fu, fv), 1.0)), k)
    diag = pb.mul(pb.fill(pb.sub(pb.min(d1, d2), pb.mul(I["Bars"], 0.4))), I["Diagonals"])
    light = pb.cut(pb.cut(opening, bars), diag)
    return overlay(pb, light, "FOLIAGE", x, y, I["Leaves"], 1.0, I["Seed"])


def build_blinds(pb, x, y, I):
    opening, _, hh = window_box(pb, x, y, I)
    sy = pb.div(pb.add(y, hh), pb.mul(hh, 2.0))
    s = pb.fract(pb.mul(sy, I["Slats"]))
    soft = pb.mul(I["Softness"], 0.5)
    slat = pb.smooth(s, pb.add(I["Openness"], soft), pb.sub(I["Openness"], soft))
    mull = pb.fill(pb.sub(pb.abs(x), pb.mul(I["Mullion"], 0.5)))
    light = pb.cut(pb.mul(opening, slat), mull)
    return overlay(pb, light, "PALM", x, y, I["Plants"], 1.0, I["Seed"])


def build_hex(pb, x, y, I):
    px, py = pb.mul(x, I["Cells"]), pb.mul(y, I["Cells"])
    sx, sy = 1.0, math.sqrt(3.0)
    ax = pb.sub(pb.mod(px, sx), sx / 2)
    ay = pb.sub(pb.mod(py, sy), sy / 2)
    bx = pb.sub(pb.mod(pb.sub(px, sx / 2), sx), sx / 2)
    by = pb.sub(pb.mod(pb.sub(py, sy / 2), sy), sy / 2)
    use_a = pb.lt(pb.add(pb.sq(ax), pb.sq(ay)), pb.add(pb.sq(bx), pb.sq(by)))
    gx, gy = pb.lerp(bx, ax, use_a), pb.lerp(by, ay, use_a)
    h = pb.max(pb.abs(gx), pb.add(pb.mul(pb.abs(gx), 0.5), pb.mul(pb.abs(gy), sy / 2)))
    hole = pb.fill(pb.sub(h, pb.mul(pb.one_minus(I["Bar"]), 0.5)), pb.mul(I["Cells"], AA * 1.5))
    rnd, _, _, _ = pb.hash(pb.floor(pb.mul(pb.sub(px, gx), 2.0)),
                           pb.floor(pb.mul(pb.sub(py, gy), 2.0)), I["Seed"])
    return pb.mul(hole, pb.gt(rnd, I["Closed"]))


def build_moroccan(pb, x, y, I):
    """Eight-pointed stars (a square and a diamond) joined tip to tip."""
    px, py = pb.mul(x, I["Cells"]), pb.mul(y, I["Cells"])
    qx, qy = pb.sub(pb.fract(px), 0.5), pb.sub(pb.fract(py), 0.5)
    ax, ay = pb.abs(qx), pb.abs(qy)
    s = I["Star"]
    d1 = pb.sub(pb.max(ax, ay), s)                                  # square
    d2 = pb.sub(pb.mul(pb.add(ax, ay), 1 / math.sqrt(2)), s)         # diamond
    star = pb.min(d1, d2)
    w = I["Bar"]
    aa = pb.mul(I["Cells"], AA * 1.5)
    tip = pb.mul(s, math.sqrt(2))
    # straps from the star tips to the neighbouring stars
    axis = pb.mul(pb.band(pb.min(ax, ay), w, aa), pb.gt(pb.max(ax, ay), tip))
    diag = pb.mul(pb.band(pb.mul(pb.sub(ax, ay), 1 / math.sqrt(2)), w, aa),
                  pb.gt(pb.add(ax, ay), pb.mul(tip, math.sqrt(2))))
    lines = pb.union(pb.band(star, w, aa), axis, diag)
    # inner star and rosette
    inner = pb.mul(pb.band(pb.add(star, pb.mul(s, 0.45)), w, aa), I["Rosette"])
    return pb.one_minus(pb.union(lines, inner))


def glass_color(pb, cell_a, cell_b, I):
    h, _, s, _ = pb.hash(cell_a, cell_b, pb.add(I["Seed"], 1.3))
    sat = pb.mul(I["Colour"], pb.madd(s, 0.4, 0.6))
    return pb.hsv(h, sat, 1.0)


def build_rose(pb, x, y, I):
    r = pb.radius(x, y)
    a = pb.atan2(y, x)
    n = I["Segments"]
    seg = pb.div(TAU, n)
    idx = pb.floor(pb.div(a, seg))
    al = pb.sub(pb.mod(a, seg), pb.mul(seg, 0.5))
    qx, qy = pb.mul(r, pb.cos(al)), pb.mul(r, pb.abs(pb.sin(al)))
    w = pb.mul(I["Bar"], 2.0)
    aa = AA * 2
    outer = 0.94
    hub = I["Hub"]
    stone = pb.union(
        pb.gt(r, outer),
        pb.band(pb.sub(r, outer - 0.04), w, aa),
        pb.fill(pb.sub(r, hub), aa),
    )
    # spokes on the sector edges
    edge = pb.mul(r, pb.sin(pb.sub(pb.mul(seg, 0.5), pb.abs(al))))
    stone = pb.union(stone, pb.mul(pb.band(edge, w, aa), pb.gt(r, hub)))
    # tracery: a ring, a large circle per sector and a small foil outside it
    mid = pb.add(hub, pb.mul(pb.sub(outer, hub), 0.42))
    stone = pb.union(stone, pb.band(pb.sub(r, mid), w, aa))
    c1 = pb.add(mid, pb.mul(pb.sub(outer, mid), 0.48))
    r1 = pb.mul(pb.min(pb.mul(c1, pb.sin(pb.mul(seg, 0.5))), pb.mul(pb.sub(outer, mid), 0.5)),
                I["Petal"])
    d1 = pb.sub(pb.len2(pb.sub(qx, c1), qy), r1)
    stone = pb.union(stone, pb.band(d1, w, aa))
    c2 = pb.add(hub, pb.mul(pb.sub(mid, hub), 0.5))
    r2 = pb.mul(pb.min(pb.mul(c2, pb.sin(pb.mul(seg, 0.5))), pb.mul(pb.sub(mid, hub), 0.5)),
                I["Petal"])
    d2 = pb.sub(pb.len2(pb.sub(qx, c2), qy), r2)
    stone = pb.union(stone, pb.band(d2, w, aa))
    eye = pb.fill(pb.sub(r, pb.mul(hub, 0.45)), aa)
    stone = pb.cut(stone, eye)
    # lead lines between the pieces of glass
    lv = pb.vor(pb.mul(x, I["Leading Scale"]), pb.mul(y, I["Leading Scale"]), "DISTANCE_TO_EDGE")
    lead = pb.mul(pb.fill(pb.sub(lv.outputs["Distance"], 0.03), 0.02), I["Leading"])
    ring_id = pb.add(pb.gt(r, mid), pb.mul(pb.lt(d1, 0.0), 2.0))
    ring_id = pb.add(ring_id, pb.mul(pb.lt(d2, 0.0), 4.0))
    col = glass_color(pb, pb.add(pb.mod(idx, 2.0), pb.mul(ring_id, 3.0)), 0.0, I)
    light = pb.cut(pb.one_minus(stone), lead)
    return pb.vmul(pb.rgb(light), col)


def arch_sdf(pb, x, y, half_w, spring, bottom, k=1.0):
    """Pointed (gothic) arch opening. k = radius / width."""
    rr = pb.mul(pb.mul(half_w, 2.0), k)
    cx = pb.sub(rr, half_w)
    d_l = pb.sub(pb.len2(pb.add(x, cx), pb.sub(y, spring)), rr)
    d_r = pb.sub(pb.len2(pb.sub(x, cx), pb.sub(y, spring)), rr)
    top = pb.max(d_l, d_r)
    side = pb.sub(pb.abs(x), half_w)
    d = pb.lerp(side, pb.max(top, side), pb.gt(y, spring))
    return pb.max(d, pb.sub(bottom, y))


def build_gothic(pb, x, y, I):
    W = 0.42
    bottom = -0.47
    spring = -0.02
    outer = arch_sdf(pb, x, y, W, spring, bottom)
    n = I["Lancets"]
    mull = I["Mullion"]
    cell = pb.div(pb.mul(W, 2.0), n)
    lx = pb.sub(pb.mod(pb.add(x, W), cell), pb.mul(cell, 0.5))
    lid = pb.floor(pb.div(pb.add(x, W), cell))
    lw = pb.sub(pb.mul(cell, 0.5), pb.mul(mull, 0.5))
    lspring = pb.sub(spring, pb.mul(cell, 0.1))
    lancet = arch_sdf(pb, lx, y, lw, lspring, pb.add(bottom, mull))
    lancet = pb.max(lancet, pb.sub(pb.abs(x), pb.sub(W, mull)))
    # roundel in the head of the arch
    top_y = pb.add(spring, pb.mul(W, 1.732 * 0.98))
    lancet_top = pb.add(lspring, pb.mul(lw, 1.73))
    ry = pb.mul(pb.add(top_y, lancet_top), 0.5)
    rrad = pb.mul(pb.sub(top_y, lancet_top), I["Roundel"])
    rd = pb.sub(pb.len2(x, pb.sub(y, ry)), rrad)
    # quatrefoil inside the roundel
    ra = pb.atan2(pb.sub(y, ry), x)
    foil = pb.sub(pb.len2(x, pb.sub(y, ry)),
                  pb.mul(rrad, pb.madd(pb.abs(pb.cos(pb.mul(ra, 2.0))), 0.25, 0.55)))
    glass_d = pb.min(lancet, pb.max(rd, pb.neg(foil)))
    glass_d = pb.min(glass_d, pb.add(foil, mull))
    glass_d = pb.max(glass_d, pb.add(outer, mull))
    glass = pb.fill(glass_d)
    # diamond quarries
    q = I["Quarries"]
    u, v = pb.rot(pb.mul(x, q), pb.mul(y, pb.mul(q, 0.7)), math.radians(45))
    fu, fv = pb.fract(u), pb.fract(v)
    dq = pb.min(pb.min(fu, pb.one_minus(fu)), pb.min(fv, pb.one_minus(fv)))
    lead = pb.mul(pb.fill(pb.sub(pb.div(dq, q), 0.0018)), I["Leading"])
    col = glass_color(pb, lid, pb.floor(pb.mul(y, 6.0)), I)
    light = pb.cut(glass, lead)
    return pb.vmul(pb.rgb(light), col)


def build_gate(pb, x, y, I):
    n = I["Bars"]
    fx = pb.sub(pb.fract(pb.add(pb.mul(x, n), 0.5)), 0.5)
    bw = I["Bar Width"]
    bars = pb.fill(pb.sub(pb.abs(pb.div(fx, n)), pb.mul(bw, 0.5)))
    rail_y = 0.3
    rails = pb.union(pb.band(pb.sub(pb.abs(y), rail_y), bw),
                     pb.band(pb.sub(pb.abs(y), 0.47), pb.mul(bw, 2.0)))
    # C-scrolls between the bars, above and below each rail
    cx = pb.div(pb.sub(pb.fract(pb.mul(x, n)), 0.5), n)
    sr = pb.div(I["Scrolls"], pb.mul(n, 4.0))
    ly = pb.sub(pb.abs(y), rail_y)
    scroll_a = pb.band(pb.sub(pb.len2(cx, pb.sub(ly, sr)), sr), pb.mul(bw, 0.7))
    scroll_b = pb.band(pb.sub(pb.len2(cx, pb.add(ly, sr)), sr), pb.mul(bw, 0.7))
    scrolls = pb.mul(pb.union(scroll_a, scroll_b), pb.gt(I["Scrolls"], 0.01))
    iron = pb.union(bars, rails, scrolls)
    light = pb.one_minus(iron)
    return overlay(pb, light, "VINES", x, y, I["Leaves"], 1.0, I["Seed"])


def build_pipes(pb, x, y, I):
    masks = []
    n = I["Count"]
    for k in range(8):
        h0, h1, h2, h3 = pb.hash(k, I["Seed"], 9.1)
        vertical = pb.gt(h0, 0.5)
        ang = pb.add(pb.mul(vertical, math.pi / 2), pb.mul(pb.sub(h1, 0.5), I["Tilt"]))
        u, v = pb.rot(x, y, pb.neg(ang))
        off = pb.mul(pb.sub(h2, 0.5), 0.9)
        w = pb.mul(I["Thickness"], pb.madd(h3, 0.9, 0.55))
        fl = pb.fract(pb.add(pb.mul(u, I["Flanges"]), h1))
        flange = pb.mul(pb.lt(pb.abs(pb.sub(fl, 0.5)), 0.035), pb.gt(I["Flanges"], 0.01))
        width = pb.mul(w, pb.madd(flange, 0.35, 1.0))
        m = pb.band(pb.sub(v, off), pb.mul(width, 2.0))
        masks.append(pb.mul(m, pb.lt(k, n)))
    return pb.one_minus(pb.union(*masks))


# -- plants --------------------------------------------------------------------------


def build_foliage(pb, x, y, I):
    keep = pb.mul(I["Coverage"], pb.frame_mask(x, y, I["Frame"]))
    d = I["Density"]
    layers = [
        leaf_layer(pb, x, y, d, I["Leaf Size"], I["Leaf Width"], keep, I["Seed"]),
        leaf_layer(pb, x, y, pb.mul(d, 1.37), I["Leaf Size"], I["Leaf Width"], keep,
                   pb.add(I["Seed"], 11.0), 5.3),
        leaf_layer(pb, x, y, pb.mul(d, 0.71), I["Leaf Size"], I["Leaf Width"], keep,
                   pb.add(I["Seed"], 23.0), 9.1),
    ]
    # thin twisting stems
    sx = pb.add(x, pb.mul(pb.sub(pb.noise2(x, y, 3.0, 2.0, 0.5, I["Seed"]), 0.5), 0.15))
    sv = pb.vor(pb.mul(sx, pb.mul(d, 0.5)), pb.mul(y, pb.mul(d, 0.5)), "DISTANCE_TO_EDGE",
                1.0, pb.mul(I["Seed"], 3.1))
    stems = pb.mul(pb.fill(pb.sub(pb.div(sv.outputs["Distance"], pb.mul(d, 0.5)), 0.0025)),
                   I["Stems"])
    stems = pb.mul(stems, pb.frame_mask(x, y, I["Frame"]))
    near = pb.union(layers[0], layers[1], stems)
    depth = pb.mul(layers[2], pb.madd(I["Depth"], -0.6, 1.0))
    return pb.mul(pb.one_minus(near), pb.one_minus(depth))


def build_fern(pb, x, y, I):
    return pb.one_minus(fronds(pb, x, y, I, "FERN", 8))


def build_palm(pb, x, y, I):
    return pb.one_minus(fronds(pb, x, y, I, "PALM", 7))


def build_blades(pb, x, y, I):
    return pb.one_minus(fronds(pb, x, y, I, "BLADE", 14))


def bamboo_layer(pb, x, y, I, seed, scale):
    n = pb.mul(I["Stalks"], scale)
    X = pb.mul(x, n)
    cell = pb.floor(X)
    h0, h1, h2, h3 = pb.hash(cell, seed, 2.2)
    fx = pb.sub(pb.fract(X), 0.5)
    lean = pb.mul(pb.sub(h1, 0.5), pb.mul(I["Lean"], n))
    c = pb.add(pb.mul(pb.sub(h0, 0.5), 0.5), pb.mul(y, lean))
    dx = pb.div(pb.sub(fx, c), n)
    w = pb.div(pb.mul(I["Thickness"], pb.madd(h2, 0.6, 0.7)), scale)
    seg = pb.div(I["Segment"], scale)
    sv = pb.fract(pb.add(pb.div(y, seg), h3))
    knot = pb.lt(pb.min(sv, pb.one_minus(sv)), 0.03)
    stalk = pb.fill(pb.sub(pb.abs(dx), pb.mul(w, pb.madd(knot, 0.25, 1.0))))
    present = pb.lt(h1, 0.85)
    leaves = leaf_layer(pb, x, y, pb.mul(I["Leaf Density"], scale), 0.9, 0.16,
                        pb.mul(I["Leaves"], pb.frame_mask(x, y, 0.5)), seed, 1.7,
                        angle=-math.pi / 2, spread=0.35, base=0.95)
    return pb.union(pb.mul(stalk, present), leaves)


def build_bamboo(pb, x, y, I):
    front = bamboo_layer(pb, x, y, I, I["Seed"], 1.0)
    back = bamboo_layer(pb, x, y, I, pb.add(I["Seed"], 17.0), 1.6)
    back = pb.mul(back, pb.mul(I["Back Layer"], 0.55))
    return pb.mul(pb.one_minus(front), pb.one_minus(back))


def build_branches(pb, x, y, I):
    P = dict(I)
    P["Leaflets"], P["Leaflet Length"], P["Slant"] = I["Twigs"], I["Twig Length"], I["Twig Angle"]
    wood = fronds(pb, x, y, P, "BRANCH", 8)
    # a fine network of twigs between the limbs
    s = I["Scale"]
    warp = 0.3
    wx = pb.add(x, pb.mul(pb.sub(pb.noise2(x, y, 2.5, 3.0, 0.55, I["Seed"]), 0.5), warp))
    wy = pb.add(y, pb.mul(pb.sub(pb.noise2(x, y, 2.5, 3.0, 0.55, pb.add(I["Seed"], 5.0)), 0.5), warp))
    e = pb.vor(pb.mul(wx, s), pb.mul(wy, s), "DISTANCE_TO_EDGE", 1.0, pb.mul(I["Seed"], 1.7))
    vis = pb.smooth(pb.noise2(x, y, 3.0, 2.0, 0.5, pb.add(I["Seed"], 4.0)), 0.5, 0.56)
    net = pb.mul(pb.fill(pb.sub(pb.div(e.outputs["Distance"], s), pb.mul(I["Twig Width"], 1.5))),
                 pb.mul(vis, I["Network"]))
    wood = pb.union(wood, pb.mul(net, pb.frame_mask(x, y, I["Frame"])))
    # leaf clumps (forest canopy)
    fine = pb.noise2(x, y, 26.0, 6.0, 0.7, pb.add(I["Seed"], 3.0))
    clump = pb.noise2(x, y, 3.0, 3.0, 0.5, pb.add(I["Seed"], 6.0))
    leafy = pb.add(pb.mul(clump, 0.7), pb.mul(fine, 0.5))
    thr = pb.sub(1.2, pb.mul(I["Leaves"], 0.55))
    thr = pb.sub(thr, pb.mul(pb.smooth(pb.radius(x, y), 0.2, 1.0), pb.mul(I["Frame"], 0.2)))
    leaves = pb.mul(pb.smooth(leafy, pb.sub(thr, 0.02), pb.add(thr, 0.02)), pb.gt(I["Leaves"], 0.0))
    return pb.one_minus(pb.union(wood, leaves))


def build_pine(pb, x, y, I):
    return pb.one_minus(fronds(pb, x, y, I, "NEEDLE", 14))


def build_vines(pb, x, y, I):
    n = I["Strands"]
    X = pb.mul(x, n)
    cell = pb.floor(X)
    h0, h1, h2, h3 = pb.hash(cell, I["Seed"], 4.4)
    fx = pb.sub(pb.fract(X), 0.5)
    sway = pb.mul(pb.mul(I["Sway"], 0.25), pb.sin(pb.add(pb.mul(y, 7.0), pb.mul(h1, 6.28))))
    dx = pb.div(pb.sub(fx, pb.add(pb.mul(pb.sub(h0, 0.5), 0.3), sway)), n)
    end = pb.sub(0.5, pb.mul(I["Length"], pb.madd(h2, 0.7, 0.3)))
    end = pb.sub(end, pb.mul(pb.abs(pb.mul(x, 2.0)), pb.mul(I["Frame"], -0.4)))
    hanging = pb.mul(pb.gt(y, end), pb.lt(h3, pb.mul(I["Density"], pb.frame_mask(x, y, I["Frame"]))))
    stem = pb.fill(pb.sub(pb.abs(dx), 0.0025))
    # leaves alternate left and right along the strand
    rate = pb.div(I["Leaves"], 1.0)
    k = pb.add(pb.mul(y, rate), h1)
    side = pb.sub(pb.mul(pb.mod(pb.floor(k), 2.0), 2.0), 1.0)
    dy = pb.div(pb.sub(pb.fract(k), 0.5), rate)
    lh, _, _, _ = pb.hash(pb.floor(k), cell, I["Seed"])
    a = pb.mul(pb.mul(I["Leaf Size"], 0.5), pb.madd(lh, 0.6, 0.7))
    lx, ly = pb.rot(pb.mul(dx, side), dy, math.radians(35))
    leaf = pb.fill(pb.vesica(pb.sub(lx, pb.mul(a, 0.95)), ly, a, pb.mul(a, I["Leaf Width"])))
    vine = pb.mul(pb.union(stem, leaf), hanging)
    return pb.one_minus(vine)


def cactus_layer(pb, x, y, I, seed, scale):
    n = pb.mul(I["Count"], scale)
    X = pb.mul(x, n)
    cell = pb.floor(X)
    h0, h1, h2, h3 = pb.hash(cell, seed, 6.6)
    cx = pb.div(pb.sub(pb.fract(X), pb.madd(h0, 0.3, 0.35)), n)
    ground = -0.42
    top = pb.add(ground, pb.mul(pb.div(I["Height"], scale), pb.madd(h1, 0.6, 0.4)))
    w = pb.div(I["Width"], scale)
    body = pb.capsule_v(cx, y, -1.0, top, w)
    # arms: out sideways, then up
    side = pb.sub(pb.mul(pb.gt(h2, 0.5), 2.0), 1.0)
    ay = pb.add(ground, pb.mul(pb.sub(top, ground), pb.madd(h3, 0.3, 0.3)))
    reach = pb.mul(w, 2.4)
    sx = pb.mul(cx, side)
    arm_h = pb.capsule_h(sx, pb.sub(y, ay), 0.0, reach, pb.mul(w, 0.7))
    arm_v = pb.capsule_v(pb.sub(sx, reach), y, ay, pb.add(ay, pb.mul(pb.sub(top, ay), 0.75)),
                         pb.mul(w, 0.7))
    arm = pb.min(arm_h, arm_v)
    has_arm = pb.lt(h3, I["Arms"])
    d = pb.min(body, pb.lerp(10.0, arm, has_arm))
    # a second arm on the other side for some
    ay2 = pb.add(ay, pb.mul(pb.sub(top, ay), 0.25))
    arm_h2 = pb.capsule_h(pb.neg(sx), pb.sub(y, ay2), 0.0, reach, pb.mul(w, 0.6))
    arm_v2 = pb.capsule_v(pb.sub(pb.neg(sx), reach), y, ay2,
                          pb.add(ay2, pb.mul(pb.sub(top, ay2), 0.6)), pb.mul(w, 0.6))
    d = pb.min(d, pb.lerp(10.0, pb.min(arm_h2, arm_v2), pb.lt(h1, pb.mul(I["Arms"], 0.5))))
    spines = pb.mul(pb.sub(pb.noise2(x, y, 180.0, 1.0, 0.5, seed), 0.5), pb.mul(I["Spines"], 0.012))
    present = pb.lt(h0, 0.8)
    plant = pb.mul(pb.fill(pb.add(d, spines)), present)
    soil = pb.fill(pb.sub(y, pb.add(ground, pb.mul(pb.noise2(x, 0.0, 6.0, 2.0, 0.5, seed), 0.04))))
    return pb.union(plant, soil)


def build_cacti(pb, x, y, I):
    front = cactus_layer(pb, x, y, I, I["Seed"], 1.0)
    back = cactus_layer(pb, x, pb.add(y, 0.08), I, pb.add(I["Seed"], 31.0), 1.5)
    back = pb.mul(back, pb.mul(I["Back Layer"], 0.6))
    return pb.mul(pb.one_minus(front), pb.one_minus(back))


# -- other ---------------------------------------------------------------------------------


def build_cobweb(pb, x, y, I):
    seed = I["Seed"]
    warp = pb.mul(I["Warp"], 0.3)
    wx = pb.add(x, pb.mul(pb.sub(pb.noise2(x, y, 2.0, 3.0, 0.6, seed), 0.5), warp))
    wy = pb.add(y, pb.mul(pb.sub(pb.noise2(x, y, 2.0, 3.0, 0.6, pb.add(seed, 3.0)), 0.5), warp))
    clump = pb.smooth(pb.noise2(x, y, 3.0, 4.0, 0.6, pb.add(seed, 8.0)), 0.5, 0.75)
    clump = pb.mul(clump, I["Clumps"])
    strands = []
    for i, (mult, thick, amt) in enumerate(((1.0, 1.0, None), (2.3, 0.55, 1.0), (5.0, 0.35, 0.7))):
        s = pb.mul(I["Scale"], mult)
        e = pb.vor(pb.mul(wx, s), pb.mul(wy, s), "DISTANCE_TO_EDGE", 1.0, pb.add(pb.mul(seed, 1.9), i * 4.0))
        t = pb.mul(pb.mul(I["Strands"], thick), pb.madd(clump, 4.0, 1.0))
        m = pb.fill(pb.sub(pb.div(e.outputs["Distance"], s), t))
        if amt is not None:
            vis = pb.smooth(pb.noise2(x, y, 4.0, 2.0, 0.5, pb.add(seed, 10.0 + i)),
                            pb.sub(1.0, pb.mul(I["Detail"], amt)), pb.sub(1.05, pb.mul(I["Detail"], amt)))
            m = pb.mul(m, vis)
        strands.append(m)
    web = pb.union(*strands)
    web = pb.union(web, pb.mul(clump, pb.smooth(pb.noise2(x, y, 30.0, 4.0, 0.6, seed), 0.55, 0.45)))
    haze = pb.mul(pb.noise2(x, y, 2.0, 3.0, 0.5, pb.add(seed, 12.0)), I["Haze"])
    return pb.mul(pb.one_minus(web), pb.one_minus(pb.mul(haze, 0.6)))


def build_orbweb(pb, x, y, I):
    cx, cy = pb.sub(x, I["Center X"]), pb.sub(y, I["Center Y"])
    r = pb.radius(cx, cy)
    a = pb.atan2(cy, cx)
    n = I["Spokes"]
    seg = pb.div(TAU, n)
    idx = pb.floor(pb.div(a, seg))
    al = pb.sub(pb.mod(a, seg), pb.mul(seg, 0.5))
    w = pb.mul(I["Thickness"], 2.0)
    aa = AA * 2
    spoke_d = pb.mul(r, pb.abs(pb.sin(pb.sub(pb.mul(seg, 0.5), pb.abs(al)))))
    spokes = pb.band(spoke_d, w, aa)
    # sagging spiral: polygon rings, pulled toward the centre between spokes
    poly = pb.mul(r, pb.div(pb.cos(al), pb.cos(pb.mul(seg, 0.5))))
    sag = pb.mul(I["Sag"], pb.sub(1.0, pb.div(pb.cos(al), pb.cos(pb.mul(seg, 0.5)))))
    rs = pb.add(poly, pb.mul(sag, pb.mul(r, 4.0)))
    k = pb.add(pb.mul(rs, I["Rings"]), pb.div(a, TAU))
    f = pb.sub(pb.fract(k), 0.5)
    ring_d = pb.div(pb.abs(f), I["Rings"])
    rings = pb.band(ring_d, w, aa)
    rings = pb.mul(rings, pb.mul(pb.gt(r, pb.mul(I["Hub"], 1.0)), pb.lt(r, 0.95)))
    broke, _, _, _ = pb.hash(pb.floor(k), idx, I["Seed"])
    rings = pb.mul(rings, pb.gt(broke, I["Broken"]))
    hub = pb.mul(pb.fill(pb.sub(r, pb.mul(I["Hub"], 0.35)), aa), 0.8)
    web = pb.union(spokes, rings, hub)
    return pb.one_minus(web)


def build_glass(pb, x, y, I):
    seed = I["Seed"]
    jag = pb.mul(pb.sub(pb.noise2(x, y, 40.0, 3.0, 0.6, seed), 0.5), 0.012)
    dx = pb.add(pb.sub(x, I["Impact X"]), jag)
    dy = pb.add(pb.sub(y, I["Impact Y"]), jag)
    r = pb.len2(dx, dy)
    a = pb.atan2(dy, dx)
    px = pb.mul(pb.div(a, TAU), I["Shards"])
    py = pb.mul(pb.math("LOGARITHM", pb.add(r, 0.08), math.e), I["Rings"])
    v = pb.vor(px, py, "DISTANCE_TO_EDGE", 0.9, pb.mul(seed, 3.7))
    f1 = pb.vor(px, py, "F1", 0.9, pb.mul(seed, 3.7))
    scale = pb.add(pb.mul(r, TAU / 1.0), 0.02)
    dist = pb.mul(v.outputs["Distance"], pb.div(scale, I["Shards"]))
    cracks = pb.fill(pb.sub(dist, I["Crack"]))
    h1, h2, _ = pb.sep(f1.outputs["Color"])
    missing = pb.lt(h1, I["Missing"])
    tint = pb.lerp(1.0, 0.82, pb.lt(h2, 0.25))
    fine_v = pb.vor(pb.mul(dx, 14.0), pb.mul(dy, 14.0), "DISTANCE_TO_EDGE", 1.0, seed)
    fine = pb.fill(pb.sub(pb.div(fine_v.outputs["Distance"], 14.0), pb.mul(I["Crack"], 0.5)))
    fine = pb.mul(fine, pb.mul(pb.smooth(pb.noise2(x, y, 5.0, 2.0, 0.5, seed), 0.5, 0.6), I["Fine Cracks"]))
    light = pb.mul(pb.one_minus(pb.union(cracks, fine, missing)), tint)
    return light


def build_barbed(pb, x, y, I):
    masks = []
    n = I["Count"]
    w = I["Thickness"]
    for k in range(6):
        h0, h1, h2, h3 = pb.hash(k, I["Seed"], 5.5)
        u, v = pb.rot(x, y, pb.neg(pb.mul(h0, math.pi)))
        curve = pb.mul(pb.mul(I["Waviness"], 0.08),
                       pb.sin(pb.add(pb.mul(u, pb.madd(h1, 4.0, 3.0)), pb.mul(h2, 6.28))))
        dv = pb.sub(v, pb.add(pb.mul(pb.sub(h3, 0.5), 0.8), curve))
        twist = pb.mul(w, pb.sin(pb.mul(u, 60.0)))
        wire = pb.union(pb.band(pb.sub(dv, twist), w), pb.band(pb.add(dv, twist), w))
        sp = I["Barb Spacing"]
        la = pb.mul(pb.sub(pb.fract(pb.add(pb.div(u, sp), h1)), 0.5), sp)
        reach = pb.lt(pb.len2(la, dv), I["Barb Size"])
        barb = pb.union(pb.band(pb.sub(dv, la), pb.mul(w, 0.9)),
                        pb.band(pb.add(dv, pb.mul(la, 0.6)), pb.mul(w, 0.9)))
        barb = pb.mul(barb, reach)
        masks.append(pb.mul(pb.union(wire, barb), pb.lt(k, n)))
    return pb.one_minus(pb.union(*masks))


def build_curtain(pb, x, y, I):
    seed = I["Seed"]
    sway = pb.mul(pb.sub(pb.noise2(pb.mul(x, 0.3), y, 1.5, 2.0, 0.5, seed), 0.5), I["Sway"])
    xs = pb.add(x, sway)
    ph = pb.mul(pb.noise2(xs, 0.0, 2.0, 2.0, 0.5, pb.add(seed, 2.0)), 4.0)
    fold = pb.madd(pb.sin(pb.add(pb.mul(xs, pb.mul(I["Folds"], TAU)), ph)), 0.5, 0.5)
    fold = pb.pow(fold, pb.madd(I["Depth"], 3.0, 0.5))
    shade = pb.mul(I["Opacity"], pb.lerp(0.35, 1.0, fold))
    # draped swags at the top
    sy = pb.add(pb.sub(0.5, y), pb.mul(pb.sq(pb.sub(pb.fract(pb.mul(x, 2.0)), 0.5)), -1.6))
    drape = pb.union(pb.smooth(pb.abs(pb.sub(sy, 0.12)), 0.06, 0.02),
                     pb.mul(pb.smooth(pb.abs(pb.sub(sy, 0.3)), 0.07, 0.02), 0.6))
    drape = pb.mul(drape, pb.mul(I["Swag"], 0.6))
    # lace rosettes
    ls = I["Lace Scale"]
    qx = pb.sub(pb.fract(pb.mul(xs, ls)), 0.5)
    qy = pb.sub(pb.fract(pb.mul(y, ls)), 0.5)
    rr = pb.len2(qx, qy)
    la = pb.atan2(qy, qx)
    petal = pb.sub(rr, pb.mul(0.33, pb.madd(pb.abs(pb.cos(pb.mul(la, 4.0))), 0.4, 0.6)))
    lace = pb.union(pb.band(petal, 0.035, 0.01), pb.band(pb.sub(rr, 0.12), 0.03, 0.01),
                    pb.mul(pb.band(pb.sub(rr, 0.45), 0.02, 0.01), 0.8))
    lace = pb.mul(lace, I["Lace"])
    return pb.mul(pb.mul(pb.one_minus(shade), pb.one_minus(drape)), pb.one_minus(pb.mul(lace, 0.85)))


def build_caustics(pb, x, y, I):
    seed = I["Seed"]
    s = I["Scale"]
    d = pb.mul(I["Distortion"], 0.15)
    wx = pb.add(x, pb.mul(pb.sub(pb.noise2(x, y, 2.0, 2.0, 0.5, seed), 0.5), d))
    wy = pb.add(y, pb.mul(pb.sub(pb.noise2(x, y, 2.0, 2.0, 0.5, pb.add(seed, 4.0)), 0.5), d))
    lines = []
    for i, m in enumerate((1.0, 1.7)):
        v = pb.vor(pb.mul(wx, pb.mul(s, m)), pb.mul(wy, pb.mul(s, m)), "DISTANCE_TO_EDGE", 1.0,
                   pb.add(pb.mul(seed, 1.3), i * 9.0))
        lines.append(pb.exp(pb.div(pb.neg(v.outputs["Distance"]), pb.max(I["Sharpness"], 0.005))))
    c = pb.clamp01(pb.add(lines[0], pb.mul(lines[1], 0.6)))
    return pb.lerp(I["Darkness"], 1.0, c)


def build_breakup(pb, x, y, I):
    n = pb.noise(pb.comb(x, y, I["Seed"]), I["Scale"], I["Detail"], 0.6, I["Distortion"])
    v = n.outputs["Fac"]
    soft = pb.add(I["Softness"], 0.002)
    return pb.smooth(v, pb.sub(I["Coverage"], soft), pb.add(I["Coverage"], soft))


# -- registry ---------------------------------------------------------------------------------

SEED = ("Seed", "float", 0.0, 0.0, 1000.0)
FRAME = ("Frame", "float", 0.0, 0.0, 1.0)


def _frond_inputs(count, length, leaflets, leaflet_len, leaflet_w, slant, stem, bend,
                  lobes=0.0, blade_w=0.02, layout=0.0, ox=0.0, oy=-0.6, direction=90.0,
                  spread=120.0, needles=0.0):
    specs = [
        ("Count", "float", count, 1.0, 14.0),
        ("Length", "float", length, 0.05, 2.0),
        ("Bend", "float", bend, 0.0, 3.0),
        ("Layout", "float", layout, 0.0, 1.0),
        ("Origin X", "float", ox, -1.5, 1.5),
        ("Origin Y", "float", oy, -1.5, 1.5),
        ("Direction", "float", direction, -360.0, 360.0, "ANGLE"),
        ("Spread", "float", spread, 0.0, 360.0, "ANGLE"),
    ]
    if needles:
        specs += [
            ("Leaflets", "float", leaflets, 2.0, 120.0),
            ("Leaflet Length", "float", leaflet_len, 0.02, 1.0),
            ("Needle Width", "float", needles, 0.0003, 0.01),
            ("Slant", "float", slant, -2.0, 2.0),
            ("Stem", "float", stem, 0.0, 0.05),
        ]
    elif leaflets:
        specs += [
            ("Leaflets", "float", leaflets, 2.0, 120.0),
            ("Leaflet Length", "float", leaflet_len, 0.02, 1.0),
            ("Leaflet Width", "float", leaflet_w, 0.05, 1.0),
            ("Slant", "float", slant, -2.0, 2.0),
            ("Stem", "float", stem, 0.0, 0.05),
        ]
        if lobes:
            specs.append(("Lobes", "float", lobes, 0.0, 20.0))
    else:
        specs.append(("Blade Width", "float", blade_w, 0.002, 0.2))
    return specs + [SEED]


PATTERNS = [
    # architecture
    Pattern("WINDOW", "Window", "MESH_GRID", "Window panes and bars, with optional leaves outside", [
        ("Columns", "float", 2.0, 1.0, 12.0),
        ("Rows", "float", 3.0, 1.0, 12.0),
        ("Width", "float", 0.8, 0.05, 1.0),
        ("Height", "float", 0.92, 0.05, 1.0),
        ("Frame", "float", 0.04, 0.0, 0.3),
        ("Bars", "float", 0.025, 0.0, 0.2),
        ("Diagonals", "float", 0.0, 0.0, 1.0),
        ("Leaves", "float", 0.0, 0.0, 1.0),
        SEED,
    ], build_window),
    Pattern("BLINDS", "Blinds", "ALIGN_JUSTIFY", "Venetian blinds, with optional palm fronds", [
        ("Slats", "float", 16.0, 2.0, 80.0),
        ("Openness", "float", 0.55, 0.0, 1.0),
        ("Softness", "float", 0.08, 0.0, 0.5),
        ("Width", "float", 0.85, 0.05, 1.0),
        ("Height", "float", 0.95, 0.05, 1.0),
        ("Frame", "float", 0.03, 0.0, 0.3),
        ("Mullion", "float", 0.03, 0.0, 0.2),
        ("Plants", "float", 0.0, 0.0, 1.0),
        SEED,
    ], build_blinds),
    Pattern("GRID", "Grid / Lattice", "LIGHTPROBE_VOLUME", "Lattices, grates and grilles", [
        ("Cells", "float", 8.0, 1.0, 60.0),
        ("Hole Size", "float", 0.75, 0.0, 1.0),
        ("Roundness", "float", 0.0, 0.0, 1.0),
        ("Aspect", "float", 1.0, 0.1, 10.0),
        ("Stagger", "float", 0.0, 0.0, 1.0),
        ("Angle", "float", 0.0, -180.0, 180.0, "ANGLE"),
    ], build_grid),
    Pattern("HEX", "Honeycomb", "SEQ_CHROMA_SCOPE", "Hexagonal honeycomb grille", [
        ("Cells", "float", 7.0, 1.0, 60.0),
        ("Bar", "float", 0.18, 0.0, 1.0),
        ("Closed", "float", 0.0, 0.0, 1.0),
        SEED,
    ], build_hex),
    Pattern("MOROCCAN", "Moroccan", "SNAP_FACE_CENTER", "Eight-pointed star screen (mashrabiya)", [
        ("Cells", "float", 4.0, 1.0, 30.0),
        ("Star", "float", 0.3, 0.05, 0.5),
        ("Bar", "float", 0.07, 0.005, 0.3),
        ("Rosette", "float", 1.0, 0.0, 1.0),
    ], build_moroccan),
    Pattern("ROSE", "Rose Window", "MESH_CIRCLE", "Round church window with tracery and stained glass", [
        ("Segments", "float", 12.0, 3.0, 36.0),
        ("Hub", "float", 0.16, 0.0, 0.6),
        ("Petal", "float", 0.9, 0.2, 1.2),
        ("Bar", "float", 0.012, 0.002, 0.06),
        ("Leading", "float", 0.6, 0.0, 1.0),
        ("Leading Scale", "float", 22.0, 2.0, 80.0),
        ("Colour", "float", 0.0, 0.0, 1.0),
        SEED,
    ], build_rose),
    Pattern("GOTHIC", "Gothic Window", "MOD_BUILD", "Pointed-arch lancet windows", [
        ("Lancets", "float", 3.0, 1.0, 8.0),
        ("Mullion", "float", 0.02, 0.002, 0.1),
        ("Roundel", "float", 0.42, 0.0, 0.5),
        ("Quarries", "float", 18.0, 2.0, 80.0),
        ("Leading", "float", 1.0, 0.0, 1.0),
        ("Colour", "float", 0.0, 0.0, 1.0),
        SEED,
    ], build_gothic),
    Pattern("GATE", "Iron Gate", "OUTLINER_DATA_LIGHTPROBE", "Wrought-iron bars with scrolls, like a birdcage", [
        ("Bars", "float", 9.0, 2.0, 40.0),
        ("Bar Width", "float", 0.012, 0.002, 0.08),
        ("Scrolls", "float", 1.0, 0.0, 2.0),
        ("Leaves", "float", 0.0, 0.0, 1.0),
        SEED,
    ], build_gate),
    Pattern("PIPES", "Pipes", "MOD_SCREW", "Industrial pipes and beams", [
        ("Count", "float", 6.0, 1.0, 8.0),
        ("Thickness", "float", 0.05, 0.005, 0.25),
        ("Flanges", "float", 2.0, 0.0, 10.0),
        ("Tilt", "float", 0.3, 0.0, 3.1416),
        SEED,
    ], build_pipes),
    # plants
    Pattern("FOLIAGE", "Leaves", "OUTLINER_OB_POINTCLOUD", "Leaves and ivy, the classic dappled shade", [
        ("Density", "float", 6.5, 1.0, 40.0),
        ("Leaf Size", "float", 0.8, 0.1, 1.6),
        ("Leaf Width", "float", 0.5, 0.05, 1.0),
        ("Coverage", "float", 0.85, 0.0, 1.0),
        ("Stems", "float", 0.6, 0.0, 1.0),
        ("Depth", "float", 0.5, 0.0, 1.0),
        FRAME,
        SEED,
    ], build_foliage),
    Pattern("FERN", "Fern", "GP_SELECT_STROKES", "Fern fronds, framing the light",
            _frond_inputs(7, 0.7, 18, 0.3, 0.75, 0.3, 0.004, 0.4, lobes=5.0), build_fern),
    Pattern("PALM", "Palm", "OUTLINER_OB_FORCE_FIELD", "Palm fronds",
            _frond_inputs(6, 0.85, 17, 0.42, 0.7, 1.1, 0.006, 0.8, layout=1.0, ox=0.45,
                          oy=-0.6, direction=125.0, spread=140.0), build_palm),
    Pattern("BLADES", "Blades", "STROKE", "Long leaves: spider plant, grass, bamboo leaves",
            _frond_inputs(14, 0.95, 0, 0, 0, 0, 0, 1.4, blade_w=0.045, layout=0.0, ox=0.0,
                          oy=-0.7, direction=90.0, spread=150.0), build_blades),
    Pattern("BAMBOO", "Bamboo", "PARTICLE_POINT", "Bamboo stalks and leaves", [
        ("Stalks", "float", 6.0, 1.0, 30.0),
        ("Thickness", "float", 0.022, 0.003, 0.1),
        ("Segment", "float", 0.22, 0.02, 1.0),
        ("Lean", "float", 0.06, 0.0, 0.5),
        ("Leaves", "float", 0.5, 0.0, 1.0),
        ("Leaf Density", "float", 7.0, 1.0, 30.0),
        ("Back Layer", "float", 0.6, 0.0, 1.0),
        SEED,
    ], build_bamboo),
    Pattern("BRANCHES", "Branches", "OUTLINER_DATA_CURVES", "Tree limbs, twigs and forest canopy", [
        ("Count", "float", 5.0, 1.0, 8.0),
        ("Length", "float", 0.9, 0.05, 2.0),
        ("Bend", "float", 0.5, 0.0, 3.0),
        ("Thickness", "float", 0.018, 0.001, 0.08),
        ("Twigs", "float", 9.0, 0.0, 40.0),
        ("Twig Length", "float", 0.35, 0.0, 1.0),
        ("Twig Width", "float", 0.003, 0.0005, 0.02),
        ("Twig Angle", "float", 1.2, -3.0, 3.0),
        ("Curl", "float", 4.0, -20.0, 20.0),
        ("Network", "float", 0.5, 0.0, 1.0),
        ("Scale", "float", 4.0, 0.3, 20.0),
        ("Leaves", "float", 0.0, 0.0, 1.0),
        ("Layout", "float", 0.0, 0.0, 1.0),
        ("Origin X", "float", -0.6, -1.5, 1.5),
        ("Origin Y", "float", -0.6, -1.5, 1.5),
        ("Direction", "float", 45.0, -360.0, 360.0, "ANGLE"),
        ("Spread", "float", 90.0, 0.0, 360.0, "ANGLE"),
        FRAME,
        SEED,
    ], build_branches),
    Pattern("PINE", "Pine", "LIGHT_SUN", "Pine twigs covered in needles",
            _frond_inputs(14, 0.5, 34, 0.16, 0, 1.4, 0.005, 0.7, needles=0.003), build_pine),
    Pattern("VINES", "Hanging Vines", "OUTLINER_OB_CURVES", "Ivy and jungle vines hanging from above", [
        ("Strands", "float", 12.0, 1.0, 40.0),
        ("Density", "float", 0.9, 0.0, 1.0),
        ("Length", "float", 0.7, 0.05, 1.0),
        ("Sway", "float", 0.4, 0.0, 2.0),
        ("Leaves", "float", 22.0, 2.0, 80.0),
        ("Leaf Size", "float", 0.05, 0.005, 0.2),
        ("Leaf Width", "float", 0.55, 0.1, 1.0),
        FRAME,
        SEED,
    ], build_vines),
    Pattern("CACTI", "Cacti", "OUTLINER_OB_CAMERA", "Desert cacti on the horizon", [
        ("Count", "float", 5.0, 1.0, 20.0),
        ("Height", "float", 0.6, 0.05, 1.0),
        ("Width", "float", 0.035, 0.005, 0.15),
        ("Arms", "float", 0.7, 0.0, 1.0),
        ("Spines", "float", 0.5, 0.0, 1.0),
        ("Back Layer", "float", 0.5, 0.0, 1.0),
        SEED,
    ], build_cacti),
    # other
    Pattern("COBWEB", "Cobweb", "OUTLINER_DATA_GP_LAYER", "Tangled, dusty cobwebs", [
        ("Scale", "float", 2.5, 0.3, 20.0),
        ("Strands", "float", 0.003, 0.0002, 0.02),
        ("Detail", "float", 0.7, 0.0, 1.0),
        ("Clumps", "float", 0.6, 0.0, 1.0),
        ("Warp", "float", 0.6, 0.0, 2.0),
        ("Haze", "float", 0.2, 0.0, 1.0),
        SEED,
    ], build_cobweb),
    Pattern("ORBWEB", "Spider Web", "PROP_CON", "A round spider web", [
        ("Spokes", "float", 22.0, 3.0, 60.0),
        ("Rings", "float", 18.0, 2.0, 60.0),
        ("Sag", "float", 0.3, 0.0, 1.0),
        ("Thickness", "float", 0.0025, 0.0002, 0.01),
        ("Hub", "float", 0.12, 0.0, 0.5),
        ("Broken", "float", 0.1, 0.0, 1.0),
        ("Center X", "float", 0.0, -1.0, 1.0),
        ("Center Y", "float", 0.0, -1.0, 1.0),
        SEED,
    ], build_orbweb),
    Pattern("GLASS", "Broken Glass", "MOD_EXPLODE", "Shattered window glass", [
        ("Impact X", "float", 0.05, -1.0, 1.0),
        ("Impact Y", "float", 0.05, -1.0, 1.0),
        ("Shards", "float", 14.0, 3.0, 60.0),
        ("Rings", "float", 2.5, 0.2, 10.0),
        ("Crack", "float", 0.0018, 0.0002, 0.02),
        ("Missing", "float", 0.15, 0.0, 1.0),
        ("Fine Cracks", "float", 0.5, 0.0, 1.0),
        SEED,
    ], build_glass),
    Pattern("BARBED", "Barbed Wire", "MOD_NOISE", "Coils of barbed wire", [
        ("Count", "float", 5.0, 1.0, 6.0),
        ("Thickness", "float", 0.005, 0.0005, 0.02),
        ("Waviness", "float", 0.6, 0.0, 3.0),
        ("Barb Spacing", "float", 0.09, 0.01, 0.5),
        ("Barb Size", "float", 0.02, 0.0, 0.08),
        SEED,
    ], build_barbed),
    Pattern("CURTAIN", "Curtain", "MOD_CLOTH", "Sheer and lace curtains", [
        ("Folds", "float", 6.0, 0.5, 30.0),
        ("Opacity", "float", 0.5, 0.0, 1.0),
        ("Depth", "float", 0.5, 0.0, 1.0),
        ("Sway", "float", 0.15, 0.0, 1.0),
        ("Swag", "float", 0.0, 0.0, 1.0),
        ("Lace", "float", 0.0, 0.0, 1.0),
        ("Lace Scale", "float", 4.0, 1.0, 30.0),
        SEED,
    ], build_curtain),
    Pattern("CAUSTICS", "Caustics", "MOD_OCEAN", "Light refracted by water", [
        ("Scale", "float", 4.0, 0.5, 40.0),
        ("Sharpness", "float", 0.06, 0.005, 0.5),
        ("Distortion", "float", 1.0, 0.0, 4.0),
        ("Darkness", "float", 0.25, 0.0, 1.0),
        SEED,
    ], build_caustics),
    Pattern("BREAKUP", "Breakup", "TEXTURE", "Soft noise to break up flat light", [
        ("Scale", "float", 3.0, 0.2, 40.0),
        ("Coverage", "float", 0.5, 0.0, 1.0),
        ("Softness", "float", 0.08, 0.0, 0.5),
        ("Detail", "float", 4.0, 0.0, 15.0),
        ("Distortion", "float", 0.3, 0.0, 5.0),
        SEED,
    ], build_breakup),
]

PATTERN_BY_ID = {p.id: p for p in PATTERNS}
IMAGE = "IMAGE"


def group_name(pid):
    return PREFIX + PATTERN_BY_ID[pid].label


def is_current(ng):
    return ng is not None and ng.get("os_version") == GROUP_VERSION


def ensure(pid):
    """The node group for a pattern, built (or rebuilt) when needed."""
    pat = PATTERN_BY_ID[pid]
    ng = bpy.data.node_groups.get(group_name(pid))
    if is_current(ng) and ng.get("os_pattern") == pid:
        return ng
    inputs = [("Vector", "vector", (0.0, 0.0, 0.0))] + list(pat.inputs)
    ng, _, gin, gout = nodekit.new_group(group_name(pid), inputs, [("Light", "color")],
                                          GROUP_VERSION)
    ng["os_pattern"] = pid
    for item in ng.interface.items_tree:
        if getattr(item, "name", "") == "Vector" and item.item_type == "SOCKET":
            item.hide_value = True
    pb = PB(ng)
    I = {s.name: s for s in gin.outputs if s.name}
    x, y, _ = pb.sep(I["Vector"])
    light = pat.build(pb, x, y, I)
    if light.type != "RGBA" and light.type != "VECTOR":
        light = pb.rgb(light)
    pb.link(light, gout.inputs["Light"])
    nodekit.auto_layout(ng)
    return ng


def default_inputs(pid):
    """{input name: default value} for a pattern."""
    out = {}
    for spec in PATTERN_BY_ID[pid].inputs:
        v = spec[2]
        if len(spec) > 5 and spec[5] == "ANGLE":
            v = math.radians(v)
        out[spec[0]] = v
    return out


# -- shared helper groups: placement and finishing -------------------------------------------

TRANSFORM = PREFIX + "Transform"
FINISH = PREFIX + "Finish"


def ensure_transform():
    ng = bpy.data.node_groups.get(TRANSFORM)
    if is_current(ng):
        return ng
    ng, _, gin, gout = nodekit.new_group(TRANSFORM, [
        ("Vector", "vector", (0.0, 0.0, 0.0)),
        ("Scale", "float", 1.0, 0.01, 100.0),
        ("Rotation", "float", 0.0, -360.0, 360.0, "ANGLE"),
        ("Offset X", "float", 0.0, -10.0, 10.0),
        ("Offset Y", "float", 0.0, -10.0, 10.0),
        ("Flip", "float", 0.0, 0.0, 1.0),
    ], [("Vector", "vector")], GROUP_VERSION)
    pb = PB(ng)
    x, y, _ = pb.sep(gin.outputs["Vector"])
    x = pb.mul(x, pb.madd(pb.gt(gin.outputs["Flip"], 0.5), -2.0, 1.0))
    x, y = pb.rot(x, y, pb.neg(gin.outputs["Rotation"]))
    x = pb.sub(pb.div(x, gin.outputs["Scale"]), gin.outputs["Offset X"])
    y = pb.sub(pb.div(y, gin.outputs["Scale"]), gin.outputs["Offset Y"])
    pb.link(pb.comb(x, y), gout.inputs["Vector"])
    nodekit.auto_layout(ng)
    return ng


def ensure_finish():
    ng = bpy.data.node_groups.get(FINISH)
    if is_current(ng):
        return ng
    ng, _, gin, gout = nodekit.new_group(FINISH, [
        ("Light", "color", (1.0, 1.0, 1.0)),
        ("Vector", "vector", (0.0, 0.0, 0.0)),
        ("Strength", "float", 1.0, 0.0, 1.0),
        ("Invert", "float", 0.0, 0.0, 1.0),
        ("Contrast", "float", 0.0, -1.0, 1.0),
        ("Tint", "color", (1.0, 1.0, 1.0)),
        ("Iris", "float", 1.5, 0.0, 1.5),
        ("Iris Softness", "float", 0.1, 0.0, 1.0),
    ], [("Light", "color")], GROUP_VERSION)
    pb = PB(ng)
    light = gin.outputs["Light"]
    inv = pb.gt(gin.outputs["Invert"], 0.5)
    light = pb.mix(light, pb.vsub((1.0, 1.0, 1.0), light), inv)
    # contrast around mid grey (pushes soft patterns towards black and white)
    c = gin.outputs["Contrast"]
    bc = pb.node("ShaderNodeBrightContrast")
    pb.set(bc, "Color", light)
    pb.set(bc, "Contrast", pb.mul(c, 100.0))
    light = bc.outputs[0]
    x, y, _ = pb.sep(gin.outputs["Vector"])
    r = pb.radius(x, y)
    iris = pb.smooth(r, gin.outputs["Iris"], pb.add(gin.outputs["Iris"], pb.max(gin.outputs["Iris Softness"], 0.001)))
    light = pb.mix(light, (0.0, 0.0, 0.0), iris)
    light = pb.mix((1.0, 1.0, 1.0), light, gin.outputs["Strength"])
    light = pb.mix(light, gin.outputs["Tint"], 1.0, blend="MULTIPLY", clamp=True)
    pb.link(light, gout.inputs["Light"])
    nodekit.auto_layout(ng)
    return ng


def all_groups():
    return [g for g in bpy.data.node_groups if g.name.startswith(PREFIX)]
