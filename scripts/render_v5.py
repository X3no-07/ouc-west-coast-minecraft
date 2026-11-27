"""Render real screenshots of the OUC West Coast campus v5 world.

Reads block data straight from the region files of the formal v5 world
(/tmp/v5-formal/OUC-West-Coast-v5, unzipped from OUC-West-Coast-v5.zip;
its 10 region files are byte-identical to the dry-run world) using
anvil.py for NBT parsing. No hand-drawn art, no AI images.

Two views:
  * top-down: highest solid block per column, coloured by block type.
  * iso: oblique view (viewer from the south-east unless flipped),
    each column drawn as an extruded prism; visible side height is how
    far the column sticks up above its front neighbours, side colour is
    the wall material below the roof.

Output: ~/workspace/minecraft-ouc/v5-screenshots/*.png
"""
import sys
import zlib
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).parent))
from anvil import (  # noqa: E402
    base_name, decode_indices, find, find_node, loads, read_region,
)

WORLD = Path("/tmp/v5-formal/OUC-West-Coast-v5")
OUT = Path(__file__).parent / "v5-screenshots"
OUT.mkdir(exist_ok=True)

FONT = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
FONT_BOLD = "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc"

Y_MIN, Y_MAX = -64, 64  # scan range (y -64..63)
NY = Y_MAX - Y_MIN

SKIP = {
    "minecraft:air", "minecraft:cave_air", "minecraft:void_air",
    "minecraft:grass", "minecraft:tall_grass", "minecraft:fern",
    "minecraft:large_fern", "minecraft:dandelion", "minecraft:poppy",
    "minecraft:blue_orchid", "minecraft:allium", "minecraft:azure_bluet",
    "minecraft:red_tulip", "minecraft:orange_tulip", "minecraft:white_tulip",
    "minecraft:pink_tulip", "minecraft:oxeye_daisy", "minecraft:cornflower",
    "minecraft:lily_of_the_valley", "minecraft:wither_rose",
    "minecraft:sunflower", "minecraft:lilac", "minecraft:rose_bush",
    "minecraft:peony", "minecraft:torch", "minecraft:wall_torch",
    "minecraft:redstone_torch", "minecraft:redstone_wall_torch",
    "minecraft:soul_torch", "minecraft:soul_wall_torch",
    "minecraft:lantern", "minecraft:soul_lantern",
    "minecraft:oak_sign", "minecraft:spruce_sign", "minecraft:birch_sign",
    "minecraft:jungle_sign", "minecraft:acacia_sign",
    "minecraft:dark_oak_sign", "minecraft:crimson_sign",
    "minecraft:warped_sign", "minecraft:mangrove_sign",
    "minecraft:cherry_sign", "minecraft:bamboo_sign",
    "minecraft:oak_wall_sign", "minecraft:spruce_wall_sign",
    "minecraft:birch_wall_sign", "minecraft:jungle_wall_sign",
    "minecraft:acacia_wall_sign", "minecraft:dark_oak_wall_sign",
    "minecraft:crimson_wall_sign", "minecraft:warped_wall_sign",
    "minecraft:mangrove_wall_sign", "minecraft:cherry_wall_sign",
    "minecraft:bamboo_wall_sign", "minecraft:oak_button",
    "minecraft:stone_button", "minecraft:oak_pressure_plate",
    "minecraft:stone_pressure_plate", "minecraft:light_weighted_pressure_plate",
    "minecraft:heavy_weighted_pressure_plate",
    "minecraft:rail", "minecraft:powered_rail", "minecraft:detector_rail",
    "minecraft:activator_rail", "minecraft:snow", "minecraft:vine",
    "minecraft:glow_lichen", "minecraft:tripwire", "minecraft:tripwire_hook",
    "minecraft:white_carpet", "minecraft:light_gray_carpet",
    "minecraft:gray_carpet", "minecraft:red_carpet", "minecraft:blue_carpet",
    "minecraft:green_carpet", "minecraft:black_carpet",
    "minecraft:bamboo", "minecraft:sugar_cane", "minecraft:cactus",
    "minecraft:dead_bush", "minecraft:seagrass", "minecraft:tall_seagrass",
    "minecraft:kelp", "minecraft:kelp_plant",
    "minecraft:azalea", "minecraft:flowering_azalea",
    "minecraft:spore_blossom", "minecraft:hanging_roots",
    "minecraft:glow_berries", "minecraft:sweet_berry_bush",
    "minecraft:nether_sprouts", "minecraft:crimson_roots",
    "minecraft:warped_roots", "minecraft:crimson_fungus",
    "minecraft:warped_fungus", "minecraft:red_mushroom",
    "minecraft:brown_mushroom", "minecraft:twisting_vines",
    "minecraft:weeping_vines", "minecraft:pointed_dripstone",
    "minecraft:sculk_vein", "minecraft:lever", "minecraft:short_grass",
    "minecraft:pink_petals", "minecraft:potted_dandelion",
    "minecraft:potted_poppy", "minecraft:potted_blue_orchid",
    "minecraft:potted_red_tulip", "minecraft:potted_allium",
    "minecraft:potted_azure_bluet", "minecraft:potted_oxeye_daisy",
    "minecraft:potted_cornflower", "minecraft:potted_lily_of_the_valley",
    "minecraft:potted_wither_rose", "minecraft:potted_cactus",
    "minecraft:potted_bamboo", "minecraft:potted_crimson_fungus",
    "minecraft:potted_warped_fungus", "minecraft:potted_brown_mushroom",
    "minecraft:potted_red_mushroom", "minecraft:potted_fern",
    "minecraft:potted_acacia_sapling", "minecraft:potted_birch_sapling",
    "minecraft:potted_dark_oak_sapling", "minecraft:potted_jungle_sapling",
    "minecraft:potted_oak_sapling", "minecraft:potted_spruce_sapling",
    "minecraft:potted_cherry_sapling", "minecraft:potted_mangrove_propagule",
    "minecraft:potted_azalea_bush", "minecraft:potted_flowering_azalea_bush",
    "minecraft:potted_dead_bush",
}

# ---------------------------------------------------------------- colours
CONCRETE = {
    "white": (207, 207, 207), "orange": (224, 128, 25),
    "magenta": (199, 78, 189), "light_blue": (58, 179, 218),
    "yellow": (254, 216, 61), "lime": (128, 199, 31),
    "pink": (243, 139, 170), "gray": (71, 79, 82),
    "light_gray": (157, 157, 151), "cyan": (22, 156, 156),
    "purple": (137, 50, 184), "blue": (60, 68, 170),
    "brown": (131, 84, 50), "green": (94, 156, 52),
    "red": (176, 46, 38), "black": (29, 29, 33),
}
TERRA = {
    "white": (209, 177, 161), "orange": (162, 84, 60),
    "magenta": (149, 103, 115), "light_blue": (135, 165, 180),
    "yellow": (186, 135, 53), "lime": (103, 118, 60),
    "pink": (171, 122, 110), "gray": (111, 102, 96),
    "light_gray": (158, 148, 140), "cyan": (105, 125, 120),
    "purple": (126, 88, 110), "blue": (96, 104, 134),
    "brown": (122, 89, 71), "green": (107, 118, 78),
    "red": (150, 81, 75), "black": (60, 46, 42),
}
WOOL = {
    "white": (234, 234, 234), "orange": (240, 118, 19),
    "magenta": (198, 79, 189), "light_blue": (58, 175, 217),
    "yellow": (254, 214, 61), "lime": (127, 204, 25),
    "pink": (241, 149, 172), "gray": (63, 68, 72),
    "light_gray": (142, 142, 134), "cyan": (21, 137, 145),
    "purple": (124, 54, 184), "blue": (53, 57, 157),
    "brown": (114, 71, 40), "green": (86, 139, 47),
    "red": (160, 39, 34), "black": (26, 26, 28),
}
WOOD = {
    "oak": (168, 136, 82), "spruce": (115, 90, 55),
    "birch": (193, 176, 126), "dark_oak": (90, 66, 40),
    "acacia": (172, 112, 60), "jungle": (168, 134, 82),
    "cherry": (214, 166, 152), "mangrove": (132, 72, 62),
    "bamboo": (193, 174, 97), "crimson": (122, 62, 72),
    "warped": (62, 142, 132),
}
LEAVES = {
    "oak": (58, 110, 34), "spruce": (50, 95, 50),
    "birch": (110, 165, 60), "dark_oak": (55, 100, 35),
    "acacia": (110, 150, 60), "jungle": (60, 120, 40),
    "azalea": (90, 140, 70), "flowering_azalea": (110, 150, 80),
    "mangrove": (70, 110, 60), "cherry": (220, 170, 190),
}
EXACT = {
    "grass_block": (126, 178, 56), "dirt": (134, 96, 67),
    "coarse_dirt": (134, 96, 67), "podzol": (107, 79, 42),
    "rooted_dirt": (144, 106, 77), "mud": (80, 68, 60),
    "grass_path": (190, 164, 105), "dirt_path": (190, 164, 105),
    "farmland": (90, 58, 34), "stone": (125, 125, 125),
    "cobblestone": (128, 128, 128), "mossy_cobblestone": (110, 120, 100),
    "stone_bricks": (122, 122, 122), "mossy_stone_bricks": (110, 118, 102),
    "cracked_stone_bricks": (118, 118, 118),
    "chiseled_stone_bricks": (120, 120, 120),
    "smooth_stone": (138, 138, 138), "smooth_stone_slab": (138, 138, 138),
    "andesite": (136, 136, 136), "polished_andesite": (140, 140, 140),
    "granite": (149, 103, 89), "polished_granite": (155, 110, 95),
    "diorite": (188, 188, 188), "polished_diorite": (195, 195, 195),
    "gravel": (130, 126, 120), "sand": (219, 207, 163),
    "red_sand": (188, 123, 70), "sandstone": (218, 210, 160),
    "smooth_sandstone": (216, 208, 158), "cut_sandstone": (216, 208, 158),
    "chiseled_sandstone": (216, 208, 158),
    "red_sandstone": (182, 110, 60), "smooth_red_sandstone": (180, 108, 58),
    "cut_red_sandstone": (180, 108, 58),
    "chiseled_red_sandstone": (180, 108, 58),
    "brick": (150, 97, 83), "bricks": (150, 97, 83),
    "nether_bricks": (90, 50, 55), "red_nether_bricks": (120, 50, 50),
    "quartz_block": (235, 230, 213), "smooth_quartz": (233, 228, 210),
    "quartz_pillar": (232, 227, 208), "chiseled_quartz_block": (232, 227, 208),
    "quartz_bricks": (230, 225, 205), "glass": (205, 228, 238),
    "tinted_glass": (70, 70, 78), "water": (63, 118, 228),
    "lava": (220, 90, 20), "snow_block": (240, 251, 251),
    "ice": (170, 210, 235), "packed_ice": (165, 205, 235),
    "blue_ice": (120, 170, 230), "clay": (159, 164, 176),
    "terracotta": (150, 97, 83), "bedrock": (85, 85, 85),
    "obsidian": (26, 15, 46), "crying_obsidian": (40, 20, 60),
    "end_stone": (220, 220, 180), "end_stone_bricks": (215, 215, 175),
    "purpur_block": (170, 130, 170), "purpur_pillar": (168, 128, 168),
    "prismarine": (93, 168, 160), "dark_prismarine": (47, 107, 94),
    "prismarine_bricks": (100, 175, 165),
    "blackstone": (50, 45, 55), "polished_blackstone": (55, 50, 60),
    "polished_blackstone_bricks": (58, 52, 62),
    "basalt": (70, 65, 75), "smooth_basalt": (72, 67, 77),
    "soul_sand": (85, 60, 45), "soul_soil": (80, 55, 45),
    "netherrack": (110, 58, 58), "crimson_nylium": (140, 50, 50),
    "warped_nylium": (50, 140, 130), "glowstone": (255, 196, 107),
    "sea_lantern": (159, 197, 184), "redstone_lamp": (245, 196, 118),
    "shroomlight": (240, 160, 90), "iron_block": (216, 216, 216),
    "gold_block": (252, 238, 75), "diamond_block": (130, 225, 225),
    "emerald_block": (90, 220, 140), "copper_block": (200, 130, 100),
    "netherite_block": (80, 70, 80), "lapis_block": (40, 70, 180),
    "redstone_block": (180, 40, 30), "coal_block": (35, 35, 35),
    "coal_ore": (60, 60, 60), "iron_ore": (210, 180, 160),
    "gold_ore": (220, 190, 80), "diamond_ore": (120, 220, 220),
    "redstone_ore": (180, 60, 60), "emerald_ore": (80, 200, 120),
    "lapis_ore": (60, 80, 180), "copper_ore": (200, 140, 110),
    "deepslate": (100, 100, 100), "cobbled_deepslate": (105, 105, 105),
    "moss_block": (95, 130, 60), "mossy_stone": (110, 118, 102),
    "hay_block": (200, 170, 70), "melon": (190, 190, 40),
    "pumpkin": (200, 140, 40), "bookshelf": (170, 140, 90),
    "crafting_table": (170, 140, 90), "furnace": (130, 130, 130),
    "chest": (170, 130, 70), "ender_chest": (40, 60, 70),
    "sponge": (200, 200, 90), "wet_sponge": (180, 180, 90),
    "slime_block": (110, 200, 90), "honey_block": (230, 170, 40),
    "tube_coral_block": (60, 120, 200), "brain_coral_block": (220, 120, 180),
    "bubble_coral_block": (200, 90, 200), "fire_coral_block": (200, 60, 60),
    "horn_coral_block": (230, 200, 90), "dead_tube_coral_block": (120, 115, 110),
    "sea_pickle": (120, 180, 90), "calcite": (225, 225, 220),
    "tuff": (130, 125, 118), "barrel": (150, 115, 70),
    "blast_furnace": (110, 110, 110), "smoker": (110, 110, 110),
    "cauldron": (90, 90, 90), "grindstone": (120, 120, 120),
    "daylight_detector": (150, 130, 100), "end_rod": (240, 230, 200),
    "iron_bars": (200, 200, 200), "light": (255, 240, 180),
    "lightning_rod": (180, 140, 100), "scaffolding": (190, 170, 110),
    "glass_pane": (205, 228, 238), "iron_door": (200, 200, 200),
    "iron_trapdoor": (200, 200, 200), "copper_door": (200, 130, 100),
    "copper_trapdoor": (200, 130, 100),
}

UNKNOWN = set()


def _light(rgb, f):
    return tuple(min(255, int(c * f + 255 * (1 - f) * 0.35)) if f > 1 else int(c * f)
                 for c in rgb)


def material_color(base):
    """Colour of a material name (no block-state suffixes)."""
    if base in EXACT:
        return EXACT[base]
    if base in WOOD:
        return WOOD[base]
    if base == "quartz":
        return EXACT["quartz_block"]
    if base == "iron":
        return EXACT["iron_block"]
    if base == "gold":
        return EXACT["gold_block"]
    if base == "glass":
        return EXACT["glass"]
    if base.endswith("_planks"):
        w = base[: -len("_planks")]
        if w in WOOD:
            return WOOD[w]
    if base.endswith("_log"):
        w = base[: -len("_log")].replace("stripped_", "")
        if w in WOOD:
            b = WOOD[w]
            return tuple(int(c * 0.75) for c in b)
    if base.endswith("_concrete"):
        c = base[: -len("_concrete")]
        if c in CONCRETE:
            return CONCRETE[c]
    if base.endswith("_terracotta"):
        c = base[: -len("_terracotta")]
        if c in TERRA:
            return TERRA[c]
    if base.endswith("_sandstone"):
        return EXACT["sandstone"]
    if base.endswith("_leaves"):
        w = base[: -len("_leaves")]
        if w in LEAVES:
            return LEAVES[w]
    if base.endswith("_wool"):
        c = base[: -len("_wool")]
        if c in WOOL:
            return WOOL[c]
    if base.endswith("_stained_glass"):
        c = base[: -len("_stained_glass")]
        if c in CONCRETE:
            b = CONCRETE[c]
            return tuple((v + 255) // 2 for v in b)
    return None


def color_for(name):
    """name: 'minecraft:...' or bare base name -> (r,g,b)."""
    n = name[10:] if name.startswith("minecraft:") else name
    c = material_color(n)
    if c is not None:
        return c
    if n.endswith("_concrete_powder"):
        c = n[: -len("_concrete_powder")]
        if c in CONCRETE:
            return CONCRETE[c]
    if n.endswith("_glazed_terracotta"):
        c = n[: -len("_glazed_terracotta")]
        if c in TERRA:
            return TERRA[c]
    if n.endswith("_pane"):
        c = material_color(n[: -len("_pane")])
        if c is not None:
            return c
    for suffix in ("_stairs", "_slab", "_wall", "_fence", "_fence_gate",
                   "_door", "_trapdoor", "_button", "_pressure_plate",
                   "_sign", "_hanging_sign"):
        if n.endswith(suffix):
            base = n[: -len(suffix)]
            if base.endswith("_brick"):
                base += "s"
            c = material_color(base)
            if c is not None:
                return c
    if n.endswith("_ore"):
        return (120, 110, 100)
    UNKNOWN.add(n)
    return (255, 0, 255)


def shade(rgb, f):
    return tuple(max(0, min(255, int(c * f))) for c in rgb)


# ---------------------------------------------------------------- world IO
class TopMaps:
    """Per-chunk top-of-column maps, cached."""

    def __init__(self, world_dir):
        self.world = Path(world_dir)
        self._regions = {}   # (rx, rz) -> { (lx, lz): (comp, ts) }
        self._tops = {}      # (cx, cz) -> (top_y (16,16) int16, top_name (16,16) object)

    def _region(self, rx, rz):
        key = (rx, rz)
        if key not in self._regions:
            self._regions[key] = read_region(self.world / "region" / f"r.{rx}.{rz}.mca")
        return self._regions[key]

    def chunk_top(self, cx, cz):
        key = (cx, cz)
        if key in self._tops:
            return self._tops[key]
        rx, rz = cx >> 5, cz >> 5
        lx, lz = cx & 31, cz & 31
        region = self._region(rx, rz)
        top_y = np.full((16, 16), -999, dtype=np.int16)
        top_name = np.empty((16, 16), dtype=object)
        top_name[:] = ""
        raw = region.get((lx, lz))
        if raw is not None:
            root = loads(zlib.decompress(raw[0]))
            _, _, nodes = root
            sec_node = find_node(nodes, "sections")
            _, items = sec_node[2]
            solid = np.zeros((NY, 16, 16), dtype=bool)
            names = np.empty((NY, 16, 16), dtype=object)
            names[:] = ""
            for sec in items:
                ysec = find(sec, "Y")[1]
                if ysec < -4 or ysec > 3:
                    continue
                bs = find_node(sec, "block_states")
                if bs is None:
                    continue
                indices, states = decode_indices(bs[2])
                if indices is None:
                    continue
                base = [base_name(s) for s in states]
                idx = np.array(indices, dtype=np.int32).reshape(16, 16, 16)
                y0 = ysec * 16 - Y_MIN
                for li, b in enumerate(base):
                    if b in SKIP:
                        continue
                    m = idx == li
                    if not m.any():
                        continue
                    solid[y0:y0 + 16][m] = True
                    names[y0:y0 + 16][m] = b
            has = solid.any(axis=0)
            if has.any():
                top_local = NY - 1 - np.argmax(solid[::-1], axis=0)
                zz, xx = np.meshgrid(np.arange(16), np.arange(16), indexing="ij")
                top_y = np.where(has, top_local + Y_MIN, -999).astype(np.int16)
                top_name = names[top_local, zz, xx]
                top_name = np.where(has, top_name, "")
        self._tops[key] = (top_y, top_name)
        return self._tops[key]

    def area(self, x0, z0, x1, z1):
        """Return (top_y (nz,nx) int16, top_name (nz,nx) object) for bbox."""
        nx, nz = x1 - x0 + 1, z1 - z0 + 1
        ty = np.full((nz, nx), -999, dtype=np.int16)
        tn = np.empty((nz, nx), dtype=object)
        tn[:] = ""
        for cz in range(z0 >> 4, (z1 >> 4) + 1):
            for cx in range(x0 >> 4, (x1 >> 4) + 1):
                cy, cn = self.chunk_top(cx, cz)
                for lz in range(16):
                    gz = cz * 16 + lz
                    if gz < z0 or gz > z1:
                        continue
                    for lx in range(16):
                        gx = cx * 16 + lx
                        if gx < x0 or gx > x1:
                            continue
                        ty[gz - z0, gx - x0] = cy[lz, lx]
                        tn[gz - z0, gx - x0] = cn[lz, lx]
        return ty, tn

    def column_volume(self, cx, cz):
        """For iso: return (names3d (NY,16,16) object, solid3d bool) or None."""
        rx, rz = cx >> 5, cz >> 5
        lx, lz = cx & 31, cz & 31
        region = self._region(rx, rz)
        raw = region.get((lx, lz))
        if raw is None:
            return None
        root = loads(zlib.decompress(raw[0]))
        _, _, nodes = root
        sec_node = find_node(nodes, "sections")
        _, items = sec_node[2]
        solid = np.zeros((NY, 16, 16), dtype=bool)
        names = np.empty((NY, 16, 16), dtype=object)
        names[:] = ""
        for sec in items:
            ysec = find(sec, "Y")[1]
            if ysec < -4 or ysec > 3:
                continue
            bs = find_node(sec, "block_states")
            if bs is None:
                continue
            indices, states = decode_indices(bs[2])
            if indices is None:
                continue
            base = [base_name(s) for s in states]
            idx = np.array(indices, dtype=np.int32).reshape(16, 16, 16)
            y0 = ysec * 16 - Y_MIN
            for li, b in enumerate(base):
                if b in SKIP:
                    continue
                m = idx == li
                if not m.any():
                    continue
                solid[y0:y0 + 16][m] = True
                names[y0:y0 + 16][m] = b
        return names, solid


# ---------------------------------------------------------------- drawing
def font(size, bold=False):
    return ImageFont.truetype(FONT_BOLD if bold else FONT, size)


def add_label(img, lines, bar_h):
    """Append a white label bar under the image with the given text lines.
    Lines are wrapped to the image width (narrow crops would otherwise
    cut the subtitle off at the right edge); the bar grows as needed."""
    w = img.width
    BREAK_AFTER = " ，｜、+-/"

    def wrap_one(text, f, maxw):
        """Greedy wrap; prefer breaking after a space/punctuation so
        Latin words (e.g. OUC-West-Coast-v5.zip) are not split mid-word."""
        lines = []
        cur = ""
        last_break = -1  # position in cur just after a break opportunity
        for ch in text:
            cur += ch
            if ch in BREAK_AFTER:
                last_break = len(cur)
            if f.getlength(cur) > maxw:
                if last_break > 0 and last_break < len(cur):
                    lines.append(cur[:last_break])
                    cur = cur[last_break:]
                    last_break = -1
                    for i, c in enumerate(cur):
                        if c in BREAK_AFTER:
                            last_break = i + 1
                else:
                    lines.append(cur[:-1])
                    cur = ch
                    last_break = 1 if ch in BREAK_AFTER else -1
        if cur:
            lines.append(cur)
        return lines

    wrapped = []
    for text, size, bold in lines:
        f = font(size, bold)
        maxw = w - 32
        if f.getlength(text) <= maxw:
            wrapped.append((text, size, bold))
        else:
            for piece in wrap_one(text, f, maxw):
                wrapped.append((piece, size, bold))
    need = 12 + sum(size + 10 for _, size, _ in wrapped) + 8
    h = max(bar_h, need)
    bar = Image.new("RGB", (w, h), (255, 255, 255))
    d = ImageDraw.Draw(bar)
    d.line([(0, 0), (w, 0)], fill=(180, 180, 180), width=2)
    y = 12
    for text, size, bold in wrapped:
        d.text((16, y), text, font=font(size, bold), fill=(20, 20, 20))
        y += size + 10
    out = Image.new("RGB", (w, img.height + h), (255, 255, 255))
    out.paste(img, (0, 0))
    out.paste(bar, (0, img.height))
    return out


def north_arrow(d, x, y, s=34):
    d.polygon([(x, y - s), (x + s // 2, y + s // 2), (x - s // 2, y + s // 2)],
              fill=(200, 30, 30), outline=(120, 0, 0))
    d.text((x - 7, y + s // 2 + 4), "北", font=font(22, True), fill=(30, 30, 30))


def top_image(tm, x0, z0, x1, z1, title, subtitle, scale=3, markers=None):
    ty, tn = tm.area(x0, z0, x1, z1)
    nz, nx = ty.shape
    uniq = sorted({n for n in tn.flat if n})
    lut = {n: color_for(n) for n in uniq}
    idx_of = {n: i for i, n in enumerate(uniq)}
    arr = np.zeros((nz, nx), dtype=np.int32)
    for n, i in idx_of.items():
        arr[tn == n] = i
    palette = np.array([lut[n] for n in uniq], dtype=np.uint8)
    rgb = palette[arr]
    img = Image.fromarray(rgb, "RGB")
    if scale != 1:
        img = img.resize((nx * scale, nz * scale), Image.NEAREST)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, img.width - 1, img.height - 1], outline=(60, 60, 60), width=3)
    if markers:
        for (mx, mz, label) in markers:
            px, py = (mx - x0 + 0.5) * scale, (mz - z0 + 0.5) * scale
            r = 13
            d.ellipse([px - r, py - r, px + r, py + r], fill=(220, 30, 30),
                      outline=(255, 255, 255), width=3)
            d.text((px - 5, py - 9), label, font=font(18, True), fill=(255, 255, 255))
    north_arrow(d, img.width - 46, 52)
    lines = [(title, 30, True),
             (subtitle, 22, False),
             ("来源：正式版 v5 世界文件（OUC-West-Coast-v5.zip）｜俯视图，1 格 = 1 米，北在上方",
              20, False),
             ("世界文件渲染图，非游戏内截图", 20, False)]
    return add_label(img, lines, 150)


def iso_image(tm, x0, z0, x1, z1, title, subtitle, flip=False):
    """Oblique view. flip=True: viewer from the north-west instead."""
    ty, tn = tm.area(x0, z0, x1, z1)
    nz, nx = ty.shape
    # Per-block lookup (cached chunk volumes) so side faces can be drawn
    # as true vertical bands: roof band, window/louver band, wall, base —
    # instead of one flat colour per column, which hid wall features
    # such as the 听海餐厅 blue louvers (2–3 blocks below the roofline).
    vols = {}

    def block_at(gx, y, gz):
        yy = y - Y_MIN
        if yy < 0 or yy >= 128:
            return None
        cx, cz = gx >> 4, gz >> 4
        key = (cx, cz)
        if key not in vols:
            vols[key] = tm.column_volume(cx, cz)
        vol = vols[key]
        if vol is None:
            return None
        names3d, solid3d = vol
        lx, lz = gx & 15, gz & 15
        if not solid3d[yy, lz, lx]:
            return None
        b = names3d[yy, lz, lx]
        if not b or b in SKIP:
            return None
        return b
    tw, th, vh = 14, 7, 7
    y_lo = int(ty[ty > -999].min()) if (ty > -999).any() else 0
    y_hi = int(ty.max())
    if flip:
        # viewer from NW: screen x grows with (z - x), y grows with -(x + z)
        def scr(gx, gz, y):
            return ((gz - z0) - (gx - x0)) * tw // 2, (-(gx - x0) - (gz - z0)) * th // 2 - (y - y_lo) * vh
        order = sorted(((gx, gz) for gz in range(z0, z1 + 1) for gx in range(x0, x1 + 1)),
                       key=lambda p: (-(p[0] + p[1]), p[0]))
        front = lambda gx, gz: [(gx - 1, gz), (gx, gz - 1), (gx - 1, gz - 1)]
    else:
        def scr(gx, gz, y):
            return ((gx - x0) - (gz - z0)) * tw // 2, ((gx - x0) + (gz - z0)) * th // 2 - (y - y_lo) * vh
        order = sorted(((gx, gz) for gz in range(z0, z1 + 1) for gx in range(x0, x1 + 1)),
                       key=lambda p: (p[0] + p[1], p[0]))
        front = lambda gx, gz: [(gx + 1, gz), (gx, gz + 1), (gx + 1, gz + 1)]
    xs = [scr(x0, z0, y_lo)[0], scr(x1, z0, y_lo)[0], scr(x0, z1, y_lo)[0], scr(x1, z1, y_lo)[0]]
    ys = [scr(x0, z0, y_hi)[1], scr(x1, z1, y_lo)[1]]
    W = max(xs) - min(xs) + tw + 80
    H = max(ys) - min(ys) + (y_hi - y_lo) * vh + th + 120
    ox = -min(xs) + 40
    oy = -min(ys) + 60
    img = Image.new("RGB", (W, H), (232, 236, 240))
    d = ImageDraw.Draw(img)

    def top_at(gx, gz):
        if gx < x0 or gx > x1 or gz < z0 or gz > z1:
            return None
        v = ty[gz - z0, gx - x0]
        return None if v <= -999 else int(v)

    for (gx, gz) in order:
        top = top_at(gx, gz)
        if top is None:
            continue
        tname = tn[gz - z0, gx - x0]
        sx, sy = scr(gx, gz, top)
        sx += ox
        sy += oy
        # Visible side heights: each face is hidden only by the neighbour
        # directly in front of it. (A single max over all front neighbours
        # is wrong: the lateral neighbour on the same roof would hide a
        # face whose own front neighbour is far below.)
        def _h(nx, nz):
            v = top_at(nx, nz)
            return max(0, top - v) if v is not None else 0
        if flip:
            # left face = north face (neighbour z-1), right = west (x-1)
            h_left = _h(gx, gz - 1)
            h_right = _h(gx - 1, gz)
        else:
            # left face = south face (neighbour z+1), right = east (x+1)
            h_left = _h(gx, gz + 1)
            h_right = _h(gx + 1, gz)

        def draw_face(h, side):
            # side -1 = left face, +1 = right face; one band per block,
            # air gaps left unpainted (reads as a recess/opening).
            for dd in range(h):
                bname = block_at(gx, top - dd, gz)
                if bname is None:
                    continue
                c = shade(color_for(bname), 0.72 if side < 0 else 0.58)
                if side < 0:
                    d.polygon([(sx, sy + th // 2 + dd * vh),
                               (sx - tw // 2, sy + dd * vh),
                               (sx - tw // 2, sy + (dd + 1) * vh),
                               (sx, sy + th // 2 + (dd + 1) * vh)], fill=c)
                else:
                    d.polygon([(sx, sy + th // 2 + dd * vh),
                               (sx + tw // 2, sy + dd * vh),
                               (sx + tw // 2, sy + (dd + 1) * vh),
                               (sx, sy + th // 2 + (dd + 1) * vh)], fill=c)
        if h_left > 0:
            draw_face(h_left, -1)
        if h_right > 0:
            draw_face(h_right, +1)
        top_c = color_for(tname)
        d.polygon([(sx, sy - th // 2), (sx + tw // 2, sy),
                   (sx, sy + th // 2), (sx - tw // 2, sy)],
                  fill=top_c, outline=shade(top_c, 0.82))
    d.rectangle([0, 0, W - 1, H - 1], outline=(60, 60, 60), width=3)
    lines = [(title, 30, True),
             (subtitle, 22, False),
             ("来源：正式版 v5 世界文件（OUC-West-Coast-v5.zip）｜斜视图，方块渲染，可看立面与台阶",
              20, False),
             ("世界文件渲染图，非游戏内截图", 20, False)]
    return add_label(img, lines, 150)


# ---------------------------------------------------------------- jobs
JOBS = [
    # (kind, filename, title, subtitle, bbox, kwargs)
    ("top", "01_学习综合体西广场_俯视.png", "学习综合体西广场",
     "X 1095–1270，Z 645–755｜浅灰大石板广场 + 同心接缝，西立面在右",
     (1095, 645, 1270, 755), {"scale": 3}),
    ("top", "02_学习综合体东立面大台阶_俯视.png", "学习综合体东立面 + 大台阶",
     "X 1140–1350，Z 630–770｜东立面灰蓝竖鳍片 + 蓝玻璃幕墙，10 级大台阶在东",
     (1140, 630, 1350, 770), {"scale": 3}),
    ("iso", "02b_学习综合体东立面大台阶_斜视.png", "学习综合体东立面 + 大台阶",
     "X 1150–1340，Z 650–760｜斜视：东立面、10 级大台阶、浩海广场一角",
     (1150, 650, 1340, 760), {}),
    ("top", "03_浩海广场_俯视.png", "浩海广场",
     "X 1245–1355，Z 630–770｜浅米色大石板，红色 1924/2023 雕塑在中央草坪",
     (1245, 630, 1355, 770), {"scale": 3}),
    ("iso", "03b_浩海广场_斜视.png", "浩海广场",
     "X 1255–1345，Z 640–765｜斜视：广场石板、雕塑、学习综合体东立面",
     (1255, 640, 1345, 765), {}),
    ("top", "04_听海苑_俯视.png", "听海苑宿舍群",
     "X 1170–1450，Z 180–370｜棕/奶油网格外墙 + 红瓦，9 栋",
     (1170, 180, 1450, 370), {"scale": 3}),
    ("top", "05_听海餐厅_俯视.png", "听海餐厅",
     "X 1170–1250，Z 280–360｜2 层，深蓝百叶上层，白色外挂楼梯在东",
     (1170, 280, 1250, 360), {"scale": 4}),
    ("iso", "05b_听海餐厅_斜视.png", "听海餐厅（东南向）",
     "X 1175–1240，Z 285–355｜斜视：东面外挂楼梯、灰石柱底层",
     (1175, 285, 1240, 355), {}),
    ("iso", "05c_听海餐厅_斜视西北.png", "听海餐厅（西北向）",
     "X 1175–1240，Z 285–355｜斜视：西面深蓝百叶墙、屋顶",
     (1175, 285, 1240, 355), {"flip": True}),
    ("top", "06_望海餐厅_俯视.png", "望海餐厅",
     "X 570–650，Z 285–365｜3 层，米色古典立面 + 红坡顶，北面蓝玻璃湾",
     (570, 285, 650, 365), {"scale": 4}),
    ("iso", "06b_望海餐厅_斜视.png", "望海餐厅",
     "X 575–645，Z 290–360｜斜视：古典立面、三角楣、红坡顶",
     (575, 290, 645, 360), {}),
    ("top", "07_工程楼拱门_俯视.png", "工程楼拱门（正立面）",
     "X 1000–1075，Z 480–530｜粉棕石拱门 + 奶油翼 + 8 级台阶",
     (1000, 480, 1075, 530), {"scale": 4}),
    ("iso", "07b_工程楼拱门_斜视.png", "工程楼拱门（正立面）",
     "X 1005–1065，Z 485–525｜斜视：拱门、台阶、奶油翼、红坡顶塔楼",
     (1005, 485, 1065, 525), {}),
    ("top", "08_工程楼内院_俯视.png", "工程楼内院",
     "X 1000–1075，Z 480–530｜俯视只见红坡顶与连廊，院子立面从上看不见",
     (1000, 480, 1075, 530), {"scale": 4}),
    ("iso", "08b_工程楼内院_斜视.png", "工程楼内院（北侧视角）",
     "X 1005–1065，Z 485–525｜从北侧斜视：北立面棕奶油墙、蓝玻璃窗带、红坡顶",
     (1005, 485, 1065, 525), {"flip": True}),
    ("top", "09_东门_俯视.png", "东门",
     "X 1600–1680，Z 720–790｜门洞 X1636–1637、Z743–755，高 7 格（估算），前后接路",
     (1600, 720, 1680, 790), {"scale": 4}),
    ("iso", "09b_东门_斜视.png", "东门",
     "X 1620–1660，Z 730–770｜斜视：双柱、顶梁、牌匾带、两侧小门与围墙",
     (1620, 730, 1660, 770), {}),
    ("top", "10_篮球场信息北楼北侧_俯视.png", "篮球场（信息北楼北侧）",
     "X 1125–1245，Z 465–520｜6 场，绿面 + 白线 + 红边",
     (1125, 465, 1245, 520), {"scale": 3}),
    ("top", "11_篮球场西区运动场_俯视.png", "篮球场（西区运动场）",
     "X 675–845，Z 178–245｜8 场，绿面 + 白线 + 红边",
     (675, 178, 845, 245), {"scale": 3}),
    ("top", "12_足球场_俯视.png", "足球场（西区运动场）",
     "X 670–760，Z 240–365｜绿草 + 白线 + 红跑道 + 球门，无看台",
     (670, 240, 760, 365), {"scale": 3}),
    ("top", "13_山海北路_俯视.png", "山海北路（中央东西主干道）",
     "X 900–1450，Z 340–410｜灰沥青 + 白虚线 + 斑马线（OSM 路名：高峪路）",
     (900, 340, 1450, 410), {"scale": 2}),
    ("top", "14_融合中路_俯视.png", "融合中路（浩海广场东侧）",
     "X 1300–1440，Z 610–800｜灰沥青 + 灰石墩，东接海军路",
     (1300, 610, 1440, 800), {"scale": 2}),
    ("top", "15_信息楼_俯视.png", "信息楼（v4 已改）",
     "X 975–1110，Z 485–860｜南北两楼 + 院子 + 西端白楼，浅灰屋顶",
     (975, 485, 1110, 860), {"scale": 3}),
    ("iso", "15b_信息楼_斜视.png", "信息楼（v4 已改）",
     "X 975–1110，Z 485–860｜斜视：南北楼、院子、白楼、主入口台阶",
     (975, 485, 1110, 860), {}),
]

MARKERS = [
    (1205, 700, "1"), (1300, 700, "2"), (1310, 275, "3"), (1207, 320, "4"),
    (610, 325, "5"), (1035, 505, "6"), (1636, 749, "7"), (1185, 493, "8"),
    (760, 212, "9"), (714, 303, "10"), (1180, 374, "11"), (1370, 700, "12"),
    (1050, 700, "13"),
]
LEGEND = ["1 学习综合体", "2 浩海广场", "3 听海苑", "4 听海餐厅",
          "5 望海餐厅", "6 工程楼", "7 东门", "8 篮球场·信息北楼北侧",
          "9 篮球场·西区运动场", "10 足球场", "11 山海北路",
          "12 融合中路", "13 信息楼"]


def overview(tm):
    # world bounds from existing chunks
    xs, zs = [], []
    for rf in sorted((WORLD / "region").glob("r.*.*.mca")):
        rx, rz = int(rf.name.split(".")[1]), int(rf.name.split(".")[2])
        region = read_region(rf)
        for (lx, lz) in region:
            xs.append((rx * 32 + lx) * 16)
            zs.append((rz * 32 + lz) * 16)
    x0, x1 = min(xs), max(xs) + 15
    z0, z1 = min(zs), max(zs) + 15
    img = top_image(tm, x0, z0, x1, z1, "全校总览",
                    f"X {x0}–{x1}，Z {z0}–{z1}｜红圈数字见下方图例", scale=1,
                    markers=[(mx, mz, lab) for (mx, mz, lab) in MARKERS])
    # legend bar: extend label with legend lines
    w = img.width
    extra_h = 200
    bar = Image.new("RGB", (w, extra_h), (255, 255, 255))
    d = ImageDraw.Draw(bar)
    d.line([(0, 0), (w, 0)], fill=(180, 180, 180), width=2)
    cols = [LEGEND[i::3] for i in range(3)]
    for ci, col in enumerate(cols):
        y = 14
        for item in col:
            d.text((16 + ci * (w // 3), y), item, font=font(21), fill=(20, 20, 20))
            y += 32
    out = Image.new("RGB", (w, img.height + extra_h), (255, 255, 255))
    out.paste(img, (0, 0))
    out.paste(bar, (0, img.height))
    out.save(OUT / "00_全校总览_俯视.png")
    print("overview saved", out.size)


def main():
    tm = TopMaps(WORLD)
    for kind, fname, title, subtitle, bbox, kw in JOBS:
        x0, z0, x1, z1 = bbox
        if kind == "top":
            img = top_image(tm, x0, z0, x1, z1, title, subtitle, **kw)
        else:
            img = iso_image(tm, x0, z0, x1, z1, title, subtitle, **kw)
        img.save(OUT / fname)
        print("saved", fname, img.size, flush=True)
    overview(tm)
    if UNKNOWN:
        print("UNKNOWN BLOCKS:", sorted(UNKNOWN))


if __name__ == "__main__":
    main()
