"""Check a generated Anvil save and render an oblique view of its surface."""

import argparse
import gzip
import io
import json
import math
from pathlib import Path
import struct
import zlib

import numpy as np
from PIL import Image, ImageDraw, ImageFont


WORK = Path(__file__).resolve().parent
AIR = {"minecraft:air", "minecraft:cave_air", "minecraft:void_air"}


def nbt(raw):
    stream = io.BytesIO(raw)
    number_types = {1: "b", 2: "h", 3: "i", 4: "q", 5: "f", 6: "d"}

    def num(code):
        layout = struct.Struct(">" + code)
        return layout.unpack(stream.read(layout.size))[0]

    def string():
        return stream.read(num("H")).decode("utf-8")

    def value(tag):
        if tag in number_types:
            return num(number_types[tag])
        if tag in (7, 11, 12):
            length = num("i")
            if tag == 7:
                return stream.read(length)
            item_type = "i" if tag == 11 else "q"
            return np.frombuffer(stream.read(length * struct.calcsize(item_type)), dtype=">" + item_type)
        if tag == 8:
            return string()
        if tag == 9:
            content_type = num("B")
            return [value(content_type) for unused in range(num("i"))]
        if tag == 10:
            result = {}
            while (child := num("B")) != 0:
                key = string()
                result[key] = value(child)
            return result
        raise ValueError(f"Unknown NBT tag {tag}")

    if num("B") != 10:
        raise ValueError("Expected compound NBT")
    string()
    return value(10)


def iter_chunks(region_path):
    x_base, z_base = (32 * int(position) for position in region_path.name.split(".")[1:3])
    region = region_path.read_bytes()
    assert len(region) >= 8192 and len(region) % 4096 == 0
    for index in range(1024):
        entry = 4 * index
        sector_offset = int.from_bytes(region[entry:entry + 3], "big")
        sector_count = region[entry + 3]
        if not sector_offset:
            continue
        assert sector_offset >= 2 and (sector_offset + sector_count) * 4096 <= len(region)
        start = sector_offset * 4096
        length = int.from_bytes(region[start:start + 4], "big")
        assert 0 < length <= sector_count * 4096 - 4 and region[start + 4] == 2
        chunk = nbt(zlib.decompress(region[start + 5:start + 4 + length]))
        assert chunk["xPos"] == x_base + index % 32 and chunk["zPos"] == z_base + index // 32
        assert chunk["Status"] == "minecraft:full"
        yield chunk


def top_blocks(chunk):
    row = np.arange(4096)
    result = np.full((16, 16), -64, dtype=np.int16)
    for section in sorted(chunk["sections"], key=lambda entry: entry["Y"]):
        if "block_states" not in section:
            continue
        state = section["block_states"]
        palette = np.array([entry["Name"] not in AIR for entry in state["palette"]])
        lowest = section["Y"] * 16
        if len(palette) == 1:
            if palette[0]:
                result.fill(lowest + 15)
            continue
        bits = max(4, (len(palette) - 1).bit_length())
        per_word = 64 // bits
        data = state["data"].astype(np.uint64)
        indices = ((data[row // per_word] >> ((row % per_word) * bits).astype(np.uint64)) & ((1 << bits) - 1)).astype(np.intp)
        filled = palette[indices].reshape(16, 16, 16)
        height = np.max(np.where(filled, lowest + np.arange(16)[:, None, None], -512), axis=0)
        result = np.maximum(result, height).astype(np.int16)
    return result


def read_world(source):
    metadata = json.loads((source / "metadata.json").read_text(encoding="utf-8"))
    level = nbt(gzip.decompress((source / "level.dat").read_bytes()))["Data"]
    assert level["Version"]["Name"] == "1.21.4" and level["GameType"] == 1
    assert (metadata["minMcX"], metadata["minMcZ"]) == (0, 0) and metadata["scale"] == 1
    width, height = metadata["maxMcX"] + 1, metadata["maxMcZ"] + 1
    surface = np.full((height + 15, width + 15), -512, dtype=np.int16)
    chunk_count = 0
    for file in sorted((source / "region").glob("*.mca")):
        for chunk in iter_chunks(file):
            x, z = 16 * chunk["xPos"], 16 * chunk["zPos"]
            if 0 <= x < width and 0 <= z < height:
                surface[z:z+16, x:x+16] = top_blocks(chunk)
            chunk_count += 1
    surface = surface[:height, :width]
    assert np.all(surface > -512)
    spawn = level["SpawnX"], level["SpawnY"], level["SpawnZ"]
    x, y, z = spawn
    print(f"Validated {chunk_count:,} chunks, {width} × {height} blocks, spawn={spawn}, ground={surface[z,x]}.")
    assert 1 <= y - surface[z, x] <= 6
    for name, x, z in [("Library", 1206, 682), ("Haide Building", 1383, 594), ("North building", 1070, 599), ("Sea", 1940, 490)]:
        print(name, (x, z), "surface y=", surface[z, x])
    return surface


def oblique_view(source, surface, target):
    with Image.open(source / "arnis_world_map.png") as preview:
        colors = np.array(preview.convert("RGB"))
    assert colors.shape[:2] == surface.shape
    x0, x1, z0, z1 = 315, 1960, 130, 946
    step = 2
    local_y = surface[z0:z1:step, x0:x1:step].tolist()
    paint = colors[z0:z1:step, x0:x1:step].tolist()
    width, depth = len(local_y[0]), len(local_y)
    scale = 1.30
    incline = 0.46
    altitude = scale / step * math.sqrt(2 * (1 - incline**2))
    block_base = -62
    margin = 44
    banner = 135
    canvas_w = int((width + depth) * scale) + 2 * margin
    canvas_h = int((width + depth) * scale * incline) + margin + banner + 28
    canvas = Image.new("RGB", (canvas_w, canvas_h), (236, 239, 235))
    draw = ImageDraw.Draw(canvas)

    def project(x, z, y):
        return (margin + (depth + x - z) * scale,
                banner + (x + z) * scale * incline - (y - block_base) * altitude)

    for row in range(width + depth - 1):
        for ix in range(max(0, row - depth + 1), min(width, row + 1)):
            iz = row - ix
            y = local_y[iz][ix]
            rgb = tuple(paint[iz][ix])
            dx, dz = ix + 1, iz + 1
            a, b, c, d = project(ix, iz, y), project(dx, iz, y), project(dx, dz, y), project(ix, dz, y)
            east = local_y[iz][dx] if dx < width else block_base
            south = local_y[dz][ix] if dz < depth else block_base
            if east < y:
                draw.polygon((b, c, project(dx, dz, east), project(dx, iz, east)),
                             fill=tuple(round(component * 0.61) for component in rgb))
            if south < y:
                draw.polygon((d, c, project(dx, dz, south), project(ix, dz, south)),
                             fill=tuple(round(component * 0.80) for component in rgb))
            draw.polygon((a, b, c, d), fill=rgb)

    font_path = Path(r"C:\Windows\Fonts\msyh.ttc")
    title = ImageFont.truetype(str(font_path), 31)
    note = ImageFont.truetype(str(font_path), 19)
    label = ImageFont.truetype(str(font_path), 20)
    draw.text((margin, 30), "中国海洋大学西海岸校区", font=title, fill=(36, 55, 48))
    draw.text((margin, 77), "存档方块渲染  ·  约 1 米 = 1 格", font=note, fill=(75, 93, 86))

    def callout(name, x, z, dx, dy):
        x1, z1 = (x - x0) / step, (z - z0) / step
        px, py = project(x1, z1, int(surface[z, x]))
        width_text = int(draw.textlength(name, font=label))
        side = 10 if dx > 0 else -10
        ax, ay = px + dx, py + dy
        draw.line(((px, py), (ax, ay)), fill=(235, 245, 235), width=2)
        draw.ellipse((px-3, py-3, px+3, py+3), fill=(250, 250, 245), outline=(37, 59, 48), width=1)
        left = ax + side if dx > 0 else ax + side - width_text - 18
        frame = (left, ay-16, left+width_text+18, ay+17)
        draw.rounded_rectangle(frame, 5, fill=(244, 248, 240), outline=(87, 110, 97))
        draw.text((left+9, ay-14), name, font=label, fill=(36, 55, 48))

    callout("望海苑", 526, 253, -70, -30)
    callout("听海苑", 1330, 242, 40, -50)
    callout("学习综合体", 1206, 682, -112, 26)
    callout("浩海广场", 1412, 725, 95, 27)
    credits = ImageFont.truetype(str(font_path), 14)
    draw.text((margin, canvas_h - 38), "© OpenStreetMap contributors  ·  Mapterhorn  ·  Contains modified Copernicus Sentinel data (2026)", font=credits, fill=(75, 93, 86))
    canvas.save(target)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("world", type=Path)
    parser.add_argument("--render", type=Path)
    args = parser.parse_args()
    surface = read_world(args.world)
    if args.render:
        oblique_view(args.world, surface, args.render)


if __name__ == "__main__":
    main()
