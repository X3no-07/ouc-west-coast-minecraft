"""Extended diff: a wider ring around Info North (walkway strips to the roads).

Box: X 1000-1120, Z 520-630, all Y.  Counts differing cells only.
"""
import sys, zlib
from pathlib import Path

sys.path.insert(0, r"C:\Users\lenovo\Documents\Codex\2026-11-25\wo\work\ouc-campus")
import anvil

SAVES = Path(r"C:\Users\lenovo\Desktop\Games\.minecraft\versions\26.2-Fabric 0.19.3\saves")
X0, X1, Z0, Z1 = 1000, 1120, 520, 630


def load_box(world):
    out = {}
    for cx in range(X0 // 16, X1 // 16 + 1):
        for cz in range(Z0 // 16, Z1 // 16 + 1):
            region = world / "region" / f"r.{cx // 32}.{cz // 32}.mca"
            chunks = anvil.read_region(region)
            key = (cx % 32, cz % 32)
            if key not in chunks:
                continue
            raw, _ = chunks[key]
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


s = load_box(SAVES / "OUC-West-Coast-InfoNorth-Sample")
f = load_box(SAVES / "OUC-West-Coast-AlignedRevision")
diffs = [(k, s.get(k, "minecraft:air"), f.get(k, "minecraft:air"))
         for k in set(s) | set(f)
         if s.get(k, "minecraft:air") != f.get(k, "minecraft:air")]
print(f"cells compared: {len(set(s) | set(f))}, differing: {len(diffs)}")
from collections import Counter
print("by Y:", dict(sorted(Counter(k[1] for k, _, _ in diffs).items())))
print("pairs:", Counter((a, b) for _, a, b in diffs).most_common(10))
for k, a, b in diffs[:20]:
    print(" ", k, a, "->", b)
