"""Compare the two source worlds inside the Info North box, cell by cell.

Box: X 1018-1098, Z 536-611, all Y.  Prints a diff report to stdout and
to compare_v1_report.txt next to this script.
"""
import sys, zlib
from collections import Counter
from pathlib import Path

sys.path.insert(0, r"C:\Users\lenovo\Documents\Codex\2026-11-25\wo\work\ouc-campus")
import anvil

SAVES = Path(r"C:\Users\lenovo\Desktop\Games\.minecraft\versions\26.2-Fabric 0.19.3\saves")
SAMPLE = SAVES / "OUC-West-Coast-InfoNorth-Sample"
FULL = SAVES / "OUC-West-Coast-AlignedRevision"

X0, X1, Z0, Z1 = 1018, 1098, 536, 611


def load_box(world):
    """Return {(x, y, z): block_name} for the box."""
    out = {}
    for cx in range(X0 // 16, X1 // 16 + 1):
        for cz in range(Z0 // 16, Z1 // 16 + 1):
            region = world / "region" / f"r.{cx // 32}.{cz // 32}.mca"
            chunks = anvil.read_region(region)
            key = (cx % 32, cz % 32)
            if key not in chunks:
                print(f"  !! chunk {(cx, cz)} missing in {world.name}")
                continue
            raw, _ts = chunks[key]
            root = anvil.loads(zlib.decompress(raw))
            _, _, root_nodes = root
            sections_node = anvil.find_node(root_nodes, "sections")
            _, sections = sections_node[2]
            for sec_nodes in sections:
                sec_y = anvil.find(sec_nodes, "Y")[1]
                bs_node = anvil.find_node(sec_nodes, "block_states")
                if bs_node is None:
                    continue
                indices, names = anvil.decode_indices(bs_node[2])
                for i, idx in enumerate(indices):
                    ly, rem = divmod(i, 256)
                    lz, lx = divmod(rem, 16)
                    gx, gy, gz = cx * 16 + lx, sec_y * 16 + ly, cz * 16 + lz
                    if X0 <= gx <= X1 and Z0 <= gz <= Z1:
                        out[(gx, gy, gz)] = names[idx]
    return out


def top_map(box):
    """Highest non-air block per (x, z)."""
    top = {}
    for (x, y, z), b in box.items():
        if b == "minecraft:air":
            continue
        k = (x, z)
        if k not in top or y > top[k][0]:
            top[k] = (y, b)
    return top


def main():
    lines = []
    def log(s=""):
        print(s)
        lines.append(s)

    log("loading sample box...")
    s = load_box(SAMPLE)
    log(f"sample cells in box: {len(s)}")
    log("loading full box...")
    f = load_box(FULL)
    log(f"full cells in box: {len(f)}")

    keys = set(s) | set(f)
    diffs = []
    for k in sorted(keys):
        a, b = s.get(k, "minecraft:air"), f.get(k, "minecraft:air")
        if a != b:
            diffs.append((k, a, b))
    log(f"total cells compared: {len(keys)}")
    log(f"DIFFERING cells: {len(diffs)}")
    pairs = Counter((a, b) for _, a, b in diffs)
    log("diff pairs (sample -> full), top 40:")
    for (a, b), n in pairs.most_common(40):
        log(f"  {n:6d}  {a} -> {b}")
    by_y = Counter(k[1] for k, _, _ in diffs)
    log("diffs by Y:")
    for y in sorted(by_y):
        log(f"  Y={y}: {by_y[y]}")

    # targeted checks: three footprints, courtyard, roofs
    def rect_count(box, x0, x1, z0, z1, y, want=None):
        c = Counter()
        for x in range(x0, x1 + 1):
            for z in range(z0, z1 + 1):
                b = box.get((x, y, z), "minecraft:air")
                c[b] += 1
        return c

    log("--- courtyard 25 blocks Y=-45 X1044-1048 Z569-573 ---")
    log(f"  sample: {dict(rect_count(s, 1044, 1048, 569, 573, -45))}")
    log(f"  full:   {dict(rect_count(f, 1044, 1048, 569, 573, -45))}")

    log("--- top block per footprint (roof check) ---")
    for name, (x0, x1, z0, z1) in {
        "long wing": (1018, 1089, 540, 557),
        "main": (1050, 1098, 582, 611),
        "west wing": (1018, 1037, 558, 611),
    }.items():
        for label, box in (("sample", s), ("full", f)):
            tops = Counter()
            for x in range(x0, x1 + 1):
                for z in range(z0, z1 + 1):
                    for y in range(40, -64, -1):
                        b = box.get((x, y, z), "minecraft:air")
                        if b != "minecraft:air":
                            tops[(y, b)] += 1
                            break
            log(f"  {name} {label}: {dict(tops)}")

    # walkway ground check: top non-air block in the courtyard gap + south of main
    log("--- ground top-block between wings (courtyard X1038-1049 Z558-581) ---")
    for label, box in (("sample", s), ("full", f)):
        c = Counter()
        for x in range(1038, 1050):
            for z in range(558, 582):
                for y in range(40, -64, -1):
                    b = box.get((x, y, z), "minecraft:air")
                    if b != "minecraft:air":
                        c[(y, b)] += 1
                        break
        log(f"  {label}: {dict(c)}")

    log("--- diff cells outside the three footprints + courtyard ---")
    def inside(x, z):
        return ((1018 <= x <= 1089 and 540 <= z <= 557)
                or (1050 <= x <= 1098 and 582 <= z <= 611)
                or (1018 <= x <= 1037 and 558 <= z <= 611)
                or (1038 <= x <= 1049 and 558 <= z <= 581))
    outside = [(k, a, b) for k, a, b in diffs if not inside(k[0], k[2])]
    log(f"  outside count: {len(outside)}")
    for (k, a, b) in outside[:60]:
        log(f"    {k} {a} -> {b}")

    Path(__file__).with_name("compare_v1_report.txt").write_text(
        "\n".join(lines), encoding="utf-8")
    log("report written.")


if __name__ == "__main__":
    main()
