"""
Derive a wall autotile table from one or more vanilla layouts, keyed on which
of a solid block's neighbours are passable.

The cave-specific derive_wall_autotile.py keyed on which neighbours were also
wall, and only reached 26.5% confidence. Keying on *open* neighbours is the
better question for a tileset whose walls are one block thick: such a wall is
defined by what it faces, not by what it continues into.

Prints the winner per mask with how decisive it is. Anything under ~80% means
the mask is not what decides the art, and the table should be read by eye
instead of trusted.

Usage:  python derive_wall_table.py NewMauville_Inside_Layout
"""
import collections
import json
import struct
import sys
from pathlib import Path

from repo import REPO  # noqa: E402  (see repo.py)

# order matters only for display
DIRS = [('N', 0, -1), ('S', 0, 1), ('W', -1, 0), ('E', 1, 0),
        ('NW', -1, -1), ('NE', 1, -1), ('SW', -1, 1), ('SE', 1, 1)]


def layouts_named(names):
    L = json.loads((REPO / 'data/layouts/layouts.json').read_text(encoding='utf-8'))
    rows = L['layouts'] if isinstance(L, dict) else L
    return [e for e in rows if e and (e.get('name') in names or e.get('id') in names)]


def mask_name(m, dirs):
    return ''.join(d[0] for i, d in enumerate(dirs) if m & (1 << i)) or '-'


def derive(names, cardinal_only=True):
    dirs = DIRS[:4] if cardinal_only else DIRS
    tally = collections.defaultdict(collections.Counter)
    for e in layouts_named(names):
        w, h = e['width'], e['height']
        raw = (REPO / e['blockdata_filepath']).read_bytes()
        b = struct.unpack(f'<{w * h}H', raw)

        def solid(x, y):
            if not (0 <= x < w and 0 <= y < h):
                return True                      # off-map counts as solid
            return ((b[y * w + x] >> 10) & 3) != 0

        for y in range(h):
            for x in range(w):
                if not solid(x, y):
                    continue
                m = 0
                for i, (_, dx, dy) in enumerate(dirs):
                    if not solid(x + dx, y + dy):
                        m |= 1 << i
                tally[m][b[y * w + x] & 0x3FF] += 1
    return tally, dirs


def main(names):
    tally, dirs = derive(names)
    print(f'{"open sides":<12} {"n":>6}  winner   share   runners up')
    for m in sorted(tally, key=lambda k: -sum(tally[k].values())):
        c = tally[m]
        total = sum(c.values())
        if total < 4:
            continue
        (mid, n), *rest = c.most_common(4)
        share = 100 * n / total
        flag = '' if share >= 80 else '   <-- not decisive'
        others = ' '.join(f'0x{i:03X}:{k}' for i, k in rest)
        print(f'{mask_name(m, dirs):<12} {total:>6}  0x{mid:03X}  {share:5.1f}%  '
              f'{others}{flag}')


if __name__ == '__main__':
    main(sys.argv[1:] or ['NewMauville_Inside_Layout'])
