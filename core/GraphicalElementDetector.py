"""@brief Computer vision detector for booktabs rules, cmidrules, series-break underlines and curly braces."""

import sys
import cv2
import numpy as np


class GraphicalElementDetector:
  """@brief Extracts graphical layout primitives (rules, sub-table blocks, underlines and braces) from binary masks."""

  def __init__ (self, arg1_config_obj):
    """
    @brief Initialise GraphicalElementDetector with configured morphological and geometric thresholds.
    @param arg1_config_obj Pipeline configuration dictionary loaded from /common/digitiser/.
    """
    #Convert from parameters
    config_obj = arg1_config_obj if isinstance(arg1_config_obj, dict) else {}

    #Declare local instance variables
    self.gfx_cfg = config_obj.get("graphical_elements", {})


  def A_detectHorizontalStrokes (self, arg1_bw_mask):
    """
    @brief Step A: Detect horizontal line segments and merge collinear fragments broken by faint ink.
    @param arg1_bw_mask Deskewed binary foreground mask (255 = ink).
    @return Sorted list of stroke dictionaries with x1, x2, y, w, h, y1 and y2.
    """
    #Convert from parameters
    bw_mask = arg1_bw_mask

    #Declare local instance variables
    merge_x_gap = int(self.gfx_cfg.get("rule_merge_x_gap_px", 36))
    merge_y_tol = int(self.gfx_cfg.get("rule_merge_y_tol_px", 9))
    min_stroke_w = int(self.gfx_cfg.get("underline_min_width_px", 34))
    merged_array = []
    raw_strokes_array = []

    if bw_mask is None:
      sys.stderr.write("Console error: null binary mask in A_detectHorizontalStrokes.\n")
      return []

    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (min_stroke_w, 1))
    h_mask = cv2.morphologyEx(bw_mask, cv2.MORPH_OPEN, h_kernel)
    num_cc, _, stats, _ = cv2.connectedComponentsWithStats(h_mask)

    for i in range(1, num_cc):
      local_x = int(stats[i, cv2.CC_STAT_LEFT])
      local_y = int(stats[i, cv2.CC_STAT_TOP])
      local_w = int(stats[i, cv2.CC_STAT_WIDTH])
      local_h = int(stats[i, cv2.CC_STAT_HEIGHT])
      if local_w >= min_stroke_w and local_h <= 18:
        raw_strokes_array.append({
          "h": local_h,
          "w": local_w,
          "x1": local_x,
          "x2": local_x + local_w,
          "y": local_y + 0.5*local_h,
          "y1": local_y,
          "y2": local_y + local_h
        })

    raw_strokes_array.sort(key=lambda item: (item["y"], item["x1"]))
    for i in range(len(raw_strokes_array)):
      cur = raw_strokes_array[i]
      did_merge = False
      for x in range(len(merged_array) - 1, -1, -1):
        prev = merged_array[x]
        if abs(cur["y"] - prev["y"]) > merge_y_tol:
          if cur["y"] - prev["y"] > merge_y_tol*3:
            break
          continue
        if cur["x1"] <= prev["x2"] + merge_x_gap and cur["x2"] >= prev["x1"] - merge_x_gap:
          new_x1 = min(prev["x1"], cur["x1"])
          new_x2 = max(prev["x2"], cur["x2"])
          new_y1 = min(prev["y1"], cur["y1"])
          new_y2 = max(prev["y2"], cur["y2"])
          total_w = prev["w"] + cur["w"]
          prev["y"] = (prev["y"]*prev["w"] + cur["y"]*cur["w"])/max(1, total_w)
          prev["x1"] = new_x1
          prev["x2"] = new_x2
          prev["w"] = new_x2 - new_x1
          prev["y1"] = new_y1
          prev["y2"] = new_y2
          prev["h"] = new_y2 - new_y1
          did_merge = True
          break
      if not did_merge:
        merged_array.append(dict(cur))

    merged_array.sort(key=lambda item: (item["y"], item["x1"]))

    #Return statement
    return merged_array


  def B_segmentTableBlocks (self, arg1_strokes_array, arg2_bw_mask):
    """
    @brief Step B: Group major horizontal rules into column-aligned sub-table blocks (top, mid, bottom).
    @param arg1_strokes_array Detected horizontal strokes from Step A.
    @param arg2_bw_mask Deskewed binary foreground mask.
    @return List of sub-table block dictionaries sorted in reading order (panel x, then vertical y).
    """
    #Convert from parameters
    strokes_array = arg1_strokes_array if isinstance(arg1_strokes_array, list) else []
    bw_mask = arg2_bw_mask

    #Declare local instance variables
    align_tol = int(self.gfx_cfg.get("stack_x_align_tol_px", 42))
    cmid_max_ratio = float(self.gfx_cfg.get("header_cmidrule_max_width_ratio", 0.92))
    header_max_h = int(self.gfx_cfg.get("header_max_height_px", 420))
    major_min_w = int(self.gfx_cfg.get("major_rule_min_width_px", 240))
    major_rules_array = [s for s in strokes_array if s["w"] >= major_min_w]
    stacks_array = []
    table_blocks_array = []

    if not major_rules_array or bw_mask is None:
      return []

    for i in range(len(major_rules_array)):
      rule = major_rules_array[i]
      best_stack = None
      best_score = 1e9
      for x in range(len(stacks_array)):
        st = stacks_array[x]
        dx1 = abs(rule["x1"] - st["x1"])
        dx2 = abs(rule["x2"] - st["x2"])
        ov_x1 = max(rule["x1"], st["x1"])
        ov_x2 = min(rule["x2"], st["x2"])
        ov_w = max(0, ov_x2 - ov_x1)
        max_w = max(1, max(rule["w"], st["x2"] - st["x1"]))
        ov_ratio = ov_w/max_w

        if (dx1 <= align_tol and dx2 <= align_tol) or ov_ratio >= 0.86:
          score = dx1 + dx2
          if score < best_score:
            best_score = score
            best_stack = st

      if best_stack is not None:
        best_stack["rules"].append(rule)
        best_stack["x1"] = min(best_stack["x1"], rule["x1"])
        best_stack["x2"] = max(best_stack["x2"], rule["x2"])
      else:
        stacks_array.append({
          "rules": [rule],
          "x1": rule["x1"],
          "x2": rule["x2"]
        })

    for i in range(len(stacks_array)):
      st = stacks_array[i]
      raw_rules = sorted(st["rules"], key=lambda r: r["y"])
      if len(raw_rules) < 2:
        continue

      # Reclassify spanning header sub-rules narrower than cmid_max_ratio * stack_w (or skipping stub col) so they become cmidrules
      stack_w = max(1, st["x2"] - st["x1"])
      full_rules = [
        r for r in raw_rules
        if r["w"] >= cmid_max_ratio*stack_w and r["x1"] <= st["x1"] + align_tol + 18
      ]
      rules = full_rules if len(full_rules) >= 2 else raw_rules
      rules = self.synthesiseSteppedBottomRules(rules, strokes_array, st["x1"], st["x2"], align_tol)

      groups_array = self.splitRuleStackIntoTables(rules, st["x1"], st["x2"], bw_mask)
      for x in range(len(groups_array)):
        grp = groups_array[x]
        if len(grp) < 2:
          continue
        top_r = grp[0]
        bot_r = grp[-1]
        if bot_r["y"] - top_r["y"] < 42:
          continue

        next_grp_y1 = int(groups_array[x + 1][0]["y1"]) - 10 if x + 1 < len(groups_array) else bw_mask.shape[0] - 10
        internal_rules = []
        mid_r = top_r

        # Probe below bot_r only at page bottom (no table-width major rule lower on the page overlapping horizontally)
        has_lower_major = any(
          mr["y"] > bot_r["y"] + 18.0
          and mr["w"] >= 0.72*stack_w
          and (min(mr["x2"], st["x2"]) - max(mr["x1"], st["x1"])) >= 0.50*stack_w
          for mr in major_rules_array
        )
        can_probe_missing_bot = (
          x == len(groups_array) - 1
          and not has_lower_major
          and (bot_r["y"] - top_r["y"]) <= header_max_h
          and (len(grp) == 2 or (bot_r["y"] - grp[-2]["y"]) <= 88)
        )
        inferred_bot_r = None
        if can_probe_missing_bot:
          inferred_bot_r = self.probeBodyBelowMissingBottomRule(bw_mask, st["x1"], st["x2"], bot_r, next_grp_y1)

        if inferred_bot_r is not None:
          mid_r = bot_r
          bot_r = inferred_bot_r
          internal_rules = []
        elif len(grp) == 2:
          mid_r = top_r
          internal_rules = []
        else:
          mid_idx = 1
          if grp[1]["y"] - top_r["y"] > header_max_h:
            mid_r = top_r
            internal_rules = grp[1:-1]
          else:
            for y in range(2, len(grp) - 1):
              if (grp[y]["y"] - top_r["y"]) <= header_max_h and (bot_r["y"] - grp[y]["y"]) >= 65:
                by0 = int(grp[y - 1]["y2"]) + 3
                by1 = int(grp[y]["y1"]) - 3
                if by1 > by0 + 8:
                  mid_band = bw_mask[by0:by1, int(st["x1"] + 0.30*stack_w):int(st["x1"] + 0.78*stack_w)]
                  if float(np.count_nonzero(mid_band))/max(1, mid_band.size) >= 0.002:
                    mid_idx = y
            mid_r = grp[mid_idx]
            internal_rules = grp[mid_idx + 1:-1]

        table_blocks_array.append({
          "all_major_rules": grp,
          "cmidrules": [],
          "col_spans": [],
          "internal_rules": internal_rules,
          "underlines": [],
          "x1": int(min(r["x1"] for r in grp)),
          "x2": int(max(r["x2"] for r in grp)),
          "y_bot": float(bot_r["y"]),
          "y_mid": float(mid_r["y"]),
          "y_top": float(top_r["y"])
        })

    table_blocks_array = self.filterNestedTableBlocks(table_blocks_array)
    table_blocks_array = self.sortBlocksReadingOrder(table_blocks_array)

    #Return statement
    return table_blocks_array


  def C_assignSubRulesAndUnderlines (self, arg1_strokes_array, arg2_table_blocks_array, arg3_bw_mask):
    """
    @brief Step C: Classify non-major horizontal strokes into header cmidrules, body column spans and underlines.
    @param arg1_strokes_array All detected horizontal strokes from Step A.
    @param arg2_table_blocks_array Sub-table blocks from Step B.
    @param arg3_bw_mask Deskewed binary foreground mask.
    @return Updated table_blocks_array with cmidrules, col_spans and underlines populated, plus erase_boxes.
    """
    #Convert from parameters
    strokes_array = arg1_strokes_array if isinstance(arg1_strokes_array, list) else []
    table_blocks_array = arg2_table_blocks_array if isinstance(arg2_table_blocks_array, list) else []
    bw_mask = arg3_bw_mask

    #Declare local instance variables
    cmid_min_w = int(self.gfx_cfg.get("cmidrule_min_width_px", 75))
    erase_boxes_array = []
    ink_lookback = int(self.gfx_cfg.get("underline_ink_above_lookback_px", 34))
    min_ink_ratio = float(self.gfx_cfg.get("underline_min_ink_above_ratio", 0.06))
    ul_max_h = int(self.gfx_cfg.get("underline_max_height_px", 10))
    ul_max_w = int(self.gfx_cfg.get("underline_max_width_px", 220))
    ul_min_w = int(self.gfx_cfg.get("underline_min_width_px", 34))
    used_major_ids = set()

    for i in range(len(table_blocks_array)):
      blk = table_blocks_array[i]
      blk.setdefault("col_spans", [])
      for x in range(len(blk["all_major_rules"])):
        mr = blk["all_major_rules"][x]
        if mr.get("extra_erase"):
          for y in range(len(mr["extra_erase"])):
            er = mr["extra_erase"][y]
            used_major_ids.add((er["x1"], er["x2"], round(er["y"], 1)))
            erase_boxes_array.append((er["x1"], max(0, er["y1"] - 2), er["x2"], er["y2"] + 2))
        else:
          used_major_ids.add((mr["x1"], mr["x2"], round(mr["y"], 1)))
          erase_boxes_array.append((mr["x1"], max(0, mr["y1"] - 2), mr["x2"], mr["y2"] + 2))
      for x in range(len(blk["internal_rules"])):
        ir = blk["internal_rules"][x]
        blk["underlines"].append(ir)

    for i in range(len(strokes_array)):
      st = strokes_array[i]
      key = (st["x1"], st["x2"], round(st["y"], 1))
      if key in used_major_ids:
        continue

      for x in range(len(table_blocks_array)):
        blk = table_blocks_array[x]
        blk_w = max(1, blk["x2"] - blk["x1"])
        if st["x1"] < blk["x1"] - 20 or st["x2"] > blk["x2"] + 20:
          continue

        if blk["y_top"] + 6 < st["y"] < blk["y_mid"] - 6 and st["w"] >= cmid_min_w:
          blk["cmidrules"].append(st)
          erase_boxes_array.append((st["x1"], max(0, st["y1"] - 2), st["x2"], st["y2"] + 2))
          break

        if blk["y_mid"] + 10 < st["y"] < blk["y_bot"] - 6:
          if ul_min_w <= st["w"] <= ul_max_w and st["h"] <= ul_max_h:
            probe_y0 = max(0, st["y1"] - ink_lookback)
            probe_y1 = max(probe_y0 + 1, st["y1"] - 2)
            above_patch = bw_mask[probe_y0:probe_y1, st["x1"]:st["x2"]]
            ink_ratio = float(np.count_nonzero(above_patch))/max(1, above_patch.size)
            if ink_ratio >= min_ink_ratio:
              blk["underlines"].append(st)
              erase_boxes_array.append((st["x1"], max(0, st["y1"] - 1), st["x2"], st["y2"] + 1))
          elif st["w"] > ul_max_w:
            if st["w"] <= 0.85*blk_w:
              blk["col_spans"].append(st)
            erase_boxes_array.append((st["x1"], max(0, st["y1"] - 2), st["x2"], st["y2"] + 2))
          break

    #Return statement
    return {
      "erase_boxes": erase_boxes_array,
      "table_blocks": table_blocks_array
    }


  def D_detectCurlyBraces (self, arg1_bw_mask, arg2_table_blocks_array, arg3_erase_boxes_array):
    """
    @brief Step D: Detect vertical curly braces ({ and }) inside sub-table bodies and determine cusp direction.
    @param arg1_bw_mask Deskewed binary foreground mask.
    @param arg2_table_blocks_array Sub-table blocks from Step C.
    @param arg3_erase_boxes_array Rule/underline boxes to suppress before brace extraction.
    @return Dictionary with updated table_blocks and combined erase_boxes (rules + braces).
    """
    #Convert from parameters
    bw_mask = arg1_bw_mask
    table_blocks_array = arg2_table_blocks_array if isinstance(arg2_table_blocks_array, list) else []
    erase_boxes_array = list(arg3_erase_boxes_array) if isinstance(arg3_erase_boxes_array, list) else []

    #Declare local instance variables
    brace_erase_array = []
    close_kx, close_ky = self.gfx_cfg.get("brace_vert_close_kernel", [1, 5])
    end_ratio = float(self.gfx_cfg.get("brace_end_band_ratio", 0.18))
    max_w = int(self.gfx_cfg.get("brace_max_width_px", 64))
    mid_high = float(self.gfx_cfg.get("brace_mid_band_high", 0.62))
    mid_low = float(self.gfx_cfg.get("brace_mid_band_low", 0.38))
    min_aspect = float(self.gfx_cfg.get("brace_min_aspect_ratio", 2.0))
    min_cusp = float(self.gfx_cfg.get("brace_min_cusp_offset_px", 1.6))
    min_h = int(self.gfx_cfg.get("brace_min_height_px", 58))
    min_w = int(self.gfx_cfg.get("brace_min_width_px", 7))

    if bw_mask is None or not table_blocks_array:
      return {
        "erase_boxes": erase_boxes_array,
        "table_blocks": table_blocks_array
      }

    clean_bw = bw_mask.copy()
    page_h, page_w = clean_bw.shape[:2]
    for i in range(len(erase_boxes_array)):
      bx1, by1, bx2, by2 = erase_boxes_array[i]
      clean_bw[max(0, int(by1)):min(page_h, int(by2)), max(0, int(bx1)):min(page_w, int(bx2))] = 0

    bridged_bw = cv2.morphologyEx(
      clean_bw,
      cv2.MORPH_CLOSE,
      cv2.getStructuringElement(cv2.MORPH_RECT, (int(close_kx), int(close_ky)))
    )
    num_cc, _, stats, _ = cv2.connectedComponentsWithStats(bridged_bw)

    for i in range(len(table_blocks_array)):
      table_blocks_array[i]["braces"] = []

    for i in range(1, num_cc):
      cx = int(stats[i, cv2.CC_STAT_LEFT])
      cy = int(stats[i, cv2.CC_STAT_TOP])
      cw = int(stats[i, cv2.CC_STAT_WIDTH])
      ch = int(stats[i, cv2.CC_STAT_HEIGHT])
      if ch < min_h or cw < min_w or cw > max_w or (ch/max(1.0, float(cw))) < min_aspect:
        continue

      target_blk = None
      for x in range(len(table_blocks_array)):
        blk = table_blocks_array[x]
        if cx >= blk["x1"] - 12 and (cx + cw) <= blk["x2"] + 12:
          if cy >= blk["y_top"] - 6 and (cy + ch) <= blk["y_bot"] + 10:
            target_blk = blk
            break
      if target_blk is None:
        continue

      crop = clean_bw[cy:cy + ch, cx:cx + cw]
      end_h = max(3, int(ch*end_ratio))
      top_xs = np.where(crop[:end_h, :] > 0)[1]
      bot_xs = np.where(crop[ch - end_h:, :] > 0)[1]
      mid_xs = np.where(crop[int(ch*mid_low):int(ch*mid_high), :] > 0)[1]
      if len(top_xs) == 0 or len(bot_xs) == 0 or len(mid_xs) == 0:
        continue

      top_mean = float(np.mean(top_xs))
      bot_mean = float(np.mean(bot_xs))
      if abs(top_mean - bot_mean) > cw*0.52:
        continue

      ends_mean = 0.5*(top_mean + bot_mean)
      mid_mean = float(np.mean(mid_xs))
      cusp_delta = mid_mean - ends_mean
      if abs(cusp_delta) < min_cusp:
        continue

      brace_char = "}" if cusp_delta > 0 else "{"
      points_toward = "right" if cusp_delta > 0 else "left"

      target_blk["braces"].append({
        "brace": brace_char,
        "cusp_delta_px": round(cusp_delta, 2),
        "h": ch,
        "points_toward": points_toward,
        "w": cw,
        "x1": cx,
        "x2": cx + cw,
        "x_centre": cx + 0.5*cw,
        "y1": cy,
        "y2": cy + ch,
        "y_centre": cy + 0.5*ch
      })
      brace_erase_array.append((max(0, cx - 1), max(0, cy - 1), min(page_w, cx + cw + 1), min(page_h, cy + ch + 1)))

    for i in range(len(table_blocks_array)):
      table_blocks_array[i]["braces"].sort(key=lambda b: (b["y1"], b["x1"]))

    #Return statement
    return {
      "erase_boxes": erase_boxes_array + brace_erase_array,
      "table_blocks": table_blocks_array
    }


  def E_detectAllElements (self, arg1_bw_mask):
    """
    @brief Step E: Run complete graphical layout detection (strokes -> table blocks -> cmidrules/underlines -> braces).
    @param arg1_bw_mask Deskewed binary foreground mask.
    @return Dictionary with strokes, table_blocks and erase_boxes.
    """
    #Convert from parameters
    bw_mask = arg1_bw_mask

    strokes_array = self.A_detectHorizontalStrokes(bw_mask)
    blocks_array = self.B_segmentTableBlocks(strokes_array, bw_mask)
    assigned_obj = self.C_assignSubRulesAndUnderlines(strokes_array, blocks_array, bw_mask)
    final_obj = self.D_detectCurlyBraces(bw_mask, assigned_obj["table_blocks"], assigned_obj["erase_boxes"])

    #Return statement
    return {
      "erase_boxes": final_obj["erase_boxes"],
      "strokes": strokes_array,
      "table_blocks": final_obj["table_blocks"]
    }


  def filterNestedTableBlocks (self, arg1_blocks_array):
    """
    @brief Suppress candidate blocks strictly enclosed inside a wider outer sub-table (e.g. horizontal underbraces).
    @param arg1_blocks_array Candidate sub-table block dictionaries.
    @return Filtered list of outer sub-table blocks.
    """
    #Convert from parameters
    blocks_array = arg1_blocks_array if isinstance(arg1_blocks_array, list) else []

    if len(blocks_array) <= 1:
      return blocks_array

    #Declare local instance variables
    filtered_array = []

    for i in range(len(blocks_array)):
      cand = blocks_array[i]
      cand_w = cand["x2"] - cand["x1"]
      is_nested = False
      for x in range(len(blocks_array)):
        if i == x:
          continue
        outer = blocks_array[x]
        outer_w = outer["x2"] - outer["x1"]
        ov_y = min(cand["y_bot"], outer["y_bot"]) - max(cand["y_top"], outer["y_top"])
        if (
          outer_w >= 1.18*cand_w
          and cand["x1"] >= outer["x1"] - 18
          and cand["x2"] <= outer["x2"] + 18
          and ov_y >= 30.0
        ):
          is_nested = True
          break
      if not is_nested:
        filtered_array.append(cand)

    #Return statement
    return filtered_array


  def probeBodyBelowMissingBottomRule (self, arg1_bw_mask, arg2_x1, arg3_x2, arg4_bot_rule_obj, arg5_max_y):
    """
    @brief Probe below the lowest header rule when a sub-table's bottom rule was cropped or faint.
    @param arg1_bw_mask Binary foreground mask.
    @param arg2_x1 Left x of rule stack.
    @param arg3_x2 Right x of rule stack.
    @param arg4_bot_rule_obj Lowest detected rule in the header group.
    @param arg5_max_y Maximum downward y coordinate before the next sub-table or page margin.
    @return Synthetic bottom rule dictionary or None if no multi-column body immediately follows.
    """
    #Convert from parameters
    bw_mask = arg1_bw_mask
    x1 = int(arg2_x1)
    x2 = int(arg3_x2)
    bot_r = arg4_bot_rule_obj
    max_y = int(arg5_max_y)

    #Declare local instance variables
    active_end_dy = -1
    blank_run = 0
    probe_y0 = int(bot_r["y2"]) + 8
    probe_y1 = min(bw_mask.shape[0] - 10, max_y, probe_y0 + 2600)
    seen_rows = 0

    if probe_y1 <= probe_y0 + 60 or x2 <= x1 + 80:
      return None

    body_patch = bw_mask[probe_y0:probe_y1, x1:x2]
    row_ink = np.sum(body_patch > 0, axis=1)
    first_band = np.where(row_ink[:min(64, len(row_ink))] >= 10)[0]
    if len(first_band) < 6:
      return None

    for i in range(len(row_ink)):
      if row_ink[i] >= 12:
        active_end_dy = i
        seen_rows = seen_rows + 1
        blank_run = 0
      else:
        blank_run = blank_run + 1
        if seen_rows >= 10 and blank_run >= 65:
          break

    if seen_rows < 28 or active_end_dy < 120:
      return None

    used_patch = body_patch[:active_end_dy + 1, :]
    col_ink = np.sum(used_patch > 0, axis=0)
    sparse_cols_ratio = float(np.sum(col_ink <= max(1, int(0.015*used_patch.shape[0]))))/max(1, used_patch.shape[1])
    if sparse_cols_ratio < 0.18:
      return None

    inferred_bot_y = float(probe_y0 + active_end_dy + 14)

    #Return statement
    return {
      "h": 2,
      "w": x2 - x1,
      "x1": x1,
      "x2": x2,
      "y": inferred_bot_y,
      "y1": int(inferred_bot_y),
      "y2": int(inferred_bot_y) + 2
    }


  def sortBlocksReadingOrder (self, arg1_blocks_array):
    """
    @brief Sort sub-table blocks in natural multi-column reading order (top-down full-width bands, left-to-right panels).
    @param arg1_blocks_array List of sub-table block dictionaries.
    @return Sorted list of sub-table block dictionaries.
    """
    #Convert from parameters
    blocks_array = arg1_blocks_array if isinstance(arg1_blocks_array, list) else []

    if len(blocks_array) <= 1:
      return blocks_array

    #Declare local instance variables
    bands_array = []
    remaining_array = sorted(blocks_array, key=lambda b: (b["y_top"], b["x1"]))
    sorted_result_array = []

    cur_band = [remaining_array[0]]
    cur_max_y = remaining_array[0]["y_bot"]
    for i in range(1, len(remaining_array)):
      blk = remaining_array[i]
      if blk["y_top"] >= cur_max_y - 8:
        bands_array.append(cur_band)
        cur_band = [blk]
        cur_max_y = blk["y_bot"]
      else:
        cur_band.append(blk)
        cur_max_y = max(cur_max_y, blk["y_bot"])
    bands_array.append(cur_band)

    for i in range(len(bands_array)):
      band = bands_array[i]
      cols_array = []
      for x in range(len(band)):
        blk = band[x]
        placed = False
        for y in range(len(cols_array)):
          col = cols_array[y]
          ov = min(blk["x2"], col["x2"]) - max(blk["x1"], col["x1"])
          if ov > 0.4*min(blk["x2"] - blk["x1"], col["x2"] - col["x1"]):
            col["blocks"].append(blk)
            col["x1"] = min(col["x1"], blk["x1"])
            col["x2"] = max(col["x2"], blk["x2"])
            placed = True
            break
        if not placed:
          cols_array.append({
            "blocks": [blk],
            "x1": blk["x1"],
            "x2": blk["x2"]
          })
      cols_array.sort(key=lambda c: c["x1"])
      for x in range(len(cols_array)):
        col_blocks = sorted(cols_array[x]["blocks"], key=lambda b: b["y_top"])
        sorted_result_array.extend(col_blocks)

    #Return statement
    return sorted_result_array


  def splitRuleStackIntoTables (self, arg1_rules_array, arg2_x1, arg3_x2, arg4_bw_mask):
    """
    @brief Partition a vertical stack of major rules sharing [x1, x2] into individual sub-tables at inter-table gaps.
    @param arg1_rules_array Major rules sorted ascending by y.
    @param arg2_x1 Left pixel boundary of the stack.
    @param arg3_x2 Right pixel boundary of the stack.
    @param arg4_bw_mask Binary foreground mask.
    @return List of rule lists, one per individual sub-table.
    """
    #Convert from parameters
    rules_array = arg1_rules_array
    x1 = int(arg2_x1)
    x2 = int(arg3_x2)
    bw_mask = arg4_bw_mask

    #Declare local instance variables
    cur_group_array = [rules_array[0]]
    groups_array = []
    span_w = max(1, x2 - x1)

    for i in range(len(rules_array) - 1):
      r_cur = rules_array[i]
      r_nxt = rules_array[i + 1]
      y_top = int(r_cur["y2"]) + 5
      y_bot = int(r_nxt["y1"]) - 5

      can_split_here = (len(cur_group_array) >= 3)
      if not can_split_here and len(cur_group_array) == 2 and (y_bot - y_top) >= 34:
        prev_r = cur_group_array[0]
        prev_y0 = int(prev_r["y2"]) + 4
        prev_y1 = int(r_cur["y1"]) - 4
        if prev_y1 - prev_y0 >= 38:
          prev_strip = bw_mask[prev_y0:prev_y1, x1:x2]
          prev_row_ink = np.sum(prev_strip > 0, axis=1)
          prev_active_rows = int(np.sum(prev_row_ink >= 10))
          prev_mid = prev_strip[:, int(span_w*0.30):int(span_w*0.85)]
          prev_mid_ink = float(np.count_nonzero(prev_mid))/max(1, prev_mid.size)
          prev_stub = prev_strip[:, :max(1, int(span_w*0.16))]
          prev_stub_rows = int(np.sum(np.sum(prev_stub > 0, axis=1) >= 6))
          if prev_active_rows >= 14 and prev_stub_rows >= 10 and prev_mid_ink >= 0.002:
            can_split_here = True

      is_inter_table_gap = False
      if can_split_here and y_bot > y_top + 4:
        strip = bw_mask[y_top:y_bot, x1:x2]
        total_ink = float(np.count_nonzero(strip))/max(1, strip.size)
        q_w = max(1, span_w//4)
        active_quarters = 0
        for x in range(4):
          q_slice = strip[:, x*q_w:min(span_w, (x + 1)*q_w)]
          if np.count_nonzero(q_slice) > 25:
            active_quarters = active_quarters + 1
        mid_slice = strip[:, int(span_w*0.35):int(span_w*0.80)]
        mid_ink = float(np.count_nonzero(mid_slice))/max(1, mid_slice.size)
        if total_ink < 0.002 or (active_quarters <= 2 and mid_ink < 0.003):
          is_inter_table_gap = True

      if is_inter_table_gap:
        groups_array.append(cur_group_array)
        cur_group_array = [r_nxt]
      else:
        cur_group_array.append(r_nxt)

    if cur_group_array:
      groups_array.append(cur_group_array)

    #Return statement
    return groups_array


  def synthesiseSteppedBottomRules (self, arg1_rules_array, arg2_strokes_array, arg3_x1, arg4_x2, arg5_align_tol):
    """
    @brief Synthesise full-width bottom rules for stepped tables where left and right column blocks end at different depths.
    @param arg1_rules_array Sorted full-width rules in the stack.
    @param arg2_strokes_array All merged horizontal strokes on the page.
    @param arg3_x1 Left pixel boundary of the stack.
    @param arg4_x2 Right pixel boundary of the stack.
    @param arg5_align_tol Alignment tolerance in pixels.
    @return Sorted rules list augmented with synthetic stepped bottom rules.
    """
    #Convert from parameters
    rules_array = list(arg1_rules_array)
    strokes_array = arg2_strokes_array
    x1 = int(arg3_x1)
    x2 = int(arg4_x2)
    align_tol = int(arg5_align_tol)

    if not rules_array or x2 - x1 < 400:
      return rules_array

    #Declare local instance variables
    left_segs = [
      s for s in strokes_array
      if s["w"] >= 180 and abs(s["x1"] - x1) <= align_tol + 12 and s["x2"] < x2 - 180
    ]
    right_segs = [
      s for s in strokes_array
      if s["w"] >= 180 and abs(s["x2"] - x2) <= align_tol + 12 and s["x1"] > x1 + 180
    ]
    synthetic_array = []

    for i in range(len(left_segs)):
      s_l = left_segs[i]
      for x in range(len(right_segs)):
        s_r = right_segs[x]
        gap_x = s_r["x1"] - s_l["x2"]
        dy = abs(s_r["y"] - s_l["y"])
        if -18 <= gap_x <= 135 and 35.0 <= dy <= 1800.0:
          y_lo = min(s_l["y"], s_r["y"])
          y_hi = max(s_l["y"], s_r["y"])
          has_above = any(r["y"] < y_lo - 60.0 for r in rules_array)
          crosses_full = any((y_lo - 15.0) <= r["y"] <= (y_hi + 15.0) for r in rules_array)
          dup_syn = any(abs(sr["y"] - y_hi) <= 24.0 for sr in synthetic_array)
          if has_above and not crosses_full and not dup_syn:
            synthetic_array.append({
              "extra_erase": [s_l, s_r],
              "h": 2,
              "w": x2 - x1,
              "x1": x1,
              "x2": x2,
              "y": float(y_hi),
              "y1": int(round(y_hi)) - 1,
              "y2": int(round(y_hi)) + 1
            })

    if synthetic_array:
      rules_array.extend(synthetic_array)
      rules_array.sort(key=lambda r: r["y"])

    #Return statement
    return rules_array
