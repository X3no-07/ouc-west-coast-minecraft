"""Read the world using the Anvil and NBT readers from vanilla Java 1.21.4."""

import argparse
from itertools import product
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory

import jpype


HERE = Path(__file__).resolve().parent
TOOLS = HERE / "validation"


def main(source):
    library = next((TOOLS / "jre").rglob("jvm.dll"))
    libraries = sorted((TOOLS / "jars").glob("*.jar"))
    jpype.startJVM(str(library), "-Xmx512m", classpath=[str(path) for path in libraries], convertStrings=True)
    jpype.JClass("ab").a()                 # SharedConstants.tryDetectVersion()
    jpype.JClass("akx").a()                # Bootstrap.bootStrap()

    paths = jpype.JClass("java.nio.file.Paths")
    java_path = jpype.JClass("java.nio.file.Path")
    data_input = jpype.JClass("java.io.DataInput")
    nbt_io = jpype.JClass("ud")              # net.minecraft.nbt.NbtIo
    accounter = jpype.JClass("tz")           # net.minecraft.nbt.NbtAccounter
    region_cls = jpype.JClass("eaj")         # net.minecraft.world.level.chunk.storage.RegionFile
    storage_info = jpype.JClass("eam")       # net.minecraft.world.level.chunk.storage.RegionStorageInfo
    chunk_position = jpype.JClass("dfp")    # net.minecraft.world.level.ChunkPos
    get_quota = accounter.a
    read_level = nbt_io.class_.getMethod("a", java_path.class_, accounter.class_)
    read_chunk = nbt_io.class_.getMethod("a", data_input.class_, accounter.class_)
    open_stream = region_cls.class_.getMethod("a", chunk_position.class_)
    meta = read_level.invoke(None, paths.get(str(source / "level.dat")), get_quota(16 * 1024 * 1024)).p("Data")
    assert meta.p("Version").l("Name") == "1.21.4"
    spawn = meta.h("SpawnX"), meta.h("SpawnZ")
    print("Vanilla read level.dat:", meta.l("LevelName"), "spawn", spawn, flush=True)

    with TemporaryDirectory(dir=TOOLS, prefix="mojang-read-") as folder:
        region_dir = Path(folder)
        files = sorted((source / "region").glob("*.mca"))
        count = 0
        spawn_seen = False
        for path in files:
            _, rx, rz, _ = path.name.split(".")
            rx, rz = 32 * int(rx), 32 * int(rz)
            copy = region_dir / path.name
            shutil.copy2(path, copy)
            handle = region_cls(storage_info("OUC", None, "chunk"),
                                paths.get(str(copy)), paths.get(str(region_dir)), False)
            try:
                for dx, dz in product(range(32), repeat=2):
                    x, z = rx + dx, rz + dz
                    stream = open_stream.invoke(handle, chunk_position(x, z))
                    if stream is None:
                        continue
                    try:
                        chunk = read_chunk.invoke(None, stream, get_quota(8 * 1024 * 1024))
                    finally:
                        stream.close()
                    assert chunk.h("xPos") == x and chunk.h("zPos") == z
                    assert chunk.l("Status") == "minecraft:full"
                    spawn_seen |= (x, z) == (spawn[0] // 16, spawn[1] // 16)
                    count += 1
            finally:
                handle.close()
        assert len(files) == 10 and count == 8253 and spawn_seen
        print(f"Vanilla decoded {count:,} of {count:,} chunks across {len(files)} regions.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("world", type=Path)
    main(parser.parse_args().world.resolve())
