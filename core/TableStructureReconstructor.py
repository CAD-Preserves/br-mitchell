"""@brief Reconstructs multi-level table headers, canonical row/column grids, two-tier qualifiers and brace spans."""

import re
import numpy as np
from core.BraceAndCellResolver import BraceAndCellResolver
from core.HeaderHierarchyResolver import HeaderHierarchyResolver


class TableStructureReconstructor:
  """@brief Converts detected graphical blocks and OCR tokens on a page into structured, analysis-ready table objects."""

  def __init__ (self, arg1_config_obj):
    """
    @brief Initialise TableStructureReconstructor and its companion BraceAndCellResolver and HeaderHierarchyResolver.
    @param arg1_config_obj Pipeline configuration dictionary loaded from /common/digitiser/.
    """
    #Convert from parameters
    config_obj = arg1_config_obj if isinstance(arg1_config_obj, dict) else {}

    #Declare local instance variables
    flat_cfg = config_obj.get("series_flattening", {})
    self.cell_resolver = BraceAndCellResolver(config_obj)
    self.header_resolver = HeaderHierarchyResolver(config_obj, self.cell_resolver)
    self.struct_cfg = config_obj.get("structure", {})
    self.subheaders_set = {str(s).lower() for s in flat_cfg.get("demographic_subheaders", [])}
    self.whole_qualifiers_set = {str(q).lower() for q in flat_cfg.get("whole_entity_qualifiers", [])}


  def A_extractSubtableMetadata (self, arg1_block_obj, arg2_all_tokens_array, arg3_prev_bot_y):
    """
    @brief Step A: Identify sub-table title, date-range banner and separate header vs body token sets.
    @param arg1_block_obj Single table block dictionary from GraphicalElementDetector.
    @param arg2_all_tokens_array Page OCR tokens below any full-page section banner.
    @param arg3_prev_bot_y Bottom y coordinate of any preceding block in the same vertical column/band.
    @return Dictionary containing above_phrases, title, title_footnotes, period_banner, header_tokens and body_tokens.
    """
    #Convert from parameters
    blk = arg1_block_obj
    all_tokens_array = arg2_all_tokens_array if isinstance(arg2_all_tokens_array, list) else []
    prev_bot_y = float(arg3_prev_bot_y)

    #Declare local instance variables
    above_phrases_array = []
    above_tokens_array = []
    body_tokens_array = []
    header_tokens_array = []
    lookback_px = int(self.struct_cfg.get("title_lookback_px", 95))
    period_banner = None
    title_footnotes_array = []
    title_str = None
    x1 = blk["x1"]
    x2 = blk["x2"]
    y_bot = blk["y_bot"]
    y_mid = blk["y_mid"]
    y_top = blk["y_top"]

    min_above_y = max(prev_bot_y + 6.0, y_top - lookback_px)
    for i in range(len(all_tokens_array)):
      t = all_tokens_array[i]
      if not t.get("text"):
        continue
      tx = t["x_centre"]
      ty = t["y_centre"]
      if tx < x1 - 18 or tx > x2 + 18:
        continue
      if min_above_y <= ty <= y_top - 2:
        above_tokens_array.append(t)
      elif y_top - 2 < ty <= y_mid - 1:
        header_tokens_array.append(t)
      elif y_mid - 1 < ty <= y_bot + 3:
        body_tokens_array.append(t)

    if above_tokens_array:
      above_lines = self.clusterTokensIntoLines(above_tokens_array, 14)
      filtered_above_lines = []
      skip_banner_tail_until_y = -1.0
      skip_legend_until_y = -1.0

      for i in range(len(above_lines)):
        ln = above_lines[i]
        joined = " ".join(tok["text"] for tok in ln).strip()
        ln_yc = float(np.mean([tok["y_centre"] for tok in ln]))

        if self.looksLikeSectionBanner(joined):
          skip_banner_tail_until_y = ln_yc + 58.0
          continue
        if re.match(r"^(?:Key\s*[:\-–—]|Key\s+to\b|Abbreviations\b|NOTES\b|FOOTNOTES\b|Symbols\b)", joined, re.IGNORECASE):
          skip_legend_until_y = ln_yc + 56.0
          continue
        if "=" in joined and not re.search(r"\b\d{4}\s*=\s*100\b", joined):
          skip_legend_until_y = ln_yc + 44.0
          continue
        if ln_yc <= skip_legend_until_y and (";" in joined or ":" in joined):
          skip_legend_until_y = ln_yc + 44.0
          continue
        if ln_yc <= skip_banner_tail_until_y or (")" in joined and "(" not in joined) or re.match(r"^\(in\s+", joined, re.IGNORECASE):
          continue
        filtered_above_lines.append(ln)

      for i in range(len(filtered_above_lines)):
        ln = filtered_above_lines[i]
        joined = " ".join(tok["text"] for tok in ln).strip()
        phrases_abv = self.header_resolver.groupLineIntoPhrases(ln, 95)

        if self.isPeriodBannerText(joined):
          period_banner = joined
        elif len(phrases_abv) >= 2 and self.isPeriodBannerText(phrases_abv[-1]["text"]):
          period_banner = phrases_abv[-1]["text"]
          left_phrases = phrases_abv[:-1]
          if len(left_phrases) == 1:
            clean_t, extra_fns = self.cell_resolver.stripAttachedTitleFootnotes(left_phrases[0]["text"])
            if clean_t:
              title_str = f"{title_str} {clean_t}".strip() if title_str else clean_t
            combined_fns = left_phrases[0]["footnotes"] + extra_fns
            for x in range(len(combined_fns)):
              if combined_fns[x] not in title_footnotes_array:
                title_footnotes_array.append(combined_fns[x])
          elif (left_phrases[1]["x1"] - left_phrases[0]["x2"]) >= 120:
            for x in range(len(left_phrases)):
              clean_p, _ = self.cell_resolver.stripAttachedTitleFootnotes(left_phrases[x]["text"])
              if clean_p:
                above_phrases_array.append({"text": clean_p, "x1": left_phrases[x]["x1"], "x2": left_phrases[x]["x2"], "x_centre": left_phrases[x]["x_centre"]})
          else:
            raw_left = " ".join(p["text"] for p in left_phrases).strip()
            clean_t, extra_fns = self.cell_resolver.stripAttachedTitleFootnotes(raw_left)
            if clean_t:
              title_str = f"{title_str} {clean_t}".strip() if title_str else clean_t
            for x in range(len(extra_fns)):
              if extra_fns[x] not in title_footnotes_array:
                title_footnotes_array.append(extra_fns[x])
        elif len(phrases_abv) >= 2 and (phrases_abv[1]["x1"] - phrases_abv[0]["x2"]) >= 120:
          for x in range(len(phrases_abv)):
            clean_p, _ = self.cell_resolver.stripAttachedTitleFootnotes(phrases_abv[x]["text"])
            if clean_p:
              above_phrases_array.append({"text": clean_p, "x1": phrases_abv[x]["x1"], "x2": phrases_abv[x]["x2"], "x_centre": phrases_abv[x]["x_centre"]})
        else:
          clean_t, extra_fns = self.cell_resolver.stripAttachedTitleFootnotes(joined)
          if clean_t:
            title_str = f"{title_str} {clean_t}".strip() if title_str else clean_t
          for x in range(len(ln)):
            for y in range(len(ln[x].get("footnotes", []))):
              fn = ln[x]["footnotes"][y]
              if fn not in title_footnotes_array:
                title_footnotes_array.append(fn)
          for x in range(len(extra_fns)):
            if extra_fns[x] not in title_footnotes_array:
              title_footnotes_array.append(extra_fns[x])

    # Only pop genuine flush-left or table-wide banners inside y_top..y_mid; never pop hyphenated or column-aligned wraps
    if header_tokens_array and not blk.get("cmidrules"):
      h_lines = self.clusterTokensIntoLines(header_tokens_array, int(self.struct_cfg.get("header_row_cluster_tol_px", 14)))
      for _ in range(len(h_lines)):
        if len(h_lines) < 2:
          break
        top_ln = h_lines[0]
        phrases = self.header_resolver.groupLineIntoPhrases(top_ln, 26)
        if len(phrases) == 1:
          p_obj = phrases[0]
          p_txt = p_obj["text"].strip()
          is_wrap_or_code = (
            p_txt.endswith(("-", "–"))
            or p_txt.lower().rstrip(".") in self.header_resolver.geo_prefix_set
            or bool(re.match(r"^(?:M|F|B|D|I|E|Total|Date|circa|Imports|Exports|\(.*\))$", p_txt, re.IGNORECASE))
            or self.isPeriodBannerText(p_txt)
          )
          is_flush_left = (p_obj["x1"] <= x1 + 65)
          is_table_centred_heading = (
            len(p_txt.split()) >= 2
            and len(h_lines[1]) >= 3
            and abs(p_obj["x_centre"] - 0.5*(x1 + x2)) <= 0.10*(x2 - x1)
          )
          if not is_wrap_or_code and (is_flush_left or is_table_centred_heading):
            clean_t, extra_fns = self.cell_resolver.stripAttachedTitleFootnotes(p_txt)
            title_str = f"{title_str} - {clean_t}" if title_str else clean_t
            combined_fns = p_obj["footnotes"] + extra_fns
            for x in range(len(combined_fns)):
              if combined_fns[x] not in title_footnotes_array:
                title_footnotes_array.append(combined_fns[x])
            used_ids = {id(tok) for tok in top_ln}
            header_tokens_array = [tok for tok in header_tokens_array if id(tok) not in used_ids]
            h_lines = h_lines[1:]
            continue
        elif len(h_lines) >= 3:
          phrases_abv = self.header_resolver.groupLineIntoPhrases(top_ln, 65)
          if (
            len(phrases_abv) >= 2
            and phrases_abv[0]["x1"] <= x1 + 65
            and (phrases_abv[1]["x1"] - phrases_abv[0]["x2"]) >= 120
            and not any(re.match(r"^\d{4}", p["text"]) or p["text"].endswith(("-", "–")) for p in phrases_abv)
          ):
            for x in range(len(phrases_abv)):
              clean_p, _ = self.cell_resolver.stripAttachedTitleFootnotes(phrases_abv[x]["text"])
              if clean_p:
                above_phrases_array.append({"text": clean_p, "x1": phrases_abv[x]["x1"], "x2": phrases_abv[x]["x2"], "x_centre": phrases_abv[x]["x_centre"]})
            used_ids = {id(tok) for tok in top_ln}
            header_tokens_array = [tok for tok in header_tokens_array if id(tok) not in used_ids]
            h_lines = h_lines[1:]
            continue
        break

    #Return statement
    return {
      "above_phrases": above_phrases_array,
      "body_tokens": body_tokens_array,
      "header_tokens": header_tokens_array,
      "period_banner": period_banner,
      "title": title_str,
      "title_footnotes": title_footnotes_array
    }


  def B_inferColumns (self, arg1_block_obj, arg2_header_tokens_array, arg3_body_tokens_array):
    """
    @brief Step B: Reconstruct stub column and data column x-anchors plus clean multi-level header paths.
    @param arg1_block_obj Table block dictionary (with x1, x2, cmidrules).
    @param arg2_header_tokens_array Header tokens inside (y_top, y_mid).
    @param arg3_body_tokens_array Body tokens inside (y_mid, y_bot).
    @return List of column descriptor dictionaries (col 0 = row_stub, cols 1..C = data columns).
    """
    #Convert from parameters
    blk = arg1_block_obj
    header_tokens_array = arg2_header_tokens_array
    body_tokens_array = arg3_body_tokens_array

    #Declare local instance variables
    cmidrules_array = blk.get("cmidrules", [])
    columns_array = []
    h_tol = int(self.struct_cfg.get("header_row_cluster_tol_px", 14))
    stub_max_offset = int(self.struct_cfg.get("stub_col_max_right_offset_px", 260))
    x1 = blk["x1"]

    h_lines = self.clusterTokensIntoLines(header_tokens_array, h_tol) if header_tokens_array else []

    anchor_stub_toks = [t for t in body_tokens_array if t["x1"] <= x1 + 65 and t["w"] <= stub_max_offset]
    base_stub_r = float(max([t["x2"] for t in anchor_stub_toks], default=x1 + 95))

    non_stub_cands = [
      t for t in body_tokens_array
      if t["x1"] > max(x1 + 85, base_stub_r + 6.0)
      and (
        t.get("symbol_kind") is not None
        or self.cell_resolver.parseNumericToken(t["text"])[0] is not None
        or bool(re.match(r"^[+\-\[]?\d{1,3},\s*$", t["text"]))
      )
    ]
    cand_x1_list = []
    if non_stub_cands:
      cand_x1_list.append(float(min(t["x1"] for t in non_stub_cands)))
    if h_lines:
      bot_h_cands = [t for t in h_lines[-1] if t["x1"] > max(x1 + 85, base_stub_r + 6.0) and not re.match(r"^(Date|circa)$", t["text"], re.IGNORECASE)]
      if bot_h_cands:
        cand_x1_list.append(float(min(t["x1"] for t in bot_h_cands)))

    non_stub_cands_x1 = min(cand_x1_list) if cand_x1_list else float(base_stub_r + 24.0)
    if non_stub_cands_x1 > base_stub_r + 6.0:
      stub_right_x = max(float(x1 + 75), 0.5*(base_stub_r + non_stub_cands_x1))
    else:
      stub_right_x = max(float(x1 + 75), base_stub_r + 8.0)

    data_body_toks = [
      t for t in body_tokens_array
      if t["x_centre"] > stub_right_x and t["w"] <= 165 and not re.match(r"^['`‘’*]\d{0,2}$", t["text"])
    ]
    body_col_clusters = self.clusterColumnCentres(data_body_toks)
    strong_body_cols = [c for c in body_col_clusters if c["count"] >= max(3, int(0.25*max([bc["count"] for bc in body_col_clusters], default=1)))]

    tier_info = self.header_resolver.A_extractLeafAndUpperTiers(h_lines, stub_right_x, len(strong_body_cols))
    leaf_phrases_array = tier_info["leaf_phrases"]
    stub_label = tier_info["stub_label"]
    upper_tiers_array = tier_info["upper_tiers"]
    leaf_y = tier_info["leaf_y"] if tier_info["leaf_y"] > 0.0 else float(blk["y_mid"])

    columns_array.append({
      "col_index": 0,
      "header_footnotes": [],
      "header_path": [stub_label] if stub_label != "row_label" else [],
      "label": stub_label,
      "role": "row_stub",
      "x1": float(x1),
      "x2": stub_right_x,
      "x_centre": 0.5*(x1 + stub_right_x)
    })

    if leaf_phrases_array and len(leaf_phrases_array) >= len(strong_body_cols):
      for i in range(len(leaf_phrases_array)):
        lp = leaf_phrases_array[i]
        near_body = [c for c in strong_body_cols if abs(c["x_centre"] - lp["x_centre"]) <= 52]
        xc = 0.5*(lp["x_centre"] + near_body[0]["x_centre"]) if len(near_body) == 1 else lp["x_centre"]
        columns_array.append({
          "col_index": i + 1,
          "header_footnotes": list(lp["footnotes"]),
          "header_path": [lp["text"]],
          "label": lp["text"],
          "role": "data",
          "x1": min(lp["x1"], near_body[0]["x1"]) if near_body else lp["x1"],
          "x2": max(lp["x2"], near_body[0]["x2"]) if near_body else lp["x2"],
          "x_centre": xc
        })
    else:
      use_clusters = strong_body_cols if strong_body_cols else body_col_clusters
      for i in range(len(use_clusters)):
        bc = use_clusters[i]
        near_leaf = [lp for lp in leaf_phrases_array if abs(lp["x_centre"] - bc["x_centre"]) <= 58]
        leaf_txt = near_leaf[0]["text"] if near_leaf else f"col_{i + 1}"
        leaf_fn = list(near_leaf[0]["footnotes"]) if near_leaf else []
        columns_array.append({
          "col_index": i + 1,
          "header_footnotes": leaf_fn,
          "header_path": [leaf_txt],
          "label": leaf_txt,
          "role": "data",
          "x1": bc["x1"],
          "x2": bc["x2"],
          "x_centre": bc["x_centre"]
        })

    data_cols = columns_array[1:]
    if data_cols:
      self.header_resolver.B_attachUpperTiersToColumns(data_cols, upper_tiers_array, leaf_y, stub_right_x, cmidrules_array)
      self.header_resolver.C_normaliseAndMergeColumnPaths(columns_array)

    #Return statement
    return columns_array


  def C_reconstructRowsAndBraces (self, arg1_block_obj, arg2_columns_array, arg3_body_tokens_array):
    """
    @brief Step C: Build canonical row grid, resolve vertical/horizontal spans and track two-tier row banners.
    @param arg1_block_obj Table block dictionary (with braces, col_spans and underlines).
    @param arg2_columns_array Reconstructed columns list from Step B.
    @param arg3_body_tokens_array Body tokens inside (y_mid, y_bot).
    @return Tuple (rows_array, brace_groups_array).
    """
    #Convert from parameters
    blk = arg1_block_obj
    columns_array = arg2_columns_array
    body_tokens_array = arg3_body_tokens_array

    if len(columns_array) <= 1 or not body_tokens_array:
      return ([], [])

    #Declare local instance variables
    braces_array = blk.get("braces", [])
    col_spans_array = blk.get("col_spans", [])
    data_cols = columns_array[1:]
    num_data_cols = len(data_cols)
    row_tol = int(self.struct_cfg.get("row_cluster_tol_px", 15))
    stub_right_x = columns_array[0]["x2"]
    underlines_array = blk.get("underlines", [])

    stub_tokens = [t for t in body_tokens_array if t["x_centre"] <= stub_right_x]
    data_tokens = [t for t in body_tokens_array if t["x_centre"] > stub_right_x]

    stub_lines = self.clusterTokensIntoLines(stub_tokens, row_tol)
    canonical_rows_array = []
    for i in range(len(stub_lines)):
      ln = stub_lines[i]
      lbl_phrase = self.header_resolver.mergeTokensList(ln)
      clean_lbl, extra_fns = self.cell_resolver.stripAttachedTitleFootnotes(lbl_phrase["text"])
      if re.match(r"^(See\s*pp?\.|Seep\.|Superior\s+figure)", clean_lbl, re.IGNORECASE):
        continue
      row_fns = list(lbl_phrase["footnotes"])
      for x in range(len(extra_fns)):
        if extra_fns[x] not in row_fns:
          row_fns.append(extra_fns[x])
      canonical_rows_array.append({
        "is_continuation": False,
        "qualifier": None,
        "row_footnotes": row_fns,
        "row_label": clean_lbl,
        "y1": min(t["y1"] for t in ln),
        "y2": max(t["y2"] for t in ln),
        "y_centre": float(np.mean([t["y_centre"] for t in ln]))
      })

    wrap_dy = float(self.struct_cfg.get("wrapped_stub_max_dy_px", 38))
    merged_rows_array = []
    skip_next = False
    for i in range(len(canonical_rows_array)):
      if skip_next:
        skip_next = False
        continue
      cur_r = canonical_rows_array[i]
      if i + 1 < len(canonical_rows_array):
        nxt_r = canonical_rows_array[i + 1]
        dy = nxt_r["y_centre"] - cur_r["y_centre"]
        cur_lbl = cur_r["row_label"]
        nxt_lbl = nxt_r["row_label"]
        not_years = not (re.match(r"^(?:1[789]\d{2}|20[01]\d)", cur_lbl) or re.match(r"^(?:1[789]\d{2}|20[01]\d)", nxt_lbl))
        unclosed_paren = (cur_lbl.count("(") > cur_lbl.count(")")) or cur_lbl.endswith((",", "-"))
        paren_continuation = nxt_lbl.startswith("(") and nxt_lbl.endswith(")") and not any(abs(t["y_centre"] - nxt_r["y_centre"]) <= row_tol - 2 for t in data_tokens)
        if dy <= wrap_dy and not_years and (unclosed_paren or paren_continuation):
          cur_r["row_label"] = f"{cur_lbl} {nxt_lbl}".strip()
          cur_r["y2"] = max(cur_r["y2"], nxt_r["y2"])
          cur_r["y_centre"] = 0.5*(cur_r["y_centre"] + nxt_r["y_centre"])
          skip_next = True
      merged_rows_array.append(cur_r)
    canonical_rows_array = merged_rows_array

    brace_regions_array = self.cell_resolver.B_resolveBraceRegions(braces_array, canonical_rows_array, data_cols, data_tokens)
    assigned_braced_ids = {id(t) for reg in brace_regions_array for t in reg["captured_tokens"]}

    unbraced_data_tokens = [t for t in data_tokens if id(t) not in assigned_braced_ids]
    orphan_tokens = [
      t for t in unbraced_data_tokens
      if not canonical_rows_array or min(abs(t["y_centre"] - r["y_centre"]) for r in canonical_rows_array) > row_tol + 3
    ]

    orphan_lines = self.clusterTokensIntoLines(orphan_tokens, row_tol)
    qualifier_events_array = []
    snapped_orphan_row_map = {}

    for i in range(len(orphan_lines)):
      oln = orphan_lines[i]
      joined_txt = " ".join(t["text"] for t in oln).strip()
      if re.match(r"^(See\s*pp?\.|Seep\.|Superior\s+figure)", joined_txt, re.IGNORECASE):
        continue
      oy = float(np.mean([t["y_centre"] for t in oln]))
      has_pure_numbers = sum(1 for t in oln if self.cell_resolver.parseNumericToken(t["text"])[0] is not None)
      if has_pure_numbers == 0 or re.match(r"^\d{4}\s*=\s*100", joined_txt) or self.isSubscopeBanner(joined_txt)[0] is not None:
        qualifier_events_array.append({
          "text": joined_txt,
          "x1": min(t["x1"] for t in oln),
          "x2": max(t["x2"] for t in oln),
          "y_centre": oy
        })
      elif has_pure_numbers >= 2 or len(data_cols) == 1:
        snapped_to_existing = False
        if canonical_rows_array:
          orphan_cols = {
            c for c in (self.cell_resolver.assignTokenToColumnIndex(t, data_cols) for t in oln)
            if c is not None
          }
          above_rows = [r for r in canonical_rows_array if r["y_centre"] <= oy]
          below_rows = [r for r in canonical_rows_array if r["y_centre"] > oy]
          adj_cands = []
          if above_rows:
            adj_cands.append(above_rows[-1])
          if below_rows:
            adj_cands.append(below_rows[0])
          adj_cands.sort(key=lambda r: abs(r["y_centre"] - oy))

          for cand_r in adj_cands:
            if abs(cand_r["y_centre"] - oy) <= 24.0 and orphan_cols:
              existing_cols = {
                c for c in (
                  self.cell_resolver.assignTokenToColumnIndex(t, data_cols)
                  for t in unbraced_data_tokens
                  if id(t) not in {id(ot) for ot in oln} and abs(t["y_centre"] - cand_r["y_centre"]) <= row_tol + 3
                )
                if c is not None
              }
              if len(orphan_cols.intersection(existing_cols)) == 0:
                for x in range(len(oln)):
                  snapped_orphan_row_map[id(oln[x])] = cand_r
                snapped_to_existing = True
                break

        if not snapped_to_existing:
          prev_rows = [r for r in canonical_rows_array if r["y_centre"] < oy]
          inherited_lbl = prev_rows[-1]["row_label"] if prev_rows else ""
          canonical_rows_array.append({
            "is_continuation": True,
            "qualifier": None,
            "row_footnotes": [],
            "row_label": inherited_lbl,
            "y1": min(t["y1"] for t in oln),
            "y2": max(t["y2"] for t in oln),
            "y_centre": oy
          })

    canonical_rows_array.sort(key=lambda r: r["y_centre"])
    brace_regions_array = self.cell_resolver.B_resolveBraceRegions(braces_array, canonical_rows_array, data_cols, data_tokens)
    assigned_braced_ids = {id(t) for reg in brace_regions_array for t in reg["captured_tokens"]}

    num_rows = len(canonical_rows_array)
    grid_tokens = [[[] for _ in range(num_data_cols)] for _ in range(num_rows)]

    for i in range(len(data_tokens)):
      t = data_tokens[i]
      if id(t) in assigned_braced_ids or num_rows == 0:
        continue
      if any(abs(t["y_centre"] - qe["y_centre"]) <= 10 and qe["x1"] - 4 <= t["x1"] and t["x2"] <= qe["x2"] + 4 for qe in qualifier_events_array):
        continue
      if id(t) in snapped_orphan_row_map:
        r_idx = canonical_rows_array.index(snapped_orphan_row_map[id(t)])
      else:
        r_idx = int(np.argmin([abs(t["y_centre"] - r["y_centre"]) for r in canonical_rows_array]))
        if abs(t["y_centre"] - canonical_rows_array[r_idx]["y_centre"]) > row_tol + 8:
          continue
      c_idx = self.cell_resolver.assignTokenToColumnIndex(t, data_cols)
      if c_idx is not None:
        grid_tokens[r_idx][c_idx].append(t)

    underlined_cells_set = set()
    for i in range(len(underlines_array)):
      ul = underlines_array[i]
      above_r = [idx for idx in range(num_rows) if canonical_rows_array[idx]["y_centre"] < ul["y"] + 4 and ul["y"] - canonical_rows_array[idx]["y_centre"] <= 36]
      if not above_r:
        continue
      r_idx = above_r[-1]
      for x in range(num_data_cols):
        dc = data_cols[x]
        ov = min(ul["x2"], dc["x2"] + 15) - max(ul["x1"], dc["x1"] - 15)
        if ov >= 18 or (ul["x1"] <= dc["x_centre"] <= ul["x2"]):
          underlined_cells_set.add((r_idx, x))

    cell_matrix = [
      [
        self.cell_resolver.C_buildCellObject(
          data_cols[x],
          sorted(grid_tokens[i][x], key=lambda item: item["x1"]),
          canonical_rows_array[i]["row_label"],
          (i, x) in underlined_cells_set
        )
        for x in range(num_data_cols)
      ]
      for i in range(num_rows)
    ]

    brace_groups_summary_array = []
    for i in range(len(brace_regions_array)):
      reg = brace_regions_array[i]
      r0, r1 = reg["r_start"], reg["r_end"]
      if r0 < 0 or r1 >= num_rows or r1 < r0:
        continue
      grouped_row_labels = [canonical_rows_array[r]["row_label"] for r in range(r0, r1 + 1)]
      grouped_col_labels = [data_cols[c]["label"] for c in reg["col_indices"]]
      non_empty_reg_cols = [c for c in reg["col_indices"] if reg["col_tokens_map"].get(c)]
      spans_multi_cols = (len(reg["col_indices"]) >= 2 and len(non_empty_reg_cols) == 1)
      group_values_array = []

      for x in range(len(reg["col_indices"])):
        c_idx = reg["col_indices"][x]
        dc = data_cols[c_idx]
        col_toks = sorted(reg["col_tokens_map"].get(c_idx, []), key=lambda item: item["x1"])
        combined_cell = self.cell_resolver.C_buildCellObject(dc, col_toks, canonical_rows_array[r0]["row_label"], (r0, c_idx) in underlined_cells_set)
        combined_cell["row_span"] = r1 - r0 + 1
        combined_cell["grouped_rows"] = grouped_row_labels
        combined_cell["grouped_columns"] = grouped_col_labels if spans_multi_cols else [dc["label"]]
        combined_cell["col_span"] = len(grouped_col_labels) if spans_multi_cols else 1
        cell_matrix[r0][c_idx] = combined_cell
        group_values_array.append({
          "column": dc["label"],
          "footnotes": combined_cell["footnotes"],
          "numeric_value": combined_cell["numeric_value"],
          "raw_text": combined_cell["raw_text"]
        })

        for y in range(r0 + 1, r1 + 1):
          cell_matrix[y][c_idx] = {
            "col_index": dc["col_index"],
            "col_span": combined_cell["col_span"],
            "column": dc["label"],
            "estimated_bracketed": False,
            "footnotes": [],
            "grouped_columns": combined_cell["grouped_columns"],
            "grouped_rows": grouped_row_labels,
            "numeric_value": None,
            "qualifier": None,
            "raw_text": "",
            "row_span": 0,
            "series_break_underline": False,
            "spanned_from_row": canonical_rows_array[r0]["row_label"],
            "value_status": "spanned_by_brace"
          }

      if any(v["raw_text"] != "" for v in group_values_array):
        brace_groups_summary_array.append({
          "grouped_columns": grouped_col_labels,
          "grouped_rows": grouped_row_labels,
          "left_brace": reg["has_left_brace"],
          "right_brace": reg["has_right_brace"],
          "values": group_values_array
        })

    # Apply horizontal body column-span strokes (e.g. \underbrace combining Manufacturing + Construction)
    for i in range(len(col_spans_array)):
      sp = col_spans_array[i]
      spanned_cols = [x for x in range(num_data_cols) if (sp["x1"] - 18.0) <= data_cols[x]["x_centre"] <= (sp["x2"] + 18.0)]
      if len(spanned_cols) < 2 or num_rows == 0:
        continue
      cand_rows = [
        idx for idx in range(num_rows)
        if -14.0 <= (sp["y"] - canonical_rows_array[idx]["y_centre"]) <= 46.0
      ]
      for x in range(len(cand_rows)):
        r_idx = cand_rows[x]
        num_hits = [c for c in spanned_cols if cell_matrix[r_idx][c]["value_status"] == "numeric"]
        empty_hits = [c for c in spanned_cols if cell_matrix[r_idx][c]["value_status"] == "empty"]
        if len(num_hits) == 1 and len(num_hits) + len(empty_hits) == len(spanned_cols):
          hit_c = num_hits[0]
          cell_matrix[r_idx][hit_c]["grouped_columns"] = [data_cols[c]["label"] for c in spanned_cols]
          cell_matrix[r_idx][hit_c]["col_span"] = len(spanned_cols)

    active_col_qualifiers = [None for _ in range(num_data_cols)]
    active_subscope = None
    final_rows_array = []
    q_ptr = 0
    qualifier_events_array.sort(key=lambda q: q["y_centre"])
    row_place_banner = None

    for i in range(num_rows):
      r_meta = canonical_rows_array[i]
      for _ in range(q_ptr, len(qualifier_events_array)):
        if qualifier_events_array[q_ptr]["y_centre"] >= r_meta["y_centre"]:
          break
        qe = qualifier_events_array[q_ptr]
        matched_cols = [
          x for x in range(num_data_cols)
          if min(qe["x2"], data_cols[x]["x2"] + 30) - max(qe["x1"], data_cols[x]["x1"] - 30) >= 10
        ]
        if matched_cols and len(matched_cols) < max(2, num_data_cols - 1):
          for x in range(len(matched_cols)):
            active_col_qualifiers[matched_cols[x]] = qe["text"]
        else:
          sub_kind, norm_sub = self.isSubscopeBanner(qe["text"])
          if sub_kind == "reset":
            active_subscope = None
          elif sub_kind == "subscope":
            active_subscope = norm_sub
          else:
            clean_pb = re.sub(
              r"\s+(?:circa\s+)?(?:1[789]\d{2}|20[01]\d)\s*[-–—/]\s*[0-9cCoOlI]{1,4}[a-zA-Z]?\s*$",
              "",
              qe["text"],
              flags=re.IGNORECASE
            ).strip()
            if clean_pb:
              row_place_banner = clean_pb
              active_subscope = None
        q_ptr = q_ptr + 1

      row_cells = cell_matrix[i]
      lbl = r_meta["row_label"]
      non_empty_cells = [c for c in row_cells if c["raw_text"] != "" or c["value_status"] == "spanned_by_brace"]

      # Two-tier state for text-only stub/spanning rows: subscope ('Males', 'Females', 'Primary') vs country/entity banner
      is_text_banner_row = (
        (not non_empty_cells and lbl and not re.match(r"^\d{4}", lbl))
        or (non_empty_cells and all(c["value_status"] == "text" for c in non_empty_cells) and not re.match(r"^\d{4}", lbl))
      )
      if is_text_banner_row:
        banner_parts = ([lbl] if lbl else []) + [c["raw_text"] for c in non_empty_cells]
        banner_txt = re.sub(
          r"\s+(?:circa\s+)?(?:1[789]\d{2}|20[01]\d)\s*[-–—/]\s*[0-9cCoOlI]{1,4}[a-zA-Z]?\s*$",
          "",
          " ".join(banner_parts).strip(),
          flags=re.IGNORECASE
        ).strip()
        sub_kind, norm_sub = self.isSubscopeBanner(banner_txt)
        if sub_kind == "reset":
          active_subscope = None
        elif sub_kind == "subscope":
          active_subscope = norm_sub
        else:
          if row_place_banner and re.search(r"(?:\b(?:of|and|the)|[,&(\-])$", row_place_banner, re.IGNORECASE):
            row_place_banner = f"{row_place_banner} {banner_txt}".strip()
          else:
            row_place_banner = banner_txt
          active_subscope = None
        continue

      for x in range(num_data_cols):
        if active_col_qualifiers[x] and row_cells[x]["qualifier"] is None:
          row_cells[x]["qualifier"] = active_col_qualifiers[x]

      final_rows_array.append({
        "cells": row_cells,
        "qualifier": active_subscope if active_subscope else row_place_banner,
        "row_footnotes": r_meta["row_footnotes"],
        "row_index": len(final_rows_array),
        "row_label": lbl,
        "row_place_banner": row_place_banner,
        "series_continuation": r_meta["is_continuation"],
        "subscope": active_subscope
      })

    #Return statement
    return (final_rows_array, brace_groups_summary_array)


  def D_reconstructPageTables (self, arg1_page_info_obj, arg2_table_blocks_array, arg3_tokens_array):
    """
    @brief Step D: Reconstruct all sub-tables detected on a single page after masking full-page banner bounds.
    @param arg1_page_info_obj Dictionary with pdf_page, book_page, orientation, region_header and banner_bottom_y.
    @param arg2_table_blocks_array Detected graphical table blocks on the page.
    @param arg3_tokens_array Recognised OCR tokens on the page.
    @return List of structured sub-table dictionaries.
    """
    #Convert from parameters
    page_info_obj = arg1_page_info_obj if isinstance(arg1_page_info_obj, dict) else {}
    table_blocks_array = arg2_table_blocks_array if isinstance(arg2_table_blocks_array, list) else []
    tokens_array = arg3_tokens_array if isinstance(arg3_tokens_array, list) else []

    #Declare local instance variables
    banner_bot_y = float(page_info_obj.get("banner_bottom_y") or 0.0)
    reconstructed_array = []
    work_tokens_array = [t for t in tokens_array if t["y_centre"] > banner_bot_y] if banner_bot_y > 0.0 else tokens_array

    for i in range(len(table_blocks_array)):
      blk = table_blocks_array[i]
      prev_bot = banner_bot_y
      for x in range(i):
        other = table_blocks_array[x]
        ov = min(blk["x2"], other["x2"]) - max(blk["x1"], other["x1"])
        if ov > 40 and other["y_bot"] < blk["y_top"]:
          prev_bot = max(prev_bot, other["y_bot"])

      meta_obj = self.A_extractSubtableMetadata(blk, work_tokens_array, prev_bot)
      cols_array = self.B_inferColumns(blk, meta_obj["header_tokens"], meta_obj["body_tokens"])
      rows_array, brace_groups_array = self.C_reconstructRowsAndBraces(blk, cols_array, meta_obj["body_tokens"])

      if not rows_array and len(cols_array) <= 1:
        continue

      reconstructed_array.append({
        "above_phrases": meta_obj["above_phrases"],
        "bbox_px": [int(blk["x1"]), int(round(blk["y_top"])), int(blk["x2"]), int(round(blk["y_bot"]))],
        "book_page": page_info_obj.get("book_page"),
        "brace_groups": brace_groups_array,
        "columns": [
          {
            "col_index": c["col_index"],
            "header_footnotes": c["header_footnotes"],
            "header_path": c["header_path"],
            "label": c["label"],
            "role": c["role"],
            "x_centre": c.get("x_centre", 0.0)
          }
          for c in cols_array
        ],
        "orientation": page_info_obj.get("orientation", "portrait"),
        "pdf_page": page_info_obj.get("pdf_page"),
        "period_banner": meta_obj["period_banner"],
        "region_header": page_info_obj.get("region_header"),
        "rows": rows_array,
        "subtable_title": meta_obj["title"],
        "title_footnotes": meta_obj["title_footnotes"]
      })

    #Return statement
    return reconstructed_array


  def clusterColumnCentres (self, arg1_tokens_array):
    """
    @brief Discover horizontal data columns by 1D interval clustering of body cell tokens.
    @param arg1_tokens_array Body tokens located right of the stub column.
    @return Sorted list of column cluster dictionaries with x1, x2, x_centre and count.
    """
    #Convert from parameters
    tokens_array = arg1_tokens_array

    if not tokens_array:
      return []

    clusters_array = []
    min_gap = int(self.struct_cfg.get("col_cluster_gap_px", 18))
    sorted_toks = sorted(tokens_array, key=lambda t: t["x_centre"])

    for i in range(len(sorted_toks)):
      t = sorted_toks[i]
      best_c = None
      best_d = 1e9
      for x in range(len(clusters_array)):
        c = clusters_array[x]
        ov = min(t["x2"], c["x2"]) - max(t["x1"], c["x1"])
        dc = abs(t["x_centre"] - c["x_centre"])
        if ov >= 2 or dc <= 28:
          if dc < best_d:
            best_d = dc
            best_c = c
      if best_c is not None:
        n = best_c["count"]
        best_c["x_centre"] = (best_c["x_centre"]*n + t["x_centre"])/(n + 1)
        best_c["x1_list"].append(t["x1"])
        best_c["x2_list"].append(t["x2"])
        best_c["x1"] = float(np.percentile(best_c["x1_list"], 10))
        best_c["x2"] = float(np.percentile(best_c["x2_list"], 90))
        best_c["count"] = n + 1
      else:
        clusters_array.append({
          "count": 1,
          "x1": float(t["x1"]),
          "x1_list": [t["x1"]],
          "x2": float(t["x2"]),
          "x2_list": [t["x2"]],
          "x_centre": float(t["x_centre"])
        })

    max_cnt = max(c["count"] for c in clusters_array)
    min_keep = 2 if max_cnt >= 6 else 1
    filtered = sorted([c for c in clusters_array if c["count"] >= min_keep], key=lambda c: c["x_centre"])

    merged_cols = []
    for i in range(len(filtered)):
      c = filtered[i]
      if merged_cols and (c["x1"] - merged_cols[-1]["x2"]) < -6 and abs(c["x_centre"] - merged_cols[-1]["x_centre"]) < min_gap + 16:
        prev = merged_cols[-1]
        tot = prev["count"] + c["count"]
        prev["x_centre"] = (prev["x_centre"]*prev["count"] + c["x_centre"]*c["count"])/tot
        prev["x1"] = min(prev["x1"], c["x1"])
        prev["x2"] = max(prev["x2"], c["x2"])
        prev["count"] = tot
      else:
        merged_cols.append(c)

    #Return statement
    return merged_cols


  def clusterTokensIntoLines (self, arg1_tokens_array, arg2_y_tol_px):
    """
    @brief Group tokens sharing approximately the same vertical baseline centre into left-to-right sorted lines.
    @param arg1_tokens_array List of token dictionaries.
    @param arg2_y_tol_px Maximum vertical centre distance in pixels.
    @return List of token lists ordered top-to-bottom, each sorted left-to-right.
    """
    #Convert from parameters
    tokens_array = arg1_tokens_array
    y_tol = float(arg2_y_tol_px)

    if not tokens_array:
      return []

    lines_array = []
    sorted_by_y = sorted(tokens_array, key=lambda t: t["y_centre"])
    for i in range(len(sorted_by_y)):
      tok = sorted_by_y[i]
      placed = False
      for x in range(len(lines_array) - 1, -1, -1):
        ln_obj = lines_array[x]
        if abs(tok["y_centre"] - ln_obj["yc"]) <= y_tol:
          n = len(ln_obj["tokens"])
          ln_obj["yc"] = (ln_obj["yc"]*n + tok["y_centre"])/(n + 1)
          ln_obj["tokens"].append(tok)
          placed = True
          break
        if tok["y_centre"] - ln_obj["yc"] > y_tol*2.5:
          break
      if not placed:
        lines_array.append({"tokens": [tok], "yc": tok["y_centre"]})

    lines_array.sort(key=lambda item: item["yc"])

    #Return statement
    return [sorted(item["tokens"], key=lambda t: t["x1"]) for item in lines_array]


  def isPeriodBannerText (self, arg1_text_str):
    """
    @brief Check whether a header string is a date-range period banner (including clipped/OCR-noisy ends like '1846-20c').
    @param arg1_text_str Candidate phrase string.
    @return Boolean True if text is a historical date range banner.
    """
    #Convert from parameters
    txt = str(arg1_text_str or "").strip()

    #Return statement
    return bool(re.match(r"^(?:circa\s+)?(?:1[789]\d{2}|20[01]\d)\s*[-–—/]\s*[0-9cCoOlI]{1,4}[a-zA-Z]?$", txt, re.IGNORECASE))


  def isSubscopeBanner (self, arg1_banner_str):
    """
    @brief Classify an in-body text row as 'reset' ('Whole country'), 'subscope' ('Males', '1957 prices') or None (place banner).
    @param arg1_banner_str Candidate text-only row string.
    @return Tuple (classification_or_None, normalised_subscope_str).
    """
    #Convert from parameters
    txt = str(arg1_banner_str or "").strip()

    if not txt:
      return (None, None)

    clean = re.sub(r"[:.;,\s]+$", "", txt).strip()
    low = re.sub(r"\s+", " ", clean.lower())

    if low in self.whole_qualifiers_set:
      return ("reset", None)
    if low in self.subheaders_set:
      return ("subscope", clean)
    if re.match(r"^(?:at\s+)?(?:\d{4}(?:[,/\-\s]+\d{2,4})*\s+)?(?:current\s+|constant\s+|market\s+)?price[s]*$", low):
      norm_p = re.sub(r"pricess\b", "prices", clean, flags=re.IGNORECASE)
      return ("subscope", norm_p)
    if re.search(r"=\s*100\b", low):
      return ("subscope", clean)

    #Return statement
    return (None, None)


  def looksLikeSectionBanner (self, arg1_text_str):
    """
    @brief Check whether a line above top_rule is a page-wide section banner (including D1O/D2O OCR variants).
    @param arg1_text_str Joined line text.
    @return Boolean True if text matches a lettered-and-numbered section banner.
    """
    #Convert from parameters
    txt = str(arg1_text_str).strip()

    m = re.match(r"^([A-J1lI68])([0-9lIi|Oo]{1,2})[a-b]?\b\s+([A-Z][A-Za-z]+|\(continued\))", txt)
    if m:
      d_str = (
        m.group(2).replace("l", "1")
        .replace("I", "1")
        .replace("i", "1")
        .replace("|", "1")
        .replace("O", "0")
        .replace("o", "0")
      )
      if d_str.isdigit():
        d_val = int(d_str)
        if m.group(1) in ["1", "l", "I"] and d_val > 4:
          return False
        if 1 <= d_val <= 30:
          return True

    #Return statement
    return bool(re.search(r"\(continued\)", txt, re.IGNORECASE))
