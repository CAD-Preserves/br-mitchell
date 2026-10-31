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

@brief High-throughput CUDA EasyOCR recognition engine with width-bucketed GPU batching.

* **`GpuOcrEngine`** ÔÇö @brief Batched GPU EasyOCR recogniser with contrast-retry fallback and post-OCR token normalisation.
* **`A_loadModel`** ÔÇö @brief Step A: Load pretrained EasyOCR recognition network onto target device without unused CRAFT weights.
* **`B_recogniseCropsBatch`** ÔÇö @brief Step B: Execute width-bucketed GPU EasyOCR recognition across an arbitrary list of token crops.
* **`C_populatePageTokens`** ÔÇö @brief Step C: Batch-recognise all OCR jobs across multiple segmented pages and populate tokens.
* **`D_normaliseSingleToken`** ÔÇö @brief Step D: Normalise OCR text, collapse spurious whitespace, and repair residual comma-group superscript merges.
* **`parseScriptFootnoteString`** ÔÇö @brief Clean a recognised superscript/subscript string into individual footnote/date markers.
* **`runBucketPass`** ÔÇö @brief Resize, right-border-pad, and run batched EasyOCR CRNN greedy decoding for one width bucket.

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

@brief Assembles page-level tables and section banners into simplified per-section JSON files.

* **`SectionAssembler`** ÔÇö @brief Classifies pages into lettered-and-numbered sections (A1, A2, ...), smooths transitions, and exports flat JSON.
* **`A_extractPageHeaderMetadata`** ÔÇö @brief Step A: Parse running header, book page number, chapter hint, and explicit section banner from page tokens.
* **`B_smoothSectionAssignments`** ÔÇö @brief Step B: Resolve missing/noisy section IDs across volume pages using chapter monotonicity and lookahead smoothing.
* **`C_exportVolumeSections`** ÔÇö @brief Step C: Flatten all pages per section (A1, A2, ...) into {<table_key>: {name, subtitle, <place_key>: {...}}} JSON files.
* **`clusterSimpleLines`** ÔÇö @brief Cluster tokens vertically into reading-order lines sorted left-to-right.
* **`extractBookPageNumber`** ÔÇö @brief Extract printed book page number from either outer margin of the running header line.
* **`joinBannerLine`** ÔÇö @brief Join left-to-right banner tokens with single spaces while attaching adjacent punctuation cleanly.
* **`matchChapterTitleToLetter`** ÔÇö @brief Map a running header string (e.g. 'Agriculture', 'Education') to its canonical chapter letter A..J.
* **`parseSectionBannerLine`** ÔÇö @brief Parse a section banner line (e.g. 'A2 AFRICA: Population... (in thousands)', '12 SOUTH AMERICA: STUDENTS...').
* **`splitSectionCode`** ÔÇö @brief Split a canonical section ID like 'A6a' into ('A', 6, 'a').

## `TableDigitiserPipeline.py`

@brief End-to-end reusable CV + GPU OCR table digitisation pipeline orchestrator.

* **`TableDigitiserPipeline`** ÔÇö @brief Orchestrates parallel CPU CV layout/glyph analysis, batched GPU OCR, structure reconstruction, and JSON export.
* **`A_initialiseComponents`** ÔÇö @brief Step A: Instantiate GPU OCR engine, table structure reconstructor, and section assembler.
* **`B_resolveTargetVolumes`** ÔÇö @brief Step B: Resolve configured BR Mitchell volumes or arbitrary user-supplied PDF file paths.
* **`C_processVolumePages`** ÔÇö @brief Step C: Run double-buffered multiprocessing CPU CV + batched GPU OCR + table reconstruction across a volume.
* **`D_runPipeline`** ÔÇö @brief Step D: Execute full digitisation pipeline across resolved volume(s) and write per-section JSON + manifest.

## `TableSeriesFlattener.py`

@brief Flattens reconstructed sub-tables into canonical per-section {name, subtitle, <place_key>: {<indicator>_<year>: number}} JSON.

* **`TableSeriesFlattener`** ÔÇö @brief Maps multi-layout historical tables into clean snake_case place and indicator_year numeric dictionaries.
* **`A_parseSectionTitleAndSubtitle`** ÔÇö @brief Step A: Split a raw section banner title into clean human-readable name and subtitle strings.
* **`B_deriveDefaultIndicator`** ÔÇö @brief Step B: Derive a concise snake_case indicator slug for single-series tables (e.g. 'population', 'electric_energy').
* **`C_flattenTableIntoPlaces`** ÔÇö @brief Step C: Populate places_obj with {<place_key>: {<indicator>_<year>: number}} entries from one reconstructed table.
* **`D_buildSectionDocument`** ÔÇö @brief Step D: Build the complete per-section JSON dictionary {<table_key>: {name, subtitle, <place_key>: {...}}}.
* **`analyseColumnHeader`** ÔÇö @brief Partition a column's header_path segments into years, semantic place/indicator labels, and ignored unit/index lines.
* **`cleanProseSpacing`** ÔÇö @brief Normalise whitespace and heal common OCR kerning artefacts such as '(inthousands)' -> '(in thousands)'.
* **`extractPlaceOverrideFromQualifier`** ÔÇö @brief Detect mid-table sovereign/entity renames over a country column (e.g. 'West Germany' beneath 'Germany').
* **`extractQualifierIndicatorSlug`** ÔÇö @brief Convert a sub-entity/scope qualifier (e.g. 'French Zone') into an indicator prefix, ignoring base-year or 'Whole Country' tags.
* **`extractSubtablePlaceKey`** ÔÇö @brief Extract a valid snake_case place key from a sub-table heading, stripping '(continued)' and rejecting banners/units.
* **`formatRowBandSlug`** ÔÇö @brief Format a curly-brace spanned group of row labels (e.g. ['10-14', '15-19'] -> '10_19', ['60-64', ..., '80 and over'] -> '60_and_over').
* **`formatYearSpanSlug`** ÔÇö @brief Format braced multi-year row labels (e.g. ['1834', '1835'] -> '1834_1835') into a compact year suffix.
* **`isAgeOrBandLabel`** ÔÇö @brief Check whether a row stub label represents a demographic age band rather than a geographic place.
* **`isUnitOrIndexPhrase`** ÔÇö @brief Check whether a header/qualifier phrase is a unit description ('million pounds') or index base ('1913 = 100').
* **`isYearOrRange`** ÔÇö @brief Check whether a string represents a historical year, slash census year ('1951/2'), or year range ('1867-77').
* **`normaliseHeadingCase`** ÔÇö @brief Convert ALL-CAPS banner titles to readable Title Case while preserving already mixed-case headings and acronyms.
* **`resolveMultiCountryColumnPlaces`** ÔÇö @brief Map data columns to country keys when multiple horizontally separated country headings sit above one shared table.
* **`slugifyPlace`** ÔÇö @brief Convert a country, province, or city name into canonical snake_case (e.g. 'U.K.' -> 'uk', 'Guinea Bissau' -> 'guinea_bissau').
* **`slugifyYear`** ÔÇö @brief Normalise a year or slash/range year into clean snake_case (e.g. '1951/2' -> '1951_2').
* **`toSnakeSlug`** ÔÇö @brief Transliterate Latin diacritics to ASCII and convert any phrase into clean lowercase snake_case.

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

* **`TokenSegmenter`** ÔÇö @brief Segments cleaned page masks into word/cell tokens while masking superscripts and subscripts prior to OCR.
* **`A_eraseGraphicalPrimitives`** ÔÇö @brief Step A: Mask out detected rules, cmidrules, underlines, and curly braces from the foreground binary image.
* **`B_extractGlyphsAndWords`** ÔÇö @brief Step B: Filter dust, extract glyph components, and group horizontally adjacent characters into word tokens.
* **`C_classifySymbolsAndSplitScripts`** ÔÇö @brief Step C: Pre-classify geometric symbols (..., --, —) and mask superscripts/subscripts out of OCR crops.
* **`D_segmentPageTokens`** ÔÇö @brief Step D: Run complete token segmentation pipeline (A -> B -> C) on a preprocessed page.
* **`detectTrailingScriptSuffix`** ÔÇö @brief Detect whether a multi-glyph token ends with a smaller raised (superscript) or lowered (subscript) suffix.
* **`splitWideTokenBox`** ÔÇö @brief Split an unusually wide multi-column box only at genuine wide whitespace gaps, never mid-word.

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
