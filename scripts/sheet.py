"""
Render a chosen list of metatiles from a tileset pair, big and labelled.

Usage:  python sheet.py gTileset_General gTileset_BikeShop 0x208 0x210 0x227 ...
        python sheet.py gTileset_General gTileset_BikeShop 0x200-0x240
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw

import tileset_atlas as ta
from tileset_resolve import TilesetResolver

from repo import REPO  # noqa: E402  (see repo.py)


def pair_for(primary, secondary):
    R = TilesetResolver(REPO)
    return ta.TilesetPair(ta.Tileset(R.resolve(primary)),
                          ta.Tileset(R.resolve(secondary)) if secondary else None)


def sheet(pair, ids, out, scale=5, cols=10, labels=None, behaviors=None):
    cell, pad, lab = 16 * scale, 6, 16
    rows = (len(ids) + cols - 1) // cols
    img = Image.new('RGB', (cols * (cell + pad) + pad,
                            rows * (cell + pad + lab) + pad), (32, 32, 40))
    d = ImageDraw.Draw(img)
    for n, i in enumerate(ids):
        cx = pad + (n % cols) * (cell + pad)
        cy = pad + (n // cols) * (cell + pad + lab)
        try:
            img.paste(ta.render_metatile(pair, i, scale), (cx, cy))
        except Exception:
            d.rectangle([cx, cy, cx + cell, cy + cell], fill=(90, 0, 0))
        d.text((cx, cy + cell + 1), f'0x{i:03X}', fill=(255, 255, 255))
        name = ''
        if labels:
            name = str(labels.get(i, '') or '')
        if not name and behaviors is not None:
            name = str(ta.behavior_of(pair, i) or '')
        d.text((cx, cy + cell + 8), name.replace('MB_', '')[:16],
               fill=(150, 200, 255))
    img.save(out)
    print(f'wrote {out}  ({len(ids)} metatiles)')


def parse_ids(args):
    out = []
    for a in args:
        if '-' in a and not a.startswith('-'):
            lo, hi = a.split('-')
            out += list(range(int(lo, 0), int(hi, 0) + 1))
        else:
            out.append(int(a, 0))
    return out


if __name__ == '__main__':
    primary, secondary, *rest = sys.argv[1:]
    pair = pair_for(primary, secondary)
    ids = parse_ids(rest)
    try:
        labels = ta.parse_labels()
    except Exception:
        labels = None
    name = secondary.replace('gTileset_', '')
    sheet(pair, ids, ta.OUTDIR / f'sheet_{name}.png', labels=labels, behaviors=True)
