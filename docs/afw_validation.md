# AFW validation bridge

`tools/compare_afw_sealed.py` is a read-only bridge between Load Forge and the
trusted legacy **AUDIO per Windows pro v2** (AFW) simulator running in an x86
Windows XP guest. The historical filename is retained, but the tool now parses
the first transducer slot for three AFW load codes:

- `1`: suspension / sealed box;
- `3`: `carico simmetrico` / fourth-order bandpass (BP4);
- `4`: `doppio reflex parallelo` / sixth-order bandpass (BP6).

It extracts the embedded 201-point `.crw` driver data, chamber volumes and
virtual-volume factors, tunings and loss-Q values. A bandpass project can then
be simulated as a single driver, two identical drivers in parallel or series,
or an isobaric pair:

```bash
.venv/bin/python tools/compare_afw_sealed.py /path/to/sealed.afw
.venv/bin/python tools/compare_afw_sealed.py /path/to/bp4.afw --json
.venv/bin/python tools/compare_afw_sealed.py /path/to/bp6.afw \
  --configuration "2 × parallel"
```

AFW codes `2` (bass reflex) and `6` (double-reflex series / DCAAV) are named in
the error message but deliberately rejected by this comparator. The parser
validates field ranges and fails instead of guessing when the file layout does
not match.

## Sealed FE126 and the historical 4.94% offset

The approximately 5% offset was a model-scope difference, not numerical error.
AFW adds the air mass coupled to a diaphragm mounted on its panel; Load Forge
originally applied the free-air T/S moving mass without that correction.

| Virtual volume | Classical Fc | AFW Fc | Classical / AFW |
|---:|---:|---:|---:|
| 3 L | 162.7500 Hz | 155.0854 Hz | +4.9422% |
| 4 L | 147.8640 Hz | 140.9005 Hz | +4.9422% |

AFW's multiplier is `0.9529055`, equivalent to moving the FE126 resonance from
89.4 Hz to 85.1898 Hz. Load Forge now enables an explicit 90% partial-baffle
air-load model by default. It predicts 0.2581 g additional mass, mounted Fs
85.2385 Hz and 3 L Fc 155.1741 Hz: **+0.057% versus AFW**, while the comparator
continues to report the historical classical +4.942% result separately.

AFW's equivalent loss Q changes total Q but not the saved resonance. The
comparator therefore reports classical `Qtc`, a separate series-loss-aware Q,
and panel-loaded frequency results without conflating those definitions.

## Fourth-order bandpass pilot

The AFW `carico simmetrico` pilot for the FE126 displayed an approximately
2.31 L virtual sealed chamber at about 163 Hz / Qt 0.76 and a 1.74 L virtual
vented chamber tuned near 163 Hz. Applying that alignment to Load Forge gives:

- response peak 90.82 dB at 147.50 Hz;
- -3 dB band approximately 101.83--273.65 Hz;
- impedance resonances approximately 100.87 and 272.81 Hz.

The Load Forge analytical starter for the same driver is 2.799 L sealed,
6.940 L vented and 159.01 Hz. Its tuning is close to the AFW pilot, but its
front-volume rule is not the same AFW optimum; the comparator intentionally
reports both sets rather than presenting them as equivalent.

The BP4 parser layout is covered by a generated AFW-format regression fixture,
and the engine test requires the expected two-resonance bandpass topology. The
AFW pilot values were read from the XP UI, but its duplicated BP4 project could
not be saved reliably through automation. Consequently the scalar bridge and
Load Forge projection are reproducible, while a numerical AFW curve delta is
still pending an AFW export.

## Sixth-order bandpass pilot and polarity correction

The real FE126 AFW BP6 project contains these virtual alignments:

| Chamber | AFW virtual volume | AFW tuning |
|---|---:|---:|
| rear | 6.8777 L | 87.6623 Hz |
| front | 2.4844 L | 170.5266 Hz |

With those saved AFW inputs, Load Forge now reports a broad response with a
94.59 dB peak at 112.79 Hz, a 90.97--227.18 Hz -3 dB band and impedance peaks
at **48.10, 110.98 and 239.80 Hz**. Those peaks agree with the AFW graph at the
available screenshot resolution (about 45, 110 and 250 Hz).

This validation found and fixed a topology error: the two vents radiate from
opposite sides of the enclosed cone, so their far-field volume velocities must
be subtracted. Same-sign addition created an artificial notch near 110--120 Hz.
The regression suite also requires equal BP6 chambers and tunings to cancel
externally. The starter is now asymmetric (2:1 chamber-volume ratio and 1:2
tuning ratio) instead of the invalid equal-branch alignment.

## Multiple-driver validation

`DriverTS.radiating_pistons` keeps the cone count separate from composite `Sd`.
Two ordinary identical drivers receive two per-cone radiation masses; treating
them as one large piston would overestimate the cubic-radius air-mass term by
`sqrt(2)`. An isobaric pair retains one externally radiating piston. Regression
tests require two separate identical cones to preserve the same mounted Fs as
one cone, while Re/Le, Vas, Sd and power follow the selected wiring topology.

As a reproducible projection, applying `2 × parallel` to the same saved AFW BP6
box preserves mounted Fs at 85.238 Hz and produces a 99.04 dB peak at 114.89 Hz
with impedance peaks at 38.69, 112.92 and 291.99 Hz. This is a same-box
multi-driver projection, not a claim that AFW selected that enclosure for two
drivers. Direct multi-driver AFW curve comparison still requires a separately
saved multi-driver reference project.

## Remaining curve-level limitation

AFW does not store the simulated loaded response and impedance curves in the
`.afw` project. Exact point-by-point curve error therefore requires controlled
GUI sampling or export inside the XP guest. Current BP6 agreement is at
screenshot resolution; sealed scalar validation is numerical; BP4 and
multiple-driver results are explicitly labelled projections where no saved AFW
curve exists.
