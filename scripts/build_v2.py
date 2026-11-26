"""Generate the v2 full-school revision: v1 contents + v2 changes.
See align_all.py, make_osm_aligned.py, make_full_plan_v2.py,
finish_world.py, build_v2_gate.py.

v2 changes (all labelled 实测/估算 in the README appendix):
- info-north renamed 信息北楼（原电子信息楼）, info-south renamed
  信息南楼（原计算机楼） (sources 3, 4); geometry unchanged.
- learning complex: 立面文字引用 only (source 6); floors per v3 data.
- west phase-2 dorms + canteen: red-tile roofs (finish override) +
  yellow walls via building:colour (source 1, correspondence inferred).
- east gate: 7-block stone-brick portal at the 浩海广场 east road /
  海军路 junction (user-provided height, no official source; 估算）.
- BBOX unchanged (south-zone total-plan registration failed, 294-699m).
- Paving unchanged (no usable DXF plaza/courtyard polygons; report 9.5)."""

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


INPUTS = ("v2-learning-aligned.geojson", "v2-haide-wisdom-aligned.geojson",
          "v2-dorms-aligned.geojson", "v2-info-north-aligned.geojson")
SAVE_NAME = "OUC-West-Coast-v2"
LEVEL_NAME = "中国海洋大学西海岸校区v2"
ARCHIVE_NAME = "OUC-West-Coast-Java-v2.zip"
PREVIEW_NAME = "OUC-West-Coast-v2-Preview.png"
FINISH_PLAN = WORK / "plan-v2.json"
OSM_ALIGNED = WORK / "osm-area-aligned-v2.xml"
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


def revised_osm(path, features, osm_source=None):
    tree = prepare_osm(path, source=osm_source)
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
    notes.append("")
    notes.extend(V2_NOTES.splitlines())
    return "\n".join(notes) + "\n"


V2_NOTES = """## v2 改动（2026-11-26/27）

v2 = v1 内容 + 以下改动。几何（轮廓、位置）除东门外全部保持 v1；BBOX、出生点、
创造模式、允许命令与 v1 一致。

### v2 资料来源清单（每个来源：是什么 / 日期 / 用来定了什么 / 实测或估算）

1. 二期四项目规划批前公告报道（来时网转载，2024-04-13）：
   https://www.laitimes.com/en/article/6jvys_7089g.html
   用来定：东区学生宿舍（三沙路东、里岛路南，45270㎡，山海通廊、现代简约）、
   西区学生宿舍及食堂（高峪路北、拥军路西，23428㎡，欧式风格、红瓦黄墙）、
   海德学院楼（融合路西、大学十一路北，40897㎡，现代）、智慧海洋楼（融合路东、
   大学十一路北，63426㎡，与海德风格相同）。性质：2024 年 4 月规划方案效果图与
   总平面图，不是建成记录——海德/智慧海洋楼与西区宿舍均已按此注明；调研员只读了
   页面文字，没看到图本身。
2. 校方百年校庆长文（2024-10-26）：
   https://news.ouc.edu.cn/2024/1026/c486a117677/page.htm
   用来定：校区在三沙路 1299 号，规划约 2800 亩、总建筑面积约 185 万㎡；边界北起
   里岛路、南至宅科路、西起山川路、东至海军路；2022 年 9 月一期清单（学习综合体、
   电子信息楼、计算机楼、工程楼、食工楼、材料楼、西区学生宿舍与食堂、海洋生物资源
   开发中心、教工公寓、东区学生宿舍与食堂）。性质：校方公开报道，实测引用。
3. 电子信息楼封顶报道（青岛日报转载，2020-04-21）：
   https://www.duannianc1.com/content/33224.html
   用来定：信息北楼原名电子信息楼（1.8 亿元、24500㎡，2020 年 4 月 20 日主体封顶，
   校区首个封顶单体，预计 2021 年竣工；计算机楼预计 5 月底封顶）。性质：公开报道，实测引用。
4. 一期单体介绍（中国教育在线，2019-09-16）：
   https://shandong.eol.cn/yuanxiaochuanzhen/201909/t20190916_1683154.shtml
   （仅见搜索摘要，正文打开失败过一次）用来定：计算机楼在三沙路以东、文化谷以南、
   学习综合体西南，24500㎡；电子信息楼在三沙路以东、文化谷以北、学习综合体西北，
   24500㎡；学习综合体 102000㎡；工程楼在三沙路以西核心办学区约 67000㎡；材料楼
   同区约 19700㎡；食工楼约 26300㎡。信息南楼 = 计算机楼、信息北楼 = 电子信息楼
   的对应关系由本条方位（文化谷南北、学习综合体西南/西北）与总图注记方位交叉核对。
   性质：摘要文字引用，正文未读到，标明。
5. 一期启用报道（中国日报网，2022-09-13）：
   https://sd.chinadaily.com.cn/a/202209/13/WS632032eea310817f312edcf6.html
   用来定：2022 年 9 月一期建成启用，5 个学院搬迁、7000 余名师生进驻，一期占地
   700 余亩、校舍约 60 万㎡。性质：公开报道，实测引用。
6. 学习综合体“创想之舟”报道（青岛日报电子版，2022-03-24）：
   https://epaper.guanhai.com.cn/conpaper/qdrb/resfile/2022-03-24/04/2022032404_pdf.pdf
   （仅见搜索摘要）用来定：学习综合体约 10 万㎡，立面竖向线条、两侧体量像排列整齐的
   书本、中间像徐徐打开的书卷；创想之舟以深海科考船为原型，1065 吨拉索悬浮钢结构，
   20 根承重索、6 个混凝土筒体，船体由 3 个连廊与主体 6、7 层相连。仅文字引用，
   未按立面图定过窗带。性质：摘要文字引用。
7. 听海/望海餐厅位置楼层（校方英文网餐饮页，栏目页 2024-06-21）：
   http://eweb.ouc.edu.cn/2024/0621/c892a478603/page.htm
   用来定：听海餐厅在东区，一楼 dining hall、二楼特色餐厅；望海餐厅在西区，
   一楼民族餐厅、二楼海景卡座、三楼教工餐厅。无外观描述。性质：校方页面，实测引用。
8. 在建状态旁证：海德学院楼、智慧海洋楼在 2025 年建筑施工安全生产标准化工地
   学习交流项目名单里（仍在建）；2026-11-20 校方新闻：智慧渔业楼、东区学生宿舍
   及食堂（三期）、工程实训及综合实验中心可行性研究评审会：
   https://news.ouc.edu.cn/2026/1120/c602a123240/page.htm
   用来定：海德/智慧海洋楼“2024 规划、仍在建”的状态注记。性质：公开名单与新闻，实测引用。

### 总图配准结论（2021 总平面图 DXF，见 v2-site-plan-report.txt）

- ODA 转换：ODA 转换：已完成。PC 上 winget 装好 ODA File Converter 27.10.0，DWG 转 DXF 成功（outputs/OUC-West-Coast-2021-Site-Plan.dxf，9,509,509 字节，SHA256 90e59929…f8d）。与 master-plan-2021.dxf 逐项比对：同为 AC1027、110 图层（图层名完全相同）、范围 EXTMIN/EXTMAX 完全相同；LINE、LWPOLYLINE、TEXT、INSERT、CIRCLE/ARC 的几何/文字多重集全部相同（LWPOLYLINE 3153 条零差异、TEXT 647 条零差异、INSERT 714 个零差异）。唯一差别是导出编码：ODA 版多 71 个 ACAD_PROXY_ENTITY（Z-BLDG-ROOF-TEXT 等注记层自定义对象）且无 HATCH 填充（原 DXF 有 19 个），不影响任何建筑轮廓、道路与注记。结论：两文件同源，报告以 DXF 为准的结论成立。
- 分区配准（每区 2-3 栋 DXF 与 OSM 共有楼，EPSG:4549）：东北角（海德楼、
  听海苑 7 号楼）平移拟合 t=(-10.0,-4.8)m 后残差各 7.4m（<15m），但听海苑
  8 号楼残差 71.3m（与报告一致，该栋存疑）；北体育区西偏约 120m、田径场
  西偏约 140m 且北偏约 500m、学习综合体约 150m、信息北楼约 280m、西南宿舍
  组团北偏约 500m（残差 294-699m）。结论：不存在单一全局变换；除东北角两栋
  外无分区通过 <15m，且 v1 楼栋位置以 OSM 现状为准、2021 规划图不作为移楼依据，
  故 v2 未移动任何楼栋位置。DXF 院落/广场边界未逐块提取（报告第 9.5 节），
  故未采用任何 DXF 铺装，铺装全部保持 v1。
- BBOX：保持 v1 的 (35.77065,120.01335,35.77960,120.03655)，2093x996 格。
  不向南扩大：南区各分区配准均未通过（残差 294-699m），且南区 OSM 楼栋
  不能按同一套规则对齐。扩范围的条件：南区拿到实景控制点、分区别分通过
  <15m 残差，且南区 OSM 楼栋能按同一套规则对齐。

### 估算清单（v2 里所有非实测项）

- 东门：高 7 米为用户提供，未找到官方出处，全程标估算；位置取浩海广场东侧
  出校路与海军路交汇处西侧（X1636-1637，Z743-755），OSM 里无东门节点；
  形式为石砖双柱 + 顶梁门洞（柱 2x2、洞宽 9 格、高 7 格），样式为估算。
- 信息北楼/南楼：北楼改名信息北楼（原电子信息楼）、南楼改名信息南楼（原计算机楼）；屋顶、外墙、开窗无照片来源，全部标估算；只改名，不编细节。
- 学习综合体：立面只引用来源 6 的文字，未按立面图定窗带；两翼层数以 v3 数据
  为准（西侧各 5 层、东侧低区各 4 层），不写“各 5 层”。
- 海德楼/智慧海洋楼、西区宿舍及食堂：2024 年规划方案，非建成记录；西区宿舍
  与 2024 规划的逐栋对应为按路名方位与建设批次的推断，未经官方逐栋对应。
- 西区宿舍黄墙：以 building:colour #EAB308 交 Arnis 渲染（淡黄 #E3C878 实测只映射到米白/砂岩系，未出黄色，故改饱和黄色重建），颜色映射须实测复核。
- 工程楼、材料楼、听海餐厅：保持 v1 外观，标估算；位置与面积见来源 4（工程楼
  三沙路以西核心办学区约 67000㎡、材料楼同区约 19700㎡、食工楼约 26300㎡）。

### 未找到的资料（v2 未采用、未编造）

- 2025 年西海岸实景图集；2024 年春季图集（水边木桥、草坡）——水边木桥和草坡
  零证据，v2 不建。
- 学习综合体东西立面图；“中央 8 层、两翼各 5 层”（只有“图书馆 8 层”的未打开
  摘要旁证，两翼 5 层无来源；v2 按 v3 数据：主楼 8 层、西侧两翼 5 层、东侧低区 4 层）。
- 教育部学校规划建设发展中心实景图（工程楼、材料楼、听海餐厅）；东门建成照片；
  “东门高 7 米”的官方出处（7 米这个数字在任何来源里都没出现过，是用户说的）。
- DWG 本体直接解码（见 ODA 结果）；总图南区配准控制点；DXF 院落/广场闭合边界。
"""


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
    tree = revised_osm(inputs, features, osm_source=OSM_ALIGNED)
    world = generate(run, inputs, tree)
    # Deterministic finish pass: roof unification + paving + plinth,
    # scoped to the plan footprints / paving cells only.
    import json as _json
    from finish_world import finish as _finish
    plan = _json.loads(FINISH_PLAN.read_text(encoding="utf-8"))
    finish_report = _finish(world, plan)
    print("Finish pass:", _json.dumps(finish_report, ensure_ascii=False), flush=True)
    from build_v2_gate import place_gate as _place_gate, top_up_red_roofs as _top_up
    gate_report = _place_gate(world)
    print("Gate:", _json.dumps(gate_report, ensure_ascii=False), flush=True)
    finish_report["gate"] = gate_report
    topup_report = _top_up(world, FINISH_PLAN)
    print("Red roof top-up:", _json.dumps(topup_report, ensure_ascii=False), flush=True)
    finish_report["red_roof_top_up"] = topup_report
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
