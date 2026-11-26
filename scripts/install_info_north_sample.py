"""Install the verified info-north sample ZIP as a new world in PCL.
Old worlds are hashed before and after; any change aborts."""

import argparse
import hashlib
from pathlib import Path, PurePosixPath
import tempfile
from zipfile import ZipFile


FOLDER = "OUC-West-Coast-InfoNorth-Sample"


def digest(data):
    return hashlib.sha256(data).hexdigest()


OLD_WORLDS = ("OUC-West-Coast-RuleBased", "OUC-West-Coast-LandmarkRevision")


def install(archive_path, saves):
    saves = saves.resolve(strict=True)
    assert saves.is_dir() and saves.name.lower() == "saves", saves
    before = {}
    for old in OLD_WORLDS:
        level = saves / old / "level.dat"
        assert level.is_file(), level
        before[old] = digest(level.read_bytes())
    target = saves / FOLDER
    with ZipFile(archive_path) as archive:
        payload = {}
        for item in archive.infolist():
            path = PurePosixPath(item.filename)
            assert len(path.parts) > 1 and path.parts[0] == FOLDER, path
            assert not path.is_absolute() and not item.is_dir(), path
            assert all(part != ".." and ":" not in part and "\\" not in part for part in path.parts), path
            relative = Path(*path.parts[1:])
            assert relative not in payload, relative
            payload[relative] = archive.read(item)
        assert Path("level.dat") in payload
        assert len([path for path in payload if path.suffix == ".mca"]) == 10

    if not target.exists():
        staging = Path(tempfile.mkdtemp(prefix=".ouc-import-", dir=saves)).resolve()
        assert staging.parent == saves and target.parent == saves
        world = staging / FOLDER
        for relative, data in payload.items():
            file = world / relative
            file.parent.mkdir(parents=True, exist_ok=True)
            with file.open("xb") as output:
                output.write(data)
        verify(world, payload)
        world.rename(target)
        staging.rmdir()

    verify(target, payload)
    for old, hash_before in before.items():
        assert digest((saves / old / "level.dat").read_bytes()) == hash_before, old
    print(f"Installed and verified {len(payload)} files in {target}")
    print(f"level.dat SHA256 {digest((target / 'level.dat').read_bytes())}")
    print("Old worlds untouched: " + ", ".join(before))


def verify(target, payload):
    for relative, data in payload.items():
        assert digest((target / relative).read_bytes()) == digest(data), relative


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("saves", type=Path)
    args = parser.parse_args()
    install(args.archive, args.saves)
