# br-mitchell

Data structuring repository for BR Mitchell's _International Historical Statistics_. This means we take source PDF files/scans of BR Mitchell from our private collections and restructure it into usable JSON for dataset work, particularly in testing and validation.

JSON outputs are in `/outputs/`. To digitise from your own PDFs, see `/common/digitiser/volumes_config.json5` to point to your own filepaths, then run `autorun.bat`/`autorun.sh`. For IP reasons, we do not include our scans of BR Mitchell.

<details>
  <summary><b>Technical Notes.</b></summary>

## Directory Structure

- `common/digitiser/` — JSON5 pipeline and volume configurations (`pipeline_config.json5`, `volumes_config.json5`).
- `core/` — Modular Python CV + CUDA EasyOCR pipeline (`PagePreprocessor`, `GraphicalElementDetector`, `TokenSegmenter`, `GpuOcrEngine`, `BraceAndCellResolver`, `TableStructureReconstructor`, `TableSeriesFlattener`, `SectionAssembler`, `TableDigitiserPipeline` and `cli_runner.py`).
- `docs/` — Doxygen configuration (`Doxyfile`), pipeline architecture, JSON schema (`architecture_and_schema.md`) and generated API reference (`api_reference.md`).
- `localisation/` — CLI localisation strings in EN-GB, FR and DE (`en_gb.json5`, `fr.json5`, `de.json5`).
- `output/json/` — Digitised per-section JSON files namespaced by volume (`africa_asia_oceania/`, `americas/`, `europe/`) plus `manifest.json`.

## Usage

### Digitise All 3 Volumes
```powershell
.\autorun.bat
```

### Digitise a Specific Volume, Page Slice or Custom PDF
```powershell
# Single configured volume
python core/cli_runner.py --volume europe

# Specific 0-based PDF page slice (e.g. pages 30 to 52)
python core/cli_runner.py --volume africa_asia_oceania --start-page 30 --end-page 52 --no-manifest

# Reuse on any external scanned statistical PDF
python core/cli_runner.py --pdf path/to/custom_tables.pdf --volume custom_id
```

### Verify Environment & Build Documentation
```powershell
.\autobuild.bat
.\autodoc.bat
```

See `docs/architecture_and_schema.md` for full details on the CV pipeline stages and output JSON schema.

</details>


