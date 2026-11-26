"""Build v3-info-north.geojson from the original OSM ways 1524352141-2143.

Properties keep the original levels/height; roof:colour is set to the exact
Arnis palette RGB for red_terracotta, (143,61,47) = #8F3D2F, and NO
roof:material is set: for a flat roof Arnis's tagged_roof_block() then uses
roof_block_for_color(), and an exact palette hit is returned alone
(block_palette.rs pick_for_usage), so the cover is deterministic.
roof:material=concrete would instead random-pick among three blocks.
"""
import json
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
OSM = HERE / "osm-area.xml"
OUT = HERE / "v3-info-north.geojson"

SPECS = {
    "1524352141": {"building:levels": 5, "height": "24", "part": "主楼"},
    "1524352142": {"building:levels": 3, "part": "西翼"},
    "1524352143": {"building:levels": 3, "part": "红顶长翼"},
}
ROOF_COLOUR = "#8F3D2F"  # exact Arnis palette colour for red_terracotta


def main():
    tree = ET.parse(OSM)
    root = tree.getroot()
    nodes = {n.get("id"): (float(n.get("lon")), float(n.get("lat")))
             for n in root.findall("node")}
    features = []
    for wid, spec in SPECS.items():
        way = root.find(f"way[@id='{wid}']")
        assert way is not None, wid
        tags = {t.get("k"): t.get("v") for t in way.findall("tag")}
        assert tags.get("name") == "信息北楼" and tags.get("building"), (wid, tags)
        coords = [nodes[nd.get("ref")] for nd in way.findall("nd")]
        assert coords[0] == coords[-1] and len(coords) == 5, (wid, len(coords))
        props = {
            "name": "信息北楼",
            "source": f"OpenStreetMap way {wid}; 信息北楼公开招标设计资料",
            "source_urls": ["https://www.openstreetmap.org/way/" + wid],
            "building": "university",
            "building:levels": spec["building:levels"],
            "roof:shape": "flat",
            "roof:colour": ROOF_COLOUR,
            "geometry_basis": "OSM 原轮廓，按楼组对齐到游戏 X/Z 网格（见 alignment_angle_deg）",
            "replace_ids": [int(wid)],
            "part": spec["part"],
        }
        if "height" in spec:
            props["height"] = spec["height"]
        features.append({"type": "Feature", "id": "info-north-" + wid,
                         "properties": props,
                         "geometry": {"type": "Polygon", "coordinates": [coords]}})
    data = {"type": "FeatureCollection", "name": "OUC West Coast Info North Building",
            "attribution": "(c) OpenStreetMap contributors, ODbL",
            "features": features}
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUT} ({len(features)} features)")


if __name__ == "__main__":
    main()
