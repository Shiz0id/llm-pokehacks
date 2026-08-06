"""
Where the ROM is actually going, read out of the linker map.

The companion to ram_budget.py. ROM is spare in a stock build and stops being
spare the moment a project adds real assets - an animated sprite set, an
imported tileset, a music pack - at which point "what would we get back by
cutting X" needs an answer from data rather than from the size of a file.

TWO THINGS THE FILE SIZE WILL NOT TELL YOU. pokeemerald.gba is exactly
33,554,432 bytes whatever you do, because `gbafix -p` pads to a power of two;
the real figure is __rom_end minus the ROM origin, which is what the linker
prints on every link. And an .o file's size is not its ROM cost either, since
assets are INCBIN'd into the object of whatever consumes them - every species
front pic lands in one graphics object, so "which file is big" answers nothing
useful on its own.

So this reads the map twice over. Input sections give the per-object split.
Symbols give a finer one, sized by the distance to the next symbol, which is
how an INCBIN'd asset inside a shared object gets attributed at all.

Run:  python rom_budget.py [--repo PATH] [--top N]
      python rom_budget.py --object src/data/graphics/pokemon.o   # drill in
      python rom_budget.py --prefix gMonFrontPic                  # by symbol
Needs a linked build - pokeemerald.map comes from `make`. Categories are matched
in order, first hit wins; add your own project's symbol prefixes to CATEGORIES
or its assets land under "other".
"""
import argparse
import re
from collections import defaultdict
from pathlib import Path

from repo import REPO  # noqa: E402  (see repo.py)

MAP = 'pokeemerald.map'
ROM_ORIGIN = 0x08000000

#  Categories are matched in order, first hit wins, so put the specific ones
#  above the general. Matched against the object path AND, for assets, against
#  the symbol name - an INCBIN sits in an object whose name says nothing about
#  what the bytes are.
CATEGORIES = [
    ('Pokemon front/back pics',  r'gMonFrontPic|gMonBackPic|gMonStillFrontPic'),
    ('Pokemon palettes',         r'gMonPalette|gMonShinyPalette'),
    ('Pokemon icons',            r'gMonIcon'),
    ('Pokemon footprints',       r'gMonFootprint'),
    ('Overworld object gfx',     r'gObjectEventPic|gObjectEventPal|ObjectEventGraphics'),
    ('Trainer pics',             r'gTrainerFrontPic|gTrainerBackPic|gTrainerPalette'),
    ('Tilesets',                 r'gTilesetTiles|gTilesetPalettes|gMetatiles|gMetatileAttributes|tilesets'),
    ('Map layouts and data',     r'_Layout|_Blockdata|_Border|MapEvents|MapHeader|script_data|map_events|maps\.o'),
    ('Battle animations',        r'battle_anim|gBattleAnim'),
    ('Battle engine',            r'battle_'),
    ('Sound and music',          r'sound|songs|voicegroup|music|cry|Cry'),
    ('Text and strings',         r'\.rodata\.str|gText_|strings'),
    ('Pokedex',                  r'pokedex|gPokedex'),
    ('Contest',                  r'contest'),
    ('Battle Frontier',          r'frontier|battle_tower|apprentice'),
    ('Interface and menus',      r'menu|window|font|interface|start_menu|party_menu'),
]


def categorise(*names):
    for label, pattern in CATEGORIES:
        for n in names:
            if n and re.search(pattern, n, re.I):
                return label
    return 'other'


def parse_map(path):
    """Input sections and symbols of every ROM output section.

    Returns (sections, symbols) where sections is a list of
    (addr, size, object) and symbols a list of (addr, name).
    """
    text = path.read_text(encoding='utf-8', errors='replace').splitlines()

    #  " .rodata        0x083cf500      0x16c src/foo.o", and the wrapped form
    #  where a long section name pushes the rest onto the next line.
    sec_re = re.compile(r'^ (\.\S+)\s+(0x[0-9a-f]+)\s+(0x[0-9a-f]+)\s+(\S+)$')
    cont_re = re.compile(r'^\s+(0x[0-9a-f]+)\s+(0x[0-9a-f]+)\s+(\S+)$')
    sym_re = re.compile(r'^\s+(0x[0-9a-f]+)\s{16,}(\S+)$')
    name_only_re = re.compile(r'^ (\.\S+)$')

    sections, symbols = [], []
    pending_name = None

    for line in text:
        m = sec_re.match(line)
        if m:
            pending_name = None
            addr, size, obj = int(m.group(2), 16), int(m.group(3), 16), m.group(4)
            if addr >= ROM_ORIGIN and size:
                sections.append((addr, size, obj, m.group(1)))
            continue

        m = name_only_re.match(line)
        if m:
            pending_name = m.group(1)
            continue

        if pending_name:
            m = cont_re.match(line)
            if m:
                addr, size, obj = int(m.group(1), 16), int(m.group(2), 16), m.group(3)
                if addr >= ROM_ORIGIN and size:
                    sections.append((addr, size, obj, pending_name))
                pending_name = None
                continue

        m = sym_re.match(line)
        if m:
            addr = int(m.group(1), 16)
            name = m.group(2)
            #  Assignments and expressions, not real symbols
            if addr >= ROM_ORIGIN and not name.startswith(('.', '_')) and '=' not in name:
                symbols.append((addr, name))

    return sections, symbols


def size_symbols(symbols, rom_end):
    """Give each symbol the distance to the next one as its size.

    This is an approximation and it is the only one available: the map does not
    record symbol sizes. It over-attributes when padding follows a symbol and
    under-attributes nothing, so totals are safe to compare against each other
    but should not be trusted to the byte.
    """
    uniq = sorted(set(symbols))
    out = []
    for i, (addr, name) in enumerate(uniq):
        nxt = uniq[i + 1][0] if i + 1 < len(uniq) else rom_end
        out.append((addr, max(0, nxt - addr), name))
    return out


def human(n):
    if n >= 1024 * 1024:
        return f'{n / 1024 / 1024:8.2f} MB'
    return f'{n / 1024:8.1f} KB'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--top', type=int, default=18)
    ap.add_argument('--object', help='drill into one object file, by symbol')
    ap.add_argument('--prefix', help='total every symbol starting with this')
    args = ap.parse_args()

    repo = REPO
    mp = repo / MAP
    if not mp.exists():
        #  The linker map only exists after a successful build. Say so, rather
        #  than raising FileNotFoundError at somebody who has just cloned.
        raise SystemExit(
            f'{mp} not found - ROM figures come from the linker map, so this '
            f'needs a completed build. Run `make` in the repo first.')

    sections, symbols = parse_map(mp)
    if not sections:
        raise SystemExit('parsed no ROM sections; the map format may have changed')

    rom_end = max(a + s for a, s, _, _ in sections)
    used = rom_end - ROM_ORIGIN
    capacity = 32 * 1024 * 1024
    sized = size_symbols(symbols, rom_end)

    if args.prefix:
        hit = [(sz, n) for _a, sz, n in sized if n.startswith(args.prefix)]
        total = sum(sz for sz, _ in hit)
        print(f'{len(hit)} symbols matching {args.prefix!r}: {human(total)}')
        for sz, n in sorted(hit, reverse=True)[:args.top]:
            print(f'  {human(sz)}  {n}')
        return 0

    if args.object:
        lo_hi = [(a, a + s) for a, s, obj, _ in sections if obj.endswith(args.object)]
        if not lo_hi:
            raise SystemExit(f'no sections from {args.object}')
        tot = sum(h - l for l, h in lo_hi)
        print(f'{args.object}: {human(tot)} in {len(lo_hi)} sections\n')
        inside = [(sz, n) for a, sz, n in sized
                  if any(l <= a < h for l, h in lo_hi)]
        for sz, n in sorted(inside, reverse=True)[:args.top]:
            print(f'  {human(sz)}  {n}')
        return 0

    print(f'ROM  {human(used)} used of {human(capacity)}'
          f'   ({100.0 * used / capacity:.2f}%)')
    print(f'     {human(capacity - used)} free\n')

    by_out = defaultdict(int)
    for _a, s, _o, name in sections:
        by_out[name.split('.')[1] if name.count('.') > 1 else name.lstrip('.')] += s
    print('By output section')
    for name, s in sorted(by_out.items(), key=lambda t: -t[1])[:6]:
        print(f'  {human(s)}  {name}')

    #  Category totals come from SYMBOLS, not objects: an INCBIN'd asset is in
    #  whatever object references it, so per-object totals put every species
    #  pic under one graphics file and answer nothing.
    by_cat = defaultdict(int)
    for _a, sz, n in sized:
        by_cat[categorise(n)] += sz
    attributed = sum(by_cat.values())

    print(f'\nBy category, from {len(sized)} symbols ({human(attributed)} attributed)')
    for cat, s in sorted(by_cat.items(), key=lambda t: -t[1]):
        print(f'  {human(s)}  {100.0 * s / used:5.1f}%  {cat}')

    by_obj = defaultdict(int)
    for _a, s, obj, _n in sections:
        by_obj[obj] += s
    print(f'\nLargest objects')
    for obj, s in sorted(by_obj.items(), key=lambda t: -t[1])[:args.top]:
        print(f'  {human(s)}  {obj}')

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
