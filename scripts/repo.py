"""Locate the decomp repo these tools operate on.

The tools originally lived inside a decomp at `<repo>/tools/rogue/` and found
the repo with `Path(__file__).parents[2]`. Outside that tree there is nothing to
walk up to, so the repo is named explicitly instead. In precedence order:

  1. `--repo <path>` anywhere on the command line (consumed, so a script's own
     argument parsing never sees it)
  2. the `POKEDECOMP_REPO` environment variable
  3. an upward search from the current directory for something that looks like a
     decomp -- convenient when you are already standing in one

A directory counts as a decomp if it has `data/layouts/layouts.json` and
`src/data/tilesets/headers.h`. That is a deliberate pair: the first is the map
data these tools read and the second is how tileset symbols resolve, so
anything satisfying both is usable even if it is a fork with an unfamiliar name.
"""
import os
import sys
from pathlib import Path

MARKERS = ('data/layouts/layouts.json', 'src/data/tilesets/headers.h')


def looks_like_decomp(path):
    return all((path / m).exists() for m in MARKERS)


def _from_argv():
    """Pull `--repo <path>` out of sys.argv so callers never see it."""
    if '--repo' not in sys.argv:
        return None
    i = sys.argv.index('--repo')
    if i + 1 >= len(sys.argv):
        raise SystemExit('--repo needs a path')
    path = sys.argv[i + 1]
    del sys.argv[i:i + 2]
    return Path(path)


def find_repo():
    explicit = _from_argv() or (
        Path(os.environ['POKEDECOMP_REPO']) if os.environ.get('POKEDECOMP_REPO')
        else None)

    if explicit is not None:
        repo = explicit.expanduser().resolve()
        if not looks_like_decomp(repo):
            missing = [m for m in MARKERS if not (repo / m).exists()]
            raise SystemExit(
                f'{repo} does not look like a decomp checkout '
                f'(missing {", ".join(missing)})')
        return repo

    here = Path.cwd().resolve()
    for candidate in (here, *here.parents):
        if looks_like_decomp(candidate):
            return candidate

    raise SystemExit(
        'Cannot find a decomp checkout. Pass --repo <path>, set '
        'POKEDECOMP_REPO, or run from inside one.')


REPO = find_repo()
