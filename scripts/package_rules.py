"""Package the verified, rule-generated Minecraft Java map."""

import gzip
from pathlib import Path
import shutil
from zipfile import ZIP_DEFLATED, ZipFile

from PIL import Image
from rules_preview import nbt


HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[1]
SOURCE = HERE / "java-rules-sentinel" / "Arnis World 1"
FOLDER = "OUC-West-Coast-RuleBased"
LABEL = "中国海洋大学西海岸校区（规则生成版）"
ARCHIVE_NAME = "OUC-West-Coast-Java-RuleBased.zip"
PREVIEW_NAME = "OUC-West-Coast-RuleBased-Preview.png"

README = """中国海洋大学西海岸校区 · Minecraft Java 规则生成版

导入
将 OUC-West-Coast-RuleBased 文件夹放进当前 Java 实例的 saves 目录。
Windows 官方启动器默认存档目录为 %APPDATA%\\.minecraft\\saves。
用 Java 1.21.4 打开单人游戏，选「中国海洋大学西海岸校区（规则生成版）」。
从浩海广场附近的出生点出发，默认是创造模式。

地图范围
东区、西区和东侧海岸，2093 × 996 格，约 1 米等于 1 格。
地图设定以公开数据快照为准，较新的楼、支路和绿化设施可能没有轮廓。
OpenStreetMap 校区边界内的 32 个建筑轮廓含部分楼翼。
学习综合体、海德楼和信息北楼使用了公开资料中的高度或层数信息。
学习综合体主楼的 7 层是校方资料可证的下限，本次按单个外轮廓近似。
信息北楼的主楼和低楼翼按公开设计资料及现有轮廓近似对应。
其余楼高和外观按 Arnis 规则生成。卫星影像提供约 10 米级的地表粗分，灰色区域也可能是裸地。

生成方法
Arnis 3.5.0 离线转换。OSM 地物和海岸线直接转为方块。
地形采用 Mapterhorn 的 Copernicus 约 30 米级高程，插值到方块网格。
两期 Sentinel-2 L2A 的 B04 和 B08 波段通过固定的 NDVI 和反射率阈值区分地表。
建筑轮廓、道路与海岸以 OSM 为准。植被、屋面与墙面按固定程序生成。

来源
© OpenStreetMap contributors（Open Database License）
https://www.openstreetmap.org/copyright
https://www.openstreetmap.org/relation/15505849

Mapterhorn
https://mapterhorn.com/attribution/
Produced using Copernicus WorldDEM-30 © DLR e.V. 2010–2014 and © Airbus Defence and Space GmbH 2014–2018, provided under COPERNICUS by the European Union and ESA. All rights reserved.

Contains modified Copernicus Sentinel data (2026), via Element 84 Earth Search.
S2B_50SQE_20261007_0_L2A and S2A_50SQE_20260904_0_L2A
https://dataspace.copernicus.eu/data-collections/copernicus-sentinel-missions/sentinel-2
https://github.com/Element84/earth-search

学习综合体公开资料
https://news.ouc.edu.cn/2022/0921/c309a110263/page.htm

海德楼公开勘察资料
https://xhaxq.ouc.edu.cn/2023/0423/c10568a430289/page.htm

信息北楼公开招标设计资料
https://ggzy.qingdao.gov.cn/c/TradeDetals-ZtbShow/131630-5021-0-0-0/b47027c3-f0de-412d-81fa-a6f30b00c0aa-B03CE5B6FC1D2D3C2D5FCEBC39AA2406.html

Arnis 工具许可与来源
https://github.com/louis-e/arnis/blob/v3.5.0/NOTICE
"""


def rename_world(source=SOURCE, label=LABEL):
    level = gzip.decompress((source / "level.dat").read_bytes())
    old = nbt(level)["Data"]["LevelName"].encode()
    new = label.encode()
    tag = b"\x08\x00\x09LevelName"
    old_tag = tag + len(old).to_bytes(2, "big") + old
    new_tag = tag + len(new).to_bytes(2, "big") + new
    assert level.count(old_tag) == 1
    renamed = level.replace(old_tag, new_tag, 1)
    assert nbt(renamed)["Data"]["LevelName"] == label
    return gzip.compress(renamed, mtime=0)


def main():
    outputs = WORKSPACE / "outputs"
    archive_path = HERE / ARCHIVE_NAME
    with ZipFile(archive_path, "w", compression=ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(SOURCE.rglob("*")):
            if path.is_file() and path.name not in ("arnis_world_map.png", "level.dat"):
                archive.write(path, (Path(FOLDER) / path.relative_to(SOURCE)).as_posix())
        archive.writestr(FOLDER + "/level.dat", rename_world())
        archive.writestr(FOLDER + "/Readme.txt", README.encode("utf-8-sig"))

    with ZipFile(archive_path) as archive:
        assert archive.testzip() is None
        assert len(archive.namelist()) == len(set(archive.namelist()))
        for path in (SOURCE / "region").glob("*.mca"):
            assert archive.read(FOLDER + "/region/" + path.name) == path.read_bytes()
        assert sum(entry.endswith(".mca") for entry in archive.namelist()) == 10
        level = nbt(gzip.decompress(archive.read(FOLDER + "/level.dat")))["Data"]
        assert level["LevelName"] == LABEL and level["Version"]["Name"] == "1.21.4"
        assert level["GameType"] == 1 and (level["SpawnX"], level["SpawnZ"]) == (1361, 711)
        assert "Sentinel" in archive.read(FOLDER + "/Readme.txt").decode("utf-8-sig")
    preview_path = HERE / "rules-oblique.png"
    with Image.open(preview_path) as preview:
        assert preview.size == (1688, 943)
        preview.verify()
    shutil.copyfile(archive_path, outputs / ARCHIVE_NAME)
    shutil.copyfile(preview_path, outputs / PREVIEW_NAME)
    print(ARCHIVE_NAME, archive_path.stat().st_size, "bytes")
    print(PREVIEW_NAME, preview_path.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
