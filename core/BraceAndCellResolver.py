"""@brief Curly-brace span resolver, cell token merger, and statistical numeric/footnote parser."""

import re


class BraceAndCellResolver:
  """@brief Resolves curly-brace ({ and }) row/column groupings and builds normalised cell objects."""

  def __init__ (self, arg1_config_obj):
    """
    @brief Initialise BraceAndCellResolver with structure and statistical symbol settings.
    @param arg1_config_obj Pipeline configuration dictionary loaded from /common/digitiser/.
    """
    #Convert from parameters
    config_obj = arg1_config_obj if isinstance(arg1_config_obj, dict) else {}

    #Declare local instance variables
    self.struct_cfg = config_obj.get("structure", {})
    self.sym_cfg = config_obj.get("symbols", {})


  def A_annotateBraceRowSpans (self, arg1_braces_array, arg2_rows_array):
    """
    @brief Step A: Map each detected curly brace onto the canonical row indices covered by [b.y1, b.y2].
    @param arg1_braces_array Detected brace dictionaries from GraphicalElementDetector.
    @param arg2_rows_array Canonical row dictionaries sorted ascending by y_centre.
    @return List of (brace_idx, brace_obj, r_start, r_end) tuples.
    """
    #Convert from parameters
    braces_array = arg1_braces_array if isinstance(arg1_braces_array, list) else []
    rows_array = arg2_rows_array if isinstance(arg2_rows_array, list) else []

    #Declare local instance variables
    annotated_array = []

    if not braces_array or not rows_array:
      return []

    for i in range(len(braces_array)):
      b = braces_array[i]
      covered = [
        idx for idx in range(len(rows_array))
        if (b["y1"] - 2.0) <= rows_array[idx]["y_centre"] <= (b["y2"] + 2.0)
      ]
      if len(covered) < 2:
        dists = sorted(range(len(rows_array)), key=lambda idx: abs(rows_array[idx]["y_centre"] - b["y_centre"]))
        covered = sorted(dists[:min(2, len(rows_array))])
      if covered:
        annotated_array.append((i, b, covered[0], covered[-1]))

    #Return statement
    return annotated_array


  def B_resolveBraceRegions (self, arg1_braces_array, arg2_rows_array, arg3_data_cols_array, arg4_data_tokens_array):
    """
    @brief Step B: Resolve paired (}...{) and unilateral (} or {) curly braces into spanned row/column regions.
    @param arg1_braces_array Detected brace dictionaries.
    @param arg2_rows_array Canonical row dictionaries sorted by y_centre.
    @param arg3_data_cols_array Data column descriptors.
    @param arg4_data_tokens_array Body tokens right of the stub column.
    @return List of non-empty resolved brace region dictionaries.
    """
    #Convert from parameters
    braces_array = arg1_braces_array
    rows_array = arg2_rows_array
    data_cols_array = arg3_data_cols_array
    data_tokens_array = arg4_data_tokens_array

    if not braces_array or not rows_array or not data_cols_array:
      return []

    #Declare local instance variables
    annotated_braces = self.A_annotateBraceRowSpans(braces_array, rows_array)
    num_cols = len(data_cols_array)
    regions_array = []
    used_brace_indices = set()

    # 1. Pair right-pointing '}' on left with matching left-pointing '{' on right
    for i in range(len(annotated_braces)):
      idx_l, b_l, r0_l, r1_l = annotated_braces[i]
      if idx_l in used_brace_indices or b_l["brace"] != "}":
        continue

      best_match = None
      for x in range(len(annotated_braces)):
        idx_r, b_r, r0_r, r1_r = annotated_braces[x]
        if idx_r in used_brace_indices or b_r["brace"] != "{":
          continue
        if b_r["x_centre"] <= b_l["x_centre"] + 25:
          continue
        same_span = (abs(r0_l - r0_r) <= 1 and abs(r1_l - r1_r) <= 1)
        fragment_inside = (r0_r >= r0_l - 1 and r1_r <= r1_l + 1 and (r1_l - r0_l) >= 3)
        if same_span or fragment_inside:
          cols_between = [
            c for c in range(num_cols)
            if b_l["x_centre"] < data_cols_array[c]["x_centre"] < b_r["x_centre"]
          ]
          if 1 <= len(cols_between) <= 4:
            if best_match is None or b_r["x_centre"] < best_match[1]["x_centre"]:
              best_match = (idx_r, b_r, cols_between)

      if best_match is not None:
        idx_r, b_r, cols_between = best_match
        used_brace_indices.add(idx_l)
        used_brace_indices.add(idx_r)
        for x in range(len(annotated_braces)):
          idx_sub, b_sub, r0_s, r1_s = annotated_braces[x]
          if b_sub["brace"] == "{" and abs(b_sub["x_centre"] - b_r["x_centre"]) <= 22 and r0_s >= r0_l - 1 and r1_s <= r1_l + 1:
            used_brace_indices.add(idx_sub)

        reg = self.collectRegionTokens(
          r0_l, r1_l, cols_between, True, True, rows_array, data_cols_array, data_tokens_array,
          min(b_l["y1"], b_r["y1"]), max(b_l["y2"], b_r["y2"])
        )
        if reg["captured_tokens"]:
          regions_array.append(reg)

    # 2. Resolve unpaired '}' or '{'
    for i in range(len(annotated_braces)):
      idx_b, b, r0, r1 = annotated_braces[i]
      if idx_b in used_brace_indices:
        continue

      if b["brace"] == "}":
        right_cols = [c for c in range(num_cols) if data_cols_array[c]["x_centre"] > b["x_centre"]]
        if not right_cols:
          continue
        first_c = right_cols[0]
        first_parent = data_cols_array[first_c]["header_path"][0] if len(data_cols_array[first_c]["header_path"]) > 1 else None
        target_cols = []
        for x in range(len(right_cols)):
          c = right_cols[x]
          if any(
            ob["x_centre"] > b["x_centre"] + 15
            and ob["x_centre"] < data_cols_array[c]["x_centre"]
            and not (ob["y2"] < b["y1"] or ob["y1"] > b["y2"])
            for _, ob, _, _ in annotated_braces
          ):
            break
          c_parent = data_cols_array[c]["header_path"][0] if len(data_cols_array[c]["header_path"]) > 1 else None
          if (c == first_c or (first_parent and c_parent == first_parent)) and (rows_array[r1]["y2"] - rows_array[r0]["y1"]) <= b["h"]*2.2:
            target_cols.append(c)
          elif self.columnHasSingleCombinedValue(c, r0, r1, rows_array, data_cols_array, data_tokens_array):
            target_cols.append(c)
          else:
            break

        if target_cols:
          used_brace_indices.add(idx_b)
          reg = self.collectRegionTokens(
            r0, r1, target_cols, True, False, rows_array, data_cols_array, data_tokens_array, b["y1"], b["y2"]
          )
          if reg["captured_tokens"]:
            regions_array.append(reg)
      else:
        left_cols = [c for c in range(num_cols) if data_cols_array[c]["x_centre"] < b["x_centre"]]
        if not left_cols:
          continue
        last_c = left_cols[-1]
        last_parent = data_cols_array[last_c]["header_path"][0] if len(data_cols_array[last_c]["header_path"]) > 1 else None
        target_cols = [last_c]
        if len(left_cols) >= 2 and last_parent:
          prev_c = left_cols[-2]
          prev_parent = data_cols_array[prev_c]["header_path"][0] if len(data_cols_array[prev_c]["header_path"]) > 1 else None
          if prev_parent == last_parent:
            target_cols = [prev_c, last_c]
        if all(self.columnHasSingleCombinedValue(c, r0, r1, rows_array, data_cols_array, data_tokens_array) for c in target_cols):
          used_brace_indices.add(idx_b)
          reg = self.collectRegionTokens(
            r0, r1, target_cols, False, True, rows_array, data_cols_array, data_tokens_array, b["y1"], b["y2"]
          )
          if reg["captured_tokens"]:
            regions_array.append(reg)

    #Return statement
    return regions_array


  def C_buildCellObject (self, arg1_col_obj, arg2_tokens_array, arg3_row_label, arg4_is_underlined):
    """
    @brief Step C: Construct a normalised cell dictionary from the token(s) inside a (row, column) slot.
    @param arg1_col_obj Data column descriptor.
    @param arg2_tokens_array Left-to-right sorted tokens inside the cell.
    @param arg3_row_label Canonical label of the row.
    @param arg4_is_underlined Boolean flag indicating a detected series-break underline beneath the cell.
    @return Structured cell dictionary with raw_text, numeric_value, value_status, footnotes, and span fields.
    """
    #Convert from parameters
    dc = arg1_col_obj
    tokens_array = arg2_tokens_array
    row_label = arg3_row_label
    is_underlined = bool(arg4_is_underlined)

    #Declare local instance variables
    estimated_bracketed = False
    footnotes_array = []
    num_val = None
    raw_text = ""
    value_status = "empty"

    if tokens_array:
      value_toks = []
      for i in range(len(tokens_array)):
        t = tokens_array[i]
        ttxt = t["text"].strip()
        if re.match(r"^['`‘’]\d{2}$", ttxt) or ttxt == "*":
          norm_fn = ("'" + ttxt[-2:]) if len(ttxt) >= 3 else ttxt
          if norm_fn not in footnotes_array:
            footnotes_array.append(norm_fn)
        else:
          value_toks.append(t)

      # If inside a cell/brace both a real digit token and a noisy ellipsis/leader-dot token exist, keep the real digit token
      if len(value_toks) >= 2 and any(any(ch.isdigit() for ch in vt["text"]) for vt in value_toks):
        value_toks = [
          vt for vt in value_toks
          if not self.isSymbolicMissingToken(vt["text"], vt.get("symbol_kind"))
          and not (not any(ch.isdigit() for ch in vt["text"]) and vt.get("w", 99) <= 15 and vt.get("h", 99) <= 15 and len(vt["text"].strip(".,- ")) <= 1)
        ]

      if value_toks:
        merged = self.mergeCellTokens(value_toks)
        raw_text = merged["text"]
        for i in range(len(merged["footnotes"])):
          if merged["footnotes"][i] not in footnotes_array:
            footnotes_array.append(merged["footnotes"][i])

        sym_status = self.classifySymbolicString(raw_text, value_toks)
        if sym_status == "not_available":
          raw_text = "..."
          value_status = "not_available"
        elif sym_status == "less_than_half_unit":
          raw_text = "--"
          value_status = "less_than_half_unit"
        elif sym_status == "nil":
          raw_text = "—"
          value_status = "nil"
        else:
          num_val, clean_disp, estimated_bracketed, extra_fn = self.parseNumericToken(raw_text)
          if clean_disp:
            raw_text = clean_disp
          for i in range(len(extra_fn)):
            if extra_fn[i] not in footnotes_array:
              footnotes_array.append(extra_fn[i])
          value_status = "numeric" if num_val is not None else "text"

    #Return statement
    return {
      "col_index": dc["col_index"],
      "col_span": 1,
      "column": dc["label"],
      "estimated_bracketed": estimated_bracketed,
      "footnotes": footnotes_array,
      "grouped_columns": [dc["label"]],
      "grouped_rows": [row_label],
      "numeric_value": num_val,
      "qualifier": None,
      "raw_text": raw_text,
      "row_span": 1,
      "series_break_underline": is_underlined,
      "value_status": value_status
    }


  def assignTokenToColumnIndex (self, arg1_token_obj, arg2_data_cols_array):
    """
    @brief Map a body token to the closest data column index (0-based into data_cols_array).
    @param arg1_token_obj Single OCR token dictionary.
    @param arg2_data_cols_array List of data column descriptors.
    @return Integer index into data_cols_array or None if beyond maximum assignment distance.
    """
    #Convert from parameters
    tok = arg1_token_obj
    data_cols_array = arg2_data_cols_array

    if not data_cols_array:
      return None

    #Declare local instance variables
    best_idx = 0
    best_dist = 1e9
    max_dist = float(self.struct_cfg.get("col_assign_max_dist_px", 85))

    for i in range(len(data_cols_array)):
      dc = data_cols_array[i]
      if dc["x1"] - 10 <= tok["x_centre"] <= dc["x2"] + 10:
        dist = abs(tok["x_centre"] - dc["x_centre"])*0.5
      else:
        dist = abs(tok["x_centre"] - dc["x_centre"])
      if dist < best_dist:
        best_dist = dist
        best_idx = i

    #Return statement
    return best_idx if best_dist <= max_dist else None


  def classifySymbolicString (self, arg1_raw_str, arg2_toks_array):
    """
    @brief Identify statistical missing/nil/sub-unit symbols including minor scanner-smudged ellipsis/dash variants.
    @param arg1_raw_str Merged cell text.
    @param arg2_toks_array Underlying token dictionaries.
    @return Symbol status ('not_available', 'less_than_half_unit', 'nil') or None.
    """
    #Convert from parameters
    raw_str = str(arg1_raw_str).strip()
    toks_array = arg2_toks_array

    if any(ch.isdigit() for ch in raw_str):
      return None

    if raw_str in self.sym_cfg.get("not_available", ["...", "…", ". . .", "..", "...."]) or all(t.get("symbol_kind") == "not_available" for t in toks_array):
      return "not_available"
    if raw_str.count(".") >= 2 and re.match(r"^[.…\-eao·,\s]{2,8}$", raw_str):
      return "not_available"

    if raw_str in self.sym_cfg.get("less_than_half_unit", ["--", "- -", "- - -", "---"]) or all(t.get("symbol_kind") == "less_than_half_unit" for t in toks_array):
      return "less_than_half_unit"
    if raw_str.count("-") >= 2 and re.match(r"^[\-–eao.,\s]{2,7}$", raw_str):
      return "less_than_half_unit"
    if raw_str.count("-") >= 1 and re.match(r"^[\-–eao.,\s]{2,7}$", raw_str) and all(t.get("h", 99) <= 14 for t in toks_array):
      return "less_than_half_unit"

    if raw_str in ["—", "–", "-"] or (len(toks_array) == 1 and toks_array[0].get("symbol_kind") == "nil"):
      return "nil"

    #Return statement
    return None


  def collectRegionTokens (self, arg1_r0, arg2_r1, arg3_col_indices, arg4_has_left, arg5_has_right, arg6_rows_array, arg7_data_cols_array, arg8_data_tokens_array, arg9_brace_y1=None, arg10_brace_y2=None):
    """
    @brief Gather tokens lying inside a braced (row_span x col_set) region, including vertically centred off-grid values.
    @param arg1_r0 Start row index.
    @param arg2_r1 End row index.
    @param arg3_col_indices Target indices into data_cols_array.
    @param arg4_has_left Whether bounded by a left '}' brace.
    @param arg5_has_right Whether bounded by a right '{' brace.
    @param arg6_rows_array Canonical rows list.
    @param arg7_data_cols_array Data columns list.
    @param arg8_data_tokens_array Body data tokens list.
    @param arg9_brace_y1 Optional top y bound of the brace stroke(s).
    @param arg10_brace_y2 Optional bottom y bound of the brace stroke(s).
    @return Resolved brace region dictionary.
    """
    #Convert from parameters
    r0 = int(arg1_r0)
    r1 = int(arg2_r1)
    col_indices = arg3_col_indices
    has_left = bool(arg4_has_left)
    has_right = bool(arg5_has_right)
    rows_array = arg6_rows_array
    data_cols_array = arg7_data_cols_array
    data_tokens_array = arg8_data_tokens_array
    brace_y1 = arg9_brace_y1
    brace_y2 = arg10_brace_y2

    #Declare local instance variables
    captured_tokens_array = []
    col_set = set(col_indices)
    col_tokens_map = {c: [] for c in col_indices}
    y_min = rows_array[r0]["y1"] - 3.0
    y_max = rows_array[r1]["y2"] + 3.0
    if brace_y1 is not None and brace_y2 is not None:
      y_min = max(y_min, float(brace_y1) - 24.0)
      y_max = min(y_max, float(brace_y2) + 24.0)

    for i in range(len(data_tokens_array)):
      t = data_tokens_array[i]
      if y_min <= t["y_centre"] <= y_max:
        c_idx = self.assignTokenToColumnIndex(t, data_cols_array)
        if c_idx in col_set:
          col_tokens_map[c_idx].append(t)
          captured_tokens_array.append(t)

    #Return statement
    return {
      "captured_tokens": captured_tokens_array,
      "col_indices": col_indices,
      "col_tokens_map": col_tokens_map,
      "has_left_brace": has_left,
      "has_right_brace": has_right,
      "r_end": r1,
      "r_start": r0
    }


  def columnHasSingleCombinedValue (self, arg1_col_idx, arg2_r0, arg3_r1, arg4_rows_array, arg5_data_cols_array, arg6_data_tokens_array):
    """
    @brief Check if column arg1_col_idx has exactly 1 line of numeric/symbol content across rows [r0..r1].
    @param arg1_col_idx Index into data_cols_array.
    @param arg2_r0 Start row index.
    @param arg3_r1 End row index.
    @param arg4_rows_array Canonical rows list.
    @param arg5_data_cols_array Data columns list.
    @param arg6_data_tokens_array Body data tokens list.
    @return Boolean True if column exhibits a single combined off-grid/spanned value across [r0..r1].
    """
    #Convert from parameters
    col_idx = int(arg1_col_idx)
    r0 = int(arg2_r0)
    r1 = int(arg3_r1)
    rows_array = arg4_rows_array
    data_cols_array = arg5_data_cols_array
    data_tokens_array = arg6_data_tokens_array

    y_min = rows_array[r0]["y1"] - 3.0
    y_max = rows_array[r1]["y2"] + 3.0
    toks = [
      t for t in data_tokens_array
      if y_min <= t["y_centre"] <= y_max and self.assignTokenToColumnIndex(t, data_cols_array) == col_idx
    ]
    if not toks:
      return False

    toks.sort(key=lambda item: item["y_centre"])
    distinct_lines = 1
    for i in range(1, len(toks)):
      if abs(toks[i]["y_centre"] - toks[i - 1]["y_centre"]) > 16.0:
        distinct_lines = distinct_lines + 1

    #Return statement
    return distinct_lines == 1 and (r1 - r0 + 1) >= 2


  def isSymbolicMissingToken (self, arg1_txt_str, arg2_sym_kind):
    """
    @brief Check whether a token inside a cell represents an ellipsis or dash symbol rather than data text.
    @param arg1_txt_str Recognised token string.
    @param arg2_sym_kind Geometric symbol_kind string or None.
    @return Boolean True if symbolic missing/nil/sub-unit token.
    """
    #Convert from parameters
    txt = str(arg1_txt_str).strip()
    sym_kind = arg2_sym_kind

    if sym_kind in ["not_available", "less_than_half_unit", "nil"]:
      return True
    if not any(ch.isdigit() for ch in txt) and (txt.count(".") >= 2 or txt.count("-") >= 2 or txt in ["—", "–"]):
      return True

    #Return statement
    return False


  def mergeCellTokens (self, arg1_tokens_array):
    """
    @brief Join tokens inside a single data cell, healing kerning gaps inside numbers (e.g. '28,1' + '12' -> '28,112').
    @param arg1_tokens_array Left-to-right sorted tokens inside one cell.
    @return Dictionary with merged text and combined footnotes list.
    """
    #Convert from parameters
    tokens_array = arg1_tokens_array

    #Declare local instance variables
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
        prev_tok = tokens_array[i - 1]
        prev_txt = parts_array[-1]
        gap = t["x1"] - prev_tok["x2"]
        is_detached_script = (
          prev_txt[-1:].isdigit()
          and txt.isdigit()
          and len(txt) <= 2
          and t.get("h", 99) <= 0.78*prev_tok.get("h", 24)
          and (t.get("y2", 0) <= prev_tok.get("y2", 0) - 4.0 or t.get("y1", 0) >= prev_tok.get("y1", 0) + 4.0)
        )
        if is_detached_script:
          if txt not in footnotes_array:
            footnotes_array.append(txt)
          continue
        same_line = abs(t.get("y_centre", 0.0) - prev_tok.get("y_centre", 0.0)) <= 15.0
        if same_line and -6.0 <= gap <= 24.0 and (
          prev_txt.endswith((",", ".", "[", "+", "-"))
          or txt.startswith((",", ".", "]"))
          or (prev_txt[-1:].isdigit() and txt[:1].isdigit())
        ):
          parts_array[-1] = prev_txt + txt
        else:
          parts_array.append(txt)

    #Return statement
    return {
      "footnotes": footnotes_array,
      "text": " ".join(parts_array).strip()
    }


  def parseNumericToken (self, arg1_raw_str):
    """
    @brief Parse a statistical string into an int/float value, clean display string, bracketed flag, and extra footnotes.
    @param arg1_raw_str Raw string inside a table cell (e.g. '1,064', '[3,691]', "46'85", '-48.2').
    @return Tuple (numeric_value_or_None, clean_display_str_or_None, is_bracketed_bool, extra_footnotes_list).
    """
    #Convert from parameters
    raw_str = str(arg1_raw_str).strip()

    #Declare local instance variables
    extra_fn = []
    is_bracketed = False
    work = raw_str

    if not work:
      return (None, None, False, [])

    if work.startswith("[") and work.endswith("]"):
      is_bracketed = True
      work = work[1:-1].strip()
    elif work.startswith("[") and "]" in work:
      idx = work.index("]")
      tail = work[idx + 1:].strip()
      work = work[1:idx].strip()
      is_bracketed = True
      if tail:
        extra_fn.append(tail)

    work = re.sub(r",\s+", ",", work)
    work = re.sub(r"\s+,", ",", work)
    if re.match(r"^[+\-]?\d{1,3}(?:\s\d{3})+(?:\.\d+)?$", work):
      work = work.replace(" ", "")

    # Separate italic census-year suffix attached via apostrophe (e.g. "46'85" -> 46 + "'85")
    apos_m = re.match(r"^([+\-]?\d[\d,]*(?:\.\d+)?)['`‘’](\d{2})$", work)
    if apos_m:
      work = apos_m.group(1)
      extra_fn.append("'" + apos_m.group(2))

    # Separate asterisk suffix (e.g. "809*" -> 809 + "*")
    if work.endswith("*") and len(work) >= 2:
      work = work[:-1]
      extra_fn.append("*")

    disp = f"[{work}]" if is_bracketed else work

    if re.match(r"^[+\-]?\d{1,3}(?:,\d{3})+(?:\.\d+)?$", work):
      clean_num = work.replace(",", "")
      val = float(clean_num) if "." in clean_num else int(clean_num)
      if abs(val) <= 10**15:
        return (val, disp, is_bracketed, extra_fn)
      return (None, None, is_bracketed, extra_fn)

    if re.match(r"^[+\-]?\d+(?:\.\d+)?$", work):
      val = float(work) if "." in work else int(work)
      if abs(val) <= 10**15:
        return (val, disp, is_bracketed, extra_fn)
      return (None, None, is_bracketed, extra_fn)

    #Return statement
    return (None, None, is_bracketed, extra_fn)


  def stripAttachedTitleFootnotes (self, arg1_text_str):
    """
    @brief Separate unsplit footnote digits attached to years ('199069') or names ('Australia86', 'New Zealand1,87').
    @param arg1_text_str Raw title, header, or stub label string.
    @return Tuple (clean_label_str, extracted_footnotes_list).
    """
    #Convert from parameters
    txt = str(arg1_text_str).strip()

    if not txt:
      return ("", [])

    slash_m = re.match(r"^((?:17|18|19|20)(\d{2}))/(\d{2,4})$", txt)
    if slash_m:
      full_yr = slash_m.group(1)
      yy = int(slash_m.group(2))
      rhs = slash_m.group(3)
      if len(rhs) == 2:
        r2 = int(rhs)
        valid_two_digit = (yy < r2 <= yy + 15) or (yy >= 90 and r2 <= 10)
        if not valid_two_digit:
          d1 = int(rhs[0])
          if (yy%10) < d1 <= (yy%10) + 5 or (yy%10 == 9 and d1 == 0):
            return (f"{full_yr}/{rhs[0]}", [rhs[1:]])
      elif len(rhs) == 3 or (len(rhs) == 4 and not (1700 <= int(rhs) <= 2025)):
        return (f"{full_yr}/{rhs[0]}", [rhs[1:]])

    yr_m = re.match(r"^((?:17|18|19|20)\d{2}(?:/\d{1,2})?)(\d{1,2}(?:,\d{1,2})*)$", txt)
    if yr_m:
      base_yr = yr_m.group(1)
      fns_array = [p for p in yr_m.group(2).split(",") if p]
      return (base_yr, fns_array)

    nm_m = re.match(r"^([A-Za-z][A-Za-z\s.&()/\-–]*?[A-Za-z.)])['`‘’]?(\d{1,2}(?:,\d{1,2})*)$", txt)
    if nm_m:
      base_nm = nm_m.group(1).strip()
      fns_array = [p for p in nm_m.group(2).split(",") if p]
      return (base_nm, fns_array)

    sc_m = re.match(r"^([A-Z])['`‘’]?(\d{1,2}(?:,\d{1,2})*)$", txt)
    if sc_m:
      return (sc_m.group(1), [p for p in sc_m.group(2).split(",") if p])

    nm_apos = re.match(r"^([A-Za-z][A-Za-z\s.&()/\-–]*?[A-Za-z.)])',\s*(\d{1,2})$", txt)
    if nm_apos:
      return (nm_apos.group(1).strip(), ["1", nm_apos.group(2)])

    #Return statement
    return (txt, [])
