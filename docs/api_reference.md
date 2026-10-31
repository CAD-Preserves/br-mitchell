# API Reference (`core/`)

## `AdminDivisionMaskResolver.py`

@brief Resolves modern and historical administrative divisions (1750-2025) across all 57 IHS A3 sub-tables.

* **`AdminDivisionMaskResolver`** ÔÇö @brief Resolves sub-national states, provinces, crownlands, guberniyas, counties, Bezirke, and princely agencies.
* **`A_discoverDelegatedCityKeys`** ÔÇö @brief Step A: Scan all A3 section dictionaries and return city keys delegated to CityMaskResolver (europe/A3 spillovers).
* **`B_resolveAllAdminDivisions`** ÔÇö @brief Step B: Resolve and rasterise every administrative division stem and parent A3 group across all three volumes.
* **`cleanDivisionStem`** ÔÇö @brief Strip trailing census years, footnotes, leading OCR column numbers, and '_revised' from an A3 series key.
* **`extractGroupStems`** ÔÇö @brief Group all raw census series keys inside an A3 group dictionary into clean division stems and active year spans.
* **`matchAdmin1ByNamesOrRegions`** ÔÇö @brief Match features in ne_admin1 by country code and state/province names or region names.
* **`matchGadmFeatures`** ÔÇö @brief Match features in a UC Davis GADM 4.1 country/level layer using compact space-insensitive ASCII slugs.
* **`matchGermany1914Features`** ÔÇö @brief Match 1914 Imperial German constituent states (STAAT_NAME) or Regierungsbezirke (REG_NAME).
* **`matchRussia1897Features`** ÔÇö @brief Match 1897 Russian Empire governorates / oblasts by source_english property.
* **`matchUkCountiesFeatures`** ÔÇö @brief Match UK ceremonial / historic counties from uk_counties, with automatic ne_admin1 GBR fallback.
* **`resolveRuleGeometryIndices`** ÔÇö @brief Execute the configured geospatial lookup and scanline rasterisation for a single division rule.
* **`resolveSingleDivision`** ÔÇö @brief Resolve and cache a single canonical administrative division entity ('admin:<prefix>:<clean_stem>').
* **`resolveSpilledGroupHeaderMask`** ÔÇö @brief Provide explicit polygon indices when an A3 group key itself is a page-break spilled division (e.g. 'ufa', 'sardinia').

## `ArealMaskPipeline.py`

@brief End-to-end orchestrator and verifier for BR Mitchell WGS84 Equirectangular (4320x2160) areal masks.

* **`ArealMaskPipeline`** ÔÇö @brief Orchestrates online vector fetching, country/subadmin/city resolution, provinces.png synthesis and 100% corpus verification.
* **`A_loadCorpusSections`** ÔÇö @brief Step A: Load all digitised IHS section JSON files across africa_asia_oceania, americas and europe.
* **`B_resolveAllEntities`** ÔÇö @brief Step B: Resolve all whole countries, individual city [lng, lat] points and sub-national administrative divisions.
* **`C_synthesiseRasters`** ÔÇö @brief Step C: Synthesise provinces.png (4320x2160 RGB) and register parent A3 group colourcode lists.
* **`D_buildFlatMaskMaps`** ÔÇö @brief Step D: Construct the 3 flat dictionaries: country_masks_map, subadmin_masks_map and city_masks_map.
* **`E_runFullPipeline`** ÔÇö @brief Step E: Execute the full areal mask synthesis pipeline, export the 3 flat JSON maps and verify 100% coverage.
* **`mergeEntityRgbLists`** ÔÇö @brief Merge and sort unique [R, G, B] triplets across one or more canonical entity IDs.
* **`verifyCompleteDeliverables`** ÔÇö @brief Reload provinces.png and the 3 exported flat JSON maps from disk and verify 100% of output/json locations.

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

## `CityMaskResolver.py`

@brief Resolves individual city [lng, lat] coordinates via Wikipedia GeoHack, Photon (OpenStreetMap) and Nominatim.

* **`CityMaskResolver`** ÔÇö @brief Geocodes all corpus cities to WGS84 [lng, lat] coordinates using GeoHack, Photon OSM and Nominatim.
* **`A_resolveAllCities`** ÔÇö @brief Step A: Geocode all unique city keys via Wikipedia GeoHack and Photon OSM into [lng, lat] coordinates.
* **`buildCityQueryPlan`** ÔÇö @brief Construct Wikipedia GeoHack title and Photon OpenStreetMap query parameters for a city key.
* **`fetchPhotonForMissing`** ÔÇö @brief Query Photon OpenStreetMap API sequentially for cities unresolved by Wikipedia GeoHack and persist disk cache.
* **`isNonCityCorpusKey`** ÔÇö @brief Check whether an A4 corpus key is an explicit country spillover (e.g. americas:A4:canada).
* **`queryPhotonSingle`** ÔÇö @brief Perform a single HTTP GET against Photon OSM API and indicate whether HTTP 200 succeeded.
* **`selectBestCoordinates`** ÔÇö @brief Cross-validate Wikipedia GeoHack and Photon OSM coordinates for a city, falling back to Nominatim point lookup if needed.

## `ConfigLoader.py`

@brief Configuration and localisation loader for the table digitisation pipeline.

* **`ConfigLoader`** ÔÇö @brief Loads JSON/JSON5 configuration files from /common/ and localised strings from /localisation/.
* **`formatEuropeanNumber`** ÔÇö @brief Format a numeric value using European decimals (58,88) and semantic suffixes (k, M, B, T).
* **`formatLocalisedString`** ÔÇö @brief Format a localised UI/CLI message replacing £1£, £2£, ... delimiters.
* **`loadAllConfigs`** ÔÇö @brief Load pipeline_config.json5, volumes_config.json5, and active locale file.
* **`loadJson5File`** ÔÇö @brief Parse a JSON or JSON5 file from disk safely without throwing unhandled exceptions.

## `CountryMaskResolver.py`

@brief Resolves modern, colonial, and historical whole-country areal masks (1750-2025) from online vector layers.

* **`CountryMaskResolver`** ÔÇö @brief Resolves canonical country definitions and maps corpus location keys to canonical country entities.
* **`A_resolveAllCountries`** ÔÇö @brief Step A: Rasterise all canonical modern and historical country entities onto the 4320x2160 grid.
* **`B_resolveCorpusCountryKey`** ÔÇö @brief Step B: Resolve a raw corpus JSON location key to one or more canonical country IDs.
* **`extractCandidateTokens`** ÔÇö @brief Generate progressive prefix/suffix-stripped slug candidates from an OCR or footnote-suffixed corpus key.
* **`matchAdmin0Features`** ÔÇö @brief Match features in ne_admin0, ne_map_units, or ne_subunits using ISO_A3, ADM0_A3, GU_A3, or SU_A3 codes.
* **`matchAdmin1Features`** ÔÇö @brief Match state/province features in ne_admin1 for sub-national country entries (e.g. Alaska, Hawaii, Java & Madura).
* **`matchBritishIndiaFeatures`** ÔÇö @brief Match features from the 1948 British India shapefile layer (e.g. Portuguese Settlements in India).
* **`matchCshapesFeatures`** ÔÇö @brief Match historical sovereign or colonial state polygons in ETH Zürich CShapes 2.0 by gwcode and target year.
* **`matchHistoricalBasemapFeatures`** ÔÇö @brief Match features from historical world basemap GeoJSONs (e.g. hist_1880) or single-territory historical layers.
* **`normaliseTargetList`** ÔÇö @brief Convert a string or list of country IDs into a validated list of canonical country IDs.
* **`resolveSingleCountry`** ÔÇö @brief Resolve and rasterise a single canonical country entity (supporting recursive union and set difference).
* **`scanSubObjectCountries`** ÔÇö @brief Extract canonical country IDs embedded in nested time-series sub-keys (e.g. 'austria_1950', 'japan_1970').

## `EquirectangularRasteriser.py`

@brief WGS84 Equirectangular scanline polygon rasteriser and lossless PNG exporter.

* **`EquirectangularRasteriser`** ÔÇö @brief Scanline-rasterises WGS84 GeoJSON/Shapely geometries onto a 4320x2160 Equirectangular grid.
* **`A_rasteriseGeometry`** ÔÇö @brief Step A: Scanline-rasterise a GeoJSON dict, Shapely geometry, or list of geometries to sorted flat pixel indices.
* **`B_exportRgbPng`** ÔÇö @brief Step B: Export a (height, width, 3) uint8 RGB numpy buffer as a lossless PNG image.
* **`computeMaskMetrics`** ÔÇö @brief Compute pixel count, pixel bounding box, WGS84 bounding box, and WGS84 centroid from flat pixel indices.
* **`extractPolygons`** ÔÇö @brief Recursively unpack GeoJSON dicts, Feature dicts, or Shapely geometries into valid Shapely Polygons.
* **`lonLatToFlatIndexArray`** ÔÇö @brief Convert a single WGS84 (lon, lat) coordinate into a 1-element int32 flat pixel index array.
* **`rasteriseBbox`** ÔÇö @brief Rasterise a WGS84 bounding box [west, south, east, north] directly to flat pixel indices.
* **`rasterisePointDisc`** ÔÇö @brief Rasterise an equirectangular urban disc centred at (lon, lat) with latitude cosine compensation.
* **`rasteriseSinglePolygon`** ÔÇö @brief Scanline-rasterise a single non-dateline-crossing Shapely Polygon (exterior minus interior holes).
* **`splitAntimeridianPolygon`** ÔÇö @brief Split polygons that wrap across the +-180 degree antimeridian into valid [-180, 180] parts.
* **`getConfiguredWidth`** ÔÇö @brief Read validated grid width from configuration dictionary.

## `GeoJsonFetcher.py`

@brief Online GeoJSON, GADM archive, ESRI Shapefile, Wikipedia GeoHack, Photon OSM and Nominatim fetcher.

* **`GeoJsonFetcher`** ÔÇö @brief Downloads, caches, and parses online vector boundary layers and city geocoding APIs.
* **`A_fetchBaseLayer`** ÔÇö @brief Step A: Fetch and parse a configured base geospatial layer (GeoJSON or zipped WGS84 ESRI Shapefile).
* **`B_fetchGadmLayer`** ÔÇö @brief Step B: Fetch UC Davis GADM 4.1 GeoJSON (plain .json or .json.zip) for an ISO3 country and admin level.
* **`C_fetchWikipediaCoordinatesBatch`** ÔÇö @brief Step C: Batch-query Wikipedia GeoData API (GeoHack source) for article coordinates with HTTP 429 backoff.
* **`D_fetchPhotonCity`** ÔÇö @brief Step D: Query Photon (photon.komoot.io/api/) for OpenStreetMap city coordinates and extent bounding box.
* **`E_fetchNominatimPolygon`** ÔÇö @brief Step E: Fetch a GeoJSON polygon from Nominatim OpenStreetMap search with polite 1,1 s rate limiting, retry and disk caching.
* **`F_fetchNominatimCityPoint`** ÔÇö @brief Step F: Fetch exact city-centre (lon, lat) and bounding box from Nominatim OpenStreetMap search.
* **`downloadUrlToFile`** ÔÇö @brief Download an HTTP URL to disk atomically with retry support.
* **`healFeatureCollectionStrings`** ÔÇö @brief Heal Latin-1-as-UTF-8 mojibake (e.g. 'PreuÃŸen' -> 'Preußen') across all feature property dictionaries.
* **`loadApiCaches`** ÔÇö @brief Load persisted Wikipedia, Photon, and Nominatim JSON caches if present in cache_dir.
* **`normaliseAsciiSlug`** ÔÇö @brief Transliterate accented/Germanic characters and normalise a string into an ASCII snake_case slug.
* **`parseDbfBytes`** ÔÇö @brief Parse an ESRI dBASE III/IV (.dbf) binary table into a list of property dictionaries.
* **`parseShapefileZip`** ÔÇö @brief Parse a zipped WGS84 ESRI Polygon Shapefile (.shp + .dbf) into a GeoJSON FeatureCollection.
* **`readGeoJsonDisk`** ÔÇö @brief Fast-load a JSON/GeoJSON file from disk using orjson with stdlib json fallback.
* **`ringsToGeoJsonMultiPolygon`** ÔÇö @brief Classify ESRI Shapefile clockwise exterior rings and counter-clockwise interior hole rings into GeoJSON geometry.
* **`saveJsonCache`** ÔÇö @brief Persist an API cache dictionary to disk using orjson.
* **`writeGeoJsonDisk`** ÔÇö @brief Serialise a parsed FeatureCollection dictionary to disk cache.

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

@brief Computer vision detector for booktabs rules, cmidrules, series-break underlines and curly braces.

* **`GraphicalElementDetector`** ÔÇö @brief Extracts graphical layout primitives (rules, sub-table blocks, underlines and braces) from binary masks.
* **`A_detectHorizontalStrokes`** ÔÇö @brief Step A: Detect horizontal line segments and merge collinear fragments broken by faint ink.
* **`B_segmentTableBlocks`** ÔÇö @brief Step B: Group major horizontal rules into column-aligned sub-table blocks (top, mid, bottom).
* **`C_assignSubRulesAndUnderlines`** ÔÇö @brief Step C: Classify non-major horizontal strokes into header cmidrules, body column spans and underlines.
* **`D_detectCurlyBraces`** ÔÇö @brief Step D: Detect vertical curly braces ({ and }) inside sub-table bodies and determine cusp direction.
* **`E_detectAllElements`** ÔÇö @brief Step E: Run complete graphical layout detection (strokes -> table blocks -> cmidrules/underlines -> braces).
* **`filterNestedTableBlocks`** ÔÇö @brief Suppress candidate blocks strictly enclosed inside a wider outer sub-table (e.g. horizontal underbraces).
* **`probeBodyBelowMissingBottomRule`** ÔÇö @brief Probe below the lowest header rule when a sub-table's bottom rule was cropped or faint.
* **`sortBlocksReadingOrder`** ÔÇö @brief Sort sub-table blocks in natural multi-column reading order (top-down full-width bands, left-to-right panels).
* **`splitRuleStackIntoTables`** ÔÇö @brief Partition a vertical stack of major rules sharing [x1, x2] into individual sub-tables at inter-table gaps.
* **`synthesiseSteppedBottomRules`** ÔÇö @brief Synthesise full-width bottom rules for stepped tables where left and right column blocks end at different depths.

## `HeaderHierarchyResolver.py`

@brief Multi-tier table column header resolver with cmidrule span matching, 1-to-1 wrap merging and de-hyphenation.

* **`HeaderHierarchyResolver`** ÔÇö @brief Resolves multi-line table column headers without Voronoi smearing across blank header space.
* **`A_extractLeafAndUpperTiers`** ÔÇö @brief Step A: Partition clustered header lines into column leaf phrases, stub label and upper/unit tiers.
* **`B_attachUpperTiersToColumns`** ÔÇö @brief Step B: Attach upper and unit header tiers onto data columns via cmidrules, centred spans or 1-to-1 wraps.
* **`C_normaliseAndMergeColumnPaths`** ÔÇö @brief Step C: Heal single-letter I/E OCR errors, de-hyphenate and merge 1-to-1 wrapped column leaves.
* **`groupHeaderLeafLine`** ÔÇö @brief Group bottom-row header leaf tokens while never merging two distinct 4-digit year or code headers.
* **`groupLineIntoPhrases`** ÔÇö @brief Group horizontally close words on a single line into multi-word phrases.
* **`isRepeatingSubindicatorLeaves`** ÔÇö @brief Check whether leaf column labels consist of repeating short sub-indicators or years (e.g. M/F/Total, I/E).
* **`isUnitHeaderLine`** ÔÇö @brief Detect whether a header line is an italic unit/scale sub-banner (e.g. 'million pounds', 'thousand dollars').
* **`isYearHeaderText`** ÔÇö @brief Check whether a header segment represents a historical year or year range.
* **`mergeTokensList`** ÔÇö @brief Merge a left-to-right list of tokens into text, footnotes and bounding coordinates.
* **`resolveTierColumnAssignments`** ÔÇö @brief Map one horizontal tier of header phrases onto data columns without Voronoi extrapolation across blank space.
* **`shouldMergeWrappedPair`** ÔÇö @brief Decide whether two consecutive single-column header lines form one wrapped phrase and return merged string.

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

## `PlaceKeyNormaliser.py`

@brief Canonical geographic place-key normaliser, OCR artefact healer and non-place indicator filter.

* **`PlaceKeyNormaliser`** ÔÇö @brief Normalises country, province and city names into snake_case keys and rejects numeric, unit or indicator strings.
* **`A_normalisePlaceKey`** ÔÇö @brief Step A: Heal OCR artefacts, strip footnote numbers, units and admin scopes, and return a validated place key.
* **`B_isValidPlaceKey`** ÔÇö @brief Step B: Strictly validate a candidate snake_case place key against numbers, years, prices, units and sectors.
* **`C_classifySubtableHeading`** ÔÇö @brief Step C: Classify a sub-table heading as either a geographic place_key or a commodity/price indicator_prefix.
* **`isIndicatorPhrase`** ÔÇö @brief Check whether a column header or row phrase consists solely of economic sector, commodity or demographic words.
* **`isMacroRegion`** ÔÇö @brief Check whether a header segment is a continent/macro-region label (e.g. 'NORTH AMERICA', 'EUROPE').
* **`toSnakeSlug`** ÔÇö @brief Transliterate Latin diacritics to ASCII and convert any phrase into clean lowercase snake_case.

## `ProvinceMapSynthesizer.py`

@brief Synthesises the collision-free 4320x2160 RGB provinces.png raster and exports the 3 flat JSON mask maps.

* **`ProvinceMapSynthesizer`** ÔÇö @brief Partitions overlapping historical/modern masks into atomic RGB provinces and exports flat JSON deliverables.
* **`A_synthesiseProvincesPng`** ÔÇö @brief Step A: Partition all modern/historical country and admin-division masks into atomic RGB provinces on provinces.png.
* **`B_registerAdminGroupMasks`** ÔÇö @brief Step B: Aggregate constituent province [R, G, B] colourcodes for all non-spillover A3 parent groups.
* **`C_exportFlatJsonMaps`** ÔÇö @brief Step C: Clean obsolete outputs and write country_masks.json, subadmin_masks.json and city_masks.json.
* **`generateDistinctRgbPalette`** ÔÇö @brief Generate deterministic, collision-free, high-visibility non-zero RGB colours ([R, G, B] != [0, 0, 0]).
* **`partitionEquivalenceClasses`** ÔÇö @brief Partition pixels across potentially overlapping entities into exact atomic equivalence classes with certified 0 collisions.
* **`writeCompactFlatJson`** ÔÇö @brief Serialise a flat key -> value JSON dictionary atomically with one 2-space indented entry per line.

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
* **`formatTableDisplayName`** ÔÇö @brief Build a concise human-readable table identifier (e.g. 'A1 (Algeria)', 'A2 (MALI / NIGERIA)', 'C1') for progress logs.
* **`updateLiveSectionState`** ÔÇö @brief Maintain live monotonic section state across streaming pages for real-time progress readout.

## `TableSeriesFlattener.py`

@brief Flattens reconstructed sub-tables into canonical per-section {name, subtitle, <place_key>: {<indicator>_<year>: number}} JSON.

* **`TableSeriesFlattener`** ÔÇö @brief Maps multi-layout historical tables into clean snake_case place and indicator_year numeric dictionaries.
* **`A_parseSectionTitleAndSubtitle`** ÔÇö @brief Step A: Split a raw section banner title into clean human-readable name and subtitle strings.
* **`B_deriveDefaultIndicator`** ÔÇö @brief Step B: Derive a concise snake_case indicator slug for single-series tables (e.g. 'population', 'aluminium').
* **`C_flattenTableIntoPlaces`** ÔÇö @brief Step C: Populate places_obj with {<place_key>: {<indicator>_<year>: number}} entries from one reconstructed table.
* **`D_buildSectionDocument`** ÔÇö @brief Step D: Build the complete per-section JSON dictionary {<table_key>: {name, subtitle, <place_key>: {...}}}.
* **`analyseColumnHeader`** ÔÇö @brief Partition a column's header_path segments into years, semantic place/indicator labels and ignored unit/index lines.
* **`applyOrCacheColumnSchema`** ÔÇö @brief Cache explicit pure-indicator column headers and apply them onto subsequent headerless col_1..col_C blocks.
* **`cleanProseSpacing`** ÔÇö @brief Normalise whitespace and heal common OCR kerning artefacts such as '(inthousands)' -> '(in thousands)'.
* **`detectInternalDateColumns`** ÔÇö @brief Detect mid-table Date/Year stub columns in side-by-side multi-country tables (e.g. Sikkim | Portuguese Settlements).
* **`extractPlaceOverrideFromQualifier`** ÔÇö @brief Detect mid-table sovereign/entity renames over a country column (e.g. 'West Germany' beneath 'Germany').
* **`extractQualifierIndicatorSlug`** ÔÇö @brief Convert a sub-scope qualifier ('Males', '1957 prices', 'French Zone') into an indicator prefix.
* **`formatRowBandSlug`** ÔÇö @brief Format a curly-brace spanned group of row labels (e.g. ['10-14', '15-19'] -> '10_19') into a compact band slug.
* **`formatSingleAgeSlug`** ÔÇö @brief Normalise single-year infant ('0'), space-separated ('0 4') and merged ('6064') age labels into canonical slugs.
* **`formatYearSpanSlug`** ÔÇö @brief Format braced multi-year row labels (e.g. ['1834', '1835'] -> '1834_1835') into a compact year suffix.
* **`isAgeOrBandLabel`** ÔÇö @brief Check whether a row stub label represents a demographic age band (including infant '0', '0 4' and '6064').
* **`isUnitOrIndexPhrase`** ÔÇö @brief Check whether a header/qualifier phrase is a unit description ('million pounds') or index base ('1913 = 100').
* **`isYearOrRange`** ÔÇö @brief Check whether a string represents a historical year, slash census year ('1951/2') or year range ('1867-77').
* **`normaliseHeadingCase`** ÔÇö @brief Convert ALL-CAPS banner titles to readable Title Case while preserving already mixed-case headings and acronyms.
* **`resolveMultiCountryColumnPlaces`** ÔÇö @brief Map data columns to country keys when horizontally separated country headings sit above a shared table.
* **`slugifyYear`** ÔÇö @brief Normalise a year or slash/range year into clean snake_case (e.g. '1951/2' -> '1951_2').
* **`toSnakeSlug`** ÔÇö @brief Convert any phrase into clean lowercase ASCII snake_case via PlaceKeyNormaliser.

## `TableStructureReconstructor.py`

@brief Reconstructs multi-level table headers, canonical row/column grids, two-tier qualifiers and brace spans.

* **`TableStructureReconstructor`** ÔÇö @brief Converts detected graphical blocks and OCR tokens on a page into structured, analysis-ready table objects.
* **`A_extractSubtableMetadata`** ÔÇö @brief Step A: Identify sub-table title, date-range banner and separate header vs body token sets.
* **`B_inferColumns`** ÔÇö @brief Step B: Reconstruct stub column and data column x-anchors plus clean multi-level header paths.
* **`C_reconstructRowsAndBraces`** ÔÇö @brief Step C: Build canonical row grid, resolve vertical/horizontal spans and track two-tier row banners.
* **`D_reconstructPageTables`** ÔÇö @brief Step D: Reconstruct all sub-tables detected on a single page after masking full-page banner bounds.
* **`clusterColumnCentres`** ÔÇö @brief Discover horizontal data columns by 1D interval clustering of body cell tokens.
* **`clusterTokensIntoLines`** ÔÇö @brief Group tokens sharing approximately the same vertical baseline centre into left-to-right sorted lines.
* **`isPeriodBannerText`** ÔÇö @brief Check whether a header string is a date-range period banner (including clipped/OCR-noisy ends like '1846-20c').
* **`isSubscopeBanner`** ÔÇö @brief Classify an in-body text row as 'reset' ('Whole country'), 'subscope' ('Males', '1957 prices') or None (place banner).
* **`looksLikeSectionBanner`** ÔÇö @brief Check whether a line above top_rule is a page-wide section banner (including D1O/D2O OCR variants).

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


## `areal_mask_runner.py`

@brief Command-line runner for generating and verifying 4320x2160 WGS84 Equirectangular areal masks for IHS.

* **`buildArgumentParser`** ÔÇö @brief Construct CLI argument parser for the BR Mitchell areal mask pipeline.
* **`runArealMaskCli`** ÔÇö @brief Parse CLI arguments, execute ArealMaskPipeline, and exit non-zero if any location is unaccounted.

## `cli_runner.py`

@brief Command-line interface for running the reusable BR Mitchell CV table digitisation pipeline.

* **`buildArgumentParser`** ÔÇö @brief Construct CLI argument parser for single-PDF, single-volume, page-slice, or full-corpus digitisation.
* **`runCli`** ÔÇö @brief Parse CLI arguments and execute TableDigitiserPipeline.

## `cpu_page_worker.py`

@brief Multiprocessing CPU worker routines for rendering, deskewing, layout detection, and token cropping.

* **`A_initCpuWorker`** ÔÇö @brief Step A: Initialise persistent PDF handle and CV processors once per spawned CPU worker process.
* **`B_processSinglePageCpu`** ÔÇö @brief Step B: Execute CPU CV stages (render -> orient/deskew -> rules/braces -> glyph/script crops) for one page.
