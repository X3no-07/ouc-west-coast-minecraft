"""Prepare task-local map inputs and run Arnis without network inference sources."""

import math
import os
from pathlib import Path
import shutil
import struct
import subprocess
import xml.etree.ElementTree as ET
import zlib

import numpy as np
from PIL import Image, ImageDraw
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import split


WORK = Path(__file__).resolve().parent
BBOX = (35.77065, 120.01335, 35.77960, 120.03655)
CACHE = WORK / "rules-cache"
WORLD_ROOT = WORK / "java-rules-only"
PIXELS_PER_DEGREE = 90_000
TILE_PIXELS = 4096
CONTAINER_PIXELS = 3 * PIXELS_PER_DEGREE
TIFF_PREFIX = "ESA_WorldCover_10m_2021_v200_N33E120_Map"

# Data applied to existing footprints. The library level is a lower bound for
# the main library; the single polygon cannot describe the different wings.
BUILDING_TAGS = {
    "1412220104": ("学习综合体", {"building:levels": "7", "roof:shape": "flat"}),
    "1524352135": ("海德楼", {"building:levels": "5"}),
    "1524352141": ("信息北楼", {"building:levels": "5", "height": "24"}),
    "1524352142": ("信息北楼", {"building:levels": "3"}),
    "1524352143": ("信息北楼", {"building:levels": "3"}),
}

LAND_USE = {
    "forest": 10,
    "orchard": 10,
    "meadow": 30,
    "grass": 30,
    "farmland": 40,
    "farmyard": 50,
    "reservoir": 80,
}
NATURAL = {"wood": 10, "scrub": 20, "grassland": 30, "beach": 60, "water": 80, "wetland": 90}


def tags(element):
    return {tag.attrib["k"]: tag.attrib["v"] for tag in element.findall("tag")}


def prepare_osm(output_path=WORK / "campus-rules.osm", source=None):
    tree = ET.parse(source or WORK / "osm-area.xml")
    ways = {way.attrib["id"]: way for way in tree.findall("way")}
    for identifier, (expected_name, updates) in BUILDING_TAGS.items():
        way = ways[identifier]
        mapped = tags(way)
        if mapped.get("name") != expected_name or not mapped.get("building"):
            raise RuntimeError(f"OSM identity changed for way {identifier}")
        for key, value in updates.items():
            if key not in mapped:
                ET.SubElement(way, "tag", {"k": key, "v": value})
    tree.write(output_path, encoding="utf-8", xml_declaration=True)
    return tree


def mapped_cover(tree):
    nodes = {
        node.attrib["id"]: (float(node.attrib["lon"]), float(node.attrib["lat"]))
        for node in tree.findall("node")
    }
    extent = box(120.011, 35.76925, 120.039, 35.78055)
    land = []
    seas = []
    coastlines = 0
    sea_point = Point(120.038, 35.775)
    for way in tree.findall("way"):
        coordinates = [nodes[ref.attrib["ref"]] for ref in way.findall("nd")]
        feature = tags(way)
        if feature.get("natural") == "coastline":
            water = next((part for part in split(extent, LineString(coordinates)).geoms if part.contains(sea_point)), None)
            if water is not None and 0 < water.area < extent.area:
                seas.append((80, water))
                coastlines += 1
            continue
        if len(coordinates) < 4 or coordinates[0] != coordinates[-1]:
            continue
        value = NATURAL.get(feature.get("natural"), LAND_USE.get(feature.get("landuse")))
        if feature.get("building") not in (None, "no", "construction") or feature.get("amenity") == "parking":
            value = 50
        if value is None:
            continue
        geometry = Polygon(coordinates)
        if not geometry.is_valid:
            geometry = geometry.buffer(0)
        if geometry.intersects(extent):
            land.append((value, geometry.intersection(extent)))
    if coastlines != 1:
        raise RuntimeError(f"Expected one verified coastline, got {coastlines}")
    return sorted(land, key=lambda item: item[0]) + seas


def paint(draw, geometry, value, tx, ty):
    if geometry.is_empty:
        return
    if geometry.geom_type != "Polygon":
        for feature in getattr(geometry, "geoms", ()):
            paint(draw, feature, value, tx, ty)
        return

    def pixel_coords(ring):
        return [
            ((lon - 120.0) * PIXELS_PER_DEGREE - tx * TILE_PIXELS,
             (36.0 - lat) * PIXELS_PER_DEGREE - ty * TILE_PIXELS)
            for lon, lat in ring.coords
        ]

    draw.polygon(pixel_coords(geometry.exterior), fill=value)
    for hole in geometry.interiors:
        draw.polygon(pixel_coords(hole), fill=30)


def write_land_mask(features, cache=CACHE):
    """Supply a synthetic TIFF-layout cache using OSM classes, with no ESA pixels."""
    folder = cache / "arnis-landcover-cache"
    folder.mkdir(parents=True, exist_ok=True)
    side = math.ceil(CONTAINER_PIXELS / TILE_PIXELS)
    offsets = [0] * side**2
    lengths = [0] * side**2
    south, west, north, east = BBOX
    tx0 = int((west - 120.0) * PIXELS_PER_DEGREE) // TILE_PIXELS
    tx1 = int((east - 120.0) * PIXELS_PER_DEGREE) // TILE_PIXELS
    ty0 = int((36.0 - north) * PIXELS_PER_DEGREE) // TILE_PIXELS
    ty1 = int((36.0 - south) * PIXELS_PER_DEGREE) // TILE_PIXELS
    remote_sensing = WORK / "sentinel-surface.npz"
    base_image = None
    if remote_sensing.exists():
        with np.load(remote_sensing) as source:
            left, bottom, right, top = source["bounds"]
            bare = source["stable_low_vegetation"]
        crop_width = round((right - left) * PIXELS_PER_DEGREE)
        crop_height = round((top - bottom) * PIXELS_PER_DEGREE)
        crop_x = round((left - 120.0) * PIXELS_PER_DEGREE)
        crop_y = round((36.0 - top) * PIXELS_PER_DEGREE)
        # Use a 3x3 majority for noisy isolated pixels. Mapped land cover still
        # overwrites this broad vegetation/hardscape classification.
        padded = np.pad(bare, 1, mode="edge")
        support = sum(padded[y:y + bare.shape[0], x:x + bare.shape[1]].astype(np.uint8)
                      for y in range(3) for x in range(3))
        classes = np.where(bare & (support >= 5), 50, 30).astype(np.uint8)
        print(f"Satellite background: {np.count_nonzero(classes == 50):,} stable low-vegetation cells.")
        base_image = Image.fromarray(classes).resize((crop_width, crop_height), Image.Resampling.NEAREST)
    for ty in range(ty0, ty1 + 1):
        for tx in range(tx0, tx1 + 1):
            tile = Image.new("L", (TILE_PIXELS, TILE_PIXELS), 30)
            if base_image is not None:
                tile.paste(base_image, (crop_x - tx * TILE_PIXELS, crop_y - ty * TILE_PIXELS))
            draw = ImageDraw.Draw(tile)
            for value, geometry in features:
                paint(draw, geometry, value, tx, ty)
            payload = zlib.compress(tile.tobytes())
            (folder / f"{TIFF_PREFIX}_tile_{tx}_{ty}.bin").write_bytes(payload)
            index = ty * side + tx
            offsets[index] = 65536
            lengths[index] = len(payload)

    tags_data = [
        (256, 4, 1, CONTAINER_PIXELS), (257, 4, 1, CONTAINER_PIXELS), (259, 3, 1, 8),
        (322, 4, 1, TILE_PIXELS), (323, 4, 1, TILE_PIXELS),
    ]
    arrays_start = 8 + 2 + 7 * 12 + 4
    tags_data.extend([(324, 4, len(offsets), arrays_start), (325, 4, len(lengths), arrays_start + 4 * len(offsets))])
    header = b"II" + struct.pack("<HIH", 42, 8, len(tags_data))
    header += b"".join(struct.pack("<HHII", *entry) for entry in tags_data) + b"\x00" * 4
    header += struct.pack(f"<{len(offsets)}I", *offsets) + struct.pack(f"<{len(lengths)}I", *lengths)
    (folder / f"{TIFF_PREFIX}_header.bin").write_bytes(header)


def main():
    tree = prepare_osm()
    features = mapped_cover(tree)
    write_land_mask(features)
    elevation = Path(os.environ["LOCALAPPDATA"]) / "arnis-tile-cache" / "mapterhorn"
    target = CACHE / "arnis-tile-cache" / "mapterhorn"
    shutil.copytree(elevation, target, dirs_exist_ok=True)
    refined = (WORK / "sentinel-surface.npz").exists()
    output_root = WORK / "java-rules-sentinel" if refined else WORLD_ROOT
    output_root.mkdir(exist_ok=True)
    env = os.environ.copy()
    env["ARNIS_CACHE_ROOT"] = str(CACHE)
    args = [
        str(WORK / "arnis-windows.exe"), "--offline", "--file=campus-rules.osm",
        "--bbox=" + ",".join(str(value) for value in BBOX),
        "--output-dir=" + str(output_root), "--scale=1", "--mode=geo-terrain",
        "--overture=false", "--canopy-height=false", "--legacy-trees", "--no-3d",
        "--spawn-lat=35.77320", "--spawn-lng=120.02845", "--map-preview", "--signage=full",
    ]
    print(f"Prepared {len(features)} mapped surfaces and {len(BUILDING_TAGS)} enriched footprints.", flush=True)
    log = WORK / ("rules-sentinel.log" if refined else "rules.log")
    with log.open("wb") as output:
        subprocess.run(args, cwd=WORK, env=env, stdout=output, stderr=subprocess.STDOUT,
                       creationflags=subprocess.CREATE_NO_WINDOW, check=True)


if __name__ == "__main__":
    main()
