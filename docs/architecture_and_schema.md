# Architecture and JSON Schema

## 1. Pipeline Overview

The digitiser converts scanned historical statistical tables (including multi-column census enumerations, multi-tier headers, rotated landscape tables, inline series-break underlines and `{` / `}` curly braces) into flat, analysis-ready per-section JSON without relying on embedded PDF text layers.

1. **`PagePreprocessor`** (`A_` to `E_`): Renders pages at 300 DPI via PyMuPDF, detects rotated landscape tables beneath upright running headers, deskews via weighted linear regression across horizontal rules and normalises illumination shadows using a 4x pyramid Gaussian background estimator.
2. **`GraphicalElementDetector`** (`A_` to `E_`): Extracts booktabs frame rules (`top`, `cmidrule`, `header_mid`, `bottom`), splits side-by-side and stacked sub-tables, identifies inline series-break underlines and classifies `{` vs `}` curly braces from left/right outer-edge cusp geometry (`<` vs `>`).
3. **`TokenSegmenter`** (`A_` to `D_`): Masks graphical lines and braces, filters scanner dust, pre-classifies statistical symbols (`...`, `--`, `—`) geometrically and masks raised superscripts and lowered subscripts out of crop images prior to OCR.
4. **`GpuOcrEngine`** (`A_` to `D_`): Runs width-bucketed CUDA `EasyOCR` (`english_g2`) recognition with contrast-retry fallback and normalises numeric and label tokens.
5. **`BraceAndCellResolver`** (`A_` to `C_`): Maps paired (`}`...`{`) and unilateral (`}` or `{`) braces onto canonical row/column spans, captures vertically off-grid combined figures, heals kerning splits inside numbers and parses bracketed estimates (`[3,691]`) and apostrophe census dates (`14'63`).
6. **`HeaderHierarchyResolver`** (`A_` to `C_`): Resolves multi-tier column headers via `\cmidrule` and centred-span matching without Voronoi smearing across blank header space, heals single-letter `I`/`E` OCR errors and merges/de-hyphenates 1-to-1 wrapped column leaves.
7. **`TableStructureReconstructor`** (`A_` to `D_`): Masks full-page section banners, splits `[Country, Period]` headers, infers stub gutters, reconstructs canonical row grids with two-tier country/sub-scope state and applies horizontal brace column spans.
8. **`PlaceKeyNormaliser`** (`A_` to `C_`): Heals OCR artefacts on geographic identifiers (`0'Higgins` -> `o_higgins`, spaced initialisms `U. K.` -> `uk`, administrative suffixes), rejects numeric/year/price/sector keys and classifies commodity sub-table headings.
9. **`TableSeriesFlattener`** (`A_` to `D_`): Extracts clean `name` and `subtitle` metadata, carries column schemas across headerless continuation blocks, derives concise `snake_case` default indicators and flattens all canonical table orientations into `<country/province/city_key>` dictionaries containing strictly numeric `<indicator>_<year>` entries.
10. **`SectionAssembler`** (`A_` to `C_`): Extracts running headers and multi-line section banners (`A1`, `A2`, ..., `D10`, `D20`, `J3`), smooths section assignments monotonically across each volume and exports `output/json/<volume_id>/<section_id>.json`.

## 2. Section JSON Schema (`output/json/<volume_id>/<section_id>.json`)

Each section file contains a single root key matching its `<table_key>` (`A1`, `A2`, `C1`, ...):

```json
{
  "A1": {
    "name": "Population of Countries at Enumerations",
    "subtitle": "in thousands",
    "guinea_bissau": {
      "m_1940": 180,
      "f_1940": 172,
      "total_1940": 351,
      "m_1950": 253,
      "f_1950": 258,
      "total_1950": 511
    },
    "morocco": {
      "french_zone_total_1921": 4334,
      "spanish_zone_total_1930": 701,
      "m_1960": 5809,
      "f_1960": 5817,
      "total_1960": 11626
    }
  }
}
```

### Key Conventions
- **`name`** (`string`): Clean section title with regional prefixes (`AFRICA:`, `EUROPE:`) and trailing unit parentheses removed.
- **`subtitle`** (`string`): Unit or secondary subtitle (e.g. `"in thousands"`, `"Rates per 1,000 Population"`), or `""` when none exists.
- **`<country/province/city_key>`** (`object`): Canonical `snake_case` place identifier (e.g. `"guinea_bissau"`, `"new_zealand"`, `"portuguese_settlements"`, `"uk"`).
- **`<indicator>_<year>`** (`number`): Strictly numeric (`int` or `float`) observation keyed by `snake_case` indicator and year/period (e.g. `"m_1940"`, `"wheat_1860"`, `"imports_1834_1835"`, `"m_70_79_1951_2"`, `"population_1750"`). Non-numeric symbols (`...`, `--`, `—`), prose notes and footnotes are omitted.
