"""Measure the visible top surface per building in a world (read-only).
For each v3 feature and each non-replaced OSM building way, count the top
solid block over its footprint cells.  Prints the top 4 blocks per roof.
"""
import json
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from align_buildings import lonlat_to_mc  # noqa: E402
from finish_world import World, cells_in_polygon  # noqa: E402

BBOX = (35.77065, 120.01335, 35.77960, 120.03655)


def mc_poly_from_lonlat(coords):
    return [(int(round(x)), int(round(z)))
            for (x, z) in (lonlat_to_mc(lon, lat) for (lon, lat) in coords)]


def main():
    world = World(Path(sys.argv[1]))
    covered = set()
    feats = []
    for f in ("v3-learning.geojson", "v3-haide-wisdom.geojson", "v3-dorms.geojson",
              "v3-info-north.geojson"):
        d = json.load(open(HERE / f))
        for ft in d["features"]:
            covered.update(str(i) for i in ft["properties"].get("replace_ids", []))
            feats.append((ft["properties"].get("name", "?"),
                          ft["properties"].get("part", ""),
                          ft["geometry"]["coordinates"][0]))
    # OSM buildings not covered by any v3 feature
    tree = ET.parse(HERE / "osm-area.xml")
    root = tree.getroot()
    nodes = {n.get("id"): (float(n.get("lon")), float(n.get("lat")))
             for n in root.iter("node")}
    for w in root.iter("way"):
        tags = {t.get("k"): t.get("v") for t in w.iter("tag")}
        if "building" not in tags:
            continue
        if w.get("id") in covered:
            continue
        nds = [nd.get("ref") for nd in w.findall("nd")]
        coords = [nodes[n] for n in nds if n in nodes]
        if len(coords) < 4:
            continue
        feats.append((tags.get("name") or f"osm-{w.get('id')}", "", coords))

    for name, part, coords in feats:
        poly = mc_poly_from_lonlat(coords)
        cells = cells_in_polygon(poly)
        if not cells:
            print(f"{name} {part}: NO CELLS")
            continue
        tops = Counter()
        for (x, z) in cells:
            try:
                y, block = world.top_solid(x, z)
            except FileNotFoundError:
                tops["<no region>"] += 1
                continue
            tops[block] += 1
        label = f"{name}" + (f"·{part}" if part else "")
        print(f"{label}: cells={len(cells)} top={tops.most_common(4)}")


if __name__ == "__main__":
    main()
