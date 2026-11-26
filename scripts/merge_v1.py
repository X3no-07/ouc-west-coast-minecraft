"""Build v1: merge InfoNorth-Sample + AlignedRevision into OUC-West-Coast-v1.

Comparison (compare_v1.py) found ZERO differing cells between the two
worlds inside the whole Info North box (X1018-1098, Z536-611, all Y,
2,363,904 cells): same three aligned footprints, same three roof colours,
same 25 courtyard stone bricks, same walkways.  The wide ring diff (117
cells) sits only at Z=520 / X=1117, i.e. other buildings that the sample
never aligned - exactly why the full version is the base.  So the merge
is a straight copy of AlignedRevision, renamed; nothing is overlaid.

This script stages the copy, renames it in level.dat, and zips it.
install_v1.py then installs the ZIP into PCL saves (with old-world hash
checks, same pattern as install_aligned_revision.py).
"""
import hashlib
import shutil
import time
import zipfile
from pathlib import Path

import nbtlib

WORK = Path(r"C:\Users\lenovo\Documents\Codex\2026-11-25\wo\work\ouc-campus")
SAVES = Path(r"C:\Users\lenovo\Desktop\Games\.minecraft\versions\26.2-Fabric 0.19.3\saves")
OUT = Path(r"C:\Users\lenovo\Documents\Codex\2026-11-25\wo\outputs")
SRC = SAVES / "OUC-West-Coast-AlignedRevision"
FOLDER = "OUC-West-Coast-v1"
NEW_NAME = "中国海洋大学西海岸校区v1"

STAGING = WORK / "staging-v1" / FOLDER
ARCHIVE = OUT / "OUC-West-Coast-v1.zip"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    assert SRC.is_dir(), SRC
    assert not (SAVES / FOLDER).exists(), "v1 already installed"
    if STAGING.parent.exists():
        shutil.rmtree(STAGING.parent)
    # 1. copy the full version (skip the stale LastPlayed backup)
    shutil.copytree(SRC, STAGING, ignore=shutil.ignore_patterns("level.dat.bak-lastplayed"))
    level = STAGING / "level.dat"
    # 2. back up level.dat, then rename + refresh LastPlayed
    shutil.copyfile(level, STAGING / "level.dat.bak-v1")
    f = nbtlib.load(str(level))
    d = f["Data"]
    old_name = str(d["LevelName"])
    print("old LevelName:", old_name)
    print("spawn:", int(d["SpawnX"]), int(d["SpawnY"]), int(d["SpawnZ"]),
          "GameType:", int(d["GameType"]), "allowCommands:", int(d["allowCommands"]),
          "DataVersion:", int(d["DataVersion"]))
    assert int(d["SpawnX"]) == 1361 and int(d["SpawnZ"]) == 711
    assert int(d["GameType"]) == 1 and int(d["allowCommands"]) == 1
    assert int(d["DataVersion"]) == 4189
    now_ms = int(time.time() * 1000)
    d["LevelName"] = nbtlib.String(NEW_NAME)
    d["LastPlayed"] = nbtlib.Long(now_ms)
    f.save(str(level))
    chk = nbtlib.load(str(level))["Data"]
    assert str(chk["LevelName"]) == NEW_NAME
    assert int(chk["LastPlayed"]) == now_ms
    assert int(chk["SpawnX"]) == 1361 and int(chk["SpawnZ"]) == 711
    print("new LevelName:", str(chk["LevelName"]), "LastPlayed:", now_ms)
    # 3. Readme header
    readme = STAGING / "Readme.txt"
    text = readme.read_text(encoding="utf-8", errors="ignore")
    header = ("中国海洋大学西海岸校区v1\n"
              "========================\n"
              "v1 由“信息北楼小样”和“对齐修订版”合并而成。逐格比对证实两世界在信息北楼范围\n"
              "（X1018-1098, Z536-611, 全部 Y, 2,363,904 格）完全一致，因此 v1 直接采用对齐修订版\n"
              "的全部内容，只改了世界名。出生点、创造模式、允许命令不变。\n\n")
    readme.write_text(header + text, encoding="utf-8")
    # 4. zip
    files = sorted(p for p in STAGING.rglob("*") if p.is_file())
    mca = [p for p in files if p.suffix == ".mca"]
    print(f"staging files: {len(files)}, region files: {len(mca)}")
    assert len(mca) == 10
    if ARCHIVE.exists():
        ARCHIVE.unlink()
    with zipfile.ZipFile(ARCHIVE, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files:
            z.write(p, FOLDER + "/" + p.relative_to(STAGING).as_posix())
    print("archive:", ARCHIVE, ARCHIVE.stat().st_size, "bytes")
    print("level.dat SHA256:", digest(level.read_bytes()))
    print("done.")


if __name__ == "__main__":
    main()
