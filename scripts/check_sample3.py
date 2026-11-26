"""Walkability BFS on the built sample world (read-only).
A cell is walkable if the ground (highest solid at y<=-44, or -45/-46)
is within 1 of its neighbour and the two blocks above the ground are air.
"""
import sys
from collections import deque
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from finish_world import World  # noqa: E402

PASSABLE = {"minecraft:air", "minecraft:short_grass", "minecraft:tall_grass",
            "minecraft:fern", "minecraft:dead_bush", "minecraft:snow"}


def ground(w, x, z):
    """Highest solid block at y <= -44; None if none."""
    for y in range(-44, -64, -1):
        name = w.get_block(x, y, z)
        if name and name != "minecraft:air":
            return y, name
    return None, None


def walkable(w, x, z):
    y, name = ground(w, x, z)
    if y is None:
        return None
    # headroom: the two blocks above the ground must be passable
    for yy in (y + 1, y + 2):
        n = w.get_block(x, yy, z)
        if n not in PASSABLE:
            return None
    return y


def bfs(w, cells, start, goals):
    walk = {c: walkable(w, *c) for c in cells}
    if walk.get(start) is None:
        return None, "start not walkable"
    seen = {start}
    q = deque([start])
    while q:
        cur = q.popleft()
        if cur in goals:
            return cur, f"reached {cur} ground_y={walk[cur]}"
        for (dx, dz) in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nb = (cur[0] + dx, cur[1] + dz)
            if nb in walk and nb not in seen and walk[nb] is not None:
                if abs(walk[nb] - walk[cur]) <= 1:
                    seen.add(nb)
                    q.append(nb)
    return None, f"no path; {len(seen)}/{len(cells)} cells reachable"


def main():
    w = World(Path(sys.argv[1]))
    # South walkway: from main south door (Z612) to the south road (Z628).
    cells = {(x, z) for x in range(1072, 1077) for z in range(612, 629)}
    end, msg = bfs(w, cells, (1074, 612), {(x, 628) for x in range(1072, 1077)})
    print("south walkway:", msg)
    # West walkway: from west wing west door (X1017) to the west road (X997).
    cells = {(x, z) for x in range(997, 1018) for z in range(583, 591)}
    end, msg = bfs(w, cells, (1017, 586), {(997, z) for z in range(583, 591)})
    print("west walkway:", msg)
    # Courtyard to south walkway: from courtyard centre to the main south door.
    cells = {(x, z) for x in range(1037, 1050) for z in range(557, 612)}
    end, msg = bfs(w, cells, (1044, 571), {(x, 611) for x in range(1044, 1050)})
    print("courtyard -> main south edge:", msg)
    # What is at (1017,590) above the ground?
    print("column (1017,590):",
          [(y, w.get_block(1017, y, 590)) for y in range(-46, -39)
           if w.get_block(1017, y, 590) != "minecraft:air"])
    print("column (1076,612):",
          [(y, w.get_block(1076, y, 612)) for y in range(-46, -21)
           if w.get_block(1076, y, 612) != "minecraft:air"][:8])
    print("column (1076,613):",
          [(y, w.get_block(1076, y, 613)) for y in range(-46, -43)
           if w.get_block(1076, y, 613) != "minecraft:air"])


if __name__ == "__main__":
    main()
