# ORKA component database: provenance policy and pipeline

## Policy

1. **Every shipped record names its source**: a URL to a primary document (manufacturer catalog or datasheet, SAAMI/C.I.P. standard, government report), with the page where applicable, and the **verbatim evidence line** it was parsed from. The Database tab shows both.
2. **Values are parsed, not typed.** Extraction scripts in `scripts/extract/` download the public document and parse its tables. They can be re-run to reproduce or update the data.
3. **Independent verification.** For each source, a separate agent re-reads a random sample of records against the document. Mismatches are fixed or the records excluded via `research/raw2/_review.json`, and sources judged unreliable are excluded entirely.
4. **Nothing from memory.** If a document does not state a value, the field is empty. ORKA then asks the user to enter a measured value: case capacity and bullet length are the usual ones.
5. **Units as published.** Inches, grains, psi, bar. **CUP is never converted to psi.**
6. **Conflicts are kept, not resolved silently.** For example, when SAAMI and C.I.P. disagree on a dimension, both values are stored under `conflicts`.
7. **Round-1 research** (`research/raw/`) was gathered from search-result snippets without page access. It is kept as background notes and is **never shipped**.

## Pipeline

```
scripts/extract/<source>.py      # download primary document(s), parse tables  → research/raw2/<source>.json
(verification agents)            # sample re-check against the documents        → research/raw2/_review.json
npx tsx scripts/build-data.ts    # merge, normalise names, apply review          → src/data/db.json
npx tsx scripts/calibrate-powders.ts  # fit powders to published pressure data  → src/data/powder-models.json, validation-report.json
npx tsx scripts/build-data.ts    # attach calibrated + chart-interpolated models → src/data/db.json
```

## User data

Your own cartridges, powders, bullets, brass, calibrations and saved loads stay in your browser's local storage. Export them to a JSON file from the Database tab, and import them on another device. Nothing is sent anywhere: the app makes no network requests at runtime.

## Open items

- Solid density of nitrocellulose propellants (currently the conventional 1.6 g/cm³, unsourced).
- Heat-loss constants from the IBHVG2 user's guide or AMCP 706-150, once read from the primary documents.
- Coverage gaps per maker are listed in the build output and in the extraction summaries.
