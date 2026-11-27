#!/usr/bin/env python3
"""v3: precompute build data from OSM + plan-v2.json (runs on VM, no world).

Outputs v3-build-data.json:
- roads: deduped in-BBOX highway centerlines with width/material by type
- courts: two basketball areas with computed 28x15 court rects + hoop cells
- info_north: wing rects, roof Y, ground Y
- missing_buildings: 海洋楼 + unnamed 1524718890 polygons (world check at build)
- door_target: the 1358 seam door (wall + fallback scan range)
"""
import json
import math
import xml.etree.ElementTree as ET

OSM = "/home/hatch/workspace/minecraft-ouc/osm-area-aligned-v2.xml"
PLAN = "/home/hatch/workspace/minecraft-ouc/plan-v2.json"
OUT = "/home/hatch/workspace/minecraft-ouc/v3-build-data.json"

LON0, LAT0 = 120.01335, 35.77065
DLON, DLAT = 0.0232, 0.00895
W, H = 2093, 996


def to_mc(lon, lat):
    return ((lon - LON0) / DLON * 2092, (1 - (lat - LAT0) / DLAT) * 995)


tree = ET.parse(OSM)
root = tree.getroot()
nodes = {int(n.get("id")): (float(n.get("lon")), float(n.get("lat")))
         for n in root.findall("node")}
ways = []
for w in root.findall("way"):
    tags = {t.get("k"): t.get("v") for t in w.findall("tag")}
    pts = [nodes[int(n.get("ref"))] for n in w.findall("nd") if int(n.get("ref")) in nodes]
    if len(pts) >= 2:
        ways.append({"id": int(w.get("id")), "tags": tags, "pts": pts})

# ---------------------------------------------------------------- roads
# width (total, incl. 1-block light sidewalk each side) and material by type
ROAD_STYLE = {
    "primary": (9, "black_concrete"),
    "secondary": (7, "black_concrete"),
    "tertiary": (7, "black_concrete"),
    "residential": (5, "black_concrete"),
    "service": (4, "black_concrete"),
    "footway": (3, "light_gray_concrete"),
    "pedestrian": (3, "light_gray_concrete"),
    "path": (2, "light_gray_concrete"),
}

# dedupe dual carriageways: same name + overlapping bbox -> keep longest
hw = [w for w in ways if "highway" in w["tags"] and w["tags"]["highway"] in ROAD_STYLE]
hw_mc = []
for w in hw:
    pts = [to_mc(lon, lat) for lon, lat in w["pts"]]
    # clip to BBOX (keep points inside, plus segment crossings are ignored:
    # endpoints outside are dropped; a road crossing the border loses its tail)
    pts = [(x, z) for (x, z) in pts if -5 <= x <= W + 5 and -5 <= z <= H + 5]
    if len(pts) < 2:
        continue
    xs = [p[0] for p in pts]; zs = [p[1] for p in pts]
    hw_mc.append({"id": w["id"], "type": w["tags"]["highway"],
                  "name": w["tags"].get("name"),
                  "pts": [[round(x), round(z)] for (x, z) in pts],
                  "bbox": [min(xs), min(zs), max(xs), max(zs)],
                  "npts": len(pts)})

kept = []
for h in sorted(hw_mc, key=lambda r: -r["npts"]):
    dup = False
    for k in kept:
        if h["name"] and h["name"] == k["name"] and h["type"] == k["type"]:
            # bbox overlap?
            if not (h["bbox"][2] < k["bbox"][0] or h["bbox"][0] > k["bbox"][2] or
                    h["bbox"][3] < k["bbox"][1] or h["bbox"][1] > k["bbox"][3]):
                dup = True
                break
    if not dup:
        kept.append(h)

roads = []
for h in kept:
    width, mat = ROAD_STYLE[h["type"]]
    roads.append({"id": h["id"], "type": h["type"], "name": h["name"],
                  "width": width, "material": mat,
                  "sidewalk": "light_gray_concrete" if mat == "black_concrete" else None,
                  "pts": h["pts"]})
print(f"roads kept: {len(roads)} (from {len(hw_mc)} in-BBOX highway ways)")

# ---------------------------------------------------------------- courts
def court_layout(bbox, cols, rows, gap=3):
    x0, z0, x1, z1 = bbox
    bw, bh = x1 - x0 + 1, z1 - z0 + 1
    total_w = cols * 28 + (cols - 1) * gap
    total_h = rows * 15 + (rows - 1) * gap
    sx = x0 + max(0, (bw - total_w) // 2)
    sz = z0 + max(0, (bh - total_h) // 2)
    courts = []
    for r in range(rows):
        for c in range(cols):
            cx = sx + c * (28 + gap)
            cz = sz + r * (15 + gap)
            courts.append({"x0": cx, "z0": cz, "x1": cx + 27, "z1": cz + 14,
                           "cx": cx + 14, "cz": cz + 7})
    return courts

courts = [
    {"area": "info-north-basketball", "osm_way": 1524352134,
     "bbox": [1131, 470, 1238, 516],
     "courts": court_layout([1131, 470, 1238, 516], 3, 2)},
    {"area": "west-sports-basketball", "osm_way": 1524718894,
     "bbox": [681, 183, 839, 241],
     "courts": court_layout([681, 183, 839, 241], 4, 2)},
]
for c in courts:
    print(f"court area {c['area']}: {len(c['courts'])} courts")

# ---------------------------------------------------------------- info north
info_north = {
    "long_wing": {"rect": [1018, 540, 1089, 557], "roof_y": -29, "ground_y": -45,
                  "floors": 3, "roof_target": "minecraft:light_gray_concrete"},
    "main": {"rect": [1050, 582, 1098, 611], "roof_y": -20, "ground_y": -45,
             "floors": 5, "roof_target": "minecraft:gray_concrete"},
    "west_wing": {"rect": [1018, 558, 1037, 611], "roof_y": -29, "ground_y": -45,
                  "floors": 3, "roof_target": "minecraft:light_gray_concrete"},
    "courtyard": [1038, 558, 1049, 581],
}

# ---------------------------------------------------------------- missing buildings (world check at build time)
def osm_poly(way_id):
    for w in ways:
        if w["id"] == way_id:
            return [[round(x), round(z)] for (x, z) in
                    (to_mc(lon, lat) for lon, lat in w["pts"])]
    return None

missing_buildings = [
    {"osm_way": 1524352137, "name": "海洋楼",
     "poly": osm_poly(1524352137), "floors_est": 4,
     "note": "OSM building=university; 总图该位置标注综合服务中心；无层数来源，估4层"},
    {"osm_way": 1524718890, "name": "望海餐厅北侧无名楼",
     "poly": osm_poly(1524718890), "floors_est": 2,
     "note": "OSM building=yes 无名；望海餐厅北侧；无层数来源，估2层"},
]

data = {
    "roads": roads,
    "courts": courts,
    "info_north": info_north,
    "missing_buildings": missing_buildings,
    "seam_door": {
        "building": "听海苑2号楼", "wall": "north", "wall_z": 320,
        "scan_x": [1355, 1363], "facing": "north",
        "note": "准星接缝：1号楼西墙(X1363)与2号楼北墙(Z320)交角；门开在2号楼北墙近角处，朝北向玩家/步道",
    },
    "east_gate": {"x": [1636, 1637], "z": [743, 755], "height_blocks": 7,
                  "passage_z": [745, 753], "road_z": 749,
                  "note": "v2结构保留（7米为用户提供，无官方出处，标估算）；只修地面与前后道路"},
    "ground_rubble_center": [944, 694],
}
json.dump(data, open(OUT, "w"), ensure_ascii=False, indent=1)
print("wrote", OUT)
print("missing buildings polys:")
for m in missing_buildings:
    print(" ", m["name"], m["poly"])
