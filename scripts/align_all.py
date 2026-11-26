"""Align all v3 building features for the full-school revision.

Grouping (connected components, split by angle):
  - 学习综合体 (10, connected) -> one group
  - 海德楼 + 海德楼北翼 -> one group
  - 智慧海洋楼 + 东翼 + 东北翼 -> one group
  - 望海苑 / 食堂 / 听海空间 / 听海餐厅: singletons (not connected)
  - 听海苑7+8 (connected, angles 0.71/2.11) -> one group
  - 听海苑4 (singleton), 听海苑5 (forced 0: diagonal-wing artifact),
    听海苑6 (forced 0)
  - 听海苑1+3 (angles 2.97/0.15) -> one group; 听海苑2 (forced 0)
  - 听海苑9 (singleton)
Features whose dominant angle has <50% edge-length support are forced to
angle 0 (their axis edges are already flat; the "angle" is a diagonal wing).

Usage: align_all.py  (reads v3-*.geojson in this dir, writes *-aligned.geojson)
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
import sys
sys.path.insert(0, str(HERE))
from align_buildings import (  # noqa: E402
    align_feature_collection, angle_support, dominant_angle,
    lonlat_to_mc, rings_from_geojson_geometry)

# name -> group; None means singleton under its own name
GROUP_OF = {
    "学习综合体·图书馆中庭采光顶": "学习综合体",
    "学习综合体·图书馆主楼": "学习综合体",
    "学习综合体·北楼（西侧）": "学习综合体",
    "学习综合体·南楼（西侧）": "学习综合体",
    "学习综合体·北楼（东侧低区）": "学习综合体",
    "学习综合体·南楼（东侧低区）": "学习综合体",
    "学习综合体·西北连廊": "学习综合体",
    "学习综合体·东北连廊": "学习综合体",
    "学习综合体·西南连廊": "学习综合体",
    "学习综合体·东南连廊": "学习综合体",
    "海德楼": "海德楼",
    "海德楼北翼": "海德楼",
    "智慧海洋楼": "智慧海洋楼",
    "智慧海洋楼东翼": "智慧海洋楼",
    "智慧海洋楼东北翼": "智慧海洋楼",
    "听海苑7号楼": "听海苑7+8号楼",
    "听海苑8号楼": "听海苑7+8号楼",
    "听海苑1号楼": "听海苑1+3号楼",
    "听海苑3号楼": "听海苑1+3号楼",
}


def feature_mc_polys(feat):
    out = []
    for poly in rings_from_geojson_geometry(feat["geometry"]):
        mc_poly = []
        for ring in poly:
            mc_poly.append([lonlat_to_mc(lon, lat) for lon, lat in ring[:-1]])
        out.append(mc_poly)
    return out


def main():
    overrides = {}
    for src in ("v3-learning.geojson", "v3-haide-wisdom.geojson", "v3-dorms.geojson"):
        data = json.loads((HERE / src).read_text(encoding="utf-8-sig"))
        feats = data["features"]
        # Decide forced-0 features first (per-feature angle support).
        group_of = {}
        for feat in feats:
            name = feat["properties"].get("name", "unnamed")
            polys = feature_mc_polys(feat)
            ang = dominant_angle(polys)
            sup = angle_support(polys, ang)
            print(f"{name}: angle={ang:.2f} support={sup:.2f}")
            if sup < 0.5:
                group_of[name] = f"__fixed0__:{name}"
                overrides[f"__fixed0__:{name}"] = 0.0
                print(f"  -> forced angle 0 (diagonal-wing artifact)")
            else:
                group_of[name] = GROUP_OF.get(name, name)
        aligned, report = align_feature_collection(
            feats, lambda f: group_of[f["properties"].get("name", "unnamed")],
            angle_overrides=overrides)
        out = dict(data)
        out["features"] = aligned
        out_path = HERE / src.replace(".geojson", "-aligned.geojson")
        out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2),
                            encoding="utf-8")
        print(f"Wrote {out_path} ({len(aligned)} features)")
        for group, info in report.items():
            print(f"  {group}: angle={info['angle_deg']}deg "
                  f"centroid={info['centroid_mc']} features={info['features']} "
                  f"non_axis={len(info['non_axis_edges'])} rects={info['rects']}")
            for bad in info["non_axis_edges"]:
                print("    NON-AXIS:", bad)


if __name__ == "__main__":
    main()
