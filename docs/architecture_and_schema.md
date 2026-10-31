# Architecture and JSON Schema

## 1. Pipeline Overview

The digitiser converts scanned historical statistical tables (including multi-column census enumerations, multi-tier headers, rotated landscape tables, inline series-break underlines and `{` / `}` curly braces) into structured JSON without relying on embedded PDF text layers.

1. **`PagePreprocessor`** (`A_` to `E_`): Renders pages at 300 DPI via PyMuPDF, detects rotated landscape tables beneath upright running headers, deskews via weighted linear regression across horizontal rules and normalises illumination shadows using a 4x pyramid Gaussian background estimator.
2. **`GraphicalElementDetector`** (`A_` to `E_`): Extracts booktabs frame rules (`top`, `cmidrule`, `header_mid`, `bottom`), splits side-by-side and stacked sub-tables, identifies inline series-break underlines and classifies `{` vs `}` curly braces from left/right outer-edge cusp geometry (`<` vs `>`).
3. **`TokenSegmenter`** (`A_` to `D_`): Masks graphical lines and braces, filters scanner dust, pre-classifies statistical symbols (`...`, `--`, `—`) geometrically and separates smaller raised superscripts and lowered subscripts into dedicated crops prior to OCR.
4. **`GpuOcrEngine`** (`A_` to `D_`): Runs batched fp16 CUDA `parseq` text recognition across full-page crops and normalises superscript/subscript footnote markers.
5. **`BraceAndCellResolver`** (`A_` to `C_`): Maps paired (`}`...`{`) and unilateral (`}` or `{`) braces onto canonical row/column spans, captures vertically off-grid combined figures, heals kerning splits inside numbers and parses bracketed estimates (`[3,691]`) and apostrophe census dates (`14'63`).
6. **`TableStructureReconstructor`** (`A_` to `D_`): Infers stub gutters, multi-tier column header paths (including `\cmidrule` spans and italic unit sub-banners), canonical row grids, mid-table scope qualifiers and dual-series continuation rows.
7. **`SectionAssembler`** (`A_` to `D_`): Extracts running headers, section banners (`A1`, `A2`, ..., `J3`), prose `NOTES` and numbered `FOOTNOTES`, smooths section assignments monotonically across each volume and exports `output/json/<volume_id>/<section_id>.json`.

## 2. Section JSON Schema (`output/json/<volume_id>/<section_id>.json`)

```json
{
  "volume_id": "africa_asia_oceania",
  "volume_title": "International Historical Statistics: Africa, Asia and Oceania 1750-2000",
  "source_pdf": "br_mitchell_africa_asia_oceania.pdf",
  "chapter_id": "A",
  "chapter_title": "Population and Vital Statistics",
  "section_id": "A2",
  "section_title": "Population of Selected Countries by Sex and Age Groups (in thousands)",
  "unit": "in thousands",
  "pdf_pages": [44, 45, 46, 47, 48, 49, 50, 51],
  "book_pages": ["15", "16", "17", "18", "19", "20", "21", "22"],
  "symbols_legend": {
    "...": "not_available",
    "--": "less_than_half_unit",
    "—": "nil"
  },
  "notes": ["1. SOURCES: ..."],
  "footnotes": {
    "1": "Excluding nomad population..."
  },
  "tables": [
    {
      "table_index": 2,
      "pdf_page": 45,
      "book_page": "16",
      "orientation": "portrait",
      "bbox_px": [104, 305, 2748, 1511],
      "region_header": "AFRICA",
      "subtable_title": "MOROCCO",
      "title_footnotes": ["1"],
      "period_banner": null,
      "columns": [
        {
          "col_index": 0,
          "role": "row_stub",
          "header_path": [],
          "label": "row_label",
          "header_footnotes": []
        },
        {
          "col_index": 1,
          "role": "data",
          "header_path": ["1951/2", "M"],
          "label": "1951/2 | M",
          "header_footnotes": ["1"]
        }
      ],
      "brace_groups": [
        {
          "grouped_rows": ["70-74", "75-79"],
          "grouped_columns": ["1951/2 | M", "1951/2 | F"],
          "left_brace": true,
          "right_brace": true,
          "values": [
            {"column": "1951/2 | M", "raw_text": "80", "numeric_value": 80, "footnotes": []},
            {"column": "1951/2 | F", "raw_text": "64", "numeric_value": 64, "footnotes": []}
          ]
        }
      ],
      "rows": [
        {
          "row_index": 0,
          "row_label": "0-4",
          "row_footnotes": [],
          "qualifier": null,
          "series_continuation": false,
          "cells": [
            {
              "col_index": 1,
              "column": "1951/2 | M",
              "raw_text": "683",
              "numeric_value": 683,
              "value_status": "numeric",
              "estimated_bracketed": false,
              "footnotes": [],
              "series_break_underline": false,
              "qualifier": null,
              "row_span": 1,
              "col_span": 1,
              "grouped_rows": ["0-4"],
              "grouped_columns": ["1951/2 | M"]
            }
          ]
        }
      ]
    }
  ]
}
```

### Cell `value_status` Values
- `numeric`: Parsed integer or floating-point value stored in `numeric_value` (with `[...]` estimates flagged via `estimated_bracketed: true`).
- `spanned_by_brace`: Cell covered by a multi-row `{` / `}` curly brace whose combined value resides on `spanned_from_row` (with `row_span > 1` on the top spanned row and full group details in `brace_groups`).
- `not_available`: Geometric or OCR ellipsis (`...`).
- `less_than_half_unit`: Double dash (`--`).
- `nil`: Em-dash (`—`).
- `empty`: Blank cell.
- `text`: Non-numeric textual annotation inside a cell.

