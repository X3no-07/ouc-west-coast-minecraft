#!/usr/bin/env python3
"""v3: compare OSM buildings in the BBOX against plan-v2.json footprints.

Finds OSM buildings that are NOT in the v2 plan (candidates to add) and
plan footprints with no matching OSM building.  Also lists OSM highways
(for the road repave) and pitches.

MC conversion (v2): X=(lon-120.01335)/0.0232*2092 ; Z=(1-(lat-35.77065)/0.00895)*995
BBOX=(35.77065,120.01335,35.77960,120.03655)
"""
import json
import math
import sys
import xml.etree.ElementTree as ET

OSM = "/home/hatch/workspace/minecraft-ouc/osm-area-aligned-v2.xml"
PLAN = "/home/hatch/workspace/minecraft-ouc/plan-v2.json"

BBOX = (35.77065, 120.01335, 35.77960, 120.03655)
LON0, LAT0 = 120.01335, 35.77065
DLON, DLAT = 0.0232, 0.00895


def to_mc(lon, lat):
    return ((lon - LON0) / DLON * 2092, (1 - (lat - LAT0) / DLAT) * 995)


def poly_area(poly):
    a = 0.0
    for (x1, z1), (x2, z2) in zip(poly, poly[1:] + poly[:1]):
        a += x1 * z2 - x2 * z1
    return abs(a) / 2.0


def point_in_poly(x, z, poly):
    inside = False
    n = len(poly)
    for i in range(n):
        x1, z1 = poly[i]
        x2, z2 = poly[(i + 1) % n]
        if (z1 > z) != (z2 > z):
            xi = (x2 - x1) * (z - z1) / (z2 - z1) + x1
            if x < xi:
                inside = not inside
    return inside


def poly_centroid(poly):
    return (sum(p[0] for p in poly) / len(poly),
            sum(p[1] for p in poly) / len(poly))


tree = ET.parse(OSM)
root = tree.getroot()
nodes = {}
for nd in root.findall("node"):
    nodes[int(nd.get("id"))] = (float(nd.get("lon")), float(nd.get("lat")))

ways = []
for w in root.findall("way"):
    tags = {t.get("k"): t.get("v") for t in w.findall("tag")}
    refs = [int(n.get("ref")) for n in w.findall("nd")]
    pts = [nodes[r] for r in refs if r in nodes]
    if len(pts) < 2:
        continue
    ways.append({"id": int(w.get("id")), "tags": tags, "pts": pts})

plan = json.load(open(PLAN))
plan_footprints = plan["footprints"]

def mc_poly(pts):
    return [to_mc(lon, lat) for lon, lat in pts]

# --- buildings ---------------------------------------------------------
buildings = [w for w in ways if "building" in w["tags"] or "building:part" in w["tags"]]
print(f"OSM building ways in file: {len(buildings)}")

missing = []
matched = []
for b in buildings:
    poly = mc_poly(b["pts"])
    if len(poly) < 3:
        continue
    cx, cz = poly_centroid(poly)
    xs = [p[0] for p in poly]; zs = [p[1] for p in poly]
    # overlap: fraction of polygon vertices inside any plan footprint
    hits = 0
    for (x, z) in poly:
        for fp in plan_footprints:
            if point_in_poly(x, z, fp["polygon"]):
                hits += 1
                break
    frac = hits / len(poly)
    rec = {
        "id": b["id"],
        "tags": {k: v for k, v in b["tags"].items() if k in
                 ("building", "building:part", "name", "building:levels",
                  "height", "building:levels:underground", "roof:shape",
                  "building:material", "addr:housenumber")},
        "mc_bbox": [round(min(xs)), round(min(zs)), round(max(xs)), round(max(zs))],
        "mc_center": [round(cx), round(cz)],
        "area_cells": round(poly_area(poly)),
        "overlap_frac": round(frac, 2),
    }
    if frac < 0.3:
        missing.append(rec)
    else:
        matched.append(rec)

print(f"\nmatched by plan footprint (>=0.3 overlap): {len(matched)}")
print(f"MISSING from plan (<0.3 overlap): {len(missing)}")
for m in sorted(missing, key=lambda r: -r["area_cells"]):
    print(json.dumps(m, ensure_ascii=False))

# plan footprints with no OSM building at all
print("\nplan footprints with no OSM building centroid inside:")
for fp in plan_footprints:
    cx, cz = poly_centroid(fp["polygon"])
    found = False
    for b in buildings:
        poly = mc_poly(b["pts"])
        if len(poly) >= 3 and point_in_poly(cx, cz, poly):
            found = True
            break
    if not found:
        print("  ", fp["name"], "center", round(cx), round(cz))

# --- highways ----------------------------------------------------------
print("\nOSM highways (for road repave):")
hw = [w for w in ways if "highway" in w["tags"]]
from collections import Counter
print(Counter(w["tags"]["highway"] for w in hw))
for w in hw:
    poly = mc_poly(w["pts"])
    xs = [p[0] for p in poly]; zs = [p[1] for p in poly]
    print(f"  {w['id']} {w['tags'].get('highway')} name={w['tags'].get('name')} "
          f"bbox=({round(min(xs))},{round(min(zs))})-({round(max(xs))},{round(max(zs))}) "
          f"pts={len(poly)} width={w['tags'].get('width')} surface={w['tags'].get('surface')}")

# --- pitches -----------------------------------------------------------
print("\nOSM pitches:")
for w in ways:
    if w["tags"].get("leisure") == "pitch" or "sport" in w["tags"]:
        poly = mc_poly(w["pts"])
        xs = [p[0] for p in poly]; zs = [p[1] for p in poly]
        print(f"  {w['id']} sport={w['tags'].get('sport')} leisure={w['tags'].get('leisure')} "
              f"bbox=({round(min(xs))},{round(min(zs))})-({round(max(xs))},{round(max(zs))})")

json.dump({"missing_buildings": missing, "matched_count": len(matched)},
          open("/home/hatch/workspace/minecraft-ouc/v3-osm-missing.json", "w"),
          ensure_ascii=False, indent=1)
print("\nwrote v3-osm-missing.json")
