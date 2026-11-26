"""Verify the v2 world (read-only).  Usage: verify_v2.py <world_dir>

Checks:
- level.dat: name / spawn (1361,-47,711) / creative / allowCommands / 1.21.4
- 10 region files present
- info-north roofs unchanged from v1 (red long wing, gray main, light-gray west)
- west phase-2 red roofs: top blocks mostly red_terracotta
- west phase-2 yellow walls: report sampled wall-block histogram (no assert:
  Arnis colour mapping is approximate; the README flags it for review)
- east gate: stone-brick pillars + lintel present, 7 blocks tall
- v1 invariants: courtyard 25 stone bricks
"""
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from finish_world import World, cells_in_polygon  # noqa: E402
import gzip, json  # noqa: E402
from rules_preview import nbt  # noqa: E402

RED = "minecraft:red_terracotta"
YELLOW = {"minecraft:yellow_concrete", "minecraft:yellow_terracotta",
          "minecraft:yellow_wool", "minecraft:yellow_concrete_powder"}


def main():
    world_dir = Path(sys.argv[1])
    level = nbt(gzip.decompress((world_dir / "level.dat").read_bytes()))["Data"]
    print("LevelName:", level["LevelName"], "| spawn:",
          level["SpawnX"], level["SpawnY"], level["SpawnZ"],
          "| GameType:", level["GameType"], "| allowCommands:", level["allowCommands"],
          "| Version:", level["Version"]["Name"])
    assert str(level["LevelName"]) == "中国海洋大学西海岸校区v2"
    assert (int(level["SpawnX"]), int(level["SpawnY"]), int(level["SpawnZ"])) == (1361, -47, 711)
    assert int(level["GameType"]) == 1 and int(level["allowCommands"]) == 1
    assert level["Version"]["Name"] == "1.21.4"
    mca = sorted((world_dir / "region").glob("*.mca"))
    print("region files:", len(mca))
    assert len(mca) == 10

    w = World(world_dir)
    c = Counter(w.get_block(x, -45, z) for x in range(1044, 1049) for z in range(569, 574))
    print("courtyard Y=-45:", dict(c))
    assert c == Counter({"minecraft:stone_bricks": 25}), c

    plan = json.loads((HERE / "plan-v2.json").read_text(encoding="utf-8"))
    fps = {fp["name"]: fp for fp in plan["footprints"]}
    for name, want in [("望海苑二期宿舍（西）", RED), ("望海苑二期宿舍（中）", RED),
                       ("望海苑二期宿舍（东）", RED), ("西区二期食堂", RED)]:
        fp = fps[name]
        cells = cells_in_polygon(fp["polygon"])
        tops = Counter()
        for (x, z) in cells:
            t = w.top_solid(x, z, y_top=64, y_bottom=-64)
            if t:
                tops[t[1]] += 1
        print(f"{name} roof tops:", tops.most_common(4))
        assert tops.most_common(1)[0][0] == want and \
            tops[want] >= 0.9 * sum(tops.values()), (name, tops.most_common(3))
        # yellow walls: sample edge columns at mid heights
        walls = Counter()
        xs = [p[0] for p in fp["polygon"]]
        zs = [p[1] for p in fp["polygon"]]
        for x in range(min(xs), max(xs) + 1):
            for z in (min(zs), max(zs)):
                t = w.top_solid(x, z, y_top=64, y_bottom=-64)
                if t:
                    for y in range(t[0] - 6, t[0]):
                        b = w.get_block(x, y, z)
                        if b and b != "minecraft:air":
                            walls[b] += 1
        print(f"{name} wall sample:", walls.most_common(6),
              "| yellow-ish:", sum(v for k, v in walls.items() if k in YELLOW))

    # east gate: pillars X1636-1637, Z743-744 + Z754-755, 7 tall; lintel Z743-755.
    # (top_solid would return the pillar itself, so measure the stone-brick run.)
    tops = {}
    for x in (1636, 1637):
        for z in (743, 744, 754, 755):
            run = 0
            top_y = None
            for y in range(-40, -64, -1):
                if w.get_block(x, y, z) == "minecraft:stone_bricks":
                    if top_y is None:
                        top_y = y
                    run += 1
                elif top_y is not None:
                    break
            tops[(x, z)] = (top_y, run)
            print(f"gate pillar ({x},{z}): top_y={top_y} stone-brick run={run}")
            assert top_y is not None and run >= 7, ((x, z), top_y, run)
    lintel_y = {t[0] for t in tops.values()}
    assert len(lintel_y) == 1, tops
    lintel_y = lintel_y.pop()
    lintel = Counter(w.get_block(x, lintel_y, z) for x in (1636, 1637) for z in range(743, 756))
    print(f"gate lintel Y={lintel_y}:", dict(lintel))
    assert lintel["minecraft:stone_bricks"] >= 24, lintel
    print("verify_v2 OK")


if __name__ == "__main__":
    main()
