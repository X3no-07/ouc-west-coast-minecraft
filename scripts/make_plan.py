"""Build a finish plan (roofs + paving + footprints) from an aligned GeoJSON.

Run on the PC (Python 3.12 + v3-python-deps) or anywhere with shapely.
Inputs: aligned GeoJSON, osm-area.xml (for highways).
Outputs: plan JSON for finish_world.py, plus a printed summary.

Roof targets are per part (from the measured roof counts in the current
world -- see the project notes in the plan file's "roof_basis"):
  * 信息北楼·红顶长翼 -> red_terracotta (was 825 red / 340 plain)
  * 信息北楼·主楼     -> gray_concrete  (was 534 grey concrete / 661 grey wool)
  * 信息北楼·西翼     -> light_gray_concrete (was 374 light-grey / 518 smooth stone)
For other groups the caller supplies --roof-targets JSON {part: block}.
"""
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from align_buildings import lonlat_to_mc
from paving import derive_paving

DEFAULT_TARGETS = {
    "红顶长翼": "minecraft:red_terracotta",
    "主楼": "minecraft:gray_concrete",
    "西翼": "minecraft:light_gray_concrete",
}


def footprints_from_geojson(path):
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    fps = []
    for feat in data["features"]:
        geom = feat["geometry"]
        polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
        for poly in polys:
            ring = poly[0]
            mc = []
            for lon, lat in ring[:-1]:
                x, z = lonlat_to_mc(lon, lat)
                mc.append([round(x), round(z)])
            # Drop consecutive duplicates.
            clean = []
            for p in mc:
                if not clean or clean[-1] != p:
                    clean.append(p)
            fps.append({"name": feat["properties"].get("part") or feat["properties"]["name"],
                        "polygon": clean, "properties": feat["properties"]})
    return fps


def highways_from_osm(osm_path):
    tree = ET.parse(osm_path)
    root = tree.getroot()
    nodes = {n.get("id"): (float(n.get("lon")), float(n.get("lat")))
             for n in root.findall("node")}
    out = []
    for way in root.findall("way"):
        tags = {t.get("k"): t.get("v") for t in way.findall("tag")}
        if tags.get("highway") not in ("residential", "service", "pedestrian",
                                        "footway", "path", "tertiary", "secondary"):
            continue
        pts = []
        for nd in way.findall("nd"):
            if nd.get("ref") in nodes:
                lon, lat = nodes[nd.get("ref")]
                pts.append(list(lonlat_to_mc(lon, lat)))
        if len(pts) >= 2:
            out.append(pts)
    return out


def main():
    geojson = Path(sys.argv[1])
    osm = Path(sys.argv[2])
    out_path = Path(sys.argv[3])
    group = sys.argv[4] if len(sys.argv) > 4 else "信息北楼"
    targets = dict(DEFAULT_TARGETS)
    if len(sys.argv) > 5:
        targets.update(json.loads(Path(sys.argv[5]).read_text(encoding="utf-8")))
    fps = footprints_from_geojson(geojson)
    print("footprints:")
    for fp in fps:
        xs = [p[0] for p in fp["polygon"]]
        zs = [p[1] for p in fp["polygon"]]
        print(f"  {fp['name']}: X{min(xs)}-{max(xs)} Z{min(zs)}-{max(zs)} ring={fp['polygon']}")
    highways = highways_from_osm(osm)
    print(f"highways: {len(highways)} polylines")
    paving = derive_paving(fps, highways, group)
    print("paving:")
    for p in paving:
        pts = p.get("cells", [])
        xs = [pt[0] for pt in pts]
        zs = [pt[1] for pt in pts]
        print(f"  {p['name']}: X{min(xs)}-{max(xs)} Z{min(zs)}-{max(zs)} cells={len(pts)}")
    roofs = []
    for fp in fps:
        part = fp["name"]
        target = targets.get(part)
        if target is None:
            print(f"WARNING: no roof target for part {part!r}, skipping roof rule")
            continue
        roofs.append({"name": f"{group}·{part}", "polygon": fp["polygon"],
                      "target": target})
    plan = {"roofs": roofs, "paving": paving,
            "footprints": [{"name": fp["name"], "polygon": fp["polygon"]} for fp in fps],
            "roof_basis": "per-part dominant sensible roof block from measured "
                          "counts in the current world; wool/polished-stone speckles "
                          "are Arnis palette noise, stone_bricks/quartz edge trim and "
                          "glass are kept by finish_world.py"}
    out_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
