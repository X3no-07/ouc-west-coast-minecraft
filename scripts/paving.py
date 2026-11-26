"""Derive paving polygons from aligned footprints + OSM highways.

Rules (all in integer Minecraft coords, all derived, none hand-drawn):
  * skirt: each footprint expanded outward by 2 blocks (mitre join),
    minus all footprints.  This is the building base / apron.
  * pair gap: when two footprints face each other across a gap <= 15
    blocks wide (their projections overlap), the whole gap rectangle is
    paved -- it is a passage / courtyard between the two buildings.
  * facing strip: when two footprints face each other across a wider gap
    (<= 30 blocks), a 4-wide strip along each facing face is paved.
  * walkway: for each footprint, the face whose centre is nearest to an
    OSM highway (residential / service / pedestrian / footway / path),
    if that distance is <= 25 blocks.  A 4-wide axis-aligned L-shaped
    strip runs from the face centre to the nearest road point.  No
    entrance nodes exist in the OSM data, so the face is chosen by
    proximity to a real road, not by guessing a door.

Requires shapely (available in the project's v3-python-deps under
Python 3.12 on the PC).  Output paving entries have "polygons": a list
of integer rings, one per connected component.
"""
import json
import math
from pathlib import Path

from shapely.geometry import Polygon, LineString, box, Point
from shapely.ops import unary_union, nearest_points


def poly_to_shapely(ring):
    return Polygon([(x, z) for x, z in ring])


def cells_in_geom(geom):
    """Integer cells whose centre lies inside geom."""
    if geom.is_empty:
        return set()
    minx, minz, maxx, maxz = [int(math.floor(v)) for v in geom.bounds]
    out = set()
    for x in range(minx, maxx + 1):
        for z in range(minz, maxz + 1):
            if geom.contains(Point(x + 0.5, z + 0.5)):
                out.add((x, z))
    return out


def cells_to_rings(cells):
    """One ring per connected component of a set of unit cells."""
    if not cells:
        return []
    squares = [box(x, z, x + 1, z + 1) for (x, z) in cells]
    merged = unary_union(squares)
    geoms = [merged] if merged.geom_type == "Polygon" else list(merged.geoms)
    rings = []
    for g in geoms:
        ring = [(int(round(x)), int(round(z))) for x, z in g.exterior.coords]
        if len(ring) > 1 and ring[0] == ring[-1]:
            ring = ring[:-1]
        rings.append(ring)
    return rings


def _add_paving(paving, name, cells, block="minecraft:stone_bricks"):
    # Store the exact cell set: converting cells -> rings -> cells loses
    # cells at component boundaries and drops holes (skirt frames).
    cells = sorted(cells)
    if cells:
        paving.append({"name": name, "cells": [list(c) for c in cells],
                       "block": block, "target_top_y": -45})


def derive_paving(footprints, highways, group_name):
    """footprints: [{"name": str, "polygon": [[x, z], ...]}] integer,
    axis-aligned.  highways: list of LineStrings in MC float coords."""
    shapes = [(fp["name"], poly_to_shapely(fp["polygon"])) for fp in footprints]
    all_foot = unary_union([s for _, s in shapes])
    highways = [hw if hasattr(hw, "geom_type") else LineString(hw) for hw in highways]
    paving = []

    # Skirt.
    skirt_cells = set()
    for _, shape in shapes:
        skirt_cells.update(cells_in_geom(shape.buffer(2, join_style=2).difference(all_foot)))
    _add_paving(paving, f"{group_name}·基座裙边", skirt_cells)

    # Pair gaps and facing strips.  Work on bounding boxes (aligned).
    boxes = []
    for name, shape in shapes:
        minx, minz, maxx, maxz = shape.bounds
        boxes.append((name, int(minx), int(minz), int(maxx), int(maxz)))
    for i, (n1, x10, z10, x11, z11) in enumerate(boxes):
        for (n2, x20, z20, x21, z21) in boxes[i + 1:]:
            # Vertical gap: n1 west of n2 (or vice versa), Z ranges overlap.
            z_overlap = (min(z11, z21) - max(z10, z20))
            if z_overlap > 0:
                if x11 <= x20:
                    gap_w, gap = x20 - x11, (x11, max(z10, z20), x20, min(z11, z21))
                elif x21 <= x10:
                    gap_w, gap = x10 - x21, (x21, max(z10, z20), x10, min(z11, z21))
                else:
                    gap_w, gap = None, None
                if gap is not None:
                    gx0, gz0, gx1, gz1 = gap
                    if gap_w <= 15:
                        cells = {(x, z) for x in range(gx0, gx1) for z in range(gz0, gz1)}
                        _add_paving(paving, f"{group_name}·{n1}与{n2}之间通道", cells)
                    elif gap_w <= 30:
                        for (fx, strip) in ((gx0, (gx0, gz0, gx0 + 4, gz1)),
                                            (gx1 - 4, (gx1 - 4, gz0, gx1, gz1))):
                            cells = {(x, z) for x in range(strip[0], strip[2])
                                     for z in range(strip[1], strip[3])}
                            _add_paving(paving, f"{group_name}·{n1}与{n2}之间步道", cells)
            # Horizontal gap: n1 north of n2, X ranges overlap.
            x_overlap = (min(x11, x21) - max(x10, x20))
            if x_overlap > 0:
                if z11 <= z20:
                    gap_w, gap = z20 - z11, (max(x10, x20), z11, min(x11, x21), z20)
                elif z21 <= z10:
                    gap_w, gap = z10 - z21, (max(x10, x20), z21, min(x11, x21), z10)
                else:
                    gap_w, gap = None, None
                if gap is not None:
                    gx0, gz0, gx1, gz1 = gap
                    if gap_w <= 15:
                        cells = {(x, z) for x in range(gx0, gx1) for z in range(gz0, gz1)}
                        _add_paving(paving, f"{group_name}·{n1}与{n2}之间通道", cells)
                    elif gap_w <= 30:
                        for strip in ((gx0, gz0, gx1, gz0 + 4), (gx0, gz1 - 4, gx1, gz1)):
                            cells = {(x, z) for x in range(strip[0], strip[2])
                                     for z in range(strip[1], strip[3])}
                            _add_paving(paving, f"{group_name}·{n1}与{n2}之间步道", cells)

    # Inter-building yard: gap cells inside the group bbox that lie within
    # 12 blocks of at least two different footprints.  This is the yard /
    # passage between buildings (for info-north it is exactly the enclosed
    # yard X1037-1050, Z557-582 that holds the 25 grass cells, plus the
    # strip between the long wing and the main building).
    group_box = box(min(x for _, s in shapes for x, _ in s.exterior.coords),
                    min(z for _, s in shapes for _, z in s.exterior.coords),
                    max(x for _, s in shapes for x, _ in s.exterior.coords),
                    max(z for _, s in shapes for _, z in s.exterior.coords))
    yard_cells = set()
    # Chebyshev (grid) distance to each footprint bbox: a yard cell is
    # "between" buildings when it is close to two of them along the grid.
    bboxes = []
    for _, s in shapes:
        minx, minz, maxx, maxz = s.bounds
        bboxes.append((minx, minz, maxx, maxz))

    def _cheb(px, pz, bb):
        minx, minz, maxx, maxz = bb
        dx = 0.0 if minx <= px <= maxx else min(abs(px - minx), abs(px - maxx))
        dz = 0.0 if minz <= pz <= maxz else min(abs(pz - minz), abs(pz - maxz))
        return max(dx, dz)

    for (x, z) in cells_in_geom(group_box.difference(all_foot)):
        near = sum(1 for bb in bboxes if _cheb(x + 0.5, z + 0.5, bb) <= 14.0)
        if near >= 2:
            yard_cells.add((x, z))
    _add_paving(paving, f"{group_name}·楼间院地", yard_cells)

    # Walkways to the nearest road (<=25 blocks, 4 wide, L-shaped).
    for name, shape in shapes:
        minx, minz, maxx, maxz = shape.bounds
        faces = [
            ("south", ((minx + maxx) / 2, maxz), (0, 1)),
            ("north", ((minx + maxx) / 2, minz), (0, -1)),
            ("west", (minx, (minz + maxz) / 2), (-1, 0)),
            ("east", (maxx, (minz + maxz) / 2), (1, 0)),
        ]
        best = None
        for face_name, centre, normal in faces:
            for hw in highways:
                p_road = nearest_points(Point(centre[0], centre[1]), hw)[1]
                dist = math.hypot(p_road.x - centre[0], p_road.y - centre[1])
                if best is None or dist < best[0]:
                    best = (dist, face_name, centre, normal, (p_road.x, p_road.y))
        if best is None or best[0] > 25:
            continue
        dist, face_name, centre, normal, road_pt = best
        cx, cz = centre
        rx, rz = road_pt
        rects = []
        if normal == (0, 1):
            rects.append(box(cx - 2, cz, cx + 2, rz))
            rects.append(box(min(cx, rx) - 2, rz - 2, max(cx, rx) + 2, rz + 2))
        elif normal == (0, -1):
            rects.append(box(cx - 2, rz, cx + 2, cz))
            rects.append(box(min(cx, rx) - 2, rz - 2, max(cx, rx) + 2, rz + 2))
        elif normal == (-1, 0):
            rects.append(box(rx, cz - 2, cx, cz + 2))
            rects.append(box(rx - 2, min(cz, rz) - 2, rx + 2, max(cz, rz) + 2))
        else:
            rects.append(box(cx, cz - 2, rx, cz + 2))
            rects.append(box(rx - 2, min(cz, rz) - 2, rx + 2, max(cz, rz) + 2))
        strip = unary_union(rects).difference(all_foot)
        _add_paving(paving, f"{group_name}·{name}步道（{face_name}）",
                    cells_in_geom(strip))
    return paving


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("footprints_json", type=Path)
    ap.add_argument("highways_json", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--group", default="info-north")
    args = ap.parse_args()
    fps = json.loads(args.footprints_json.read_text(encoding="utf-8"))
    hws = json.loads(args.highways_json.read_text(encoding="utf-8"))
    paving = derive_paving(fps, [LineString(pts) for pts in hws], args.group)
    args.output.write_text(json.dumps({"paving": paving}, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    for p in paving:
        print(p["name"], "rings", len(p["polygons"]))


if __name__ == "__main__":
    main()
