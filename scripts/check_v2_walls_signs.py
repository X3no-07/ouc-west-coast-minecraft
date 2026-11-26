"""Compare v1 vs v2 mid-wall blocks for the 4 west phase-2 buildings and
check the renamed signs exist in the v2 world. Read-only."""
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from finish_world import World, cells_in_polygon, is_edge_cell  # noqa: E402
import json  # noqa: E402

SAVES = Path(r"C:\Users\lenovo\Desktop\Games\.minecraft\versions\26.2-Fabric 0.19.3\saves")
NAMES = ["望海苑二期宿舍（西）", "望海苑二期宿舍（中）",
         "望海苑二期宿舍（东）", "西区二期食堂"]

plan = json.loads((HERE / "plan-v2.json").read_text(encoding="utf-8"))
fps = {fp["name"]: fp for fp in plan["footprints"]}
worlds = {v: World(SAVES / f"OUC-West-Coast-{v}") for v in ("v1", "v2")}

for name in NAMES:
    fp = fps[name]
    poly = fp["polygon"]
    edge = [(x, z) for (x, z) in cells_in_polygon(poly) if is_edge_cell(x, z, poly)]
    for v, w in worlds.items():
        # mid-wall: sample several heights between ground (-51) and roof base
        c = Counter()
        for (x, z) in edge:
            for y in (-45, -35, -25, -15):
                b = w.get_block(x, y, z)
                if b and b != "minecraft:air":
                    c[b] += 1
        print(f"{name} {v} mid-wall:", c.most_common(8))
    print()

# signs: search raw region bytes for the new names (UTF-8)
for needle in ["原电子信息楼", "原计算机楼", "信息北楼", "信息南楼"]:
    hits = []
    for f in sorted((SAVES / "OUC-West-Coast-v2" / "region").glob("*.mca")):
        data = f.read_bytes()
        if needle.encode("utf-8") in data:
            hits.append(f.name)
    print(f"sign text {needle!r} in v2 regions:", hits)
