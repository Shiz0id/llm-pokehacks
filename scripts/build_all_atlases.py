"""Build a contact sheet + JSON index for every tileset pair used by a layout."""
import json, sys, time, collections
from pathlib import Path
import tileset_atlas as ta
from tileset_resolve import TilesetResolver

_cache = {}
RESOLVER = TilesetResolver(ta.REPO)


def load(sym):
    """Resolve and load a tileset. Raises rather than returning None, so an
    unresolvable tileset is a loud failure instead of a silent primary-only
    atlas that quietly overwrites a sibling."""
    if sym not in _cache:
        res = RESOLVER.resolve(sym)
        if res is None:
            raise KeyError(f'unresolvable tileset symbol: {sym}')
        _cache[sym] = ta.Tileset(res)
    return _cache[sym]


def main():
    L = json.loads((ta.REPO / 'data/layouts/layouts.json').read_text(encoding='utf-8'))
    entries = [e for e in (L['layouts'] if isinstance(L, dict) else L)
               if e and e.get('primary_tileset')]
    pairs = collections.Counter((e['primary_tileset'], e['secondary_tileset']) for e in entries)

    labels, behaviors = ta.parse_labels(), ta.parse_behaviors()
    ok = skipped = 0
    failures = []
    t0 = time.time()
    manifest = []

    for (psym, ssym), used_by in pairs.most_common():
        try:
            prim = load(psym)
            # a layout may declare no secondary tileset; it shows up as the
            # string "0" (truthy in python) rather than null.
            has_sec = ssym not in (None, '', '0', 0)
            sec = load(ssym) if has_sec else None
            pair = ta.TilesetPair(prim, sec)
            # stem from symbols, not directory names: directories are shared
            # between tilesets, so dir-based stems collide and overwrite.
            stem = f"{psym.replace('gTileset_','')}__{ssym.replace('gTileset_','') if has_sec else 'none'}"
            size, total = ta.build_atlas(pair, ta.OUT / f'{stem}.png', labels, behaviors, scale=3)
            n = ta.export_index(pair, ta.OUT / f'{stem}.json', labels, behaviors, psym, ssym)
            manifest.append({'primary': psym, 'secondary': ssym, 'stem': stem,
                             'layouts_using': used_by, 'metatiles': n,
                             'frlg': pair.frlg, 'png': f'{stem}.png'})
            ok += 1
        except Exception as exc:
            skipped += 1
            failures.append(f'{psym} + {ssym}: {type(exc).__name__}: {exc}')

    (ta.OUT / 'manifest.json').write_text(json.dumps(manifest, indent=1), encoding='utf-8')

    print(f'pairs found : {len(pairs)}')
    print(f'atlases built: {ok}')
    print(f'skipped     : {skipped}')
    print(f'elapsed     : {time.time()-t0:.1f}s')
    if failures:
        print('\nfailures:')
        for f in failures[:15]:
            print('  ', f)
    return 0 if not failures else 1


if __name__ == '__main__':
    sys.exit(main())
