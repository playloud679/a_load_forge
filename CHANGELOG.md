# Changelog

## 1.0.0 (2026-05-26)

- Initial release
- Three acoustic profiles: Tractrix, Le Cléac'h (Euler integration with 160° roll-back), Iwata (Salmon T=0.707)
- Shared 3D mesh engine: normal-vector offset, revolution, watertight STL
- Parametric circular flange generator (outer/inner diameter, bolt holes)
- Web UI (Streamlit) with horn, flange, and merge tabs
- CLI orchestrator (`python -m src.main`)
- Cutoff frequency (Fc) calculation and display for all profiles
- Boundary protection for degenerate profiles
- Automatic normal flip on negative volume
- Multi-section horn splitting for 250mm³ printers
- Merge flange + horn into single watertight STL
