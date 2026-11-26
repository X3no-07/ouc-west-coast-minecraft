"""Deterministic finish pass for an Arnis-generated world (before packaging).

Scope is strictly limited by the plan file: a roof rule only touches cells
inside one building footprint at that roof's top layer; a paving rule only
touches cells inside one named paving polygon; a plinth rule only fills air
directly under a building edge.  Nothing here does a global find-replace.

Roof rule (per part):
  * roof_y is auto-detected as the modal topmost solid Y inside the
    footprint (interior cells only).
  * The target is the plan's "target" when given; otherwise it is the most
    common plausible roof surface among interior cells at roof_y (concrete
    / terracotta / smooth_stone / granite_stairs / andesite family; wool and
    polished_blackstone are palette noise and are never picked as target).
  * At roof_y, cells whose block is in UNIFY_FROM (the palette-random
    cover blocks Arnis draws from) are set to the part's target block.
  * Kept as-is at roof_y: stone_bricks / quartz_block (parapet and edge
    trim), glass (skylight), and anything else not in UNIFY_FROM.
  * Everything above roof_y (equipment, rods, slabs at roof_y+1) is untouched.

Paving rule (per polygon):
  * For each cell, find the top solid block (ignoring short/tall grass
    above it).  If it is grass/dirt/gravel, replace it in place with
    stone_bricks and clear vegetation above it (up to 3 blocks).
  * Already-paved / stone / concrete tops are left alone.
  * If the top is more than 1 block below the polygon's target top Y,
    fill air above it up to that Y with stone_bricks (a low plinth).

Plinth rule: for each footprint edge cell, fill air at Y=-46/-45 directly
under the building floor with stone_bricks.  Reports 0 when not needed.

Usage: python finish_world.py <world_dir> <plan.json> [--out-report path]
The world dir is an Arnis output (region/ at its top level).  Edits are
written back into that world in place; the script prints a JSON report and
re-reads the edited world to verify the counts.
"""
import json
import sys
import zlib
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from anvil import (TAG_COMPOUND, decode_indices, find, loads, dumps,
                   read_region, write_region, set_blocks_in_chunk)

AIR = {"minecraft:air", "minecraft:cave_air", "minecraft:void_air"}
VEGETATION = {"minecraft:short_grass", "minecraft:tall_grass", "minecraft:fern",
              "minecraft:large_fern", "minecraft:dandelion", "minecraft:poppy",
              "minecraft:grass", "minecraft:dead_bush"}
UNIFY_FROM = {"minecraft:red_terracotta", "minecraft:terracotta",
              "minecraft:white_terracotta", "minecraft:white_concrete",
              "minecraft:smooth_stone", "minecraft:gray_concrete",
              "minecraft:gray_wool", "minecraft:blue_wool",
              "minecraft:polished_blackstone",
              "minecraft:polished_andesite", "minecraft:andesite",
              "minecraft:light_gray_concrete", "minecraft:granite_stairs",
              "minecraft:grass_block", "minecraft:dirt"}
# Extra blocks that count as "unify to the target" at a roof layer, beyond
# UNIFY_FROM: every terracotta colour (Arnis draws brown/cyan/etc. as roof
# speckles) and the diorite / granite / calcite speckles.  Sandstone and
# smooth_sandstone are deliberately NOT here: they are parapet trim
# (verified: all their cells sit on footprint edges).
_UNIFY_EXTRA = {"minecraft:diorite", "minecraft:polished_diorite",
                "minecraft:granite", "minecraft:polished_granite",
                "minecraft:calcite"}


def _is_unify_from(block):
    return (block in UNIFY_FROM or block in _UNIFY_EXTRA
            or (block or "").endswith("_terracotta"))


# Blocks that may be picked as a roof target (auto mode): plausible roof
# surfaces only.  Wool / polished_blackstone are Arnis palette noise, never
# a target; stone_bricks / quartz_block are parapet trim, never a target.
def _is_roof_candidate(block):
    if block is None:
        return False
    return (block.endswith("_concrete") or block.endswith("_terracotta")
            or block in {"minecraft:smooth_stone", "minecraft:granite_stairs",
                         "minecraft:andesite", "minecraft:polished_andesite"})
PAVING_FROM = {"minecraft:grass_block", "minecraft:dirt",
               "minecraft:coarse_dirt", "minecraft:gravel",
               "minecraft:sand", "minecraft:grass_path"}
PAVING_KEEP = {"minecraft:stone_bricks", "minecraft:stone",
               "minecraft:smooth_stone", "minecraft:light_gray_concrete",
               "minecraft:gray_concrete", "minecraft:polished_andesite",
               "minecraft:cobblestone", "minecraft:brick"}


def point_in_polygon(x, z, poly):
    """poly: list of [x, z] integer vertices (open ring). Cell centre test."""
    px, pz = x + 0.5, z + 0.5
    inside = False
    n = len(poly)
    for i in range(n):
        x1, z1 = poly[i]
        x2, z2 = poly[(i + 1) % n]
        if (z1 > pz) != (z2 > pz):
            xin = (pz - z1) * (x2 - x1) / (z2 - z1) + x1
            if px < xin:
                inside = not inside
    return inside


def cells_in_polygon(poly):
    xs = [p[0] for p in poly]
    zs = [p[1] for p in poly]
    out = []
    for x in range(min(xs), max(xs) + 1):
        for z in range(min(zs), max(zs) + 1):
            if point_in_polygon(x, z, poly):
                out.append((x, z))
    return out


def rings_of(entry):
    if "polygons" in entry:
        return entry["polygons"]
    return [entry["polygon"]]


def cells_in_entry(entry):
    if "cells" in entry:
        return [tuple(c) for c in entry["cells"]]
    out = []
    for poly in rings_of(entry):
        out.extend(cells_in_polygon(poly))
    return out


def is_edge_cell_entry(x, z, entry):
    return any(is_edge_cell(x, z, poly) for poly in rings_of(entry))


def is_edge_cell(x, z, poly):
    return (not point_in_polygon(x + 1, z, poly) or not point_in_polygon(x - 1, z, poly)
            or not point_in_polygon(x, z + 1, poly) or not point_in_polygon(x, z - 1, poly))


class World:
    """Chunk cache over one Arnis world dir (region/ at top level)."""

    def __init__(self, world_dir):
        self.world = Path(world_dir)
        self.region_dir = self.world / "region"
        if not self.region_dir.is_dir():
            raise FileNotFoundError(f"no region/ in {world_dir}")
        self._chunks = {}   # (rx, rz) -> {(lx, lz): parsed chunk root}
        self._raw = {}      # (rx, rz) -> {(lx, lz): (compressed, ts)}
        self._sections = {}  # id(chunk root) -> {sec_y: (palette, indices)}
        self.edits = {}     # (cx, cz) global chunk -> {(lx, y, lz): block}
        self.changed_chunks = set()

    def _region_file(self, rx, rz):
        return self.region_dir / f"r.{rx}.{rz}.mca"

    def _load_region(self, rx, rz):
        if (rx, rz) in self._chunks:
            return
        raw = read_region(self._region_file(rx, rz))
        self._raw[(rx, rz)] = raw
        parsed = {}
        for (lx, lz), (comp, _ts) in raw.items():
            parsed[(lx, lz)] = loads(zlib.decompress(comp))
        self._chunks[(rx, rz)] = parsed

    def _section_data(self, root, sec_y):
        key = id(root)
        cache = self._sections.setdefault(key, {})
        if sec_y in cache:
            return cache[sec_y]
        _, _, nodes = root
        sections_node = None
        for node in nodes:
            if node[1] == "sections":
                sections_node = node
                break
        _, items = sections_node[2]
        for sec_nodes in items:
            if find(sec_nodes, "Y")[1] == sec_y:
                bs = None
                for node in sec_nodes:
                    if node[1] == "block_states":
                        bs = node[2]
                        break
                if bs is None:
                    cache[sec_y] = ([], [0] * 4096)
                else:
                    indices, names = decode_indices(bs)
                    cache[sec_y] = (names, indices)
                return cache[sec_y]
        cache[sec_y] = ([], [0] * 4096)
        return cache[sec_y]

    def get_block(self, x, y, z):
        cx, cz = x // 16, z // 16
        rx, rz = cx // 32, cz // 32
        self._load_region(rx, rz)
        root = self._chunks[(rx, rz)].get((cx % 32, cz % 32))
        if root is None:
            return None
        sec_y = y // 16
        palette, indices = self._section_data(root, sec_y)
        if not palette:
            return None
        idx = (y % 16) * 256 + (z % 16) * 16 + (x % 16)
        return palette[indices[idx]]

    def set_block(self, x, y, z, block):
        cx, cz = x // 16, z // 16
        self.edits.setdefault((cx, cz), {})[(x % 16, y, z % 16)] = block
        self.changed_chunks.add((cx, cz))

    def top_solid(self, x, z, y_top=10, y_bottom=-60):
        """Highest non-air, non-vegetation block, or None."""
        for y in range(y_top, y_bottom - 1, -1):
            b = self.get_block(x, y, z)
            if b is None or b in AIR or b in VEGETATION:
                continue
            return (y, b)
        return None

    def flush(self):
        """Write all collected edits back into the region files."""
        by_region = {}
        for (cx, cz), edits in self.edits.items():
            by_region.setdefault((cx // 32, cz // 32), {})[(cx, cz)] = edits
        total = 0
        for (rx, rz), chunk_edits in by_region.items():
            self._load_region(rx, rz)
            new_chunks = {}
            for (lx, lz), (comp, ts) in self._raw[(rx, rz)].items():
                root = self._chunks[(rx, rz)][(lx, lz)]
                gcx, gcz = rx * 32 + lx, rz * 32 + lz
                edits = chunk_edits.get((gcx, gcz))
                if edits:
                    total += set_blocks_in_chunk(root, edits)
                    new_chunks[(lx, lz)] = (zlib.compress(dumps(root), level=6), ts)
                else:
                    new_chunks[(lx, lz)] = (comp, ts)
            write_region(self._region_file(rx, rz), new_chunks)
        return total


def finish(world_dir, plan):
    world = World(world_dir)
    report = {"roofs": [], "paving": [], "plinth": {"filled": 0, "checked": 0}}

    for roof in plan.get("roofs", []):
        cells = cells_in_entry(roof)
        interior = [(x, z) for (x, z) in cells if not is_edge_cell_entry(x, z, roof)]
        # Detect roof_y as the modal topmost solid Y among interior cells.
        # Range covers the whole school: west dorm roofs sit as high as
        # Y=+10 and the wisdom-ocean NE wing as low as Y=-44.  (The
        # original [-40,-5] window missed both ends and left 6 roofs
        # untouched.)  A missing building is still safe: its ground level
        # yields no roof candidate and the roof is skipped.
        tops = Counter()
        for (x, z) in interior:
            top = world.top_solid(x, z, y_top=64, y_bottom=-64)
            if top is not None and -64 <= top[0] <= 32:
                tops[top[0]] += 1
        if not tops:
            report["roofs"].append({"name": roof["name"], "error": "no roof top found"})
            continue
        roof_y = tops.most_common(1)[0][0]
        # Stepped roofs have more than one real level (e.g. 听海苑7 has
        # sizeable tops at -36, -15 and -13).  Unify every level that holds
        # >=5% of interior tops (and >=20 cells); the main level picks the
        # target.  Equipment spikes (a few cells) never qualify.
        n_interior = len(interior)
        levels = sorted([y for y, c in tops.items()
                         if c >= max(20, 0.05 * n_interior)], reverse=True)
        before = Counter(world.get_block(x, roof_y, z) for (x, z) in cells)
        target = roof.get("target")
        auto = False
        if not target:
            # Auto target: most common plausible roof surface among interior
            # cells at roof_y (edge trim excluded by the interior filter).
            cand = Counter()
            for (x, z) in interior:
                b = world.get_block(x, roof_y, z)
                if _is_roof_candidate(b):
                    cand[b] += 1
            if not cand:
                report["roofs"].append({
                    "name": roof["name"], "roof_y": roof_y,
                    "target": None, "cells": len(cells),
                    "top_y_votes": dict(tops), "before": dict(before),
                    "changed": 0, "skipped": "no roof candidate at top layer",
                })
                continue
            target = cand.most_common(1)[0][0]
            auto = True
        changed = 0
        veg_cleared = 0
        level_changed = {}
        for level_y in levels:
            n = 0
            for (x, z) in cells:
                b = world.get_block(x, level_y, z)
                if _is_unify_from(b) and b != target:
                    world.set_block(x, level_y, z, target)
                    n += 1
                    for yy in range(level_y + 1, level_y + 4):
                        vb = world.get_block(x, yy, z)
                        if vb in VEGETATION:
                            world.set_block(x, yy, z, "minecraft:air")
                            veg_cleared += 1
            level_changed[level_y] = n
            changed += n
        entry = {
            "name": roof["name"], "roof_y": roof_y,
            "target": target, "cells": len(cells),
            "top_y_votes": dict(tops), "before": dict(before),
            "changed": changed, "vegetation_cleared": veg_cleared,
            "levels": levels, "level_changed": {str(k): v for k, v in level_changed.items()},
        }
        if auto:
            entry["target_auto"] = True
        report["roofs"].append(entry)

    for pav in plan.get("paving", []):
        target_top = pav.get("target_top_y", -45)
        block = pav.get("block", "minecraft:stone_bricks")
        cells = cells_in_entry(pav)
        before = Counter()
        changed = 0
        veg_cleared = 0
        filled = 0
        for (x, z) in cells:
            top = world.top_solid(x, z, y_top=10, y_bottom=-60)
            if top is None:
                continue
            y, b = top
            before[b] += 1
            if b in PAVING_FROM:
                world.set_block(x, y, z, block)
                changed += 1
                for yy in range(y + 1, y + 4):
                    vb = world.get_block(x, yy, z)
                    if vb in VEGETATION:
                        world.set_block(x, yy, z, "minecraft:air")
                        veg_cleared += 1
                if y < target_top:
                    for yy in range(y + 1, target_top + 1):
                        if world.get_block(x, yy, z) in AIR:
                            world.set_block(x, yy, z, block)
                            filled += 1
            elif b in PAVING_KEEP:
                # Already paved: still clear vegetation sitting on it.
                for yy in range(y + 1, y + 4):
                    vb = world.get_block(x, yy, z)
                    if vb in VEGETATION:
                        world.set_block(x, yy, z, "minecraft:air")
                        veg_cleared += 1
        report["paving"].append({
            "name": pav["name"], "cells": len(cells), "before_top": dict(before),
            "changed": changed, "vegetation_cleared": veg_cleared,
            "filled": filled, "block": block,
        })

    # Plinth: fill air directly under footprint edges (Y -46/-45).
    filled = 0
    checked = 0
    for foot in plan.get("footprints", []):
        for (x, z) in cells_in_entry(foot):
            if not is_edge_cell_entry(x, z, foot):
                continue
            for y in (-46, -45):
                checked += 1
                if world.get_block(x, y, z) in AIR:
                    world.set_block(x, y, z, "minecraft:stone_bricks")
                    filled += 1
    report["plinth"] = {"filled": filled, "checked": checked}

    written = world.flush()
    report["chunks_changed"] = len(world.changed_chunks)
    report["blocks_written"] = written

    # Verify by re-reading the edited world.
    verify = World(world_dir)
    vreport = {"roofs": [], "paving": []}
    for i, roof in enumerate(plan.get("roofs", [])):
        cells = cells_in_entry(roof)
        # One report entry per plan roof, in order (names need not be unique).
        if i >= len(report["roofs"]) or "roof_y" not in report["roofs"][i]:
            continue
        roof_y = report["roofs"][i]["roof_y"]
        after = Counter(verify.get_block(x, roof_y, z) for (x, z) in cells)
        vreport["roofs"].append({"name": roof["name"], "roof_y": roof_y,
                                 "after": dict(after)})
    for pav in plan.get("paving", []):
        cells = cells_in_entry(pav)
        after = Counter()
        for (x, z) in cells:
            top = verify.top_solid(x, z, y_top=10, y_bottom=-60)
            if top is not None:
                after[top[1]] += 1
        vreport["paving"].append({"name": pav["name"], "after_top": dict(after)})
    report["verify"] = vreport
    return report


def main():
    world_dir, plan_path = sys.argv[1], sys.argv[2]
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    report = finish(world_dir, plan)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    out = Path(sys.argv[3]) if len(sys.argv) > 3 else None
    if out:
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")


if __name__ == "__main__":
    main()
