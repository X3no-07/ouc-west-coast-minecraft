"""Build the finish plan for the full-school aligned revision.

Inputs (in this dir): v3-learning-aligned.geojson, v3-haide-wisdom-aligned.geojson,
v3-dorms-aligned.geojson, v3-info-north-aligned.geojson, osm-area-aligned.xml
(for the 6 OSM buildings no v3 feature covers, and for highways).
Output: plan-full.json.

Roofs: one entry per aligned building part, except
  * 图书馆中庭采光顶 (glass roof by design - leave alone), and
  * hipped / roof_tiles dorm roofs (sloped roofs are already deterministic
    in Arnis via nearest_roof_shade - leave alone).
Targets: explicit for the three info-north parts (kept identical to the
sample world); every other roof gets its target auto-picked by finish_world
(most common plausible roof surface at the top layer; wool and polished
blackstone are palette noise and are never picked).
Paving: derived per alignment group (skirt + inter-building yard + walkways
to the nearest OSM road) with the same rules as the sample.
"""
import json
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from align_buildings import lonlat_to_mc  # noqa: E402
from finish_world import cells_in_polygon  # noqa: E402
from make_plan import footprints_from_geojson, highways_from_osm  # noqa: E402
from paving import derive_paving  # noqa: E402

INFO_NORTH_TARGETS = {
    "红顶长翼": "minecraft:red_terracotta",
    "主楼": "minecraft:gray_concrete",
    "西翼": "minecraft:light_gray_concrete",
}
OSM_BUILDINGS = {
    "1524352138": ("未来楼", "未来楼"),
    "1524352139": ("信息南楼", "信息南楼"),
    "1524352140": ("信息南楼", "信息南楼"),
    "1524352144": ("unnamed-144", "unnamed-144"),
    "1524352145": ("unnamed-145", "unnamed-145"),
    "1524352146": ("unnamed-146", "unnamed-146"),
}


def osm_footprints(osm_path):
    tree = ET.parse(osm_path)
    root = tree.getroot()
    nodes = {n.get("id"): (float(n.get("lon")), float(n.get("lat")))
             for n in root.findall("node")}
    out = []
    for way in root.findall("way"):
        wid = way.get("id")
        if wid not in OSM_BUILDINGS:
            continue
        group, name = OSM_BUILDINGS[wid]
        nds = [nd.get("ref") for nd in way.findall("nd")]
        if nds[0] == nds[-1]:
            nds = nds[:-1]
        ring = []
        for ref in nds:
            x, z = lonlat_to_mc(*nodes[ref])
            ring.append([round(x), round(z)])
        clean = []
        for p in ring:
            if not clean or clean[-1] != p:
                clean.append(p)
        out.append({"name": name, "group": group, "polygon": clean,
                    "properties": {"name": name, "way_id": wid}})
    return out


def roof_cells(fp):
    """Exact roof cells for a footprint (outer ring minus any holes)."""
    geom = fp.get("geometry")
    if geom is None:
        return cells_in_polygon(fp["polygon"])
    polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
    cells = set()
    for poly in polys:
        outer = [[round(x), round(z)] for (x, z) in
                 (lonlat_to_mc(lon, lat) for lon, lat in poly[0][:-1])]
        cells.update(cells_in_polygon(outer))
        for hole in poly[1:]:
            inner = [[round(x), round(z)] for (x, z) in
                     (lonlat_to_mc(lon, lat) for lon, lat in hole[:-1])]
            cells.difference_update(cells_in_polygon(inner))
    return sorted(cells)


def main():
    all_fps = []  # each: name, group, polygon, properties
    for src in ("v3-learning-aligned.geojson", "v3-haide-wisdom-aligned.geojson",
                "v3-dorms-aligned.geojson", "v3-info-north-aligned.geojson"):
        fps = footprints_from_geojson(HERE / src)
        for fp in fps:
            fp["group"] = fp["properties"].get("alignment_group") or fp["name"]
            all_fps.append(fp)
    osm_fps = osm_footprints(HERE / "osm-area-aligned.xml")
    all_fps.extend(osm_fps)
    print(f"footprints: {len(all_fps)}")

    highways = highways_from_osm(HERE / "osm-area-aligned.xml")
    print(f"highways: {len(highways)} polylines")

    # Roofs.
    roofs = []
    skipped = []
    for fp in all_fps:
        props = fp["properties"]
        name = props.get("name", fp["name"])
        part = props.get("part") or fp["name"]
        if name == "学习综合体·图书馆中庭采光顶":
            skipped.append((name, "glass roof by design"))
            continue
        if props.get("roof:shape") == "hipped" or props.get("roof:material") == "roof_tiles":
            skipped.append((f"{name}·{part}", "hipped/roof_tiles - already deterministic"))
            continue
        cells = roof_cells(fp) if fp.get("geometry") else cells_in_polygon(fp["polygon"])
        rname = f"{fp['group']}·{part}"
        if fp["properties"].get("way_id"):
            rname += f" ({fp['properties']['way_id']})"
        entry = {"name": rname, "polygon": fp["polygon"],
                 "cells": [list(c) for c in cells]}
        if fp["group"] == "信息北楼" and part in INFO_NORTH_TARGETS:
            entry["target"] = INFO_NORTH_TARGETS[part]
        roofs.append(entry)
    print(f"roofs: {len(roofs)} (skipped: {skipped})")

    # Paving per alignment group.
    by_group = defaultdict(list)
    for fp in all_fps:
        by_group[fp["group"]].append(fp)
    paving = []
    for group, fps in sorted(by_group.items()):
        got = derive_paving(fps, highways, group)
        print(f"paving {group}: {len(got)} entries, "
              f"{sum(len(p.get('cells', [])) for p in got)} cells")
        paving.extend(got)

    plan = {
        "roofs": roofs,
        "paving": paving,
        "footprints": [{"name": fp["name"], "polygon": fp["polygon"]}
                       for fp in all_fps],
        "roof_basis": "info-north targets kept identical to the sample world; "
                      "all other roofs auto-picked by finish_world.py as the "
                      "most common plausible roof surface at the top layer "
                      "(wool / polished blackstone are Arnis palette noise; "
                      "stone_bricks / quartz edge trim and glass are kept)",
    }
    out = HERE / "plan-full.json"
    out.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
