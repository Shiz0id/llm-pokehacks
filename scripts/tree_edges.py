"""Find the tiles vanilla uses at the top and bottom edge of a tree mass."""
import json, struct, collections
from pathlib import Path

from repo import REPO  # noqa: E402  (see repo.py)
L = json.loads((REPO / 'data/layouts/layouts.json').read_text(encoding='utf-8'))

# every General+Rustboro layout, for a bigger sample than Petalburg alone
layouts = [x for x in (L['layouts'] if isinstance(L, dict) else L)
           if x and x.get('primary_tileset') == 'gTileset_General'
           and x.get('secondary_tileset') == 'gTileset_Rustboro']

top_edge = collections.Counter()
bottom_edge = collections.Counter()
total_blocked = collections.Counter()

for e in layouts:
    w, h = e['width'], e['height']
    raw = (REPO / e['blockdata_filepath']).read_bytes()
    if len(raw) != w * h * 2:
        continue
    b = struct.unpack(f'<{w*h}H', raw)
    blocked = lambda x, y: ((b[y*w+x] >> 10) & 3) != 0 if 0 <= x < w and 0 <= y < h else True
    mt = lambda x, y: b[y*w+x] & 0x3FF if 0 <= x < w and 0 <= y < h else -1

    for y in range(h):
        for x in range(w):
            if not blocked(x, y):
                continue
            total_blocked[mt(x, y)] += 1
            if not blocked(x, y - 1):      # open above -> top edge of a mass
                top_edge[mt(x, y)] += 1
            if not blocked(x, y + 1):      # open below -> bottom edge
                bottom_edge[mt(x, y)] += 1

print(f'layouts sampled: {len(layouts)}')
print('\nmost common blocked metatiles overall:')
for m, n in total_blocked.most_common(8):
    print(f'   0x{m:03X}  x{n}')
print('\nTOP edge of a blocked mass (open above):')
for m, n in top_edge.most_common(8):
    print(f'   0x{m:03X}  x{n}')
print('\nBOTTOM edge of a blocked mass (open below):')
for m, n in bottom_edge.most_common(8):
    print(f'   0x{m:03X}  x{n}')
