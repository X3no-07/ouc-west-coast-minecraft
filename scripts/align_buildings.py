"""Align building footprints to the Minecraft X/Z grid, per group.

Pure-python (no shapely required for the core transform; shapely is used
only for optional validity / overlap checks when available).

Method (per group, never one global angle):
  1. Convert lon/lat to Minecraft float coords with the project's local
     linear projection:  X = (lon-west)/(east-west)*2092,
     Z = (1-(lat-south)/(north-south))*995,  BBOX=(35.77065,120.01335,35.77960,120.03655).
  2. Dominant angle = length-weighted circular mean of edge angles mod 90deg.
  3. Rotate every polygon of the group by -angle around the group centroid
     (mean of all vertices).
  4. Orthogonalise: edges that are within ~15deg of an axis get their
     perpendicular coordinate averaged (rounded) across their two ends.
     Genuine diagonals (near 45deg) are left alone.
  5. Round vertices to integer blocks, drop duplicate consecutive vertices.
  6. Convert back to lon/lat at 1e-9 precision for the OSM/GeoJSON input.

The aligned polygons are written as a new GeoJSON that build scripts can
feed to Arnis exactly like the v3 files (same properties, plus
alignment_angle_deg / alignment_group for traceability).
"""
import json
import math
from pathlib import Path

BBOX = (35.77065, 120.01335, 35.77960, 120.03655)  # south, west, north, east
SCALE_X = 2092
SCALE_Z = 995


def lonlat_to_mc(lon, lat):
    south, west, north, east = BBOX
    x = (lon - west) / (east - west) * SCALE_X
    z = (1.0 - (lat - south) / (north - south)) * SCALE_Z
    return (x, z)


def mc_to_lonlat(x, z):
    south, west, north, east = BBOX
    lon = west + (x / SCALE_X) * (east - west)
    lat = south + (1.0 - z / SCALE_Z) * (north - south)
    return (lon, lat)


def dominant_angle(polygons):
    """Length-weighted dominant edge angle mod 90deg, in (-45, 45] degrees.

    Returns 0.0 for an already axis-aligned group.  An angle of e.g. +7.6
    means long edges run 7.6deg below the +X axis (dz positive as x grows).
    """
    sx = sy = 0.0
    for poly in polygons:
        ring = poly[0] if poly else []
        for a, b in zip(ring, ring[1:] + ring[:1]):
            dx, dz = b[0] - a[0], b[1] - a[1]
            length = math.hypot(dx, dz)
            if length < 2.0:
                continue
            m = math.atan2(dz, dx) % (math.pi / 2.0)
            sx += length * math.cos(4 * m)
            sy += length * math.sin(4 * m)
    if sx == 0.0 and sy == 0.0:
        return 0.0
    mean = math.degrees((math.atan2(sy, sx) / 4.0) % (math.pi / 2.0))
    return mean if mean <= 45.0 else mean - 90.0


def _rotate(pt, centre, cos_a, sin_a):
    dx, dz = pt[0] - centre[0], pt[1] - centre[1]
    return (centre[0] + dx * cos_a - dz * sin_a,
            centre[1] + dx * sin_a + dz * cos_a)


def orthogonalise(ring):
    """Snap a rotated ring to integer blocks and force near-axis edges flat.

    ring: list of (x, z) floats (open ring, no repeated closing vertex).
    Returns a list of (int, int).  Edges whose |dx|>=3*|dz| (or vice versa)
    have their perpendicular coordinate averaged across both ends.
    """
    pts = [(round(x), round(z)) for x, z in ring]
    # Drop consecutive duplicates created by rounding.
    cleaned = []
    for p in pts:
        if not cleaned or cleaned[-1] != p:
            cleaned.append(p)
    pts = cleaned
    if len(pts) < 3:
        return pts
    for _ in range(3):
        changed = False
        n = len(pts)
        for i in range(n):
            a = pts[i]
            b = pts[(i + 1) % n]
            dx, dz = b[0] - a[0], b[1] - a[1]
            if abs(dx) >= 3 * max(1, abs(dz)) and dz != 0:
                zm = round((a[1] + b[1]) / 2)
                if a[1] != zm or b[1] != zm:
                    pts[i] = (a[0], zm)
                    pts[(i + 1) % n] = (b[0], zm)
                    changed = True
            elif abs(dz) >= 3 * max(1, abs(dx)) and dx != 0:
                xm = round((a[0] + b[0]) / 2)
                if a[0] != xm or b[0] != xm:
                    pts[i] = (xm, a[1])
                    pts[(i + 1) % n] = (xm, b[1])
                    changed = True
        if not changed:
            break
    # Final duplicate sweep (orthogonalise can merge neighbours).
    cleaned = []
    for p in pts:
        if not cleaned or cleaned[-1] != p:
            cleaned.append(p)
    if len(cleaned) > 1 and cleaned[0] == cleaned[-1]:
        cleaned.pop()
    return cleaned


def _repair_ring(ring):
    """Fix a self-touching ring produced by orthogonalise (a zero-width
    spike or a vertex lying on another edge of the same ring).  Uses
    shapely's buffer(0) when available; area is preserved exactly for
    these axis-aligned degeneracies.  Returns a list of rings: the repaired
    exterior first, then any holes."""
    try:
        from shapely.geometry import Polygon as _Polygon
    except Exception:
        return [ring]
    poly = _Polygon(ring)
    if poly.is_valid:
        return [ring]
    fixed = poly.buffer(0)
    if fixed.is_empty:
        return [ring]
    geoms = list(fixed.geoms) if fixed.geom_type == "MultiPolygon" else [fixed]
    if len(geoms) > 1:
        # Keep the largest part; a split would need a MultiPolygon feature.
        geoms = [max(geoms, key=lambda g: g.area)]
    out = []
    for g in geoms:
        ext = [(int(round(x)), int(round(z))) for (x, z) in g.exterior.coords[:-1]]
        out.append(ext)
        for hole in g.interiors:
            out.append([(int(round(x)), int(round(z))) for (x, z) in hole.coords[:-1]])
    return out


def align_group(polygons_mc, angle_override=None):
    """polygons_mc: list of polygons; each polygon is a list of rings;
    each ring is a list of (x, z) float MC coords (open, unclosed).
    Returns (aligned_polygons_int, angle_deg, centroid).
    angle_override: force this rotation (deg) instead of the dominant angle;
    use 0.0 for buildings whose dominant angle is an artifact of a diagonal
    wing (their axis edges are already flat)."""
    all_pts = [p for poly in polygons_mc for ring in poly for p in ring]
    cx = sum(p[0] for p in all_pts) / len(all_pts)
    cz = sum(p[1] for p in all_pts) / len(all_pts)
    angle = dominant_angle(polygons_mc) if angle_override is None else angle_override
    theta = math.radians(-angle)
    cos_a, sin_a = math.cos(theta), math.sin(theta)
    aligned = []
    for poly in polygons_mc:
        new_poly = []
        for ring in poly:
            rotated = [_rotate(p, (cx, cz), cos_a, sin_a) for p in ring]
            repaired = _repair_ring(orthogonalise(rotated))
            new_poly.extend(repaired)
        aligned.append(new_poly)
    return aligned, angle, (cx, cz)


def check_axis_aligned(polygons_int, name=""):
    """Report edges that should be axis-aligned but are not.

    Returns a list of dicts for edges with length>=4 whose angle is within
    15deg of an axis but which are not exactly horizontal/vertical.
    Genuine diagonals are not reported.
    """
    bad = []
    for poly in polygons_int:
        for ring in poly:
            n = len(ring)
            for i in range(n):
                a, b = ring[i], ring[(i + 1) % n]
                dx, dz = b[0] - a[0], b[1] - a[1]
                length = math.hypot(dx, dz)
                if length < 4:
                    continue
                if dx == 0 or dz == 0:
                    continue
                ang = abs(math.degrees(math.atan2(dz, dx))) % 90.0
                near_axis = min(ang, 90.0 - ang)
                if near_axis <= 15.0:
                    bad.append({"name": name, "a": a, "b": b,
                                "length": round(length, 1),
                                "angle_deg": round(ang, 2)})
    return bad


def rings_from_geojson_geometry(geom):
    """Return polygons as list of list-of-rings, each ring a list of (lon, lat)."""
    if geom["type"] == "Polygon":
        return [geom["coordinates"]]
    if geom["type"] == "MultiPolygon":
        return list(geom["coordinates"])
    raise ValueError(f"unsupported geometry {geom['type']}")


def angle_support(polygons_mc, angle):
    """Fraction of total edge length within 5deg of the dominant angle
    (mod 90).  Below ~0.5 the dominant angle is an artifact of a diagonal
    wing, not the building's real orientation."""
    total = 0.0
    supported = 0.0
    for poly in polygons_mc:
        for ring in poly:
            for a, b in zip(ring, ring[1:] + ring[:1]):
                dx, dz = b[0] - a[0], b[1] - a[1]
                length = math.hypot(dx, dz)
                if length < 2.0:
                    continue
                total += length
                m = math.degrees(math.atan2(dz, dx)) % 90.0
                d = min(abs(m - angle) % 90.0, abs(m - angle - 90.0) % 90.0)
                d = min(d, 90.0 - d)
                if d <= 5.0:
                    supported += length
    return (supported / total) if total else 0.0


def align_feature_collection(features, group_key, angle_overrides=None):
    """features: GeoJSON feature dicts. group_key: feature -> group name.
    angle_overrides: optional {group: angle_deg} forcing a rotation.
    Returns (aligned_features, report dict)."""
    groups = {}
    for feat in features:
        groups.setdefault(group_key(feat), []).append(feat)

    out_features = []
    report = {}
    for group, feats in groups.items():
        # Convert all polygons of the group to MC floats.
        mc_polys = []
        for feat in feats:
            for poly in rings_from_geojson_geometry(feat["geometry"]):
                mc_poly = []
                for ring in poly:
                    mc_poly.append([lonlat_to_mc(lon, lat) for lon, lat in ring[:-1]])
                mc_polys.append(mc_poly)
        override = (angle_overrides or {}).get(group)
        aligned, angle, centroid = align_group(mc_polys, angle_override=override)
        bad = check_axis_aligned(aligned, group)
        rects = []
        for poly in aligned:
            ring = poly[0]
            xs = [p[0] for p in ring]
            zs = [p[1] for p in ring]
            rects.append((min(xs), min(zs), max(xs), max(zs)))
        report[group] = {
            "angle_deg": round(angle, 3),
            "centroid_mc": (round(centroid[0], 2), round(centroid[1], 2)),
            "features": len(feats),
            "rects": rects,
            "non_axis_edges": bad,
        }
        # Write aligned coords back, feature by feature, in the same order.
        pos = 0
        for feat in feats:
            n_poly = len(rings_from_geojson_geometry(feat["geometry"]))
            polys = aligned[pos:pos + n_poly]
            pos += n_poly
            if feat["geometry"]["type"] == "Polygon":
                coords = []
                for ring in polys[0]:
                    ll = [(round(lon, 9), round(lat, 9))
                          for lon, lat in (mc_to_lonlat(x, z) for x, z in ring)]
                    ll.append(ll[0])
                    coords.append(ll)
                geom = {"type": "Polygon", "coordinates": coords}
            else:
                coords_all = []
                for poly in polys:
                    coords = []
                    for ring in poly:
                        ll = [(round(lon, 9), round(lat, 9))
                              for lon, lat in (mc_to_lonlat(x, z) for x, z in ring)]
                        ll.append(ll[0])
                        coords.append(ll)
                    coords_all.append(coords)
                geom = {"type": "MultiPolygon", "coordinates": coords_all}
            props = dict(feat["properties"])
            props["alignment_angle_deg"] = round(angle, 3)
            props["alignment_group"] = group
            out_features.append({"type": "Feature", "id": feat.get("id"),
                                 "properties": props, "geometry": geom})
    return out_features, report


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("input", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--group-by", default="name", choices=["name", "file"])
    args = ap.parse_args()
    data = json.loads(args.input.read_text(encoding="utf-8-sig"))
    feats = data["features"]
    if args.group_by == "name":
        key = lambda f: f["properties"].get("name", "unnamed")
    else:
        key = lambda f: args.input.stem
    aligned, report = align_feature_collection(feats, key)
    for group, info in report.items():
        print(f"{group}: angle={info['angle_deg']}deg centroid={info['centroid_mc']} "
              f"rects={info['rects']} non_axis={info['non_axis_edges']}")
    out = {"type": "FeatureCollection", "name": data.get("name", args.input.stem),
           "features": aligned}
    args.output.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(f"Wrote {args.output} ({len(aligned)} features)")


if __name__ == "__main__":
    main()
