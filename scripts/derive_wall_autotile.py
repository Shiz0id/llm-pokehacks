"""
Derive a full wall autotile table from vanilla, instead of the hand-rolled 3x2.

For every wall block in the 62 General+Cave layouts, build a bitmask of which
neighbours are also wall, then tally which metatile vanilla uses for that mask.
The winner per mask becomes our lookup table.

Reports how decisive each mask is - a mask whose top metatile only wins 30% of
the time is telling us the 8-neighbour context is not what decides it.
"""
import json, struct, collections
from pathlib import Path

from repo import REPO  # noqa: E402  (see repo.py)

# bit order: N, S, W, E, NW, NE, SW, SE
OFFSETS = [(0,-1),(0,1),(-1,0),(1,0),(-1,-1),(1,-1),(-1,1),(1,1)]


def load_cave_layouts():
    L = json.loads((REPO/'data/layouts/layouts.json').read_text(encoding='utf-8'))
    E = L['layouts'] if isinstance(L, dict) else L
    out = []
    for e in E:
        if not e or e.get('primary_tileset') != 'gTileset_General' \
                 or e.get('secondary_tileset') != 'gTileset_Cave':
            continue
        w, h = e['width'], e['height']
        raw = (REPO/e['blockdata_filepath']).read_bytes()
        if len(raw) != w*h*2:
            continue
        out.append((e['id'], w, h, struct.unpack(f'<{w*h}H', raw)))
    return out


def main():
    layouts = load_cave_layouts()
    print(f'cave layouts: {len(layouts)}')

    tally = collections.defaultdict(collections.Counter)
    for _id, w, h, b in layouts:
        wall = lambda x, y: (b[y*w+x] >> 10) & 3 if 0 <= x < w and 0 <= y < h else 1
        for y in range(h):
            for x in range(w):
                if not wall(x, y):
                    continue
                mask = 0
                for bit, (dx, dy) in enumerate(OFFSETS):
                    if wall(x+dx, y+dy):
                        mask |= 1 << bit
                tally[mask][b[y*w+x] & 0x3FF] += 1

    # cardinal-only (4-bit) view, for comparison
    tally4 = collections.defaultdict(collections.Counter)
    for mask, c in tally.items():
        tally4[mask & 0b1111].update(c)

    for name, t, bits in (('4-bit cardinal', tally4, 4), ('8-bit full', tally, 8)):
        total = sum(sum(c.values()) for c in t.values())
        decisive = sum(c.most_common(1)[0][1] for c in t.values())
        print(f'\n{name}: {len(t)} masks seen of {2**bits}, '
              f'top choice covers {100*decisive/total:.1f}% of blocks')

    print('\n4-bit table (N S W E) -> metatile, with confidence:')
    names = {0b0000:'isolated', 0b1111:'enclosed'}
    for mask in sorted(tally4):
        c = tally4[mask]
        mt, n = c.most_common(1)[0]
        tot = sum(c.values())
        flags = ''.join(ch for ch, bit in zip('NSWE', range(4)) if mask >> bit & 1) or '-'
        print(f'  {mask:04b} {flags:<4} -> 0x{mt:03X}  {100*n/tot:5.1f}%  (n={tot})')

    out = {f'{m:04b}': tally4[m].most_common(1)[0][0] for m in sorted(tally4)}
    Path('wall_autotile_4bit.json').write_text(json.dumps(out, indent=1))
    print('\nwrote wall_autotile_4bit.json')


if __name__ == '__main__':
    main()
