"""Attribute EWRAM/IWRAM usage to source files, from the linker map."""
import re, collections
from pathlib import Path

from repo import REPO  # noqa: E402  (see repo.py)
MAP = REPO / 'pokeemerald.map'

if not MAP.exists():
    # The linker map only exists after a successful build, and this is the one
    # tool here that reads build output rather than source. Say so, rather than
    # raising FileNotFoundError at somebody who has just cloned.
    raise SystemExit(
        f'{MAP} not found - RAM figures come from the linker map, so this needs '
        f'a completed build. Run `make` in the repo first.')

lines = MAP.read_text(errors='replace').split('\n')

# The map lists output sections in order; track which region we are inside.
region = None
sizes = collections.Counter()

sec_re = re.compile(r'^(\S+)\s+0x([0-9a-f]+)\s+0x([0-9a-f]+)')
inp_re = re.compile(r'^\s+\.(?:bss|data|sbss|common)[.\w]*\s+0x([0-9a-f]+)\s+0x([0-9a-f]+)\s+(\S+)')

for l in lines:
    m = sec_re.match(l)
    if m:
        name = m.group(1)
        if name in ('ewram_data', '.ewram', 'ewram'):
            region = 'EWRAM'
        elif name in ('iwram_data', '.bss', '.iwram', 'iwram'):
            region = 'IWRAM'
        elif name.startswith('.') and region and not name.startswith(('.bss', '.data')):
            pass
    m = inp_re.match(l)
    if m and region:
        size = int(m.group(2), 16)
        obj = m.group(3).split('/')[-1]
        if size:
            sizes[(region, obj)] += size

for reg in ('EWRAM', 'IWRAM'):
    items = sorted(((v, f) for (r, f), v in sizes.items() if r == reg), reverse=True)
    tot = sum(v for v, _ in items)
    print(f'=== {reg} — attributed {tot:,} bytes across {len(items)} objects ===')
    shown = 0
    for v, f in items[:18]:
        print(f'  {v:>9,}  {f}')
        shown += v
    print(f'  {tot-shown:>9,}  (everything else)')
    print()
