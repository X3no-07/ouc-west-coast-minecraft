"""Place the v2 east gate (东门） in a finished world, by direct Anvil edit.

Placement (all 估算 — no official source for the east gate; see README):
- OSM has no 东门 node (only 北门/南门）.  The gate sits where the
  east-west campus road out of 浩海广场 meets 海军路 (the north-south road
  along the campus east edge): road axis Z~749, 海军路 surface starts
  ~X1640.  Gate wall runs north-south just west of 海军路 at X=1636-1637.
- Form (user: 7 m high): two 2x2 stone-brick pillars at Z743-744 and
  Z754-755, 7 blocks tall from the ground, opening 9 wide (Z745-753),
  one stone-brick lintel beam across Z743-755 at the top.  Ground is read
  per column from the world itself (v1: Y -52/-53 here).
"""
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from finish_world import World  # noqa: E402

PILLAR = "minecraft:stone_bricks"
LINTEL = "minecraft:stone_bricks"
GATE_X = (1636, 1637)
PILLAR_Z = ((743, 744), (754, 755))
HEIGHT = 7
RED_ROOFS = ["望海苑二期宿舍（西）", "望海苑二期宿舍（中）",
             "望海苑二期宿舍（东）", "西区二期食堂"]
RED_TARGET = "minecraft:red_terracotta"


def top_up_red_roofs(world_dir, plan):
    """Complete the v2 red-tile roofs.

    finish_world only unifies roof levels holding >=5% of interior tops,
    so the small peak levels of the big sloped dorm roofs keep a few
    granite stairs (v1 dry run: 190/1360 cells on the west dorm).  This
    top-up sets the topmost solid block of every footprint cell to red
    terracotta when it is a unify-from block, preserving the stepped
    silhouette and touching nothing below the roof surface.
    """
    import json as _json
    from finish_world import _is_unify_from, cells_in_polygon  # noqa: E402
    plan = _json.loads(Path(plan).read_text(encoding="utf-8")) if isinstance(plan, (str, Path)) else plan
    fps = {fp["name"]: fp for fp in plan["footprints"]}
    world = World(world_dir)
    report = {}
    for name in RED_ROOFS:
        fp = fps[name]
        changed = 0
        for (x, z) in cells_in_polygon(fp["polygon"]):
            top = world.top_solid(x, z, y_top=64, y_bottom=-64)
            if top is None:
                continue
            y, b = top
            if b != RED_TARGET and _is_unify_from(b):
                world.set_block(x, y, z, RED_TARGET)
                changed += 1
        report[name] = changed
    written = world.flush()
    return {"red_roof_top_up": report, "blocks_written": written}


def place_gate(world_dir):
    world = World(world_dir)
    grounds = {}
    for x in GATE_X:
        for z0, z1 in PILLAR_Z:
            for z in range(z0, z1 + 1):
                top = world.top_solid(x, z, y_top=64, y_bottom=-64)
                assert top is not None, (x, z)
                grounds[(x, z)] = top[0]
    base = max(grounds.values())
    placed = Counter()
    for (x, z), gy in grounds.items():
        for y in range(gy + 1, base + HEIGHT + 1):
            world.set_block(x, y, z, PILLAR)
            placed[PILLAR] += 1
    lintel_y = base + HEIGHT
    for x in GATE_X:
        for z in range(743, 756):
            if world.get_block(x, lintel_y, z) in (None, "minecraft:air"):
                world.set_block(x, lintel_y, z, LINTEL)
                placed[LINTEL] += 1
    written = world.flush()
    report = {
        "gate": "east",
        "x": list(GATE_X),
        "pillars_z": [list(p) for p in PILLAR_Z],
        "opening_z": [745, 753],
        "height_blocks": HEIGHT,
        "ground_y": {f"{x},{z}": y for (x, z), y in sorted(grounds.items())},
        "base_y": base,
        "lintel_y": lintel_y,
        "blocks_placed": dict(placed),
        "blocks_written": written,
        "basis": "估算（用户提供 7 米；OSM 无东门节点，位置取浩海广场东侧出校路与海军路交汇处西侧；无官方出处）",
    }
    return report


def main():
    print(place_gate(Path(sys.argv[1])))


if __name__ == "__main__":
    main()
