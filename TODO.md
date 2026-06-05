# TODO

Priorita operative per tenere `flare_forge` semplice da estendere e difficile da rompere.

## P0 - Stabilizzare l'architettura

- [ ] Estrarre da `ui_app.py` un dispatcher puro per profilo/sezione.
      Obiettivo: sostituire gli `if is_*` sparsi con una tabella esplicita
      `ProfileSpec -> generator`.
- [ ] Introdurre un modello dati minimo:
      `AcousticContext`, `ProfileSpec`, `SectionSpec`, `FlangeSpec`,
      `AdapterSpec`, `SliceSpec`, `BuildResult`.
- [ ] Eliminare la mutazione globale di `SOUND_SPEED` dai moduli.
      Passare la velocita del suono tramite `AcousticContext` o parametro
      esplicito.
- [ ] Separare `ui_app.py` in moduli piccoli:
      `ui_profile.py`, `ui_flanges.py`, `ui_assembly.py`, `ui_slicer.py`.
      La UI deve orchestrare, non contenere regole geometriche.

## P1 - Rendere il slicing manutenibile

- [ ] Dividere `src/_slicer.py` in responsabilita separate:
      `axial_slicer.py`, `petal_slicer.py`, `print_volume_slicer.py`,
      `joint_geometry.py`.
- [ ] Rappresentare i pezzi print-volume con una struttura esplicita:
      `Chunk(id, mesh, bounds, role, neighbors)`.
- [ ] Rendere deterministica e testabile la neighbor detection dei box joint.
      Evitare che la logica dipenda solo da tolleranze su bounding box.
- [ ] Aggiungere test su Iwata full-size per verificare che i T&G print-volume
      modifichino davvero dimensioni/volumi in `center_up`.
- [ ] Aggiungere una modalita debug che esporta una preview colorata dei chunk
      con ruoli `core`, `wing`, `tongue`, `groove`.

## P1 - Unificare CLI e API pubblica

- [ ] Decidere un solo entrypoint CLI.
      Preferenza: aggiornare `src/main.py` o deprecarlo a favore di
      `python -m src.profile_generator`.
- [ ] Portare la CLI allo stesso livello della UI: oblate, Le Cleac'h, Iwata,
      sezioni polygonal/rectangular/radial, flange, adapter, slicing.
- [ ] Aggiungere test CLI smoke per ogni profilo principale.
- [ ] Rimuovere o ridurre i `sys.path.insert(...)` duplicati quando il package
      e installabile correttamente.

## P2 - Qualita geometrica

- [ ] Formalizzare una pipeline mesh unica: `numpy-stl` solo se serve davvero,
      altrimenti preferire `trimesh.Trimesh` come tipo interno.
- [ ] Ridurre i fallback silenziosi su boolean fallite.
      Ogni fallback deve lasciare metadata o warning verificabile.
- [ ] Aggiungere metriche mesh per export: watertight, body_count, volume,
      non-manifold edges, bounding box.
- [ ] Rendere i warning "Your mesh is not closed" actionable: capire quali
      casi sono accettabili e quali sono bug.
- [ ] Testare i box joint su geometrie cave reali, non solo cubi pieni.

## P2 - Documentazione e versioning

- [ ] Aggiornare `README.md`: profili reali supportati, numero test corrente,
      slicing print-volume, box T&G.
- [ ] Spostare i numeri volatili della README in una sezione generata o facile
      da aggiornare.
- [ ] Aggiungere `docs/architecture.md` con il flusso:
      profile -> section -> mesh -> flange/adapter -> assembly -> slicing.
- [ ] Aggiornare `VERSION` e `pyproject.toml` nello stesso commit quando si fa
      release.
- [ ] Aggiungere una checklist release:
      test suite, README, docs, CHANGELOG, version bump, tag.

## P3 - UX e workflow stampa

- [ ] Salvare preset utente per stampante: volume, clearance, joint depth,
      materiale, wall thickness.
- [ ] Aggiungere nomi pezzi piu leggibili e stabili: `core_z000_250`,
      `wing_left_z335_572`, ecc.
- [ ] Mostrare in UI una tabella chunk con dimensioni, ruolo, warning volume
      e superamento volume di stampa.
- [ ] Segnalare chiaramente quando un pezzo supera il volume per mantenere
      throat adapter/flange monolitici.
- [ ] Aggiungere export ZIP con manifest JSON dei pezzi.

## P3 - Pulizia tecnica

- [ ] Convertire i test custom print-based a `pytest`, mantenendo output leggibile.
- [ ] Centralizzare helper temporanei STL/load/unlink usati nei test.
- [ ] Aggiungere type aliases per profili: `CircularProfile`, `RectProfile`.
- [ ] Ridurre `except Exception` generici nei moduli geometrici.
- [ ] Aggiungere lint/format minimo nel Makefile.
