"""Align the in-map OSM buildings that no v3 feature covers, by rotating
their nodes in the OSM file itself (their tags carry no levels/height, so
a GeoJSON replacement would have to invent them; rotating the nodes keeps
Arnis's current height handling exactly as-is).

Ways (all inside the map BBOX; the south-zone buildings are outside the
generated map and are left alone):
  未来楼 1524352138 (singleton, ~6.15deg)
  信息南楼 1524352139+1524352140 (one group, ~7.2deg)
  1524352144 (singleton, ~7.14deg), 1524352145 (singleton, ~0.54deg),
  1524352146 (singleton, ~-0.83deg)
Nodes are not shared between building ways (verified), so rotating one
way's nodes cannot move another building or a road.

Usage: make_osm_aligned.py  (reads osm-area.xml, writes osm-area-aligned.xml)
"""
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from align_buildings import (  # noqa: E402
    align_group, check_axis_aligned, dominant_angle, lonlat_to_mc,
    mc_to_lonlat)

GROUPS = {
    "未来楼": ["1524352138"],
    "信息南楼": ["1524352139", "1524352140"],
    "unnamed-144": ["1524352144"],
    "unnamed-145": ["1524352145"],
    "unnamed-146": ["1524352146"],
}


def main():
    src = HERE / "osm-area.xml"
    tree = ET.parse(src)
    root = tree.getroot()
    nodes = {n.get("id"): n for n in root.iter("node")}
    ways = {w.get("id"): w for w in root.iter("way")}
    # Safety: no node may be used by two different ways in the set.
    use = {}
    for group, ids in GROUPS.items():
        for wid in ids:
            for nd in ways[wid].findall("nd"):
                ref = nd.get("ref")
                if ref in use and use[ref] != wid:
                    raise SystemExit(f"node {ref} shared by {use[ref]} and {wid}")
                use[ref] = wid
    for group, ids in GROUPS.items():
        mc_polys = []
        rings = []
        for wid in ids:
            nds = [nd.get("ref") for nd in ways[wid].findall("nd")]
            if nds[0] == nds[-1]:
                nds = nds[:-1]
            pts = []
            for ref in nds:
                el = nodes[ref]
                pts.append(lonlat_to_mc(float(el.get("lon")), float(el.get("lat"))))
            rings.append((wid, nds, pts))
            mc_polys.append([pts])
        angle = dominant_angle(mc_polys)
        aligned, used_angle, centroid = align_group(mc_polys)
        bad = check_axis_aligned(aligned, group)
        print(f"{group}: angle={used_angle:.3f}deg centroid="
              f"({centroid[0]:.2f},{centroid[1]:.2f}) non_axis={len(bad)}")
        for b in bad:
            print("  NON-AXIS:", b)
        for (wid, nds, _pts), poly in zip(rings, aligned):
            ring = poly[0]
            xs = [p[0] for p in ring]
            zs = [p[1] for p in ring]
            print(f"  {wid}: X{min(xs)}-{max(xs)} Z{min(zs)}-{max(zs)}")
            if len(ring) != len(nds):
                raise SystemExit(f"{wid}: vertex count changed "
                                 f"{len(nds)} -> {len(ring)}")
            for ref, (x, z) in zip(nds, ring):
                lon, lat = mc_to_lonlat(x, z)
                el = nodes[ref]
                el.set("lon", f"{lon:.9f}")
                el.set("lat", f"{lat:.9f}")
    out = HERE / "osm-area-aligned.xml"
    tree.write(out, encoding="utf-8", xml_declaration=True)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
