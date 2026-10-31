"""@brief Computer vision detector for booktabs rules, cmidrules, series-break underlines, and curly braces."""

import sys
import cv2
import numpy as np


class GraphicalElementDetector:
  """@brief Extracts graphical layout primitives (rules, sub-table blocks, underlines, and braces) from binary masks."""

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
    @return Sorted list of stroke dictionaries with x1, x2, y, w, h, bbox.
    """
    #Convert from parameters
    bw_mask = arg1_bw_mask

    #Declare local instance variables
    merge_x_gap = int(self.gfx_cfg.get("rule_merge_x_gap_px", 28))
    merge_y_tol = int(self.gfx_cfg.get("rule_merge_y_tol_px", 6))
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
    header_max_h = int(self.gfx_cfg.get("header_max_height_px", 290))
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

        if (dx1 <= align_tol and dx2 <= align_tol) or ov_ratio >= 0.88:
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
      rules = sorted(st["rules"], key=lambda r: r["y"])
      if len(rules) < 2:
        continue

      groups_array = self.splitRuleStackIntoTables(rules, st["x1"], st["x2"], bw_mask)
      for x in range(len(groups_array)):
        grp = groups_array[x]
        if len(grp) < 2:
          continue
        top_r = grp[0]
        bot_r = grp[-1]
        if bot_r["y"] - top_r["y"] < 45:
          continue

        if len(grp) == 2:
          if (bot_r["y"] - top_r["y"]) <= header_max_h:
            # Check if table body extends below bot_r when bottom rule was cropped or faint
            probe_y0 = int(bot_r["y2"]) + 8
            probe_y1 = min(bw_mask.shape[0] - 10, probe_y0 + 2600)
            if probe_y1 > probe_y0 + 60:
              body_patch = bw_mask[probe_y0:probe_y1, st["x1"]:st["x2"]]
              row_ink = np.sum(body_patch > 0, axis=1)
              active_ys = np.where(row_ink >= 12)[0]
              if len(active_ys) >= 10:
                mid_r = bot_r
                inferred_bot_y = float(probe_y0 + int(active_ys[-1]) + 14)
                bot_r = {"x1": st["x1"], "x2": st["x2"], "y": inferred_bot_y, "y1": int(inferred_bot_y), "y2": int(inferred_bot_y) + 2, "w": st["x2"] - st["x1"], "h": 2}
              else:
                mid_r = top_r
            else:
              mid_r = top_r
          else:
            mid_r = top_r
          internal_rules = []
        else:
          mid_r = grp[1]
          if mid_r["y"] - top_r["y"] > header_max_h:
            mid_r = top_r
            internal_rules = grp[1:-1]
          else:
            if len(grp) >= 4 and (grp[2]["y"] - top_r["y"]) <= header_max_h and (bot_r["y"] - grp[2]["y"]) >= 70:
              mid_r = grp[2]
              internal_rules = grp[3:-1]
            else:
              internal_rules = grp[2:-1]

        table_blocks_array.append({
          "all_major_rules": grp,
          "cmidrules": [],
          "internal_rules": internal_rules,
          "underlines": [],
          "x1": int(min(r["x1"] for r in grp)),
          "x2": int(max(r["x2"] for r in grp)),
          "y_bot": float(bot_r["y"]),
          "y_mid": float(mid_r["y"]),
          "y_top": float(top_r["y"])
        })

    table_blocks_array = self.sortBlocksReadingOrder(table_blocks_array)

    #Return statement
    return table_blocks_array


  def C_assignSubRulesAndUnderlines (self, arg1_strokes_array, arg2_table_blocks_array, arg3_bw_mask):
    """
    @brief Step C: Classify non-major horizontal strokes into header cmidrules and body series-break underlines.
    @param arg1_strokes_array All detected horizontal strokes from Step A.
    @param arg2_table_blocks_array Sub-table blocks from Step B.
    @param arg3_bw_mask Deskewed binary foreground mask.
    @return Updated table_blocks_array with cmidrules and underlines populated, plus list of graphical erase boxes.
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
      for x in range(len(blk["all_major_rules"])):
        mr = blk["all_major_rules"][x]
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
    @return Dictionary with strokes, table_blocks, and erase_boxes.
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
    remaining_array = sorted(blocks_array, key=lambda b: (b["y_top"], b["x1"]))
    sorted_result_array = []

    # Partition vertically wherever a horizontal cut separates top blocks from bottom blocks,
    # then within each vertical band group horizontally non-overlapping columns left-to-right.
    bands_array = []
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

      is_inter_table_gap = False
      if len(cur_group_array) >= 3:
        if y_bot <= y_top + 4:
          is_inter_table_gap = False
        else:
          strip = bw_mask[y_top:y_bot, x1:x2]
          total_ink = float(np.count_nonzero(strip))/max(1, strip.size)
          q_w = max(1, span_w//4)
          active_quarters = 0
          for x in range(4):
            q_slice = strip[:, x*q_w:min(span_w, (x + 1)*q_w)]
            if np.count_nonzero(q_slice) > 25:
              active_quarters = active_quarters + 1
          # Inter-table gaps are either blank or contain only a left title / right date label (<= 2 quarters active, middle mostly empty)
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
