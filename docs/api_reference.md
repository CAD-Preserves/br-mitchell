# API Reference (`core/`)

## `BraceAndCellResolver.py`

@brief Curly-brace span resolver, cell token merger, and statistical numeric/footnote parser.

* **`BraceAndCellResolver`** ÔÇö @brief Resolves curly-brace ({ and }) row/column groupings and builds normalised cell objects.
* **`A_annotateBraceRowSpans`** ÔÇö @brief Step A: Map each detected curly brace onto the canonical row indices covered by [b.y1, b.y2].
* **`B_resolveBraceRegions`** ÔÇö @brief Step B: Resolve paired (}...{) and unilateral (} or {) curly braces into spanned row/column regions.
* **`C_buildCellObject`** ÔÇö @brief Step C: Construct a normalised cell dictionary from the token(s) inside a (row, column) slot.
* **`assignTokenToColumnIndex`** ÔÇö @brief Map a body token to the closest data column index (0-based into data_cols_array).
* **`classifySymbolicString`** ÔÇö @brief Identify statistical missing/nil/sub-unit symbols including minor scanner-smudged ellipsis/dash variants.
* **`collectRegionTokens`** ÔÇö @brief Gather tokens lying inside a braced (row_span x col_set) region, including vertically centred off-grid values.
* **`columnHasSingleCombinedValue`** ÔÇö @brief Check if column arg1_col_idx has exactly 1 line of numeric/symbol content across rows [r0..r1].
* **`isSymbolicMissingToken`** ÔÇö @brief Check whether a token inside a cell represents an ellipsis or dash symbol rather than data text.
* **`mergeCellTokens`** ÔÇö @brief Join tokens inside a single data cell, healing kerning gaps inside numbers (e.g. '28,1' + '12' -> '28,112').
* **`parseNumericToken`** ÔÇö @brief Parse a statistical string into an int/float value, clean display string, bracketed flag, and extra footnotes.
* **`stripAttachedTitleFootnotes`** ÔÇö @brief Separate unsplit footnote digits attached to years ('199069') or names ('Australia86', 'New Zealand1,87').

## `ConfigLoader.py`

@brief Configuration and localisation loader for the table digitisation pipeline.

* **`ConfigLoader`** ÔÇö @brief Loads JSON/JSON5 configuration files from /common/ and localised strings from /localisation/.
* **`formatEuropeanNumber`** ÔÇö @brief Format a numeric value using European decimals (58,88) and semantic suffixes (k, M, B, T).
* **`formatLocalisedString`** ÔÇö @brief Format a localised UI/CLI message replacing £1£, £2£, ... delimiters.
* **`loadAllConfigs`** ÔÇö @brief Load pipeline_config.json5, volumes_config.json5, and active locale file.
* **`loadJson5File`** ÔÇö @brief Parse a JSON or JSON5 file from disk safely without throwing unhandled exceptions.

## `GpuOcrEngine.py`

@brief High-throughput CUDA fp16 Optical Character Recognition engine wrapping DocTR PARSeq/CRNN.

* **`GpuOcrEngine`** ÔÇö @brief Batched GPU word/token recogniser with post-OCR footnote and numeric token normalisation.
* **`A_loadModel`** ÔÇö @brief Step A: Load pretrained DocTR recognition model onto target device (fp16 on CUDA when available).
* **`B_recogniseCropsBatch`** ÔÇö @brief Step B: Execute batched neural text recognition across an arbitrary list of RGB token crops.
* **`C_populatePageTokens`** ÔÇö @brief Step C: Batch-recognise all OCR jobs across multiple segmented pages in one GPU call and populate tokens.
* **`D_normaliseSingleToken`** ÔÇö @brief Step D: Normalise OCR text, attach script footnotes, and repair residual comma-group superscript merges.
* **`parseScriptFootnoteString`** ÔÇö @brief Clean a recognised superscript/subscript string into individual footnote/date markers.

## `GraphicalElementDetector.py`

@brief Computer vision detector for booktabs rules, cmidrules, series-break underlines, and curly braces.

* **`GraphicalElementDetector`** ÔÇö @brief Extracts graphical layout primitives (rules, sub-table blocks, underlines, and braces) from binary masks.
* **`A_detectHorizontalStrokes`** ÔÇö @brief Step A: Detect horizontal line segments and merge collinear fragments broken by faint ink.
* **`B_segmentTableBlocks`** ÔÇö @brief Step B: Group major horizontal rules into column-aligned sub-table blocks (top, mid, bottom).
* **`C_assignSubRulesAndUnderlines`** ÔÇö @brief Step C: Classify non-major horizontal strokes into header cmidrules and body series-break underlines.
* **`D_detectCurlyBraces`** ÔÇö @brief Step D: Detect vertical curly braces ({ and }) inside sub-table bodies and determine cusp direction.
* **`E_detectAllElements`** ÔÇö @brief Step E: Run complete graphical layout detection (strokes -> table blocks -> cmidrules/underlines -> braces).
* **`sortBlocksReadingOrder`** ÔÇö @brief Sort sub-table blocks in natural multi-column reading order (top-down full-width bands, left-to-right panels).
* **`splitRuleStackIntoTables`** ÔÇö @brief Partition a vertical stack of major rules sharing [x1, x2] into individual sub-tables at inter-table gaps.

## `PagePreprocessor.py`

@brief Page rendering, landscape table orientation correction, deskewing, and shadow-free binarisation.

* **`PagePreprocessor`** ÔÇö @brief Converts a scanned PDF page into an upright, deskewed, shadow-normalised 300 DPI image and binary mask.
* **`A_renderPage`** ÔÇö @brief Step A: Render a PDF page at configured DPI into RGB and greyscale numpy arrays.
* **`B_detectAndFixLandscape`** ÔÇö @brief Step B: Detect rotated landscape tables (even beneath upright running headers) and rotate upright.
* **`C_deskewPage`** ÔÇö @brief Step C: Measure sub-degree scan skew from horizontal table rules and text baselines, then deskew.
* **`D_binarisePage`** ÔÇö @brief Step D: Normalise book-gutter illumination shadows and produce a crisp binary foreground mask.
* **`E_preprocessPage`** ÔÇö @brief Step E: Execute full preprocessing pipeline (A -> B -> C -> D) for a single PDF page.
* **`computeIlluminationNormalisedDiff`** ÔÇö @brief Compute illumination-compensated ink contrast in native uint8 SIMD without float32 allocations.
* **`estimateSmoothBackground`** ÔÇö @brief Estimate low-frequency page illumination background via 4x pyramid downsample + Gaussian blur.

## `SectionAssembler.py`

@brief Assembles page-level tables, section banners, notes, and footnotes into per-section JSON files.

* **`SectionAssembler`** ÔÇö @brief Classifies pages into lettered-and-numbered sections (A1, A2, ...), smooths transitions, and exports JSON.
* **`A_extractPageHeaderMetadata`** ÔÇö @brief Step A: Parse running header, book page number, chapter hint, and explicit section banner from page tokens.
* **`B_smoothSectionAssignments`** ÔÇö @brief Step B: Resolve missing/noisy section IDs across volume pages using chapter monotonicity and lookahead smoothing.
* **`C_extractNotesAndFootnotes`** ÔÇö @brief Step C: Extract prose NOTES paragraphs and numbered FOOTNOTES entries outside framed table blocks.
* **`D_exportVolumeSections`** ÔÇö @brief Step D: Aggregate all pages per lettered-and-numbered section (A1, A2, ...) and write JSON files.
* **`clusterSimpleLines`** ÔÇö @brief Cluster tokens vertically into reading-order lines sorted left-to-right.
* **`extractBookPageNumber`** ÔÇö @brief Extract printed book page number from either outer margin of the running header line.
* **`joinProseLineSmart`** ÔÇö @brief Join tokens on a prose or banner line, healing wide-kerned intra-word splits (e.g. 'Popu' + 'lati' + 'on' -> 'Population').
* **`matchChapterTitleToLetter`** ÔÇö @brief Map a running header string (e.g. 'Agriculture', 'Education') to its canonical chapter letter A..J.
* **`parseSectionBannerLine`** ÔÇö @brief Parse a section banner line (e.g. 'A2 AFRICA: Population... (in thousands)', 'Al Population...', '12 SOUTH AMERICA: STUDENTS...').
* **`splitSectionCode`** ÔÇö @brief Split a canonical section ID like 'A6a' into ('A', 6, 'a').

## `TableDigitiserPipeline.py`

@brief End-to-end reusable CV + GPU OCR table digitisation pipeline orchestrator.

* **`TableDigitiserPipeline`** ÔÇö @brief Orchestrates parallel CPU CV layout/glyph analysis, batched GPU OCR, structure reconstruction, and JSON export.
* **`A_initialiseComponents`** ÔÇö @brief Step A: Instantiate GPU OCR engine, table structure reconstructor, and section assembler.
* **`B_resolveTargetVolumes`** ÔÇö @brief Step B: Resolve configured BR Mitchell volumes or arbitrary user-supplied PDF file paths.
* **`C_processVolumePages`** ÔÇö @brief Step C: Run double-buffered multiprocessing CPU CV + batched GPU OCR + table reconstruction across a volume.
* **`D_runPipeline`** ÔÇö @brief Step D: Execute full digitisation pipeline across resolved volume(s) and write per-section JSON + manifest.

## `TableStructureReconstructor.py`

@brief Reconstructs multi-level table headers, canonical row/column grids, qualifiers, and brace spans.

* **`TableStructureReconstructor`** ÔÇö @brief Converts detected graphical blocks and OCR tokens on a page into structured, analysis-ready table objects.
* **`A_extractSubtableMetadata`** ÔÇö @brief Step A: Identify sub-table title, date-range banner, and separate header vs body token sets.
* **`B_inferColumns`** ÔÇö @brief Step B: Reconstruct stub column and data column x-anchors plus multi-level header paths.
* **`C_reconstructRowsAndBraces`** ÔÇö @brief Step C: Build canonical row grid, resolve curly braces via BraceAndCellResolver, underlines, and qualifiers.
* **`D_reconstructPageTables`** ÔÇö @brief Step D: Reconstruct all sub-tables detected on a single page.
* **`attachHeaderTierToColumns`** ÔÇö @brief Attach a horizontal tier of header phrases onto matching data columns via cmidrules or Voronoi/overlap.
* **`clusterColumnCentres`** ÔÇö @brief Discover horizontal data columns by 1D interval clustering of body cell tokens.
* **`clusterTokensIntoLines`** ÔÇö @brief Group tokens sharing approximately the same vertical baseline centre into left-to-right sorted lines.
* **`groupHeaderLeafLine`** ÔÇö @brief Group bottom-row header leaf tokens while never merging two distinct 4-digit year or code headers.
* **`groupLineIntoPhrases`** ÔÇö @brief Group horizontally close words on a single line into multi-word phrases.
* **`isUnitHeaderLine`** ÔÇö @brief Detect whether a bottom header line is an italic unit/scale sub-banner (e.g. 'million pounds', 'thousand dollars').
* **`looksLikeSectionBanner`** ÔÇö @brief Check whether a line above top_rule is the page-wide section banner (e.g. 'A2 AFRICA: Population...', 'A1 Population...').
* **`mergeTokensList`** ÔÇö @brief Merge a left-to-right list of phrase/stub tokens into text, footnotes, and bounding coordinates.

## `TokenSegmenter.py`

@brief Connected-component word tokeniser, statistical symbol classifier, and superscript/subscript splitter.

* **`TokenSegmenter`** ÔÇö @brief Segments cleaned page masks into word/cell tokens while separating superscripts and subscripts prior to OCR.
* **`A_eraseGraphicalPrimitives`** ÔÇö @brief Step A: Mask out detected rules, cmidrules, underlines, and curly braces from the foreground binary image.
* **`B_extractGlyphsAndWords`** ÔÇö @brief Step B: Filter dust, extract glyph components, and group horizontally adjacent characters into word tokens.
* **`C_classifySymbolsAndSplitScripts`** ÔÇö @brief Step C: Pre-classify geometric symbols (..., --, —) and split superscripts/subscripts into separate OCR crops.
* **`D_segmentPageTokens`** ÔÇö @brief Step D: Run complete token segmentation pipeline (A -> B -> C) on a preprocessed page.
* **`detectTrailingScriptSuffix`** ÔÇö @brief Detect whether a multi-glyph token ends with a smaller raised (superscript) or lowered (subscript) suffix.
* **`splitWideTokenBox`** ÔÇö @brief Split an overly wide merged word box at vertical projection whitespace valleys.

## `__init__.py`

@brief Package initialiser with lazy attribute loading so CPU worker processes avoid importing PyTorch.


## `cli_runner.py`

@brief Command-line interface for running the reusable BR Mitchell CV table digitisation pipeline.

* **`buildArgumentParser`** ÔÇö @brief Construct CLI argument parser for single-PDF, single-volume, page-slice, or full-corpus digitisation.
* **`runCli`** ÔÇö @brief Parse CLI arguments and execute TableDigitiserPipeline.

## `cpu_page_worker.py`

@brief Multiprocessing CPU worker routines for rendering, deskewing, layout detection, and token cropping.

* **`A_initCpuWorker`** ÔÇö @brief Step A: Initialise persistent PDF handle and CV processors once per spawned CPU worker process.
* **`B_processSinglePageCpu`** ÔÇö @brief Step B: Execute CPU CV stages (render -> orient/deskew -> rules/braces -> glyph/script crops) for one page.
