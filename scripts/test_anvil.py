#!/usr/bin/env python3
"""Round-trip test for anvil.py Properties preservation (v3 gate).

1. Decode every section of every chunk in a region file; re-encode without
   changes; assert the palette (full state strings) is identical.
2. Use set_blocks_in_chunk to place a 2-block oak door with full state in a
   section that already holds stateful blocks (stairs/trapdoors), then
   decode again and assert both the door states and the pre-existing states
   survived byte-for-byte at the palette level.
"""
import sys
import zlib
from collections import Counter

sys.path.insert(0, "/home/hatch/workspace/minecraft-ouc")
from anvil import (decode_indices, encode_indices, find, loads, dumps,
                   read_region, set_blocks_in_chunk, parse_state)

REGION = sys.argv[1] if len(sys.argv) > 1 else "/tmp/test_r11.mca"

raw = read_region(REGION)
print(f"chunks in region: {len(raw)}")

stateful_before = Counter()
roundtrip_bad = 0
chunks_checked = 0
for (lx, lz), (comp, _ts) in sorted(raw.items()):
    root = loads(zlib.decompress(comp))
    _, _, root_nodes = root
    _t, sections = find(root_nodes, "sections")[1]
    for sec_nodes in sections:
        bs = None
        for node in sec_nodes:
            if node[1] == "block_states":
                bs = node[2]
                break
        if bs is None:
            continue
        indices, names = decode_indices(bs)
        for n in names:
            if "[" in n:
                stateful_before[n.split("[")[0]] += 1
        # Re-encode with no changes and compare palettes exactly.
        new_bs = encode_indices(indices, names)
        idx2, names2 = decode_indices(new_bs)
        if names2 != names or idx2 != indices:
            roundtrip_bad += 1
            print(f"  MISMATCH chunk ({lx},{lz}) section Y={find(sec_nodes,'Y')[1]}")
            print(f"    before: {names}")
            print(f"    after:  {names2}")
    chunks_checked += 1

print(f"chunks checked: {chunks_checked}, round-trip mismatches: {roundtrip_bad}")
print("stateful block types in region (palette occurrences):")
for k, v in stateful_before.most_common(20):
    print(f"  {k}: {v}")

# --- Door insertion test on the first chunk that has a stateful section ---
DOOR_LOWER = "minecraft:oak_door[facing=north,half=lower,hinge=left,open=false,powered=false]"
DOOR_UPPER = "minecraft:oak_door[facing=north,half=upper,hinge=left,open=false,powered=false]"

tested = False
for (lx, lz), (comp, _ts) in sorted(raw.items()):
    root = loads(zlib.decompress(comp))
    _, _, root_nodes = root
    _t, sections = find(root_nodes, "sections")[1]
    # Find a section that already has a stateful palette entry.
    target_sec = None
    target_states = None
    for sec_nodes in sections:
        for node in sec_nodes:
            if node[1] == "block_states":
                _i, names = decode_indices(node[2])
                if any("[" in n for n in names):
                    target_sec = find(sec_nodes, "Y")[1]
                    target_states = sorted(n for n in names if "[" in n)
                    break
        if target_sec is not None:
            break
    if target_sec is None:
        continue
    # Place door at local (8, y, 8) where y is inside that section.
    y0 = target_sec * 16 + 4
    edits = {(8, y0, 8): DOOR_LOWER, (8, y0 + 1, 8): DOOR_UPPER}
    changed = set_blocks_in_chunk(root, edits)
    # Re-decode the edited section and check.
    _, _, root_nodes2 = root
    _t2, sections2 = find(root_nodes2, "sections")[1]
    ok = False
    for sec_nodes in sections2:
        if find(sec_nodes, "Y")[1] == target_sec:
            for node in sec_nodes:
                if node[1] == "block_states":
                    idx2, names2 = decode_indices(node[2])
                    got_lower = names2[idx2[(y0 % 16) * 256 + 8 * 16 + 8]]
                    got_upper = names2[idx2[((y0 + 1) % 16) * 256 + 8 * 16 + 8]]
                    survived = all(s in names2 for s in target_states)
                    print(f"\ndoor test chunk ({lx},{lz}) section Y={target_sec}:")
                    print(f"  changed cells: {changed}")
                    print(f"  lower: {got_lower}")
                    print(f"  upper: {got_upper}")
                    print(f"  pre-existing states survived: {survived} ({len(target_states)} states)")
                    print(f"  door lower ok: {got_lower == DOOR_LOWER}, upper ok: {got_upper == DOOR_UPPER}")
                    ok = (got_lower == DOOR_LOWER and got_upper == DOOR_UPPER and survived)
                    break
    print("DOOR TEST:", "PASS" if ok else "FAIL")
    tested = True
    break

if not tested:
    print("no stateful section found for door test")
print("ROUND-TRIP:", "PASS" if roundtrip_bad == 0 else "FAIL")
