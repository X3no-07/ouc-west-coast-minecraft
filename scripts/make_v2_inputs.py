"""Build v2 inputs from v1 inputs (additive edits only, v1 files untouched).

Edits (all labelled with their basis; see v2-changes.json):
1. info-north: name -> "信息北楼（原电子信息楼）" + note (sources 3, 4).
2. learning: 主楼 += 创想之舟 epaper URL + 立面文字 note (source 6).
3. haide/wisdom: note + laitimes URL (source 1; 2024 planning, NOT as-built).
4. dorms: 望海苑二期宿舍 x3 + 西区二期食堂: building:colour yellow + note
   (source 1 west dorms; correspondence inferred, marked 估算).
5. osm-area-aligned-v2.xml: ways 1524352139/1524352140 name ->
   "信息南楼（原计算机楼）" (sources 3, 4).
"""
import copy
import json
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
LAITIMES = "https://www.laitimes.com/en/article/6jvys_7089g.html"
EPAPER = "https://epaper.guanhai.com.cn/conpaper/qdrb/resfile/2022-03-24/04/2022032404_pdf.pdf"

CHANGES = []


def load_geo(name):
    return json.loads((HERE / name).read_text(encoding="utf-8-sig"))


def save_geo(name, data):
    (HERE / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
    print("wrote", name)


def edit_info_north(src, dst):
    d = load_geo(src)
    for ft in d["features"]:
        p = ft["properties"]
        assert p["name"] == "信息北楼", p
        p["name"] = "信息北楼（原电子信息楼）"
        p["note"] = ("原名电子信息楼：2020-04-21 封顶报道（校区首个封顶单体，1.8亿元、"
                     "24500㎡，预计2021年竣工）与 2019-09-16 一期单体介绍"
                     "（文化谷以北、学习综合体西北，同济设计）。几何保持 v1 的 OSM 轮廓；"
                     "屋顶/外墙/开窗无照片来源，全部标估算。")
    save_geo(dst, d)
    CHANGES.append("info-north: name -> 信息北楼（原电子信息楼）, note added (sources 3, 4); geometry unchanged")


def edit_learning(src, dst):
    d = load_geo(src)
    for ft in d["features"]:
        p = ft["properties"]
        if p["name"] == "学习综合体·图书馆主楼":
            urls = p.setdefault("source_urls", [])
            if EPAPER not in urls:
                urls.append(EPAPER)
            p["note"] = ("立面文字参考（青岛日报 2022-03-24《学习综合体“创想之舟”》报道摘要）："
                         "约10万㎡，立面竖向线条，两侧体量如排列整齐的书本、中间如徐徐打开的书卷；"
                         "“创想之舟”以深海科考船为原型，1065吨拉索悬浮钢结构，20根承重索、"
                         "6个混凝土筒体，船体由3个连廊与主体6、7层相连。仅文字引用，未按立面图定过窗带；"
                         "层数以本文件 building:levels 为准（主楼8层、西侧两翼各5层、东侧低区各4层、"
                         "连廊2层）；“两翼各5层”不成立，东侧低区为4层。")
    save_geo(dst, d)
    CHANGES.append("learning: 主楼 += 创想之舟 epaper URL + 立面文字 note (source 6); floors per v3 data (8/5/5/4/4/2); geometry unchanged")


def edit_haide(src, dst):
    d = load_geo(src)
    for ft in d["features"]:
        p = ft["properties"]
        if p["name"] == "海德楼":
            p["note"] = ("2024-04-13 二期四项目规划批前公告报道（规划方案，非建成记录）："
                         "海德学院楼位于融合路西、大学十一路北，40897㎡，现代风格。"
                         "位置与用地按该报道文字，几何保持 v1。")
            urls = p.setdefault("source_urls", [])
            if LAITIMES not in urls:
                urls.append(LAITIMES)
        elif p["name"] == "智慧海洋楼":
            p["note"] = ("2024-04-13 二期四项目规划批前公告报道（规划方案，非建成记录）："
                         "智慧海洋楼位于融合路东、大学十一路北，63426㎡，与海德风格相同。"
                         "位置与用地按该报道文字，几何保持 v1。")
            urls = p.setdefault("source_urls", [])
            if LAITIMES not in urls:
                urls.append(LAITIMES)
    save_geo(dst, d)
    CHANGES.append("haide-wisdom: 海德楼/智慧海洋楼 += 2024规划 note + laitimes URL (source 1, planning not as-built); geometry unchanged")


WEST_DORM_RED = ["望海苑二期宿舍（西）", "望海苑二期宿舍（中）",
                 "望海苑二期宿舍（东）", "西区二期食堂"]


def edit_dorms(src, dst):
    d = load_geo(src)
    for ft in d["features"]:
        p = ft["properties"]
        if p["name"] in WEST_DORM_RED:
            p["building:colour"] = "#E3C878"
            p["note"] = ("2024-04-13 规划报道中的西区学生宿舍及食堂（高峪路北、拥军路西，"
                         "23428㎡，欧式风格、红瓦黄墙）：按路名方位与建设批次推断对应本组二期宿舍与食堂，"
                         "未经官方逐栋对应，标估算。红瓦以 finish 红陶土统一（plan-v2.json）；"
                         "黄墙以 building:colour 交 Arnis 渲染，须实测复核。")
    save_geo(dst, d)
    CHANGES.append("dorms: 望海苑二期宿舍x3 + 西区二期食堂 += building:colour #E3C878 (黄墙) + note (source 1; correspondence inferred, 估算); shape unchanged")


def edit_osm(src, dst):
    tree = ET.parse(HERE / src)
    root = tree.getroot()
    done = []
    for way in root.findall("way"):
        if way.get("id") in ("1524352139", "1524352140"):
            for tag in way.findall("tag"):
                if tag.get("k") == "name":
                    assert tag.get("v") == "信息南楼", tag.get("v")
                    tag.set("v", "信息南楼（原计算机楼）")
                    done.append(way.get("id"))
    assert sorted(done) == ["1524352139", "1524352140"], done
    tree.write(HERE / dst, encoding="utf-8", xml_declaration=True)
    print("wrote", dst)
    CHANGES.append("osm-aligned-v2: ways 1524352139/1524352140 name -> 信息南楼（原计算机楼） (sources 3, 4); geometry unchanged")


def main():
    edit_info_north("v3-info-north-aligned.geojson", "v2-info-north-aligned.geojson")
    edit_info_north("v3-info-north.geojson", "v2-info-north.geojson")
    edit_learning("v3-learning-aligned.geojson", "v2-learning-aligned.geojson")
    edit_learning("v3-learning.geojson", "v2-learning.geojson")
    edit_haide("v3-haide-wisdom-aligned.geojson", "v2-haide-wisdom-aligned.geojson")
    edit_haide("v3-haide-wisdom.geojson", "v2-haide-wisdom.geojson")
    edit_dorms("v3-dorms-aligned.geojson", "v2-dorms-aligned.geojson")
    edit_dorms("v3-dorms.geojson", "v2-dorms.geojson")
    edit_osm("osm-area-aligned.xml", "osm-area-aligned-v2.xml")
    manifest = {"changes": CHANGES}
    (HERE / "v2-changes.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("v2-changes.json written")
    print("\n".join("- " + c for c in CHANGES))


if __name__ == "__main__":
    main()
