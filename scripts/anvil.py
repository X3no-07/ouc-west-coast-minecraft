"""Minimal typed NBT + Anvil region read/write for the campus finish pass.

Why this exists: Arnis 3.5.0 picks flat-roof cover blocks at random from a
palette (see build notes), so a deterministic finish pass edits only the
cells it is told to, inside one building footprint / one paving polygon at
a time.  It never does a global find-and-replace.

Design:
  * NBT is parsed into typed nodes so re-serialising preserves every tag
    type of the untouched parts of a chunk.  A node is a tuple
    (tag_id, name, value); values are Python ints/floats/str/bytes, lists
    are (elem_tag_id, [nodes]), compounds are [nodes], int/long arrays are
    lists of ints.
  * Only the chunks that contain an edited cell are rewritten, and only
    their compressed payload changes; every other chunk is copied
    byte-for-byte.  The region file is rebuilt with a fresh sector table.
  * block_states indices use Minecraft order: index = y*256 + z*16 + x
    inside a 16x16x16 section (verified against rules_preview.py).

Only the Java (Anvil) format is supported.  Compression type 2 (zlib).
"""
import struct
import zlib
from pathlib import Path

TAG_END = 0
TAG_BYTE = 1
TAG_SHORT = 2
TAG_INT = 3
TAG_LONG = 4
TAG_FLOAT = 5
TAG_DOUBLE = 6
TAG_BYTE_ARRAY = 7
TAG_STRING = 8
TAG_LIST = 9
TAG_COMPOUND = 10
TAG_INT_ARRAY = 11
TAG_LONG_ARRAY = 12

_FMT = {TAG_BYTE: (">b", 1), TAG_SHORT: (">h", 2), TAG_INT: (">i", 4),
        TAG_LONG: (">q", 8), TAG_FLOAT: (">f", 4), TAG_DOUBLE: (">d", 8)}


class NBTError(ValueError):
    pass


class Reader:
    def __init__(self, data):
        self.data = data
        self.pos = 0

    def read(self, n):
        out = self.data[self.pos:self.pos + n]
        if len(out) != n:
            raise NBTError("truncated NBT")
        self.pos += n
        return out

    def u8(self):
        return self.read(1)[0]

    def u16(self):
        return struct.unpack(">H", self.read(2))[0]

    def i32(self):
        return struct.unpack(">i", self.read(4))[0]

    def string(self):
        return self.read(self.u16()).decode("utf-8")

    def payload(self, tag):
        if tag in _FMT:
            fmt, size = _FMT[tag]
            return struct.unpack(fmt, self.read(size))[0]
        if tag == TAG_BYTE_ARRAY:
            n = self.i32()
            return bytes(self.read(n))
        if tag == TAG_STRING:
            return self.string()
        if tag == TAG_LIST:
            elem = self.u8()
            n = self.i32()
            return (elem, [self.payload(elem) for _ in range(n)])
        if tag == TAG_COMPOUND:
            return self.compound()
        if tag == TAG_INT_ARRAY:
            n = self.i32()
            return [struct.unpack(">i", self.read(4))[0] for _ in range(n)]
        if tag == TAG_LONG_ARRAY:
            n = self.i32()
            return [struct.unpack(">q", self.read(8))[0] for _ in range(n)]
        raise NBTError(f"unknown tag {tag}")

    def compound(self):
        nodes = []
        while True:
            tag = self.u8()
            if tag == TAG_END:
                return nodes
            name = self.string()
            nodes.append((tag, name, self.payload(tag)))

    def root(self):
        tag = self.u8()
        if tag != TAG_COMPOUND:
            raise NBTError("root must be a compound")
        name = self.string()
        return (tag, name, self.compound())


def _write_string(buf, s):
    raw = s.encode("utf-8")
    buf += struct.pack(">H", len(raw)) + raw


def _write_payload(buf, tag, value):
    if tag in _FMT:
        fmt, _ = _FMT[tag]
        buf += struct.pack(fmt, value)
    elif tag == TAG_BYTE_ARRAY:
        buf += struct.pack(">i", len(value)) + bytes(value)
    elif tag == TAG_STRING:
        _write_string(buf, value)
    elif tag == TAG_LIST:
        elem, items = value
        buf += struct.pack(">b", elem) + struct.pack(">i", len(items))
        for item in items:
            _write_payload(buf, elem, item)
    elif tag == TAG_COMPOUND:
        for child_tag, name, child_val in value:
            buf.append(child_tag)
            _write_string(buf, name)
            _write_payload(buf, child_tag, child_val)
        buf.append(TAG_END)
    elif tag == TAG_INT_ARRAY:
        buf += struct.pack(">i", len(value))
        for v in value:
            buf += struct.pack(">i", v)
    elif tag == TAG_LONG_ARRAY:
        buf += struct.pack(">i", len(value))
        for v in value:
            buf += struct.pack(">q", v)
    else:
        raise NBTError(f"unknown tag {tag}")


def dumps(root):
    tag, name, value = root
    buf = bytearray()
    buf.append(tag)
    _write_string(buf, name)
    _write_payload(buf, tag, value)
    return bytes(buf)


def loads(data):
    return Reader(data).root()


# ---- compound helpers -------------------------------------------------
def find(compound_nodes, name):
    for tag, n, val in compound_nodes:
        if n == name:
            return (tag, val)
    return None


def find_node(compound_nodes, name):
    for node in compound_nodes:
        if node[1] == name:
            return node
    return None


# ---- block_states -----------------------------------------------------
def _bits_for_palette(n):
    return max(4, (n - 1).bit_length())


def decode_indices(block_states):
    """Return (indices list[4096], palette_names list) for one section."""
    tag, palette = find(block_states, "palette")
    if palette is None:
        return None, None
    names = []
    for compound_value in palette[1]:
        name = find(compound_value, "Name")[1]
        names.append(name)
    if len(names) == 1:
        return [0] * 4096, names
    _, data = find(block_states, "data")
    bits = _bits_for_palette(len(names))
    per_word = 64 // bits
    mask = (1 << bits) - 1
    indices = [0] * 4096
    for i in range(4096):
        word = data[i // per_word] & 0xFFFFFFFFFFFFFFFF
        indices[i] = (word >> ((i % per_word) * bits)) & mask
    return indices, names


def encode_indices(indices, names):
    """Build a new block_states value (list of nodes) for the given cells."""
    bits = _bits_for_palette(len(names))
    per_word = 64 // bits
    words = [0] * ((4096 + per_word - 1) // per_word)
    for i, idx in enumerate(indices):
        words[i // per_word] |= (idx & ((1 << bits) - 1)) << ((i % per_word) * bits)
    # Convert to signed 64-bit for NBT long storage.
    signed = [w - (1 << 64) if w >= (1 << 63) else w for w in words]
    palette_nodes = []
    for name in names:
        # A list item is a compound *value* (a list of nodes), not a node.
        palette_nodes.append([(TAG_STRING, "Name", name)])
    nodes = [(TAG_LIST, "palette", (TAG_COMPOUND, palette_nodes))]
    if len(names) > 1:
        nodes.append((TAG_LONG_ARRAY, "data", signed))
    return nodes


def block_index(x, y, z):
    """Index inside a section: x/z 0..15 local, y 0..15 within section."""
    return y * 256 + z * 16 + x


# ---- region files -----------------------------------------------------
def read_region(region_path):
    """Return { (cx, cz): (compressed_bytes, timestamp) } for present chunks."""
    data = Path(region_path).read_bytes()
    if len(data) < 8192 or len(data) % 4096 != 0:
        raise NBTError(f"bad region file {region_path}")
    out = {}
    for i in range(1024):
        off = int.from_bytes(data[i * 4:i * 4 + 3], "big")
        cnt = data[i * 4 + 3]
        if off == 0:
            continue
        cx, cz = i % 32, i // 32
        start = off * 4096
        length = int.from_bytes(data[start:start + 4], "big")
        comp = data[start + 4]
        if comp != 2:
            raise NBTError(f"chunk {(cx, cz)} compression {comp} != zlib")
        out[(cx, cz)] = (data[start + 5:start + 4 + length], int.from_bytes(data[4096 + i * 4:4096 + i * 4 + 4], "big"))
    return out


def read_chunk_nbt(region_path, cx, cz):
    chunks = read_region(region_path)
    raw = chunks[(cx, cz)][0]
    return loads(zlib.decompress(raw))


def write_region(region_path, chunks):
    """chunks: {(cx, cz): (compressed_bytes, timestamp)}; rebuild the file."""
    # chunks are stored in sector order; assign sectors sequentially.
    header = bytearray(8192)
    body = bytearray()
    sector = 2
    for (cx, cz) in sorted(chunks):
        # Chunk keys are LOCAL coords inside this region file (0..31).
        raw, ts = chunks[(cx, cz)]
        payload = struct.pack(">I", len(raw) + 1) + bytes([2]) + raw
        n_sectors = (len(payload) + 4095) // 4096
        payload = payload + b"\x00" * (n_sectors * 4096 - len(payload))
        idx = (cz % 32) * 32 + (cx % 32)
        header[idx * 4:idx * 4 + 3] = sector.to_bytes(3, "big")
        header[idx * 4 + 3] = n_sectors
        header[4096 + idx * 4:4096 + idx * 4 + 4] = struct.pack(">I", ts)
        body += payload
        sector += n_sectors
    Path(region_path).write_bytes(bytes(header) + bytes(body))


def set_blocks_in_chunk(chunk_root, edits):
    """edits: {(x, y, z) global-in-chunk (0..15, any Y, 0..15): new_block_name}
    Returns the number of cells changed.  chunk_root is mutated in place
    (its section nodes are replaced where needed)."""
    _, _, root_nodes = chunk_root
    sections_node = find_node(root_nodes, "sections")
    if sections_node is None:
        raise NBTError("chunk has no sections")
    _, sections = sections_node[2]  # list payload: (elem_tag, [compound values])
    # sections is the list of compound values; each value is a node list.
    by_y = {}
    for sec_nodes in sections:
        y = find(sec_nodes, "Y")[1]
        by_y[y] = sec_nodes
    changed = 0
    # Group edits by section.
    per_section = {}
    for (x, y, z), block in edits.items():
        per_section.setdefault(y // 16, []).append((x, y % 16, z, block))
    for sec_y, items in per_section.items():
        sec_nodes = by_y.get(sec_y)
        if sec_nodes is None:
            raise NBTError(f"chunk has no section Y={sec_y}")
        bs_node = find_node(sec_nodes, "block_states")
        if bs_node is None:
            raise NBTError(f"section Y={sec_y} has no block_states")
        indices, names = decode_indices(bs_node[2])
        names = list(names)
        for x, ly, z, block in items:
            idx = block_index(x, ly, z)
            if block not in names:
                names.append(block)
            new_idx = names.index(block)
            if indices[idx] != new_idx:
                indices[idx] = new_idx
                changed += 1
        new_bs = encode_indices(indices, names)
        # Replace the block_states node in place.
        for i, node in enumerate(sec_nodes):
            if node[1] == "block_states":
                sec_nodes[i] = (TAG_COMPOUND, "block_states", new_bs)
                break
    return changed
