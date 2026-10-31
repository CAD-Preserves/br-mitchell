"""@brief Flattens reconstructed sub-tables into canonical per-section {name, subtitle, <place_key>: {<indicator>_<year>: number}} JSON."""

import re
import unicodedata


class TableSeriesFlattener:
  """@brief Maps multi-layout historical tables into clean snake_case place and indicator_year numeric dictionaries."""

  def __init__ (self, arg1_config_obj):
    """
    @brief Initialise TableSeriesFlattener with vocabulary and prefix rules from /common/digitiser/.
    @param arg1_config_obj Pipeline configuration dictionary.
    """
    #Convert from parameters
    config_obj = arg1_config_obj if isinstance(arg1_config_obj, dict) else {}

    #Declare local instance variables
    flat_cfg = config_obj.get("series_flattening", {})
    self.default_fallback_ind = str(flat_cfg.get("default_fallback_indicator", "value"))
    self.max_ind_words = int(flat_cfg.get("max_derived_indicator_words", 4))
    self.pure_indicators_set = {
      "arrivals", "b", "births", "boys", "cargo", "d", "deaths", "departures", "exports", "f",
      "female", "females", "freight", "girls", "goods", "imports", "infants", "m", "male",
      "males", "marriages", "men", "passengers", "re_exports", "sailing", "steam", "tonnage",
      "total", "totals", "value", "vessels", "volume", "women"
    }
    self.reserved_keys_set = {"name", "subtitle"}
    self.strip_prefixes_array = [str(p).lower() for p in flat_cfg.get("strip_title_prefixes", [])]
    self.strip_scopes_array = [str(s).lower() for s in flat_cfg.get("strip_title_scope_nouns", [])]
    self.unit_vocab_set = {str(u).lower() for u in flat_cfg.get("unit_vocab", [])}
    self.whole_qualifiers_set = {str(q).lower() for q in flat_cfg.get("whole_entity_qualifiers", [])}


  def A_parseSectionTitleAndSubtitle (self, arg1_raw_title, arg2_raw_unit=None):
    """
    @brief Step A: Split a raw section banner title into clean human-readable name and subtitle strings.
    @param arg1_raw_title Raw section title string extracted from the page banner.
    @param arg2_raw_unit Optional unit string extracted from trailing parentheses.
    @return Tuple (clean_name_str, clean_subtitle_str).
    """
    #Convert from parameters
    raw_title = str(arg1_raw_title or "").strip()
    raw_unit = str(arg2_raw_unit or "").strip()

    #Declare local instance variables
    clean_name = ""
    clean_sub = ""
    work = re.sub(r"\s+", " ", raw_title).strip()

    # Strip regional prefixes and '(continued)' markers
    work = re.sub(
      r"^(?:AFRICA|ASIA|OCEANIA|NORTH\s+AMERICA|CENTRAL\s+AMERICA|SOUTH\s+AMERICA|EUROPE)\s*:\s*",
      "",
      work,
      flags=re.IGNORECASE
    ).strip()
    work = re.sub(r"\s*\(continued\)\s*$", "", work, flags=re.IGNORECASE).strip()

    # Repair occasional missing space inside '(inthousands)' -> 'in thousands'
    paren_m = re.search(r"\(([^()]+)\)\s*$", work)
    if paren_m:
      cand_sub = paren_m.group(1).strip()
      if "continued" not in cand_sub.lower():
        clean_sub = self.cleanProseSpacing(cand_sub)
        work = work[:paren_m.start()].strip()

    if not clean_sub and raw_unit and "continued" not in raw_unit.lower():
      clean_sub = self.cleanProseSpacing(raw_unit)

    if not clean_sub and ":" in work:
      left_p, right_p = work.split(":", 1)
      clean_name = self.normaliseHeadingCase(self.cleanProseSpacing(left_p))
      clean_sub = self.normaliseHeadingCase(self.cleanProseSpacing(right_p))
    else:
      clean_name = self.normaliseHeadingCase(self.cleanProseSpacing(work))

    if clean_sub and clean_sub.isupper():
      clean_sub = self.normaliseHeadingCase(clean_sub)

    #Return statement
    return (clean_name, clean_sub)


  def B_deriveDefaultIndicator (self, arg1_section_name, arg2_chapter_title=""):
    """
    @brief Step B: Derive a concise snake_case indicator slug for single-series tables (e.g. 'population', 'electric_energy').
    @param arg1_section_name Clean section name string from Step A.
    @param arg2_chapter_title Optional chapter title fallback.
    @return Non-empty snake_case indicator string.
    """
    #Convert from parameters
    sec_name = str(arg1_section_name or "").strip()
    chap_title = str(arg2_chapter_title or "").strip()

    #Declare local instance variables
    slug = ""
    words_array = []
    work = sec_name.lower()

    work = re.sub(r"\([^()]*\)", " ", work)
    if ":" in work:
      lhs, rhs = [p.strip() for p in work.split(":", 1)]
      if chap_title and lhs == chap_title.lower():
        work = rhs
      else:
        work = lhs

    work = re.sub(r"\s+", " ", work).strip()

    for i in range(len(self.strip_prefixes_array)):
      pfx = self.strip_prefixes_array[i]
      if work.startswith(pfx + " "):
        work = work[len(pfx):].strip()
        break

    for i in range(len(self.strip_scopes_array)):
      scp = self.strip_scopes_array[i]
      work = re.sub(rf"\b(?:of|in|at|by|for)\s+{re.escape(scp)}\b.*$", "", work).strip()

    slug = self.toSnakeSlug(work)
    if slug:
      words_array = [w for w in slug.split("_") if w]
      if len(words_array) > self.max_ind_words:
        words_array = words_array[:self.max_ind_words]
      slug = "_".join(words_array)

    if not slug and chap_title:
      slug = self.toSnakeSlug(chap_title)

    #Return statement
    return slug if slug else self.default_fallback_ind


  def C_flattenTableIntoPlaces (self, arg1_table_obj, arg2_default_indicator, arg3_places_obj, arg4_last_place=None):
    """
    @brief Step C: Populate places_obj with {<place_key>: {<indicator>_<year>: number}} entries from one reconstructed table.
    @param arg1_table_obj Reconstructed sub-table dictionary.
    @param arg2_default_indicator Derived default indicator slug for single-series columns/rows.
    @param arg3_places_obj Mutable dictionary accumulating per-place series across the section.
    @param arg4_last_place Optional place_key from the preceding sub-table for untitled continuations.
    @return Updated active sub-table place_key (or arg4_last_place).
    """
    #Convert from parameters
    tbl = arg1_table_obj if isinstance(arg1_table_obj, dict) else {}
    default_ind = str(arg2_default_indicator or self.default_fallback_ind)
    places_obj = arg3_places_obj if isinstance(arg3_places_obj, dict) else {}
    last_place = arg4_last_place

    #Declare local instance variables
    col_lookup_obj = {}
    cols_array = tbl.get("columns", [])
    rows_array = tbl.get("rows", [])
    subtable_place = self.extractSubtablePlaceKey(tbl.get("subtable_title"))

    if not rows_array or len(cols_array) <= 1:
      return subtable_place or last_place

    for i in range(len(cols_array)):
      c = cols_array[i]
      if c.get("role") == "data":
        col_lookup_obj[c["col_index"]] = self.analyseColumnHeader(c.get("header_path", []))

    if not col_lookup_obj:
      return subtable_place or last_place

    multi_col_places_map, last_multi_place = self.resolveMultiCountryColumnPlaces(
      cols_array,
      col_lookup_obj,
      tbl.get("above_phrases", [])
    )

    # Detect untitled continuation sub-tables (e.g. 'M | F | Total' or '1960 | M' continuing previous country across column/page break)
    active_place = subtable_place
    if active_place is None and not multi_col_places_map and last_place is not None:
      all_pure_ind = all(
        (not info["semantic"]) or (len(info["semantic"]) == 1 and self.toSnakeSlug(info["semantic"][0]) in self.pure_indicators_set)
        for info in col_lookup_obj.values()
      )
      sample_rows_age = sum(1 for r in rows_array if self.isAgeOrBandLabel(r.get("row_label", "")))
      if all_pure_ind and (not any(info["years"] for info in col_lookup_obj.values()) or sample_rows_age >= max(1, len(rows_array)//3)):
        active_place = last_place

    for i in range(len(rows_array)):
      r = rows_array[i]
      raw_rlbl = str(r.get("row_label", "")).strip()
      row_qual = str(r.get("qualifier") or "").strip()
      is_cont_row = bool(r.get("series_continuation", False))
      row_is_yr = self.isYearOrRange(raw_rlbl)
      cells_array = r.get("cells", [])

      for x in range(len(cells_array)):
        cell = cells_array[x]
        if cell.get("value_status") != "numeric":
          continue
        num_val = cell.get("numeric_value")
        if not isinstance(num_val, (int, float)) or isinstance(num_val, bool):
          continue

        c_info = col_lookup_obj.get(cell.get("col_index"))
        if c_info is None:
          continue

        grouped_rows = cell.get("grouped_rows") or ([raw_rlbl] if raw_rlbl else [])
        row_span = int(cell.get("row_span", 1))
        cell_qual = str(cell.get("qualifier") or row_qual or "").strip()
        mapped_place = multi_col_places_map.get(cell.get("col_index"))
        effective_place = mapped_place if mapped_place else active_place

        place_key = None
        ind_slug = ""
        yr_slug = ""

        # Case 1: Rows are years and sub-table/column belongs to a known place (e.g. A1 Guinea Bissau, A6 Sri Lanka side-table)
        if (row_is_yr or (row_span > 1 and grouped_rows and all(self.isYearOrRange(gr) for gr in grouped_rows))) and effective_place:
          place_key = effective_place
          yr_slug = self.formatYearSpanSlug(grouped_rows) if row_span > 1 else self.slugifyYear(raw_rlbl)
          ind_parts = []
          qual_slug = self.extractQualifierIndicatorSlug(cell_qual)
          if qual_slug:
            ind_parts.append(qual_slug)
          for y in range(len(c_info["semantic"])):
            s_slug = self.toSnakeSlug(c_info["semantic"][y])
            if s_slug and s_slug != place_key:
              ind_parts.append(s_slug)
          ind_slug = "_".join(ind_parts) if ind_parts else default_ind

        # Case 2: Rows are years and columns specify places (+ optional indicators like Wheat/Barley or Imports/Exports)
        elif row_is_yr or (row_span > 1 and grouped_rows and all(self.isYearOrRange(gr) for gr in grouped_rows)):
          if not c_info["semantic"]:
            continue
          yr_slug = self.formatYearSpanSlug(grouped_rows) if row_span > 1 else self.slugifyYear(raw_rlbl)
          raw_col_place = c_info["semantic"][0]
          override_place = self.extractPlaceOverrideFromQualifier(cell_qual, raw_col_place)
          place_key = override_place if override_place else self.slugifyPlace(raw_col_place)

          ind_parts = []
          for y in range(1, len(c_info["semantic"])):
            s_slug = self.toSnakeSlug(c_info["semantic"][y])
            if s_slug:
              ind_parts.append(s_slug)
          if not override_place:
            qual_slug = self.extractQualifierIndicatorSlug(cell_qual)
            if qual_slug and qual_slug not in ind_parts:
              ind_parts.insert(0, qual_slug)
          ind_slug = "_".join(ind_parts) if ind_parts else default_ind

        # Case 3: Columns have years and sub-table/column belongs to a known place (e.g. A2 Age/Sex groups for MOROCCO or multi-country A2)
        elif c_info["years"] and effective_place:
          place_key = effective_place
          yr_slug = self.slugifyYear(c_info["years"][0])
          row_ind = self.formatRowBandSlug(grouped_rows) if row_span > 1 else self.toSnakeSlug(raw_rlbl)
          col_inds = [self.toSnakeSlug(s) for s in c_info["semantic"] if self.toSnakeSlug(s) and self.toSnakeSlug(s) != place_key]
          if col_inds and row_ind:
            ind_slug = "_".join(col_inds + [row_ind])
          elif row_ind:
            ind_slug = row_ind
          elif col_inds:
            ind_slug = "_".join(col_inds)
          else:
            ind_slug = default_ind

        # Case 3b: Multi-country A2 table where each column's top header_path holds the country and rows are age bands
        elif c_info["years"] and self.isAgeOrBandLabel(raw_rlbl) and c_info["semantic"]:
          place_key = self.slugifyPlace(c_info["semantic"][0])
          yr_slug = self.slugifyYear(c_info["years"][0])
          row_ind = self.formatRowBandSlug(grouped_rows) if row_span > 1 else self.toSnakeSlug(raw_rlbl)
          col_inds = [self.toSnakeSlug(s) for s in c_info["semantic"][1:] if self.toSnakeSlug(s)]
          ind_slug = "_".join(col_inds + ([row_ind] if row_ind else [])) if (col_inds or row_ind) else default_ind

        # Case 4: Columns have years and rows are places/cities (e.g. A4 Population of Major Cities)
        elif c_info["years"] and raw_rlbl and not self.isAgeOrBandLabel(raw_rlbl):
          place_key = self.slugifyPlace(raw_rlbl)
          yr_slug = self.slugifyYear(c_info["years"][0])
          col_inds = [self.toSnakeSlug(s) for s in c_info["semantic"] if self.toSnakeSlug(s)]
          ind_slug = "_".join(col_inds) if col_inds else default_ind

        if not place_key or place_key in self.reserved_keys_set or place_key in self.pure_indicators_set or not yr_slug or not ind_slug:
          continue

        if place_key not in places_obj:
          places_obj[place_key] = {}

        series_key = f"{ind_slug}_{yr_slug}"
        if is_cont_row and series_key in places_obj[place_key]:
          series_key = f"{ind_slug}_revised_{yr_slug}"
        places_obj[place_key][series_key] = num_val

    #Return statement
    if subtable_place:
      return subtable_place
    elif active_place:
      return active_place
    else:
      return last_multi_place


  def D_buildSectionDocument (self, arg1_section_id, arg2_raw_title, arg3_raw_unit, arg4_chapter_title, arg5_tables_array):
    """
    @brief Step D: Build the complete per-section JSON dictionary {<table_key>: {name, subtitle, <place_key>: {...}}}.
    @param arg1_section_id Canonical section key (e.g. 'A1', 'A2', 'C1').
    @param arg2_raw_title Raw section banner title.
    @param arg3_raw_unit Optional raw unit string.
    @param arg4_chapter_title Chapter title string.
    @param arg5_tables_array List of reconstructed sub-table dictionaries across all pages of the section.
    @return Tuple (section_document_dict, stats_summary_dict).
    """
    #Convert from parameters
    sec_id = str(arg1_section_id).strip()
    raw_title = arg2_raw_title
    raw_unit = arg3_raw_unit
    chap_title = arg4_chapter_title
    tables_array = arg5_tables_array if isinstance(arg5_tables_array, list) else []

    #Declare local instance variables
    clean_name, clean_sub = self.A_parseSectionTitleAndSubtitle(raw_title, raw_unit)
    default_ind = self.B_deriveDefaultIndicator(clean_name, chap_title)
    inner_obj = {
      "name": clean_name,
      "subtitle": clean_sub
    }
    last_place = None
    places_obj = {}
    total_points = 0

    for i in range(len(tables_array)):
      last_place = self.C_flattenTableIntoPlaces(tables_array[i], default_ind, places_obj, last_place)

    for place_k in sorted(places_obj.keys()):
      series_map = places_obj[place_k]
      if series_map:
        inner_obj[place_k] = series_map
        total_points = total_points + len(series_map)

    doc_obj = {sec_id: inner_obj}
    stats_obj = {
      "data_points": total_points,
      "name": clean_name,
      "place_count": len(inner_obj) - 2,
      "subtitle": clean_sub
    }

    #Return statement
    return (doc_obj, stats_obj)


  def analyseColumnHeader (self, arg1_header_path_array):
    """
    @brief Partition a column's header_path segments into years, semantic place/indicator labels, and ignored unit/index lines.
    @param arg1_header_path_array List of strings from col['header_path'].
    @return Dictionary with 'years' and 'semantic' string lists.
    """
    #Convert from parameters
    path_array = arg1_header_path_array if isinstance(arg1_header_path_array, list) else []

    #Declare local instance variables
    semantic_array = []
    years_array = []

    for i in range(len(path_array)):
      seg = self.cleanProseSpacing(str(path_array[i]))
      if not seg or re.match(r"^(?:col_\d+|row_label|Date|circa)$", seg, re.IGNORECASE):
        continue
      if self.isYearOrRange(seg):
        years_array.append(seg)
      elif self.isUnitOrIndexPhrase(seg):
        continue
      else:
        semantic_array.append(seg)

    #Return statement
    return {
      "semantic": semantic_array,
      "years": years_array
    }


  def cleanProseSpacing (self, arg1_text_str):
    """
    @brief Normalise whitespace and heal common OCR kerning artefacts such as '(inthousands)' -> '(in thousands)'.
    @param arg1_text_str Input string.
    @return Cleaned string.
    """
    #Convert from parameters
    txt = str(arg1_text_str or "")

    txt = re.sub(r"\s+", " ", txt).strip()
    txt = re.sub(r"\bin(thousands|millions|billions|hundreds|metric|tons|tonnes|units)\b", r"in \1", txt, flags=re.IGNORECASE)
    txt = re.sub(r"\s+([,.;:)\]])", r"\1", txt)
    txt = re.sub(r"([(\[])\s+", r"\1", txt)

    #Return statement
    return txt.strip()


  def extractPlaceOverrideFromQualifier (self, arg1_qualifier_str, arg2_col_place_str):
    """
    @brief Detect mid-table sovereign/entity renames over a country column (e.g. 'West Germany' beneath 'Germany').
    @param arg1_qualifier_str Active cell/row qualifier text.
    @param arg2_col_place_str Base column place name.
    @return Overridden snake_case place_key or None.
    """
    #Convert from parameters
    qual = str(arg1_qualifier_str or "").strip()
    col_place = str(arg2_col_place_str or "").strip()

    if not qual or not col_place:
      return None
    if self.isUnitOrIndexPhrase(qual) or self.isYearOrRange(qual):
      return None

    q_low = qual.lower()
    p_low = col_place.lower()
    if p_low in q_low and q_low != p_low and len(qual) <= 40:
      return self.slugifyPlace(qual)

    #Return statement
    return None


  def extractQualifierIndicatorSlug (self, arg1_qualifier_str):
    """
    @brief Convert a sub-entity/scope qualifier (e.g. 'French Zone') into an indicator prefix, ignoring base-year or 'Whole Country' tags.
    @param arg1_qualifier_str Qualifier string.
    @return Clean snake_case qualifier prefix or empty string.
    """
    #Convert from parameters
    qual = str(arg1_qualifier_str or "").strip()

    if not qual:
      return ""
    if self.isUnitOrIndexPhrase(qual) or self.isYearOrRange(qual):
      return ""
    if qual.lower() in self.whole_qualifiers_set:
      return ""

    #Return statement
    return self.toSnakeSlug(qual)


  def extractSubtablePlaceKey (self, arg1_subtable_title):
    """
    @brief Extract a valid snake_case place key from a sub-table heading, stripping '(continued)' and rejecting banners/units.
    @param arg1_subtable_title Raw subtable_title string or None.
    @return Valid snake_case place key or None.
    """
    #Convert from parameters
    raw_t = str(arg1_subtable_title or "").strip()

    if not raw_t:
      return None

    reject_re = r"^(?:NOTES|FOOTNOTES|Key\b|circa|Date|See\s+pp?\.|The\s+population\b|Included\s+from\b)"
    work = re.sub(r"\s*\((?:continued|cont['’]?d?\.?)\)\s*", " ", raw_t, flags=re.IGNORECASE).strip()
    if " - " in work:
      parts = [p.strip() for p in work.split(" - ") if p.strip()]
      valid_parts = [
        p for p in parts
        if not self.isUnitOrIndexPhrase(p)
        and not self.isYearOrRange(p)
        and "=" not in p
        and len(p.split()) <= 6
        and not re.match(reject_re, p, re.IGNORECASE)
      ]
      work = valid_parts[0] if valid_parts else ""

    if not work or self.isYearOrRange(work) or self.isUnitOrIndexPhrase(work):
      return None
    if "=" in work or len(work.split()) > 6:
      return None
    if re.match(reject_re, work, re.IGNORECASE):
      return None

    slug = self.slugifyPlace(work)
    if not slug or slug in self.pure_indicators_set or slug in self.reserved_keys_set:
      return None

    #Return statement
    return slug


  def formatRowBandSlug (self, arg1_grouped_rows_array):
    """
    @brief Format a curly-brace spanned group of row labels (e.g. ['10-14', '15-19'] -> '10_19', ['60-64', ..., '80 and over'] -> '60_and_over').
    @param arg1_grouped_rows_array List of spanned row label strings.
    @return Clean snake_case band slug.
    """
    #Convert from parameters
    rows_list = [str(r).strip() for r in (arg1_grouped_rows_array or []) if str(r).strip()]

    if not rows_list:
      return ""

    # Deduplicate consecutive identical labels while preserving order
    dedup = []
    for i in range(len(rows_list)):
      if not dedup or dedup[-1] != rows_list[i]:
        dedup.append(rows_list[i])

    if len(dedup) == 1:
      return self.toSnakeSlug(dedup[0])

    first_m = re.match(r"^(\d{1,3})\s*[-–]\s*(\d{1,3})$", dedup[0])
    last_m = re.match(r"^(\d{1,3})\s*[-–]\s*(\d{1,3})$", dedup[-1])
    if first_m and last_m:
      return f"{first_m.group(1)}_{last_m.group(2)}"
    if first_m and re.search(r"\band\s+over\b", dedup[-1], re.IGNORECASE):
      return f"{first_m.group(1)}_and_over"

    #Return statement
    return self.toSnakeSlug("_".join(dedup))


  def formatYearSpanSlug (self, arg1_grouped_years_array):
    """
    @brief Format braced multi-year row labels (e.g. ['1834', '1835'] -> '1834_1835') into a compact year suffix.
    @param arg1_grouped_years_array List of year row labels.
    @return Clean year span slug.
    """
    #Convert from parameters
    yrs = [self.slugifyYear(y) for y in (arg1_grouped_years_array or []) if self.slugifyYear(y)]

    if not yrs:
      return ""
    if len(yrs) == 1 or yrs[0] == yrs[-1]:
      return yrs[0]

    #Return statement
    return f"{yrs[0]}_{yrs[-1]}"


  def isAgeOrBandLabel (self, arg1_label_str):
    """
    @brief Check whether a row stub label represents a demographic age band rather than a geographic place.
    @param arg1_label_str Row label string.
    @return Boolean True if label is an age group or 'Unknown' band.
    """
    #Convert from parameters
    lbl = str(arg1_label_str or "").strip()

    if re.match(r"^\d{1,2}\s*[-–]\s*\d{1,3}$", lbl):
      return True
    if re.match(r"^(?:\d{1,3}\s+and\s+over|under\s+\d+|unknown)$", lbl, re.IGNORECASE):
      return True

    #Return statement
    return False


  def isUnitOrIndexPhrase (self, arg1_text_str):
    """
    @brief Check whether a header/qualifier phrase is a unit description ('million pounds') or index base ('1913 = 100').
    @param arg1_text_str Candidate phrase string.
    @return Boolean True if unit/scale or base-year index phrase.
    """
    #Convert from parameters
    txt = str(arg1_text_str or "").strip()

    if not txt:
      return True
    if re.search(r"=\s*100\b", txt) or re.match(r"^100$", txt):
      return True

    words = re.sub(r"[()\[\].,:%0-9/\-–—=]", " ", txt.lower()).split()
    if not words:
      return True

    #Return statement
    return all(w in self.unit_vocab_set for w in words)


  def isYearOrRange (self, arg1_text_str):
    """
    @brief Check whether a string represents a historical year, slash census year ('1951/2'), or year range ('1867-77').
    @param arg1_text_str Candidate label string.
    @return Boolean True if string is a year expression.
    """
    #Convert from parameters
    txt = str(arg1_text_str or "").strip()

    txt = re.sub(r"^circa\s+", "", txt, flags=re.IGNORECASE).strip()

    #Return statement
    return bool(re.match(r"^(?:1[789]\d{2}|20[01]\d)(?:\s*[/\-–—]\s*\d{1,4})?$", txt))


  def normaliseHeadingCase (self, arg1_heading_str):
    """
    @brief Convert ALL-CAPS banner titles to readable Title Case while preserving already mixed-case headings and acronyms.
    @param arg1_heading_str Heading string.
    @return Cleanly cased heading string.
    """
    #Convert from parameters
    txt = str(arg1_heading_str or "").strip()

    if not txt or len(txt) <= 3:
      return txt

    lower_words = {"a", "an", "and", "as", "at", "by", "for", "from", "in", "into", "of", "on", "or", "per", "the", "to", "with"}
    acronyms = {"GDP", "GNP", "NMP", "U.K.", "U.S.A.", "U.S.S.R.", "UK", "USA", "USSR"}
    tokens = txt.split(" ")
    out_array = []

    for i in range(len(tokens)):
      w = tokens[i]
      clean_w = w.strip(":,;()")
      if not clean_w.isupper() or clean_w in acronyms:
        out_array.append(w)
      elif i > 0 and clean_w.lower() in lower_words:
        out_array.append(w.lower())
      elif len(clean_w) >= 2:
        out_array.append(w[:1].upper() + w[1:].lower())
      else:
        out_array.append(w)

    #Return statement
    return " ".join(out_array)


  def resolveMultiCountryColumnPlaces (self, arg1_cols_array, arg2_col_lookup_obj, arg3_above_phrases_array):
    """
    @brief Map data columns to country keys when multiple horizontally separated country headings sit above one shared table.
    @param arg1_cols_array Reconstructed columns list from TableStructureReconstructor.
    @param arg2_col_lookup_obj Mapping of col_index to analysed header years and semantic segments.
    @param arg3_above_phrases_array List of phrase dictionaries extracted above the table's top rule.
    @return Tuple (col_index_to_place_dict, rightmost_place_key_or_None).
    """
    #Convert from parameters
    cols_array = arg1_cols_array if isinstance(arg1_cols_array, list) else []
    col_lookup_obj = arg2_col_lookup_obj if isinstance(arg2_col_lookup_obj, dict) else {}
    above_phrases_array = arg3_above_phrases_array if isinstance(arg3_above_phrases_array, list) else []

    #Declare local instance variables
    col_places_map = {}
    data_cols = [c for c in cols_array if c.get("role") == "data"]
    dated_runs_array = []
    prev_yr = -1
    run_seen_set = set()
    sorted_phrases = sorted(above_phrases_array, key=lambda p: float(p.get("x1", 0.0)))
    valid_phrases = []

    for i in range(len(sorted_phrases)):
      phr = sorted_phrases[i]
      p_slug = self.extractSubtablePlaceKey(phr.get("text"))
      if p_slug:
        valid_phrases.append({
          "place": p_slug,
          "x1": float(phr.get("x1", 0.0)),
          "x_centre": float(phr.get("x_centre", 0.0))
        })

    if len(valid_phrases) < 2 or not data_cols:
      return ({}, None)

    for i in range(len(data_cols)):
      c_idx = data_cols[i]["col_index"]
      c_meta = col_lookup_obj.get(c_idx, {})
      yrs = c_meta.get("years", [])
      if not yrs:
        continue
      yr_m = re.search(r"(?:1[789]\d{2}|20[01]\d)", yrs[0])
      if not yr_m:
        continue
      cur_yr = int(yr_m.group(0))
      sem_sig = (cur_yr, tuple(self.toSnakeSlug(s) for s in c_meta.get("semantic", [])))
      if not dated_runs_array or cur_yr < prev_yr or sem_sig in run_seen_set:
        dated_runs_array.append([c_idx])
        run_seen_set = {sem_sig}
      else:
        dated_runs_array[-1].append(c_idx)
        run_seen_set.add(sem_sig)
      prev_yr = cur_yr

    if len(dated_runs_array) == len(valid_phrases):
      for i in range(len(dated_runs_array)):
        for x in range(len(dated_runs_array[i])):
          col_places_map[dated_runs_array[i][x]] = valid_phrases[i]["place"]
    elif valid_phrases[0]["x_centre"] > float(data_cols[0].get("x_centre", 0.0)) - 20.0:
      bounds = [-1e9] + [0.5*(valid_phrases[i]["x_centre"] + valid_phrases[i + 1]["x_centre"]) for i in range(len(valid_phrases) - 1)] + [1e9]
      for i in range(len(data_cols)):
        xc = float(data_cols[i].get("x_centre", 0.0))
        for x in range(len(valid_phrases)):
          if bounds[x] <= xc < bounds[x + 1]:
            col_places_map[data_cols[i]["col_index"]] = valid_phrases[x]["place"]
            break
    else:
      for i in range(len(data_cols)):
        xc = float(data_cols[i].get("x_centre", 0.0))
        assigned = valid_phrases[0]["place"]
        for x in range(1, len(valid_phrases)):
          if xc >= valid_phrases[x]["x1"] - 45.0:
            assigned = valid_phrases[x]["place"]
        col_places_map[data_cols[i]["col_index"]] = assigned

    #Return statement
    return (col_places_map, valid_phrases[-1]["place"])


  def slugifyPlace (self, arg1_place_str):
    """
    @brief Convert a country, province, or city name into canonical snake_case (e.g. 'U.K.' -> 'uk', 'Guinea Bissau' -> 'guinea_bissau').
    @param arg1_place_str Raw place label.
    @return Canonical snake_case place key.
    """
    #Convert from parameters
    txt = str(arg1_place_str or "").strip()

    if not txt:
      return ""

    # Collapse dotted initialisms ('U.K.' -> 'UK', 'U.S.A.' -> 'USA') prior to punctuation splitting
    txt = re.sub(r"\b(?:[A-Za-z]\.){2,}", lambda m: m.group(0).replace(".", ""), txt)
    # Strip trailing space-separated or OCR-garbled superscript footnote suffixes (e.g. 'India 2', 'India?2', 'China2o', 'Indiazz')
    txt = re.sub(r"\s+\d{1,2}(?:,\s*\d{1,2})*$", "", txt).strip()
    txt = re.sub(r"([A-Za-z.)])[?*'‘’`´]+\d{0,2}(?:,\d{1,2})*$", r"\1", txt).strip()
    txt = re.sub(r"([A-Za-z.)])['`‘’]?\d{1,2}[oOlIzZsS]?(?:,\d{1,2})*$", r"\1", txt).strip()
    txt = re.sub(r"([A-Za-z]{3,}?)[zZ]{2}$", r"\1", txt).strip()

    #Return statement
    return self.toSnakeSlug(txt)


  def slugifyYear (self, arg1_year_str):
    """
    @brief Normalise a year or slash/range year into clean snake_case (e.g. '1951/2' -> '1951_2').
    @param arg1_year_str Raw year label.
    @return Clean year string.
    """
    #Convert from parameters
    txt = str(arg1_year_str or "").strip()

    txt = re.sub(r"^circa\s+", "", txt, flags=re.IGNORECASE).strip()

    #Return statement
    return self.toSnakeSlug(txt)


  def toSnakeSlug (self, arg1_raw_str):
    """
    @brief Transliterate Latin diacritics to ASCII and convert any phrase into clean lowercase snake_case.
    @param arg1_raw_str Arbitrary label string.
    @return Clean snake_case identifier string.
    """
    #Convert from parameters
    raw_str = str(arg1_raw_str or "").strip()

    if not raw_str:
      return ""

    work = raw_str.replace("ß", "ss").replace("Æ", "AE").replace("æ", "ae").replace("Œ", "OE").replace("œ", "oe")
    work = work.replace("&", " and ")
    norm = unicodedata.normalize("NFKD", work)
    ascii_str = "".join(ch for ch in norm if not unicodedata.combining(ch))
    slug = re.sub(r"[^A-Za-z0-9]+", "_", ascii_str.lower())
    slug = re.sub(r"_+", "_", slug).strip("_")

    #Return statement
    return slug
