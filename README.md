# br-mitchell

Reusable Computer Vision and GPU OCR pipeline for digitising B.R. Mitchell's *International Historical Statistics* (and similarly typeset booktabs statistical volumes) from scanned PDFs into structured JSON.

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
