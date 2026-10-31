"""@brief Multi-tier table column header resolver with cmidrule span matching, 1-to-1 wrap merging and de-hyphenation."""

import re
import numpy as np


class HeaderHierarchyResolver:
  """@brief Resolves multi-line table column headers without Voronoi smearing across blank header space."""

  def __init__ (self, arg1_config_obj, arg2_cell_resolver_obj):
    """
    @brief Initialise HeaderHierarchyResolver with vocabulary sets and cell footnote stripper.
    @param arg1_config_obj Pipeline configuration dictionary loaded from /common/digitiser/.
    @param arg2_cell_resolver_obj BraceAndCellResolver instance for stripping attached footnotes.
    """
    #Convert from parameters
    config_obj = arg1_config_obj if isinstance(arg1_config_obj, dict) else {}
    cell_resolver_obj = arg2_cell_resolver_obj

    #Declare local instance variables
    flat_cfg = config_obj.get("series_flattening", {})
    self.cell_resolver = cell_resolver_obj
    self.geo_prefix_set = {
      "antigua", "belgian", "bosnia", "british", "burkina", "cape", "cayman", "central", "costa",
      "dominican", "dutch", "east", "ei", "el", "equatorial", "falkland", "french", "german",
      "gold", "great", "hong", "inner", "italian", "ivory", "lower", "marshall", "netherland",
      "netherlands", "new", "north", "northern", "outer", "papua", "portuguese", "puerto",
      "saint", "san", "santa", "santo", "sao", "saudi", "sierra", "solomon", "south", "southern",
      "spanish", "sri", "st", "trinidad", "united", "upper", "viet", "virgin", "west", "western"
    }
    self.indicator_vocab_set = {str(w).lower() for w in flat_cfg.get("pure_sector_and_indicator_vocab", [])}
    self.subindicator_codes_set = {
      "a", "all", "b", "both", "br", "c", "cb", "constant", "cp", "current", "d", "e", "entered",
      "exp", "exports", "f", "female", "females", "g", "gcf", "gdp", "gfcf", "girls", "gnp", "h",
      "higher", "i", "ib", "imports", "imr", "loaded", "m", "male", "males", "men", "motor",
      "nmp", "ocb", "p", "pkm", "pp", "primary", "r", "re_exports", "rev", "s", "sailing",
      "secondary", "steam", "t", "tkm", "total", "totals", "ttb", "tv", "unloaded", "v", "value",
      "vb", "volume", "women"
    }
    self.unit_vocab_set = {str(u).lower() for u in flat_cfg.get("unit_vocab", [])}


  def A_extractLeafAndUpperTiers (self, arg1_header_lines_array, arg2_stub_right_x, arg3_strong_body_col_count):
    """
    @brief Step A: Partition clustered header lines into column leaf phrases, stub label and upper/unit tiers.
    @param arg1_header_lines_array Top-to-bottom sorted header token lines.
    @param arg2_stub_right_x Right pixel boundary of the row stub column.
    @param arg3_strong_body_col_count Count of strong body data column clusters.
    @return Dictionary containing leaf_phrases, stub_label, upper_tiers and leaf_y.
    """
    #Convert from parameters
    h_lines = arg1_header_lines_array if isinstance(arg1_header_lines_array, list) else []
    stub_right_x = float(arg2_stub_right_x)
    strong_cnt = int(arg3_strong_body_col_count)

    #Declare local instance variables
    active_leaf_ln = []
    leaf_phrases_array = []
    leaf_y = 0.0
    stub_label = "row_label"
    unit_footer_lines = []
    upper_h_lines = []
    work_h_lines = list(h_lines)

    for _ in range(len(work_h_lines)):
      if len(work_h_lines) >= 2 and self.isUnitHeaderLine(work_h_lines[-1]):
        unit_footer_lines.insert(0, work_h_lines.pop())
      else:
        break

    for _ in range(len(work_h_lines)):
      if len(work_h_lines) >= 2 and self.isUnitHeaderLine(work_h_lines[0]):
        unit_footer_lines.append(work_h_lines.pop(0))
      else:
        break

    upper_h_lines = work_h_lines
    if work_h_lines:
      bot_ln = work_h_lines[-1]
      cand_leaves = self.groupHeaderLeafLine(bot_ln, 16)
      data_leaves = [p for p in cand_leaves if p["x_centre"] > stub_right_x - 12.0]
      stub_leaves = [p for p in cand_leaves if p["x_centre"] <= stub_right_x - 12.0]

      if len(data_leaves) >= max(1, strong_cnt - 1):
        leaf_phrases_array = data_leaves
        upper_h_lines = work_h_lines[:-1]
        active_leaf_ln = bot_ln
      elif len(work_h_lines) >= 2:
        prev_ln = work_h_lines[-2]
        prev_leaves = [p for p in self.groupHeaderLeafLine(prev_ln, 16) if p["x_centre"] > stub_right_x - 12.0]
        if len(prev_leaves) > len(data_leaves) and len(prev_leaves) >= max(1, strong_cnt - 1):
          leaf_phrases_array = prev_leaves
          upper_h_lines = work_h_lines[:-2] + [work_h_lines[-1]]
          active_leaf_ln = prev_ln
        else:
          active_leaf_ln = bot_ln
      else:
        active_leaf_ln = bot_ln

      if stub_leaves:
        stub_label = stub_leaves[0]["text"]

    if active_leaf_ln:
      leaf_y = float(np.mean([t["y_centre"] for t in active_leaf_ln]))

    #Return statement
    return {
      "leaf_phrases": leaf_phrases_array,
      "leaf_y": leaf_y,
      "stub_label": stub_label,
      "upper_tiers": list(upper_h_lines) + unit_footer_lines
    }


  def B_attachUpperTiersToColumns (self, arg1_data_cols_array, arg2_upper_tiers_array, arg3_leaf_y, arg4_stub_right_x, arg5_cmidrules_array):
    """
    @brief Step B: Attach upper and unit header tiers onto data columns via cmidrules, centred spans or 1-to-1 wraps.
    @param arg1_data_cols_array Data column descriptor dictionaries (cols 1..C).
    @param arg2_upper_tiers_array Non-leaf header token lines.
    @param arg3_leaf_y Baseline y coordinate of the active leaf header line.
    @param arg4_stub_right_x Right pixel boundary of the row stub column.
    @param arg5_cmidrules_array Detected header cmidrule strokes.
    @return Updated data_cols_array with header_entries populated.
    """
    #Convert from parameters
    data_cols_array = arg1_data_cols_array if isinstance(arg1_data_cols_array, list) else []
    upper_tiers_array = arg2_upper_tiers_array if isinstance(arg2_upper_tiers_array, list) else []
    leaf_y = float(arg3_leaf_y)
    stub_right_x = float(arg4_stub_right_x)
    cmidrules_array = arg5_cmidrules_array if isinstance(arg5_cmidrules_array, list) else []

    if not data_cols_array:
      return data_cols_array

    for i in range(len(data_cols_array)):
      dc = data_cols_array[i]
      if not re.match(r"^col_\d+$", str(dc.get("label", ""))):
        dc["header_entries"] = [{"is_span": False, "text": dc["label"]}]
      else:
        dc["header_entries"] = []

    if not upper_tiers_array:
      return data_cols_array

    ordered_tiers = sorted(upper_tiers_array, key=lambda ln: float(np.mean([t["y_centre"] for t in ln])))
    for i in range(len(ordered_tiers)):
      tier_ln = ordered_tiers[i]
      tier_y = float(np.mean([t["y_centre"] for t in tier_ln]))
      is_unit_tier = self.isUnitHeaderLine(tier_ln)
      append_end = (leaf_y > 0.0 and tier_y > leaf_y + 4.0) or is_unit_tier
      phrase_gap = 68.0 if is_unit_tier else 24.0
      phrases = [p for p in self.groupLineIntoPhrases(tier_ln, phrase_gap) if p["x2"] > stub_right_x - 10.0]
      if not phrases:
        continue

      assignments = self.resolveTierColumnAssignments(phrases, data_cols_array, cmidrules_array, append_end, is_unit_tier)
      for x in range(len(assignments)):
        p, matched_cols, is_span = assignments[x]
        for y in range(len(matched_cols)):
          dc = matched_cols[y]
          entry_obj = {"is_span": is_span, "text": p["text"]}
          if append_end or not dc["header_entries"]:
            dc["header_entries"].append(entry_obj)
          else:
            dc["header_entries"].insert(max(0, len(dc["header_entries"]) - 1), entry_obj)
          for z in range(len(p["footnotes"])):
            if p["footnotes"][z] not in dc["header_footnotes"]:
              dc["header_footnotes"].append(p["footnotes"][z])

    #Return statement
    return data_cols_array


  def C_normaliseAndMergeColumnPaths (self, arg1_columns_array):
    """
    @brief Step C: Heal single-letter I/E OCR errors, de-hyphenate and merge 1-to-1 wrapped column leaves.
    @param arg1_columns_array Full columns list (col 0 = row_stub, cols 1..C = data columns).
    @return Updated columns_array with clean header_path and label strings.
    """
    #Convert from parameters
    columns_array = arg1_columns_array if isinstance(arg1_columns_array, list) else []

    if len(columns_array) <= 1:
      return columns_array

    #Declare local instance variables
    has_export_sibling = False

    # 1. Clean raw segments and strip attached footnotes on each data column
    for i in range(1, len(columns_array)):
      col = columns_array[i]
      raw_entries = col.get("header_entries")
      if raw_entries is None:
        raw_entries = [{"is_span": False, "text": s} for s in col.get("header_path", [])]
      cleaned_entries = []
      for x in range(len(raw_entries)):
        seg_raw = re.sub(r"(?:\s*[.…]{2,})+\s*$", "", str(raw_entries[x]["text"])).strip()
        if not seg_raw or seg_raw in ["...", "—"] or re.match(r"^col_\d+$", seg_raw):
          continue
        c_seg, extra_fns = self.cell_resolver.stripAttachedTitleFootnotes(seg_raw)
        if c_seg:
          cleaned_entries.append({"is_span": bool(raw_entries[x]["is_span"]), "text": c_seg})
          if x == len(raw_entries) - 1 and c_seg in ["E", "Exports"]:
            has_export_sibling = True
        for y in range(len(extra_fns)):
          if extra_fns[y] not in col["header_footnotes"]:
            col["header_footnotes"].append(extra_fns[y])
      col["header_entries"] = cleaned_entries

    # 2. Heal EasyOCR '1' / 'l' / '|' / '[' / 'J' -> 'I' when paired alongside 'E' / 'Exports' on leaf tier
    if has_export_sibling:
      for i in range(1, len(columns_array)):
        entries = columns_array[i].get("header_entries", [])
        if entries and entries[-1]["text"] in ["1", "l", "|", "[", "]", "!", "J"]:
          entries[-1]["text"] = "I"

    # 3. Merge 1-to-1 wrapped column labels and multi-word geographic span prefixes ('New' + 'Zealand', 'South' + 'Korea')
    span_upgrades_map = {}
    for i in range(1, len(columns_array)):
      col = columns_array[i]
      entries = col.get("header_entries", [])
      merged_entries = []
      for x in range(len(entries)):
        cur_e = entries[x]
        if merged_entries:
          prev_txt = merged_entries[-1]["text"]
          prev_alpha = re.findall(r"[A-Za-z]+", prev_txt.lower())
          force_geo_or_hyph = prev_txt.endswith(("-", "–")) or bool(prev_alpha and prev_alpha[-1] in self.geo_prefix_set) or prev_txt in ["EI", "E1"]
          if (not merged_entries[-1]["is_span"] and not cur_e["is_span"]) or force_geo_or_hyph:
            do_merge, joined_txt = self.shouldMergeWrappedPair(prev_txt, cur_e["text"])
            if do_merge:
              if force_geo_or_hyph and cur_e["is_span"]:
                span_upgrades_map[(i, cur_e["text"])] = joined_txt
              merged_entries[-1]["text"] = joined_txt
              merged_entries[-1]["is_span"] = merged_entries[-1]["is_span"] or cur_e["is_span"]
              continue
        merged_entries.append(dict(cur_e))
      col["header_entries"] = merged_entries

    # 4. Propagate merged 2-line country prefixes across sibling span columns (e.g. Col 1 'New'+'Zealand' -> Col 2 'Zealand')
    for (src_idx, tail_txt), full_txt in span_upgrades_map.items():
      for adj_idx in [src_idx - 1, src_idx + 1]:
        if 1 <= adj_idx < len(columns_array):
          adj_entries = columns_array[adj_idx].get("header_entries", [])
          for x in range(len(adj_entries)):
            if adj_entries[x]["text"] == tail_txt:
              adj_entries[x]["text"] = full_txt

    for i in range(1, len(columns_array)):
      col = columns_array[i]
      merged_entries = col.get("header_entries", [])
      clean_path = [e["text"] for e in merged_entries if e["text"]]
      col["header_path"] = clean_path
      col["label"] = " | ".join(clean_path) if clean_path else f"col_{i}"
      if "header_entries" in col:
        del col["header_entries"]

    #Return statement
    return columns_array


  def groupHeaderLeafLine (self, arg1_line_tokens_array, arg2_max_gap_px):
    """
    @brief Group bottom-row header leaf tokens while never merging two distinct 4-digit year or code headers.
    @param arg1_line_tokens_array Left-to-right sorted tokens on the bottom header line.
    @param arg2_max_gap_px Maximum horizontal gap in pixels for multi-word column leaves.
    @return List of merged phrase dictionaries.
    """
    #Convert from parameters
    line_tokens_array = arg1_line_tokens_array
    max_gap = float(arg2_max_gap_px)

    if not line_tokens_array:
      return []

    groups_array = [[line_tokens_array[0]]]
    for i in range(1, len(line_tokens_array)):
      prev = groups_array[-1][-1]
      cur = line_tokens_array[i]
      gap = cur["x1"] - prev["x2"]
      both_years = bool(re.match(r"^\d{4}", prev["text"]) and re.match(r"^\d{4}", cur["text"]))
      both_codes = bool(re.match(r"^[A-Z1l|\[!]{1,4}$", prev["text"]) and re.match(r"^[A-Z1l|\[!]{1,4}$", cur["text"]))
      if gap <= max_gap and not both_years and not both_codes:
        groups_array[-1].append(cur)
      else:
        groups_array.append([cur])

    #Return statement
    return [self.mergeTokensList(grp) for grp in groups_array]


  def groupLineIntoPhrases (self, arg1_line_tokens_array, arg2_max_gap_px):
    """
    @brief Group horizontally close words on a single line into multi-word phrases.
    @param arg1_line_tokens_array Left-to-right sorted tokens on one line.
    @param arg2_max_gap_px Maximum horizontal pixel gap between words in the same phrase.
    @return List of phrase dictionaries.
    """
    #Convert from parameters
    line_tokens_array = arg1_line_tokens_array
    max_gap = float(arg2_max_gap_px)

    if not line_tokens_array:
      return []

    groups_array = [[line_tokens_array[0]]]
    for i in range(1, len(line_tokens_array)):
      prev = groups_array[-1][-1]
      cur = line_tokens_array[i]
      if cur["x1"] - prev["x2"] <= max_gap:
        groups_array[-1].append(cur)
      else:
        groups_array.append([cur])

    #Return statement
    return [self.mergeTokensList(grp) for grp in groups_array]


  def isRepeatingSubindicatorLeaves (self, arg1_data_cols_array):
    """
    @brief Check whether leaf column labels consist of repeating short sub-indicators or years (e.g. M/F/Total, I/E).
    @param arg1_data_cols_array Data column descriptor dictionaries.
    @return Boolean True if at least 80% of leaves are short sub-indicators or years.
    """
    #Convert from parameters
    data_cols = arg1_data_cols_array

    if not data_cols or len(data_cols) < 4:
      return False

    matched_cnt = 0
    for i in range(len(data_cols)):
      lbl = str(data_cols[i].get("label", "")).strip()
      clean_l = re.sub(r"[^A-Za-z0-9]+", "_", lbl.lower()).strip("_")
      if self.isYearHeaderText(lbl) or clean_l in self.subindicator_codes_set or lbl in ["1", "l", "|", "["]:
        matched_cnt = matched_cnt + 1

    #Return statement
    return matched_cnt >= int(np.ceil(0.8*len(data_cols)))


  def isUnitHeaderLine (self, arg1_line_tokens_array):
    """
    @brief Detect whether a header line is an italic unit/scale sub-banner (e.g. 'million pounds', 'thousand dollars').
    @param arg1_line_tokens_array Tokens on a single header line.
    @return Boolean True if every word on the line belongs to statistical unit/scale vocabulary.
    """
    #Convert from parameters
    ln = arg1_line_tokens_array

    if not ln:
      return False

    words_checked = 0
    for i in range(len(ln)):
      raw_w = re.sub(r"[()\[\].,:%0-9/\-–—=$]", " ", ln[i]["text"].lower()).split()
      for x in range(len(raw_w)):
        words_checked = words_checked + 1
        if raw_w[x] not in self.unit_vocab_set:
          return False

    #Return statement
    return words_checked >= 1


  def isYearHeaderText (self, arg1_text_str):
    """
    @brief Check whether a header segment represents a historical year or year range.
    @param arg1_text_str Candidate header segment string.
    @return Boolean True if year or range.
    """
    #Convert from parameters
    txt = re.sub(r"^circa\s+", "", str(arg1_text_str or "").strip(), flags=re.IGNORECASE).strip()

    #Return statement
    return bool(re.match(r"^(?:1[789]\d{2}|20[01]\d)(?:\s*[/\-–—]\s*\d{1,4})?$", txt))


  def mergeTokensList (self, arg1_tokens_array):
    """
    @brief Merge a left-to-right list of tokens into text, footnotes and bounding coordinates.
    @param arg1_tokens_array Left-to-right sorted token dictionaries.
    @return Merged phrase dictionary.
    """
    #Convert from parameters
    tokens_array = arg1_tokens_array

    footnotes_array = []
    parts_array = []
    for i in range(len(tokens_array)):
      t = tokens_array[i]
      txt = t["text"]
      for x in range(len(t.get("footnotes", []))):
        fn = t["footnotes"][x]
        if fn not in footnotes_array:
          footnotes_array.append(fn)
      if not parts_array:
        parts_array.append(txt)
      else:
        gap = t["x1"] - tokens_array[i - 1]["x2"]
        prev_txt = parts_array[-1]
        if gap <= 14 and (prev_txt.endswith(("/", "-", "–", "(")) or txt.startswith(("/", "-", "–", ")", ",", ":"))):
          parts_array[-1] = prev_txt + txt
        else:
          parts_array.append(txt)

    x1 = min(t["x1"] for t in tokens_array)
    x2 = max(t["x2"] for t in tokens_array)
    y1 = min(t["y1"] for t in tokens_array)
    y2 = max(t["y2"] for t in tokens_array)

    #Return statement
    return {
      "footnotes": footnotes_array,
      "text": " ".join(parts_array).strip(),
      "x1": x1,
      "x2": x2,
      "x_centre": 0.5*(x1 + x2),
      "y1": y1,
      "y2": y2,
      "y_centre": 0.5*(y1 + y2)
    }


  def resolveTierColumnAssignments (self, arg1_phrases_array, arg2_data_cols_array, arg3_cmidrules_array, arg4_append_end, arg5_is_unit_tier):
    """
    @brief Map one horizontal tier of header phrases onto data columns without Voronoi extrapolation across blank space.
    @param arg1_phrases_array Left-to-right sorted header phrases on the tier.
    @param arg2_data_cols_array Data column descriptor dictionaries.
    @param arg3_cmidrules_array Detected header cmidrule strokes.
    @param arg4_append_end Boolean True when tier sits below column leaves.
    @param arg5_is_unit_tier Boolean True when tier is a unit/currency sub-banner.
    @return List of (phrase_obj, matched_cols_list, is_span_bool) tuples.
    """
    #Convert from parameters
    phrases_array = sorted(arg1_phrases_array, key=lambda p: p["x_centre"])
    data_cols = arg2_data_cols_array
    cmidrules = arg3_cmidrules_array
    append_end = bool(arg4_append_end)
    is_unit_tier = bool(arg5_is_unit_tier)

    #Declare local instance variables
    assignments_array = []
    cmid_matches = []
    has_any_cmid = False

    for i in range(len(phrases_array)):
      p = phrases_array[i]
      best_rule = None
      best_dy = 1e9
      if not p["text"].rstrip().endswith(("-", "–")):
        for x in range(len(cmidrules)):
          r = cmidrules[x]
          dy = (p["y1"] - r["y"]) if append_end else (r["y"] - p["y2"])
          max_dy = 95.0 if append_end else 52.0
          ov = min(p["x2"], r["x2"]) - max(p["x1"], r["x1"])
          if -8.0 <= dy <= max_dy and ov >= min(14.0, 0.28*(p["x2"] - p["x1"])):
            if abs(dy) < best_dy:
              best_dy = abs(dy)
              best_rule = r
      if best_rule is not None:
        has_any_cmid = True
      cmid_matches.append(best_rule)

    # Fallback Voronoi ONLY when cmidrules were faint/missed AND leaves are repeating sub-indicators (never distinct countries)
    use_repeating_subind_groups = (
      not has_any_cmid
      and not is_unit_tier
      and not append_end
      and len(phrases_array) >= 2
      and len(data_cols) >= 2*len(phrases_array)
      and not any(p["text"].rstrip().endswith(("-", "–")) for p in phrases_array)
      and self.isRepeatingSubindicatorLeaves(data_cols)
    )

    if use_repeating_subind_groups:
      bounds = [-1e9] + [0.5*(phrases_array[i]["x_centre"] + phrases_array[i + 1]["x_centre"]) for i in range(len(phrases_array) - 1)] + [1e9]
      for i in range(len(phrases_array)):
        matched = [dc for dc in data_cols if bounds[i] <= dc["x_centre"] < bounds[i + 1]]
        assignments_array.append((phrases_array[i], matched, len(matched) >= 2))
      return assignments_array

    for i in range(len(phrases_array)):
      p = phrases_array[i]
      rule = cmid_matches[i]
      if rule is not None:
        rx1 = rule["x1"] - 14.0
        rx2 = rule["x2"] + 14.0
        matched = [dc for dc in data_cols if rx1 <= dc["x_centre"] <= rx2]
        assignments_array.append((p, matched, len(matched) >= 2))
      elif is_unit_tier:
        if len(phrases_array) == 1 and len(data_cols) >= 2 and data_cols[0]["x1"] - 30.0 <= p["x_centre"] <= data_cols[-1]["x2"] + 30.0:
          assignments_array.append((p, list(data_cols), True))
        else:
          matched = [dc for dc in data_cols if (p["x1"] - 55.0) <= dc["x_centre"] <= (p["x2"] + 55.0)]
          assignments_array.append((p, matched, len(matched) >= 2))
      elif p["text"].rstrip().endswith(("-", "–")):
        dists = sorted(data_cols, key=lambda dc: abs(dc["x_centre"] - p["x_centre"]))
        matched = [dists[0]] if dists and abs(dists[0]["x_centre"] - p["x_centre"]) <= 72.0 else []
        assignments_array.append((p, matched, False))
      else:
        direct_cols = [dc for dc in data_cols if (p["x1"] - 26.0) <= dc["x_centre"] <= (p["x2"] + 26.0)]
        if len(direct_cols) >= 2:
          assignments_array.append((p, direct_cols, True))
        elif len(direct_cols) == 1:
          assignments_array.append((p, direct_cols, False))
        else:
          centred_pair = []
          if not append_end:
            for x in range(len(data_cols) - 1):
              c0 = data_cols[x]
              c1 = data_cols[x + 1]
              if c0["x_centre"] < p["x_centre"] < c1["x_centre"] and abs(0.5*(c0["x_centre"] + c1["x_centre"]) - p["x_centre"]) <= 34.0:
                other_overlaps = any(
                  y != i and ((phrases_array[y]["x1"] - 26.0) <= c0["x_centre"] <= (phrases_array[y]["x2"] + 26.0) or (phrases_array[y]["x1"] - 26.0) <= c1["x_centre"] <= (phrases_array[y]["x2"] + 26.0))
                  for y in range(len(phrases_array))
                )
                if not other_overlaps:
                  centred_pair = [c0, c1]
                  break
          if centred_pair:
            assignments_array.append((p, centred_pair, True))
          else:
            dists = sorted(data_cols, key=lambda dc: abs(dc["x_centre"] - p["x_centre"]))
            matched = [dists[0]] if dists and abs(dists[0]["x_centre"] - p["x_centre"]) <= 62.0 else []
            assignments_array.append((p, matched, False))

    #Return statement
    return assignments_array


  def shouldMergeWrappedPair (self, arg1_prev_txt, arg2_cur_txt):
    """
    @brief Decide whether two consecutive single-column header lines form one wrapped phrase and return merged string.
    @param arg1_prev_txt Upper single-column segment string.
    @param arg2_cur_txt Lower single-column segment string.
    @return Tuple (should_merge_bool, merged_string).
    """
    #Convert from parameters
    prev_txt = str(arg1_prev_txt or "").strip()
    cur_txt = str(arg2_cur_txt or "").strip()

    if not prev_txt or not cur_txt:
      return (False, "")

    # 1. Explicit hyphenated word wrap ('Cam-' + 'eroon' -> 'Cameroon', 'Austria-' + 'Hungary' -> 'Austria-Hungary')
    if prev_txt.endswith(("-", "–")):
      stem = prev_txt[:-1].rstrip()
      if not stem:
        return (False, "")
      if stem.lower() in ["alsace", "austria", "bosnia", "guinea", "schleswig"]:
        return (True, f"{stem}-{cur_txt.lstrip()}")
      return (True, f"{stem}{cur_txt.lstrip()}")

    # 2. Never merge years or index-base/unit lines into semantic text
    if self.isYearHeaderText(prev_txt) or self.isYearHeaderText(cur_txt):
      return (False, "")
    if "=" in prev_txt or "=" in cur_txt:
      return (False, "")
    prev_words_u = re.sub(r"[()\[\].,:%0-9/\-–—=$]", " ", prev_txt.lower()).split()
    cur_words_u = re.sub(r"[()\[\].,:%0-9/\-–—=$]", " ", cur_txt.lower()).split()
    if (prev_words_u and all(w in self.unit_vocab_set for w in prev_words_u)) or (cur_words_u and all(w in self.unit_vocab_set for w in cur_words_u)):
      return (False, "")

    # 3. Heal OCR 'EI' + 'Salvador' -> 'El Salvador'
    if prev_txt in ["EI", "E1"] and cur_txt.lower().startswith("salvador"):
      return (True, f"El {cur_txt}")

    # 4. Geographic multi-word prefixes ('New' + 'Zealand', 'South' + 'Africa', 'Sri' + 'Lanka', 'West' + 'Germany')
    prev_alpha = re.findall(r"[A-Za-z]+", prev_txt.lower())
    if prev_alpha and prev_alpha[-1] in self.geo_prefix_set:
      return (True, f"{prev_txt} {cur_txt}")

    # 5. Grammatical connectors and parenthetical qualifiers ('Agriculture,' + 'Forestry', 'Congo' + '(Kinshasa)')
    if (
      prev_txt.endswith((",", "&", "("))
      or bool(re.search(r"\b(?:and|or|of|in|by|for|to|at|on|the|de|la|du|del)\s*$", prev_txt, re.IGNORECASE))
      or cur_txt.startswith(("(", ")", "&"))
      or bool(re.match(r"^(?:and|or|of|in|by|for|to|etc\.?)\b", cur_txt, re.IGNORECASE))
    ):
      return (True, f"{prev_txt} {cur_txt}")

    # 6. Keep [Country, ShortIndicatorCode] as 2-level path ('Austria' | 'I', 'Ghana' | 'M')
    if re.match(r"^[A-Z]{1,4}$", cur_txt):
      return (False, "")

    # 7. Merge multi-line sector/commodity descriptors ('Extractive' + 'Industry', 'Current' + 'Prices')
    cur_alpha = re.findall(r"[A-Za-z]+", cur_txt.lower())
    if prev_alpha and cur_alpha:
      if all(w in self.indicator_vocab_set for w in prev_alpha) and all(w in self.indicator_vocab_set for w in cur_alpha):
        return (True, f"{prev_txt} {cur_txt}")

    #Return statement
    return (False, "")

