"""Refresh LastPlayed on the installed v2 world (anvil.py NBT, no nbtlib)."""
import gzip
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from anvil import dumps, find, find_node, loads  # noqa: E402

SAVES = Path(r"C:\Users\lenovo\Desktop\Games\.minecraft\versions\26.2-Fabric 0.19.3\saves")
WORLDS = ["OUC-West-Coast-v2"]
now_ms = int(time.time() * 1000)
for w in WORLDS:
    p = SAVES / w / "level.dat"
    shutil.copyfile(p, p.with_name("level.dat.bak-lastplayed"))
    root = loads(gzip.decompress(p.read_bytes()))
    assert root[0] == 10 and root[1] == ""
    data = find_node(root[2], "Data")
    assert data is not None
    tag, old = find(data[2], "LastPlayed")
    assert tag == 4, tag
    print(w, "before: LevelName=", find(data[2], "LevelName")[1], "LastPlayed=", old)
    data_nodes = [(t, n, now_ms if n == "LastPlayed" else v) for (t, n, v) in data[2]]
    new_root = (root[0], root[1],
                [(t, n, data_nodes if n == "Data" else v) for (t, n, v) in root[2]])
    p.write_bytes(gzip.compress(dumps(new_root), compresslevel=6))
    root2 = loads(gzip.decompress(p.read_bytes()))
    data2 = find_node(root2[2], "Data")
    print(w, "after:  LevelName=", find(data2[2], "LevelName")[1],
          "LastPlayed=", find(data2[2], "LastPlayed")[1])
    assert find(data2[2], "LastPlayed")[1] == now_ms
print("done", now_ms)
