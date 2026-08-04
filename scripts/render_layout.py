"""
Render a vanilla layout to PNG, and census which metatiles it uses.

Reading a real layout is how the cave wall table was derived. Statistical
adjacency mining over the same data only reached 26.5% confidence, because the
8-neighbour context is not what decides which wall metatile vanilla uses.

Usage:  python render_layout.py NewMauville_Inside_Layout [--grid]
"""
import collections
import json
import struct
import sys
from pathlib import Path

from PIL import Image, ImageDraw

import tileset_atlas as ta
from tileset_resolve import TilesetResolver

from repo import REPO  # noqa: E402  (see repo.py)


def find(name):
    L = json.loads((REPO / 'data/layouts/layouts.json').read_text(encoding='utf-8'))
    for e in (L['layouts'] if isinstance(L, dict) else L):
        if e and (e.get('name') == name or e.get('id') == name):
            return e
    raise SystemExit(f'no layout named {name}')


def blocks(e):
    w, h = e['width'], e['height']
    raw = (REPO / e['blockdata_filepath']).read_bytes()
    return w, h, struct.unpack(f'<{w * h}H', raw)


def main(name, grid=False):
    e = find(name)
    w, h, b = blocks(e)
    R = TilesetResolver(REPO)
    pair = ta.TilesetPair(ta.Tileset(R.resolve(e['primary_tileset'])),
                          ta.Tileset(R.resolve(e['secondary_tileset'])))
    print(f'{name}  {w}x{h}  {e["primary_tileset"]} + {e["secondary_tileset"]}')

    cache = {}

    def tile(mid):
        if mid not in cache:
            cache[mid] = ta.render_metatile(pair, mid, 1)
        return cache[mid]

    img = Image.new('RGB', (w * 16, h * 16))
    for y in range(h):
        for x in range(w):
            v = b[y * w + x]
            img.paste(tile(v & 0x3FF), (x * 16, y * 16))

    if grid:                       # 8-metatile ruler, for reading coordinates
        d = ImageDraw.Draw(img)
        for x in range(0, w, 8):
            d.line([(x * 16, 0), (x * 16, h * 16)], fill=(255, 0, 255))
            d.text((x * 16 + 2, 2), str(x), fill=(255, 0, 255))
        for y in range(0, h, 8):
            d.line([(0, y * 16), (w * 16, y * 16)], fill=(255, 0, 255))
            d.text((2, y * 16 + 2), str(y), fill=(255, 0, 255))

    out = ta.OUTDIR / f'{name}.png'
    img.save(out)
    print(f'wrote {out}')

    # census, split by collision, since that is what makes a block a wall
    by_coll = collections.defaultdict(collections.Counter)
    for v in b:
        by_coll[(v >> 10) & 3][v & 0x3FF] += 1
    for coll in sorted(by_coll):
        c = by_coll[coll]
        kind = 'passable' if coll == 0 else f'collision {coll}'
        print(f'\n{kind}: {len(c)} distinct metatiles, {sum(c.values())} blocks')
        for mid, n in c.most_common(24):
            print(f'   0x{mid:03X} x{n}')


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    main(args[0] if args else 'NewMauville_Inside_Layout',
         '--grid' in sys.argv)
