# `src/acoustics.py` — neutral acoustic-load public API

`src/acoustics.py` is the primary public facade for every supported enclosure
and waveguide topology. It deliberately has no preferred load: DCCAV, bass
reflex (vent or passive radiator), sealed, infinite baffle, fourth- and
sixth-order bandpass, TL, MLTL, quarter-wave, back-loaded horn and tapped horn
are peers behind the same API.

The implementation remains split by responsibility:

- `src/engine.py`: acoustic physics, simulations, optimizers and analysis;
- `src/presets.py`: driver T/S catalogs and metadata;
- `src/pricing.py`: verified retailer prices and value scoring;
- `src/ranking.py`: Finder candidate evaluation.

The Streamlit app imports this facade as a top-level module after adding
`src/` to `sys.path`. Package callers use `from src import acoustics` or the
names re-exported by `src`.

`src/dccav.py` is retained only as a backward-compatible alias. Its matching
`docs/dccav.md` documents that compatibility surface and the DCCAV-specific
topology; new cross-load code and documentation should use `acoustics`.

The public types and functions are those exported by the implementation
modules. Detailed contracts, formulas, validation rules and limitations live
in [engine.md](engine.md), [presets.md](presets.md), [pricing.md](pricing.md)
and [ranking.md](ranking.md). DCCAV-specific theory remains in
[dccav.md](dccav.md).

The neutral smoke check is:

```bash
.venv/bin/python tests/test_all.py -m "acoustic-load smoke"
```

It must exercise all supported lumped and distributed load families, not only
the topology touched most recently.
