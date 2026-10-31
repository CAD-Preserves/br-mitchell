"""@brief Flattens reconstructed sub-tables into canonical per-section {name, subtitle, <place_key>: {<indicator>_<year>: number}} JSON."""

import re
from core.PlaceKeyNormaliser import PlaceKeyNormaliser


class TableSeriesFlattener:
  """@brief Maps multi-layout historical tables into clean snake_case place and indicator_year numeric dictionaries."""

  def __init__ (self, arg1_config_obj):
    """
    @brief Initialise TableSeriesFlattener with vocabulary rules and companion PlaceKeyNormaliser.
    @param arg1_config_obj Pipeline configuration dictionary.
    """
    #Convert from parameters
    config_obj = arg1_config_obj if isinstance(arg1_config_obj, dict) else {}

    #Declare local instance variables
    flat_cfg = config_obj.get("series_flattening", {})
    self.default_fallback_ind = str(flat_cfg.get("default_fallback_indicator", "value"))
    self.max_ind_words = int(flat_cfg.get("max_derived_indicator_words", 4))
    self.normaliser = PlaceKeyNormaliser(config_obj)
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

    work = re.sub(
      r"^(?:(?:AFRICA|ASIA|OCEANIA|NORTH\s+AMERICA|CENTRAL\s+AMERICA|SOUTH\s+AMERICA|THE\s+AMERICAS|AMERICAS|EUROPE)(?:[\s,]*(?:AND|&)?\s*)?)+\s*:\s*",
      "",
      work,
      flags=re.IGNORECASE
    ).strip()
    work = re.sub(r"\s*\(continued\)\s*$", "", work, flags=re.IGNORECASE).strip()
    work = re.sub(r"\)\s*[1-9]\s*$", ")", work).strip()

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
    @brief Step B: Derive a concise snake_case indicator slug for single-series tables (e.g. 'population', 'aluminium').
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


  def C_flattenTableIntoPlaces (self, arg1_table_obj, arg2_default_indicator, arg3_places_obj, arg4_last_place=None, arg5_options=None):
    """
    @brief Step C: Populate places_obj with {<place_key>: {<indicator>_<year>: number}} entries from one reconstructed table.
    @param arg1_table_obj Reconstructed sub-table dictionary.
    @param arg2_default_indicator Derived default indicator slug for single-series columns/rows.
    @param arg3_places_obj Mutable dictionary accumulating per-place series across the section.
    @param arg4_last_place Optional place_key from the preceding sub-table for untitled continuations.
    @param arg5_options Optional context dictionary (is_city_section).
    @return Updated active sub-table place_key (or None for city-list tables).
    """
    #Convert from parameters
    tbl = arg1_table_obj if isinstance(arg1_table_obj, dict) else {}
    default_ind = str(arg2_default_indicator or self.default_fallback_ind)
    places_obj = arg3_places_obj if isinstance(arg3_places_obj, dict) else {}
    last_place = arg4_last_place
    options = arg5_options if isinstance(arg5_options, dict) else {}

    #Declare local instance variables
    col_label_map = {}
    col_lookup_obj = {}
    cols_array = tbl.get("columns", [])
    heading_info = self.normaliser.C_classifySubtableHeading(tbl.get("subtable_title"))
    is_city_section = bool(options.get("is_city_section", False))
    last_inbody_place = None
    rows_array = tbl.get("rows", [])
    subtable_ind_prefix = heading_info["indicator_prefix"]
    subtable_place = heading_info["place_key"]

    if not rows_array or len(cols_array) <= 1:
      return subtable_place or last_place

    for i in range(len(cols_array)):
      c = cols_array[i]
      if c.get("role") == "data":
        col_lookup_obj[c["col_index"]] = self.analyseColumnHeader(c.get("header_path", []))
        col_label_map[c["label"]] = col_lookup_obj[c["col_index"]]

    if not col_lookup_obj:
      return subtable_place or last_place

    multi_col_places_map, single_above_place, last_multi_place = self.resolveMultiCountryColumnPlaces(
      cols_array,
      col_lookup_obj,
      tbl.get("above_phrases", [])
    )
    if subtable_place is None and single_above_place:
      subtable_place = single_above_place

    date_cols_map = self.detectInternalDateColumns(cols_array, col_lookup_obj, rows_array)

    has_year_cols = any(bool(info["years"]) for info in col_lookup_obj.values())
    all_cols_indicators = all(
      (not info["semantic"]) or all(self.normaliser.isIndicatorPhrase(s) for s in info["semantic"])
      for info in col_lookup_obj.values()
    )
    sample_rows_age = sum(1 for r in rows_array if self.isAgeOrBandLabel(r.get("row_label", "")))
    is_age_table = (sample_rows_age >= max(1, len(rows_array)//4))

    # Carry last_place onto untitled continuation blocks (both year-row sector/crop tables and A2/A3 year-column continuations)
    active_place = subtable_place
    if active_place is None and not multi_col_places_map and last_place is not None and subtable_ind_prefix is None:
      if not has_year_cols and all_cols_indicators:
        active_place = last_place
      elif has_year_cols and all_cols_indicators and (is_age_table or not is_city_section):
        active_place = last_place

    for i in range(len(rows_array)):
      r = rows_array[i]
      raw_rlbl = str(r.get("row_label", "")).strip()
      row_subscope = str(r.get("subscope") or "").strip()
      raw_row_place = str(r.get("row_place_banner") or "").strip()
      row_qual = str(r.get("qualifier") or "").strip()
      is_cont_row = bool(r.get("series_continuation", False))
      row_is_yr = self.isYearOrRange(raw_rlbl)
      cells_array = r.get("cells", [])
      row_date_overrides = {}

      row_banner_place = None
      if raw_row_place:
        cand_rp = self.normaliser.A_normalisePlaceKey(raw_row_place)
        if cand_rp and not self.normaliser.isMacroRegion(cand_rp) and (not has_year_cols or is_age_table or not is_city_section):
          row_banner_place = cand_rp
          last_inbody_place = cand_rp

      if date_cols_map:
        for x in range(len(cells_array)):
          dc_cell = cells_array[x]
          dc_idx = dc_cell.get("col_index")
          if dc_idx in date_cols_map:
            dc_txt = str(dc_cell.get("raw_text", "")).strip()
            if self.isYearOrRange(dc_txt):
              row_date_overrides[date_cols_map[dc_idx]] = self.slugifyYear(dc_txt)

      for x in range(len(cells_array)):
        cell = cells_array[x]
        if cell.get("col_index") in date_cols_map:
          continue
        if cell.get("value_status") != "numeric":
          continue
        num_val = cell.get("numeric_value")
        if not isinstance(num_val, (int, float)) or isinstance(num_val, bool):
          continue

        c_info = col_lookup_obj.get(cell.get("col_index"))
        if c_info is None:
          continue

        grouped_rows = cell.get("grouped_rows") or ([raw_rlbl] if raw_rlbl else [])
        grouped_cols = cell.get("grouped_columns") or []
        row_span = int(cell.get("row_span", 1))
        cell_only_qual = str(cell.get("qualifier") or "").strip()
        if len(self.toSnakeSlug(cell_only_qual)) <= 2:
          cell_only_qual = ""
        eff_subscope = cell_only_qual if cell_only_qual else row_subscope
        mapped_place = multi_col_places_map.get(cell.get("col_index"))

        if mapped_place:
          effective_place = mapped_place
        elif row_banner_place and all_cols_indicators:
          effective_place = row_banner_place
        else:
          effective_place = active_place

        place_key = None
        ind_slug = ""
        yr_slug = ""

        # Case 1: Rows are years and sub-table, row banner or column group belongs to a known place
        if (row_is_yr or (row_span > 1 and grouped_rows and all(self.isYearOrRange(gr) for gr in grouped_rows)) or ("*" in row_date_overrides)) and effective_place:
          place_key = effective_place
          yr_slug = row_date_overrides.get(place_key) or row_date_overrides.get("*") or (self.formatYearSpanSlug(grouped_rows) if row_span > 1 else self.slugifyYear(raw_rlbl))
          ind_parts = []
          if subtable_ind_prefix and subtable_ind_prefix != default_ind:
            ind_parts.append(subtable_ind_prefix)
          qual_slug = self.extractQualifierIndicatorSlug(eff_subscope)
          if qual_slug and qual_slug not in ind_parts:
            ind_parts.append(qual_slug)

          if len(grouped_cols) >= 2:
            for y in range(len(grouped_cols)):
              gc_info = col_label_map.get(grouped_cols[y]) or self.analyseColumnHeader([grouped_cols[y]])
              for z in range(len(gc_info["semantic"])):
                s_slug = self.toSnakeSlug(gc_info["semantic"][z])
                if s_slug and s_slug != place_key and s_slug not in ind_parts:
                  ind_parts.append(s_slug)
          else:
            for y in range(len(c_info["semantic"])):
              s_slug = self.toSnakeSlug(c_info["semantic"][y])
              if s_slug and s_slug != place_key and s_slug not in ind_parts:
                ind_parts.append(s_slug)
          ind_slug = "_".join(ind_parts) if ind_parts else default_ind

        # Case 2: Rows are years and columns specify places (+ optional indicators like Primary/Secondary or I/E)
        elif row_is_yr or (row_span > 1 and grouped_rows and all(self.isYearOrRange(gr) for gr in grouped_rows)) or bool(row_date_overrides):
          if all_cols_indicators or not c_info["semantic"]:
            continue
          sem_list = list(c_info["semantic"])

          raw_col_place = sem_list[0]
          override_place = self.extractPlaceOverrideFromQualifier(raw_row_place or cell_only_qual or row_qual, raw_col_place)
          place_key = override_place if override_place else self.normaliser.A_normalisePlaceKey(raw_col_place)
          yr_slug = row_date_overrides.get(place_key) or row_date_overrides.get("*") or (self.formatYearSpanSlug(grouped_rows) if row_span > 1 else self.slugifyYear(raw_rlbl))

          ind_parts = []
          if subtable_ind_prefix and subtable_ind_prefix != default_ind:
            ind_parts.append(subtable_ind_prefix)
          if not override_place:
            qual_slug = self.extractQualifierIndicatorSlug(eff_subscope)
            if qual_slug and qual_slug not in ind_parts:
              ind_parts.append(qual_slug)
          for y in range(1, len(sem_list)):
            s_slug = self.toSnakeSlug(sem_list[y])
            if s_slug and s_slug not in ind_parts:
              ind_parts.append(s_slug)
          ind_slug = "_".join(ind_parts) if ind_parts else default_ind

        # Case 3: Columns have years and sub-table/column belongs to a known place (e.g. A2 Age/Sex or A3 Administrative Divisions)
        elif c_info["years"] and effective_place:
          place_key = effective_place
          yr_slug = self.slugifyYear(c_info["years"][0])
          if row_span > 1:
            row_ind = self.formatRowBandSlug(grouped_rows)
          elif self.isAgeOrBandLabel(raw_rlbl):
            row_ind = self.formatSingleAgeSlug(raw_rlbl)
          else:
            norm_div = self.normaliser.A_normalisePlaceKey(raw_rlbl)
            row_ind = norm_div if norm_div else self.toSnakeSlug(raw_rlbl)

          col_inds = []
          qual_slug = self.extractQualifierIndicatorSlug(eff_subscope)
          if qual_slug:
            col_inds.append(qual_slug)
          for y in range(len(c_info["semantic"])):
            s_slug = self.toSnakeSlug(c_info["semantic"][y])
            if s_slug and s_slug != place_key and s_slug not in col_inds:
              col_inds.append(s_slug)

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
          sem_list = list(c_info["semantic"])
          place_key = self.normaliser.A_normalisePlaceKey(sem_list[0])
          yr_slug = self.slugifyYear(c_info["years"][0])
          row_ind = self.formatRowBandSlug(grouped_rows) if row_span > 1 else self.formatSingleAgeSlug(raw_rlbl)
          col_inds = [self.toSnakeSlug(s) for s in sem_list[1:] if self.toSnakeSlug(s)]
          qual_slug = self.extractQualifierIndicatorSlug(eff_subscope)
          if qual_slug and qual_slug not in col_inds:
            col_inds.insert(0, qual_slug)
          ind_slug = "_".join(col_inds + ([row_ind] if row_ind else [])) if (col_inds or row_ind) else default_ind

        # Case 4: Columns have years and rows are places/cities (e.g. A4 Population of Major Cities)
        elif c_info["years"] and raw_rlbl and not self.isAgeOrBandLabel(raw_rlbl):
          place_key = self.normaliser.A_normalisePlaceKey(raw_rlbl)
          yr_slug = self.slugifyYear(c_info["years"][0])
          col_inds = [self.toSnakeSlug(s) for s in c_info["semantic"] if self.toSnakeSlug(s)]
          qual_slug = self.extractQualifierIndicatorSlug(eff_subscope)
          if qual_slug and qual_slug not in col_inds:
            col_inds.insert(0, qual_slug)
          ind_slug = "_".join(col_inds) if col_inds else default_ind

        if not self.normaliser.B_isValidPlaceKey(place_key) or not yr_slug or not ind_slug:
          continue

        if place_key not in places_obj:
          places_obj[place_key] = {}

        series_key = f"{ind_slug}_{yr_slug}"
        if is_cont_row and series_key in places_obj[place_key]:
          series_key = f"{ind_slug}_revised_{yr_slug}"
        places_obj[place_key][series_key] = num_val

    #Return statement
    if last_inbody_place and not is_city_section:
      return last_inbody_place
    elif subtable_place:
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
    is_city_section = (sec_id == "A4" or "cities" in clean_name.lower())
    last_place = None
    places_obj = {}
    schema_state_obj = {
      "by_count": {},
      "last_cols": None,
      "last_orientation": None
    }
    total_points = 0

    for i in range(len(tables_array)):
      self.applyOrCacheColumnSchema(tables_array[i], schema_state_obj)
      last_place = self.C_flattenTableIntoPlaces(
        tables_array[i],
        default_ind,
        places_obj,
        last_place,
        {"is_city_section": is_city_section}
      )

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
    @brief Partition a column's header_path segments into years, semantic place/indicator labels and ignored unit/index lines.
    @param arg1_header_path_array List of strings from col['header_path'].
    @return Dictionary with 'has_date_hdr', 'years' and 'semantic' string lists.
    """
    #Convert from parameters
    path_array = arg1_header_path_array if isinstance(arg1_header_path_array, list) else []

    #Declare local instance variables
    has_date_hdr = False
    semantic_array = []
    years_array = []

    for i in range(len(path_array)):
      seg = self.cleanProseSpacing(str(path_array[i]))
      if not seg or re.match(r"^(?:col_\d+|row_label|circa)$", seg, re.IGNORECASE):
        continue
      if re.match(r"^(?:Date|Year)s?$", seg, re.IGNORECASE):
        has_date_hdr = True
        continue
      if self.isYearOrRange(seg):
        years_array.append(seg)
      elif self.isUnitOrIndexPhrase(seg) or self.normaliser.isMacroRegion(seg):
        continue
      else:
        semantic_array.append(seg)

    #Return statement
    return {
      "has_date_hdr": has_date_hdr,
      "semantic": semantic_array,
      "years": years_array
    }


  def applyOrCacheColumnSchema (self, arg1_table_obj, arg2_schema_state_obj):
    """
    @brief Cache explicit pure-indicator column headers and apply them onto subsequent headerless col_1..col_C blocks.
    @param arg1_table_obj Reconstructed sub-table dictionary (mutated in place when headerless).
    @param arg2_schema_state_obj Mutable dictionary storing by_count and last_cols schemas across the section.
    @return Updated sub-table dictionary.
    """
    #Convert from parameters
    tbl = arg1_table_obj if isinstance(arg1_table_obj, dict) else {}
    state = arg2_schema_state_obj

    #Declare local instance variables
    cols_array = tbl.get("columns", [])
    data_cols = [c for c in cols_array if c.get("role") == "data"]
    num_c = len(data_cols)

    if num_c == 0:
      return tbl

    dummy_cnt = sum(1 for c in data_cols if re.match(r"^col_\d+$", str(c.get("label", ""))))
    if dummy_cnt >= max(1, num_c - 1):
      if num_c in state["by_count"]:
        ref_cols = state["by_count"][num_c]
        for i in range(num_c):
          if re.match(r"^col_\d+$", str(data_cols[i].get("label", ""))):
            data_cols[i]["header_path"] = list(ref_cols[i]["header_path"])
            data_cols[i]["label"] = ref_cols[i]["label"]
      elif state["last_cols"] and tbl.get("orientation") == state["last_orientation"]:
        ref_cols = state["last_cols"]
        cand_pairs = []
        direct_map = {}
        span_map = {}
        used_r_set = set()
        for i in range(num_c):
          xc = float(data_cols[i].get("x_centre", 0.0))
          for x in range(len(ref_cols)):
            d = abs(xc - float(ref_cols[x].get("x_centre", 0.0)))
            if d <= 68.0:
              cand_pairs.append((d, i, x))
        cand_pairs.sort(key=lambda item: item[0])
        for i in range(len(cand_pairs)):
          _, c_i, r_x = cand_pairs[i]
          if c_i in direct_map or r_x in used_r_set:
            continue
          if any((k < c_i and v >= r_x) or (k > c_i and v <= r_x) for k, v in direct_map.items()):
            continue
          direct_map[c_i] = r_x
          used_r_set.add(r_x)
        for i in range(num_c):
          if i in direct_map:
            continue
          xc = float(data_cols[i].get("x_centre", 0.0))
          for x in range(len(ref_cols) - 1):
            xl = float(ref_cols[x].get("x_centre", 0.0))
            xr = float(ref_cols[x + 1].get("x_centre", 0.0))
            if xl + 15.0 < xc < xr - 15.0:
              comb_path = list(ref_cols[x]["header_path"]) + [
                s for s in ref_cols[x + 1]["header_path"] if s not in ref_cols[x]["header_path"]
              ]
              span_map[i] = (comb_path, f"{ref_cols[x]['label']} | {ref_cols[x + 1]['label']}")
              break
        if len(direct_map) + len(span_map) >= max(2, num_c - 1):
          for i in range(num_c):
            if not re.match(r"^col_\d+$", str(data_cols[i].get("label", ""))):
              continue
            if i in direct_map:
              r_col = ref_cols[direct_map[i]]
              data_cols[i]["header_path"] = list(r_col["header_path"])
              data_cols[i]["label"] = r_col["label"]
            elif i in span_map:
              data_cols[i]["header_path"] = span_map[i][0]
              data_cols[i]["label"] = span_map[i][1]
    elif dummy_cnt == 0 and num_c >= 2:
      analysed = [self.analyseColumnHeader(c.get("header_path", [])) for c in data_cols]
      has_yrs = any(bool(a["years"]) for a in analysed)
      ind_cnt = sum(
        1 for a in analysed
        if bool(a["semantic"]) and all(self.normaliser.isIndicatorPhrase(s) for s in a["semantic"])
      )
      if not has_yrs and ind_cnt >= max(2, num_c - 1):
        snap = [
          {
            "header_path": list(c.get("header_path", [])),
            "label": c.get("label", ""),
            "x_centre": float(c.get("x_centre", 0.0))
          }
          for c in data_cols
        ]
        state["by_count"][num_c] = snap
        state["last_cols"] = snap
        state["last_orientation"] = tbl.get("orientation")

    #Return statement
    return tbl


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


  def detectInternalDateColumns (self, arg1_cols_array, arg2_col_lookup_obj, arg3_rows_array):
    """
    @brief Detect mid-table Date/Year stub columns in side-by-side multi-country tables (e.g. Sikkim | Portuguese Settlements).
    @param arg1_cols_array Reconstructed columns list.
    @param arg2_col_lookup_obj Analysed column header lookup dictionary.
    @param arg3_rows_array Reconstructed rows list.
    @return Dictionary mapping date col_index to its target place_key (or '*').
    """
    #Convert from parameters
    cols_array = arg1_cols_array if isinstance(arg1_cols_array, list) else []
    col_lookup_obj = arg2_col_lookup_obj if isinstance(arg2_col_lookup_obj, dict) else {}
    rows_array = arg3_rows_array if isinstance(arg3_rows_array, list) else []

    #Declare local instance variables
    data_cols = [c for c in cols_array if c.get("role") == "data"]
    date_cols_map = {}

    for i in range(len(data_cols)):
      c_idx = data_cols[i]["col_index"]
      c_info = col_lookup_obj.get(c_idx, {})
      if c_info.get("years"):
        continue
      sem = c_info.get("semantic", [])
      target_place = self.normaliser.A_normalisePlaceKey(sem[0]) if sem else "*"
      if sem and not target_place:
        continue

      if c_info.get("has_date_hdr"):
        date_cols_map[c_idx] = target_place if target_place else "*"
        continue

      has_sibling = False
      if len(sem) == 1 and i + 1 < len(data_cols):
        nxt_sem = col_lookup_obj.get(data_cols[i + 1]["col_index"], {}).get("semantic", [])
        if nxt_sem and self.normaliser.A_normalisePlaceKey(nxt_sem[0]) == target_place:
          has_sibling = True
      if not has_sibling:
        continue

      yr_vals = []
      all_valid_years = True
      for x in range(len(rows_array)):
        for y in range(len(rows_array[x].get("cells", []))):
          cell = rows_array[x]["cells"][y]
          if cell.get("col_index") != c_idx:
            continue
          raw_t = str(cell.get("raw_text", "")).strip()
          if not raw_t or cell.get("value_status") in ("missing", "nil", "less_than_half_unit", "spanned_by_brace", "not_available", "empty"):
            continue
          if not self.isYearOrRange(raw_t):
            all_valid_years = False
            break
          yr_m = re.match(r"^(\d{4})", re.sub(r"^circa\s+", "", raw_t, flags=re.IGNORECASE).strip())
          if yr_m:
            yr_vals.append(int(yr_m.group(1)))
        if not all_valid_years:
          break

      if all_valid_years and len(yr_vals) >= 3 and all(yr_vals[z] > yr_vals[z - 1] for z in range(1, len(yr_vals))):
        date_cols_map[c_idx] = target_place

    #Return statement
    return date_cols_map


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
      norm_ov = self.normaliser.A_normalisePlaceKey(qual)
      if norm_ov:
        return norm_ov

    #Return statement
    return None


  def extractQualifierIndicatorSlug (self, arg1_qualifier_str):
    """
    @brief Convert a sub-scope qualifier ('Males', '1957 prices', 'French Zone') into an indicator prefix.
    @param arg1_qualifier_str Qualifier string.
    @return Clean snake_case qualifier prefix or empty string.
    """
    #Convert from parameters
    qual = str(arg1_qualifier_str or "").strip()

    if not qual:
      return ""
    if self.isYearOrRange(qual):
      return ""
    if qual.lower() in self.whole_qualifiers_set:
      return ""

    # Preserve explicit price-mode / base-year price qualifiers ('1957 prices', 'current prices', 'constant prices')
    clean_q = re.sub(r"pricess\b", "prices", qual, flags=re.IGNORECASE)
    if re.search(r"\bprices?\b", clean_q, re.IGNORECASE) and not clean_q.lower().startswith("in "):
      return self.toSnakeSlug(clean_q)

    if self.isUnitOrIndexPhrase(clean_q):
      return ""

    #Return statement
    return self.toSnakeSlug(clean_q)


  def formatRowBandSlug (self, arg1_grouped_rows_array):
    """
    @brief Format a curly-brace spanned group of row labels (e.g. ['10-14', '15-19'] -> '10_19') into a compact band slug.
    @param arg1_grouped_rows_array List of spanned row label strings.
    @return Clean snake_case band slug.
    """
    #Convert from parameters
    rows_list = [str(r).strip() for r in (arg1_grouped_rows_array or []) if str(r).strip()]

    if not rows_list:
      return ""

    dedup = []
    for i in range(len(rows_list)):
      if not dedup or dedup[-1] != rows_list[i]:
        dedup.append(rows_list[i])

    if len(dedup) == 1:
      return self.formatSingleAgeSlug(dedup[0]) if self.isAgeOrBandLabel(dedup[0]) else self.toSnakeSlug(dedup[0])

    first_norm = self.formatSingleAgeSlug(dedup[0])
    last_norm = self.formatSingleAgeSlug(dedup[-1])
    first_m = re.match(r"^(\d{1,3})_(\d{1,3})$", first_norm)
    last_m = re.match(r"^(\d{1,3})_(\d{1,3})$", last_norm)
    if first_m and last_m:
      return f"{first_m.group(1)}_{last_m.group(2)}"
    if first_m and re.search(r"\band\s+over\b", dedup[-1], re.IGNORECASE):
      return f"{first_m.group(1)}_and_over"

    #Return statement
    return self.toSnakeSlug("_".join(dedup))


  def formatSingleAgeSlug (self, arg1_age_label):
    """
    @brief Normalise single-year infant ('0'), space-separated ('0 4') and merged ('6064') age labels into canonical slugs.
    @param arg1_age_label Raw row age band label.
    @return Canonical age slug (e.g. '0', '0_4', '60_64').
    """
    #Convert from parameters
    lbl = str(arg1_age_label or "").strip()

    if re.match(r"^\d{4}$", lbl):
      aa = int(lbl[:2])
      bb = int(lbl[2:])
      if 10 <= aa < bb <= 99 and (bb - aa) in [4, 9]:
        return f"{aa}_{bb}"

    #Return statement
    return self.toSnakeSlug(lbl)


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
    @brief Check whether a row stub label represents a demographic age band (including infant '0', '0 4' and '6064').
    @param arg1_label_str Row label string.
    @return Boolean True if label is an age group or 'Unknown' band.
    """
    #Convert from parameters
    lbl = str(arg1_label_str or "").strip()

    if not lbl:
      return False
    if re.match(r"^[0-4]$", lbl):
      return True
    if re.match(r"^\d{1,2}\s*[-–]\s*\d{1,3}$", lbl):
      return True
    sp_m = re.match(r"^(\d{1,2})\s+(\d{1,3})$", lbl)
    if sp_m:
      a_val = int(sp_m.group(1))
      b_val = int(sp_m.group(2))
      if 0 <= a_val < b_val <= 105 and (b_val - a_val) in [1, 3, 4, 5, 9, 10, 14, 19]:
        return True
    if re.match(r"^\d{1,2}[\s\-–]+\d{1,2}[\s\-–]+\d{1,2}$", lbl):
      return True
    if re.match(r"^\d{4}$", lbl):
      aa = int(lbl[:2])
      bb = int(lbl[2:])
      if 10 <= aa < bb <= 99 and (bb - aa) in [4, 9] and aa not in [18, 19]:
        return True
    if re.match(r"^(?:\d{1,3}\s+and\s+over|\d{2,3}\+|under\s+\d+|<\s*\d+|unknown|not\s+stated|all\s+ages)$", lbl, re.IGNORECASE):
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
    if re.match(r"^in\s+(?:thousands?|millions?|billions?|hundreds?|metric|national|local|stated)\b", txt, re.IGNORECASE):
      return True
    if re.search(r"\b(?:current|constant)\s+price", txt, re.IGNORECASE) or re.match(r"^\d{4}(?:[,/\-\s]+\d{2,4})*\s*price", txt, re.IGNORECASE):
      return False

    words = re.sub(r"[()\[\].,:%0-9/\-–—=$]", " ", txt.lower()).split()
    if not words:
      return True

    #Return statement
    return all(w in self.unit_vocab_set for w in words)


  def isYearOrRange (self, arg1_text_str):
    """
    @brief Check whether a string represents a historical year, slash census year ('1951/2') or year range ('1867-77').
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
    @brief Map data columns to country keys when horizontally separated country headings sit above a shared table.
    @param arg1_cols_array Reconstructed columns list from TableStructureReconstructor.
    @param arg2_col_lookup_obj Mapping of col_index to analysed header years and semantic segments.
    @param arg3_above_phrases_array List of phrase dictionaries extracted above the table's top rule.
    @return Tuple (col_index_to_place_dict, single_place_or_None, rightmost_place_key_or_None).
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
      h_cls = self.normaliser.C_classifySubtableHeading(phr.get("text"))
      p_slug = h_cls["place_key"]
      if p_slug:
        valid_phrases.append({
          "place": p_slug,
          "x1": float(phr.get("x1", 0.0)),
          "x_centre": float(phr.get("x_centre", 0.0))
        })

    if len(valid_phrases) == 1:
      return ({}, valid_phrases[0]["place"], valid_phrases[0]["place"])
    if len(valid_phrases) < 2 or not data_cols:
      return ({}, None, None)

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
    return (col_places_map, None, valid_phrases[-1]["place"])


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
    @brief Convert any phrase into clean lowercase ASCII snake_case via PlaceKeyNormaliser.
    @param arg1_raw_str Arbitrary label string.
    @return Clean snake_case identifier string.
    """
    #Convert from parameters
    raw_str = arg1_raw_str

    #Return statement
    return self.normaliser.toSnakeSlug(raw_str)
