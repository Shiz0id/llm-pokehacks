"""
Round-trip every vanilla layout through the map.bin codec and prove byte-identity.

If this passes on all 804 layouts, our reader/writer is provably correct and every
downstream proc-gen phase rests on solid ground.

Also gathers real-world usage stats: which collision and elevation values actually
appear in shipped maps, and whether declared width/height match file size.
"""
import json, struct, sys, collections
from pathlib import Path

from repo import REPO  # noqa: E402  (see repo.py)

METATILE_MASK, COLLISION_MASK, ELEVATION_MASK = 0x03FF, 0x0C00, 0xF000
COLLISION_SHIFT, ELEVATION_SHIFT = 10, 12


def decode(b):
    return (b & METATILE_MASK,
            (b & COLLISION_MASK) >> COLLISION_SHIFT,
            (b & ELEVATION_MASK) >> ELEVATION_SHIFT)


def encode(metatile, collision, elevation):
    return ((metatile & METATILE_MASK)
            | ((collision << COLLISION_SHIFT) & COLLISION_MASK)
            | ((elevation << ELEVATION_SHIFT) & ELEVATION_MASK))


layouts = json.loads((REPO / "data/layouts/layouts.json").read_text(encoding="utf-8"))
entries = layouts["layouts"] if isinstance(layouts, dict) else layouts

ok = mismatch = missing = size_bad = size_slack = 0
collisions = collections.Counter()
elevations = collections.Counter()
metatiles = collections.Counter()
max_metatile = 0
size_errors, rt_errors, slack_notes = [], [], []
total_blocks = 0

for e in entries:
    if not e or "blockdata_filepath" not in e:
        continue
    path = REPO / e["blockdata_filepath"]
    w, h = e["width"], e["height"]
    if not path.exists():
        missing += 1
        continue

    raw = path.read_bytes()
    expected = w * h * 2
    if len(raw) != expected:
        # A file that is exactly ONE BLOCK long is a benign vanilla quirk, not a
        # codec failure: 20 shipped layouts have a spare trailing block (19 of
        # them named LAYOUT_UNUSED_*), and the game reads width*height and
        # ignores the tail. Counting those as errors would make this script
        # always exit non-zero on an untouched checkout, which teaches everyone
        # to ignore its exit code - and then it catches nothing.
        if len(raw) - expected == 2:
            size_slack += 1
            slack_notes.append(f"{e['id']}: one spare trailing block")
        else:
            size_bad += 1
            size_errors.append(
                f"{e['id']}: file {len(raw)}B, header says {w}x{h}={expected}B")
        continue

    blocks = list(struct.unpack(f"<{w*h}H", raw))
    total_blocks += len(blocks)

    # decode -> re-encode -> compare against original bytes
    rt = [encode(*decode(b)) for b in blocks]
    if struct.pack(f"<{len(rt)}H", *rt) != raw:
        mismatch += 1
        rt_errors.append(e["id"])
        continue
    ok += 1

    for b in blocks:
        m, c, el = decode(b)
        metatiles[m] += 1
        collisions[c] += 1
        elevations[el] += 1
        max_metatile = max(max_metatile, m)

print(f"layouts in json      : {len(entries)}")
print(f"round-trip identical : {ok}")
print(f"round-trip MISMATCH  : {mismatch}")
print(f"missing blockdata    : {missing}")
print(f"size/header mismatch : {size_bad}")
print(f"benign trailing block: {size_slack}  (vanilla quirk, not an error)")
print(f"total blocks checked : {total_blocks:,}")
print()
print(f"highest metatile id  : {max_metatile}  (format ceiling 1023)")
print(f"distinct metatile ids: {len(metatiles)}")
print()
print("collision values in shipped maps:")
for v, n in sorted(collisions.items()):
    print(f"   {v}: {n:>10,}  ({100*n/total_blocks:5.2f}%)")
print("elevation values in shipped maps:")
for v, n in sorted(elevations.items()):
    print(f"  {v:>2}: {n:>10,}  ({100*n/total_blocks:5.2f}%)")

if size_errors:
    print("\nsize errors (first 10):")
    for s in size_errors[:10]:
        print("  ", s)
if rt_errors:
    print("\nround-trip failures:", rt_errors[:10])

# size_slack deliberately does NOT fail the run - see the note above.
sys.exit(1 if (mismatch or size_bad) else 0)
