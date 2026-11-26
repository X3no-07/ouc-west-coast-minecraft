"""Generate the info-north sample: whole campus, only the info-north
building group aligned / paved / roof-unified.  See align_buildings.py,
paving.py and finish_world.py for the rules; this file only wires them
into the existing landmark-revision pipeline."""

import gzip
import itertools
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile

from shapely.geometry import box, shape

from build_rules_only import BBOX, CACHE, WORK, mapped_cover, prepare_osm, tags, write_land_mask
from package_rules import README as BASE_README, rename_world
from rules_preview import nbt, oblique_view, read_world
from validate_mojang import main as validate_vanilla


INPUTS = ("v3-learning.geojson", "v3-haide-wisdom.geojson", "v3-dorms.geojson",
          "v3-info-north-aligned.geojson")
SAVE_NAME = "OUC-West-Coast-InfoNorth-Sample"
LEVEL_NAME = "中国海洋大学西海岸校区（信息北楼小样）"
ARCHIVE_NAME = "OUC-West-Coast-Java-InfoNorth-Sample.zip"
PREVIEW_NAME = "OUC-West-Coast-InfoNorth-Sample-Preview.png"
FINISH_PLAN = WORK / "plan-info-north.json"
TAG_KEYS = {
    "name", "building", "building:levels", "height", "building:material",
    "building:colour", "roof:shape", "roof:material", "roof:colour",
    "roof:height", "building:min_level", "min_height",
}


def load_features():
    south, west, north, east = BBOX
    extent = box(west, south, east, north)
    features = []
    for filename in INPUTS:
        data = json.loads((WORK / filename).read_text(encoding="utf-8-sig"))
        assert data["type"] == "FeatureCollection" and data["features"], filename
        for feature in data["features"]:
            geometry = shape(feature["geometry"])
            properties = feature["properties"]
            assert geometry.geom_type in ("Polygon", "MultiPolygon"), filename
            assert not geometry.is_empty and geometry.is_valid, properties
            assert extent.covers(geometry), (filename, geometry.bounds)
            assert properties["name"] and properties["source"], properties
            assert any(key in properties for key in ("building:levels", "height")), properties
            features.append((geometry, properties))
    return features


def revised_osm(path, features):
    tree = prepare_osm(path)
    root = tree.getroot()
    ways = {way.get("id"): way for way in root.findall("way")}
    relations = {relation.get("id"): relation for relation in root.findall("relation")}
    disabled = set()
    for _, properties in features:
        replace = properties.get("replace_ids", ())
        if isinstance(replace, (int, str)):
            replace = (replace,)
        disabled.update(map(str, replace))
    for key in disabled:
        item = ways.get(key)
        if item is None:
            item = relations[key]
        old_tags = tags(item)
        assert "building" in old_tags or "building:part" in old_tags, (key, old_tags)
        for tag in item.findall("tag"):
            key_name = tag.get("k")
            if key_name != "type":
                item.remove(tag)

    sequence = itertools.count(910_000_000_000)
    node_ids = {}

    def ring_way(ring):
        identifier = str(next(sequence))
        way = ET.Element("way", id=identifier)
        for lon, lat in ring.coords:
            coordinate = f"{lon:.9f}", f"{lat:.9f}"
            node = node_ids.get(coordinate)
            if node is None:
                node = str(next(sequence))
                node_ids[coordinate] = node
                ET.SubElement(root, "node", id=node, lon=coordinate[0], lat=coordinate[1])
            ET.SubElement(way, "nd", ref=node)
        root.append(way)
        return way

    for geometry, properties in features:
        building_tags = {"building": "yes"}
        building_tags.update({key: str(properties[key]) for key in TAG_KEYS & properties.keys()})
        parts = (geometry,) if geometry.geom_type == "Polygon" else geometry.geoms
        for polygon in parts:
            way = ring_way(polygon.exterior)
            target = way
            if polygon.interiors:
                target = ET.Element("relation", id=str(next(sequence)))
                ET.SubElement(target, "member", type="way", ref=way.get("id"), role="outer")
                for hole in polygon.interiors:
                    inner = ring_way(hole)
                    ET.SubElement(target, "member", type="way", ref=inner.get("id"), role="inner")
                ET.SubElement(target, "tag", k="type", v="multipolygon")
                root.append(target)
            for key, value in sorted(building_tags.items()):
                ET.SubElement(target, "tag", k=key, v=value)

    tree.write(path, encoding="utf-8", xml_declaration=True)
    print(f"Added {len(features)} documented building parts, replaced {len(disabled)} original outlines.")
    return tree


def generate(run, inputs, tree):
    cache = run / "cache"
    shutil.copytree(CACHE / "arnis-tile-cache", cache / "arnis-tile-cache")
    write_land_mask(mapped_cover(tree), cache)
    world_root = run / "world"
    world_root.mkdir()
    args = [
        str(WORK / "arnis-windows.exe"), "--offline", f"--file={inputs}",
        "--bbox=" + ",".join(str(value) for value in BBOX),
        f"--output-dir={world_root}", "--scale=1", "--mode=geo-terrain",
        "--overture=false", "--canopy-height=false", "--legacy-trees", "--no-3d",
        "--spawn-lat=35.77320", "--spawn-lng=120.02845", "--map-preview", "--signage=full",
    ]
    with (run / "arnis.log").open("wb") as report:
        subprocess.run(
            args, cwd=run, env={**os.environ, "ARNIS_CACHE_ROOT": str(cache)},
            stdout=report, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW,
            check=True,
        )
    return world_root / "Arnis World 1"


def readme(features):
    notes = [
        "中国海洋大学西海岸校区 · Minecraft Java 建筑细化版",
        "",
        "导入时，把 " + SAVE_NAME + " 文件夹放到对应实例的 saves 目录。",
        f"打开单人游戏，选择「{LEVEL_NAME}」。存档以 Minecraft Java 1.21.4 格式生成。",
        "",
        "以每格约一米的比例按公开轮廓和规划图生成，楼层、材料与屋面只在资料支持的范围内体现。",
        "图纸配准、分段边界、未实测楼高和材质均可能有误差。室内、立面细节和较新的校园设施以简化表达为主。",
        "",
        "本次使用的建筑资料",
    ]
    for name in dict.fromkeys(properties["name"] for _, properties in features):
        records = [properties for _, properties in features if properties["name"] == name]
        levels = sorted({int(item["building:levels"]) for item in records if "building:levels" in item})
        heights = sorted({str(item["height"]) for item in records if "height" in item})
        parameters = [f"{value} 层" for value in levels] + [f"{value} 米" for value in heights]
        notes.append(f"• {name}" + (f"（{' / '.join(parameters)}）" if parameters else ""))
        for item in records:
            notes.extend(dict.fromkeys([
                str(item["source"]),
                *(str(item[key]) for key in ("note", "height_basis", "geometry_basis", "geometry_status", "source_url")
                  if item.get(key)),
                *item.get("source_urls", []),
            ]))
    notes.append("")
    notes.extend(BASE_README[BASE_README.index("来源\n"):].splitlines())
    return "\n".join(notes) + "\n"


def package(run, world, features):
    archive_path = run / ARCHIVE_NAME
    with ZipFile(archive_path, "w", compression=ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(world.rglob("*")):
            if path.is_file() and path.name not in {"arnis_world_map.png", "level.dat", "session.lock"}:
                archive.write(path, (Path(SAVE_NAME) / path.relative_to(world)).as_posix())
        archive.writestr(f"{SAVE_NAME}/level.dat", rename_world(world, LEVEL_NAME))
        archive.writestr(f"{SAVE_NAME}/Readme.txt", readme(features).encode("utf-8-sig"))
    with ZipFile(archive_path) as archive:
        assert archive.testzip() is None
        level = nbt(gzip.decompress(archive.read(f"{SAVE_NAME}/level.dat")))["Data"]
        assert level["Version"]["Name"] == "1.21.4" and level["LevelName"] == LEVEL_NAME
        for path in (world / "region").glob("*.mca"):
            assert archive.read(f"{SAVE_NAME}/region/{path.name}") == path.read_bytes()
    return archive_path


def main():
    features = load_features()
    run = Path(tempfile.mkdtemp(prefix="landmark-revision-", dir=WORK))
    print(f"Building in {run}", flush=True)
    inputs = run / "campus-landmark-revision.osm"
    tree = revised_osm(inputs, features)
    world = generate(run, inputs, tree)
    # Deterministic finish pass: roof unification + paving + plinth,
    # scoped to the info-north footprints / paving polygons only.
    import json as _json
    from finish_world import finish as _finish
    plan = _json.loads(FINISH_PLAN.read_text(encoding="utf-8"))
    finish_report = _finish(world, plan)
    print("Finish pass:", _json.dumps(finish_report, ensure_ascii=False), flush=True)
    (run / "finish-report.json").write_text(
        _json.dumps(finish_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    surface = read_world(world)
    preview = run / PREVIEW_NAME
    oblique_view(world, surface, preview)
    validate_vanilla(world)
    archive = package(run, world, features)
    outputs = WORK.parents[1] / "outputs"
    shutil.copy2(archive, outputs / ARCHIVE_NAME)
    shutil.copy2(preview, outputs / PREVIEW_NAME)
    print(f"Verified archive: {outputs / ARCHIVE_NAME}", flush=True)


if __name__ == "__main__":
    main()
