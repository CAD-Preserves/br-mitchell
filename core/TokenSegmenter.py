"""@brief Connected-component word tokeniser, statistical symbol classifier, and superscript/subscript splitter."""

import sys
import cv2
import numpy as np


class TokenSegmenter:
  """@brief Segments cleaned page masks into word/cell tokens while masking superscripts and subscripts prior to OCR."""

  def __init__ (self, arg1_config_obj):
    """
    @brief Initialise TokenSegmenter with morphological and glyph-geometry parameters.
    @param arg1_config_obj Pipeline configuration dictionary loaded from /common/digitiser/.
    """
    #Convert from parameters
    config_obj = arg1_config_obj if isinstance(arg1_config_obj, dict) else {}

    #Declare local instance variables
    self.tok_cfg = config_obj.get("token_segmentation", {})


  def A_eraseGraphicalPrimitives (self, arg1_bw_mask, arg2_erase_boxes_array):
    """
    @brief Step A: Mask out detected rules, cmidrules, underlines, and curly braces from the foreground binary image.
    @param arg1_bw_mask Deskewed binary foreground mask.
    @param arg2_erase_boxes_array List of (x1, y1, x2, y2) graphical element boxes.
    @return Cleaned binary mask containing only text and statistical symbol glyphs.
    """
    #Convert from parameters
    bw_mask = arg1_bw_mask
    erase_boxes_array = arg2_erase_boxes_array if isinstance(arg2_erase_boxes_array, list) else []

    if bw_mask is None:
      sys.stderr.write("Console error: null bw_mask in A_eraseGraphicalPrimitives.\n")
      return None

    #Declare local instance variables
    clean_bw = bw_mask.copy()
    page_h, page_w = clean_bw.shape[:2]

    for i in range(len(erase_boxes_array)):
      x1, y1, x2, y2 = erase_boxes_array[i]
      clean_bw[max(0, int(y1)):min(page_h, int(y2)), max(0, int(x1)):min(page_w, int(x2))] = 0

    #Return statement
    return clean_bw


  def B_extractGlyphsAndWords (self, arg1_clean_bw, arg2_max_y=None):
    """
    @brief Step B: Filter dust, extract glyph components, and group horizontally adjacent characters into word tokens.
    @param arg1_clean_bw Binary mask with graphical lines and braces removed.
    @param arg2_max_y Optional vertical cutoff y coordinate to skip prose footnote tails below tables.
    @return Dictionary containing filtered_bw, glyph_labels, glyphs, and word_boxes.
    """
    #Convert from parameters
    clean_bw = arg1_clean_bw
    max_y = float(arg2_max_y) if arg2_max_y is not None else None

    #Declare local instance variables
    close_kx, close_ky = self.tok_cfg.get("word_close_kernel", [14, 3])
    dust_max_area = int(self.tok_cfg.get("dust_max_area_px", 3))
    filtered_bw = None
    glyphs_array = []
    max_tok_w = int(self.tok_cfg.get("max_token_width_px", 800))
    min_tok_h = int(self.tok_cfg.get("min_token_height_px", 3))
    min_tok_w = int(self.tok_cfg.get("min_token_width_px", 4))
    word_boxes_array = []

    if clean_bw is None:
      return {
        "filtered_bw": None,
        "glyph_labels": None,
        "glyphs": [],
        "word_boxes": []
      }

    filtered_bw = clean_bw.copy()
    if max_y is not None and 0 < int(max_y) < filtered_bw.shape[0]:
      filtered_bw[int(max_y):, :] = 0

    num_g, glyph_labels, g_stats, _ = cv2.connectedComponentsWithStats(filtered_bw)

    for i in range(1, num_g):
      gx = int(g_stats[i, cv2.CC_STAT_LEFT])
      gy = int(g_stats[i, cv2.CC_STAT_TOP])
      gw = int(g_stats[i, cv2.CC_STAT_WIDTH])
      gh = int(g_stats[i, cv2.CC_STAT_HEIGHT])
      ga = int(g_stats[i, cv2.CC_STAT_AREA])
      if ga <= dust_max_area:
        sub = filtered_bw[gy:gy + gh, gx:gx + gw]
        sub[glyph_labels[gy:gy + gh, gx:gx + gw] == i] = 0
        continue
      glyphs_array.append({
        "area": ga,
        "bot": gy + gh,
        "h": gh,
        "label_id": i,
        "right": gx + gw,
        "top": gy,
        "w": gw,
        "x": gx,
        "yc": gy + 0.5*gh
      })

    word_mask = cv2.morphologyEx(
      filtered_bw,
      cv2.MORPH_CLOSE,
      cv2.getStructuringElement(cv2.MORPH_RECT, (int(close_kx), int(close_ky)))
    )
    num_w, _, w_stats, _ = cv2.connectedComponentsWithStats(word_mask)

    for i in range(1, num_w):
      wx = int(w_stats[i, cv2.CC_STAT_LEFT])
      wy = int(w_stats[i, cv2.CC_STAT_TOP])
      ww = int(w_stats[i, cv2.CC_STAT_WIDTH])
      wh = int(w_stats[i, cv2.CC_STAT_HEIGHT])
      if ww < min_tok_w or wh < min_tok_h:
        continue
      # Suppress compact isolated scanner dust/speckle blobs (<=8x9 px) while preserving dashes, ellipses, and 6pt text
      if ww <= 8 and wh <= 9:
        continue
      if ww > max_tok_w:
        split_sub_boxes = self.splitWideTokenBox(filtered_bw, wx, wy, ww, wh)
        word_boxes_array.extend(split_sub_boxes)
      else:
        word_boxes_array.append((wx, wy, ww, wh))

    #Return statement
    return {
      "filtered_bw": filtered_bw,
      "glyph_labels": glyph_labels,
      "glyphs": glyphs_array,
      "word_boxes": word_boxes_array
    }


  def C_classifySymbolsAndSplitScripts (self, arg1_page_img, arg2_extracted_obj):
    """
    @brief Step C: Pre-classify geometric symbols (..., --, —) and mask superscripts/subscripts out of OCR crops.
    @param arg1_page_img Deskewed greyscale or RGB page image.
    @param arg2_extracted_obj Output dictionary from Step B.
    @return Dictionary with tokens and ocr_jobs.
    """
    #Convert from parameters
    page_img = arg1_page_img
    extracted_obj = arg2_extracted_obj if isinstance(arg2_extracted_obj, dict) else {}

    #Declare local instance variables
    band_size = 64
    dash_max_h = int(self.tok_cfg.get("dash_max_height_px", 9))
    dd_max_w = int(self.tok_cfg.get("double_dash_max_width_px", 56))
    dd_min_w = int(self.tok_cfg.get("double_dash_min_width_px", 16))
    el_dot_max = int(self.tok_cfg.get("ellipsis_dot_max_dim_px", 12))
    el_max_h = int(self.tok_cfg.get("ellipsis_max_height_px", 14))
    el_max_w = int(self.tok_cfg.get("ellipsis_max_width_px", 68))
    el_min_w = int(self.tok_cfg.get("ellipsis_min_width_px", 15))
    em_max_w = int(self.tok_cfg.get("em_dash_max_width_px", 54))
    em_min_w = int(self.tok_cfg.get("em_dash_min_width_px", 19))
    filtered_bw = extracted_obj.get("filtered_bw")
    glyph_labels = extracted_obj.get("glyph_labels")
    glyphs_array = extracted_obj.get("glyphs", [])
    gray_img = None
    ocr_jobs_array = []
    pad = int(self.tok_cfg.get("crop_padding_px", 6))
    recognise_fn = bool(self.tok_cfg.get("recognise_footnotes", False))
    row_buckets_obj = {}
    tokens_array = []
    word_boxes_array = extracted_obj.get("word_boxes", [])

    if page_img is None or filtered_bw is None:
      return {
        "ocr_jobs": [],
        "tokens": []
      }

    if page_img.ndim == 3:
      gray_img = cv2.cvtColor(page_img, cv2.COLOR_RGB2GRAY)
    else:
      gray_img = page_img

    page_h, page_w = gray_img.shape[:2]
    for i in range(len(glyphs_array)):
      g = glyphs_array[i]
      b0 = g["top"]//band_size
      b1 = g["bot"]//band_size
      for x in range(b0, b1 + 1):
        if x not in row_buckets_obj:
          row_buckets_obj[x] = []
        row_buckets_obj[x].append(g)

    for i in range(len(word_boxes_array)):
      wx, wy, ww, wh = word_boxes_array[i]
      wx2 = wx + ww
      wy2 = wy + wh

      cand_map = {}
      b0 = wy//band_size
      b1 = wy2//band_size
      for x in range(b0, b1 + 1):
        bucket = row_buckets_obj.get(x, [])
        for y in range(len(bucket)):
          g = bucket[y]
          if g["x"] >= wx - 1 and g["right"] <= wx2 + 1 and g["top"] >= wy - 1 and g["bot"] <= wy2 + 1:
            cand_map[g["label_id"]] = g
      tok_glyphs = sorted(cand_map.values(), key=lambda g: g["x"])

      # 1. Check geometric ellipsis (...)
      if 2 <= len(tok_glyphs) <= 5 and wh <= el_max_h and el_min_w <= ww <= el_max_w:
        if all(g["w"] <= el_dot_max and g["h"] <= el_dot_max for g in tok_glyphs):
          tokens_array.append({
            "conf": 1.0,
            "footnotes": [],
            "h": wh,
            "script_type": None,
            "symbol_kind": "not_available",
            "text": "...",
            "w": ww,
            "x1": wx,
            "x2": wx2,
            "x_centre": wx + 0.5*ww,
            "y1": wy,
            "y2": wy2,
            "y_centre": wy + 0.5*wh
          })
          continue

      # 2. Check geometric double dash (-- / - -)
      if len(tok_glyphs) == 2 and wh <= dash_max_h + 2 and dd_min_w <= ww <= dd_max_w:
        g0, g1 = tok_glyphs[0], tok_glyphs[1]
        if 6 <= g0["w"] <= 24 and 6 <= g1["w"] <= 24 and g0["h"] <= dash_max_h and g1["h"] <= dash_max_h:
          if abs(g0["yc"] - g1["yc"]) <= 4.0 and g1["x"] > g0["right"]:
            tokens_array.append({
              "conf": 1.0,
              "footnotes": [],
              "h": wh,
              "script_type": None,
              "symbol_kind": "less_than_half_unit",
              "text": "--",
              "w": ww,
              "x1": wx,
              "x2": wx2,
              "x_centre": wx + 0.5*ww,
              "y1": wy,
              "y2": wy2,
              "y_centre": wy + 0.5*wh
            })
            continue

      # 3. Check geometric nil em-dash (—)
      if len(tok_glyphs) == 1 and wh <= dash_max_h and em_min_w <= ww <= em_max_w:
        fill_ratio = float(tok_glyphs[0]["area"])/max(1, ww*wh)
        if fill_ratio >= 0.48:
          tokens_array.append({
            "conf": 1.0,
            "footnotes": [],
            "h": wh,
            "script_type": None,
            "symbol_kind": "nil",
            "text": "—",
            "w": ww,
            "x1": wx,
            "x2": wx2,
            "x_centre": wx + 0.5*ww,
            "y1": wy,
            "y2": wy2,
            "y_centre": wy + 0.5*wh
          })
          continue

      # 4. Mask trailing superscript or subscript suffix (e.g. 13,934_64, 1990^69,71, MOROCCO^1, 14'63)
      split_res = self.detectTrailingScriptSuffix(tok_glyphs)
      tok_idx = len(tokens_array)

      if split_res is not None:
        main_glyphs, script_glyphs, script_kind = split_res
        mx1 = min(g["x"] for g in main_glyphs)
        my1 = min(g["top"] for g in main_glyphs)
        mx2 = max(g["right"] for g in main_glyphs)
        my2 = max(g["bot"] for g in main_glyphs)

        cx0 = max(0, mx1 - pad)
        cy0 = max(0, my1 - pad)
        cx1 = min(page_w, mx2 + pad)
        cy1 = min(page_h, my2 + pad)
        main_crop = gray_img[cy0:cy1, cx0:cx1].copy()
        bg_val = int(np.median(main_crop))

        # Mask script glyph pixels out of main_crop so OCR cannot concatenate them onto the main number or label
        lbl_patch = glyph_labels[cy0:cy1, cx0:cx1]
        script_ids = {g["label_id"] for g in script_glyphs}
        script_mask = np.isin(lbl_patch, list(script_ids)).astype(np.uint8)*255
        if np.any(script_mask):
          script_mask = cv2.dilate(script_mask, np.ones((3, 3), np.uint8))
          main_crop[script_mask > 0] = bg_val

        tokens_array.append({
          "conf": 0.0,
          "footnotes": [],
          "h": my2 - my1,
          "script_raw": "",
          "script_type": script_kind,
          "symbol_kind": None,
          "text": "",
          "w": mx2 - mx1,
          "x1": mx1,
          "x2": mx2,
          "x_centre": 0.5*(mx1 + mx2),
          "y1": my1,
          "y2": my2,
          "y_centre": 0.5*(my1 + my2)
        })
        ocr_jobs_array.append({"crop": main_crop, "role": "main", "token_index": tok_idx})

        if recognise_fn:
          sx1 = min(g["x"] for g in script_glyphs)
          sy1 = min(g["top"] for g in script_glyphs)
          sx2 = max(g["right"] for g in script_glyphs)
          sy2 = max(g["bot"] for g in script_glyphs)
          scx0 = max(0, sx1 - pad)
          scy0 = max(0, sy1 - pad)
          scx1 = min(page_w, sx2 + pad)
          scy1 = min(page_h, sy2 + pad)
          script_crop = gray_img[scy0:scy1, scx0:scx1].copy()
          lbl_spatch = glyph_labels[scy0:scy1, scx0:scx1]
          main_ids = {g["label_id"] for g in main_glyphs}
          main_mask = np.isin(lbl_spatch, list(main_ids)).astype(np.uint8)*255
          if np.any(main_mask):
            main_mask = cv2.dilate(main_mask, np.ones((3, 3), np.uint8))
            s_bg = int(np.median(script_crop))
            script_crop[main_mask > 0] = s_bg
          if script_crop.shape[0] > 0 and script_crop.shape[1] > 0:
            script_crop = cv2.resize(
              script_crop,
              (max(8, int(script_crop.shape[1]*1.6)), max(12, int(script_crop.shape[0]*1.6))),
              interpolation=cv2.INTER_CUBIC
            )
          ocr_jobs_array.append({"crop": script_crop, "role": "script", "token_index": tok_idx})
      else:
        cx0 = max(0, wx - pad)
        cy0 = max(0, wy - pad)
        cx1 = min(page_w, wx2 + pad)
        cy1 = min(page_h, wy2 + pad)
        crop = gray_img[cy0:cy1, cx0:cx1]
        tokens_array.append({
          "conf": 0.0,
          "footnotes": [],
          "h": wh,
          "script_raw": "",
          "script_type": None,
          "symbol_kind": None,
          "text": "",
          "w": ww,
          "x1": wx,
          "x2": wx2,
          "x_centre": wx + 0.5*ww,
          "y1": wy,
          "y2": wy2,
          "y_centre": wy + 0.5*wh
        })
        ocr_jobs_array.append({"crop": crop, "role": "main", "token_index": tok_idx})

    #Return statement
    return {
      "ocr_jobs": ocr_jobs_array,
      "tokens": tokens_array
    }


  def D_segmentPageTokens (self, arg1_page_img, arg2_bw_mask, arg3_erase_boxes_array, arg4_max_y=None):
    """
    @brief Step D: Run complete token segmentation pipeline (A -> B -> C) on a preprocessed page.
    @param arg1_page_img Deskewed greyscale or RGB page image.
    @param arg2_bw_mask Deskewed binary foreground mask.
    @param arg3_erase_boxes_array Graphical element boxes to mask out prior to glyph extraction.
    @param arg4_max_y Optional vertical cutoff y coordinate to skip prose footnote regions below tables.
    @return Dictionary containing tokens and ocr_jobs.
    """
    #Convert from parameters
    page_img = arg1_page_img
    bw_mask = arg2_bw_mask
    erase_boxes_array = arg3_erase_boxes_array
    max_y = arg4_max_y

    clean_bw = self.A_eraseGraphicalPrimitives(bw_mask, erase_boxes_array)
    extracted_obj = self.B_extractGlyphsAndWords(clean_bw, max_y)
    segmented_obj = self.C_classifySymbolsAndSplitScripts(page_img, extracted_obj)

    #Return statement
    return segmented_obj


  def detectTrailingScriptSuffix (self, arg1_tok_glyphs_array):
    """
    @brief Detect whether a multi-glyph token ends with a smaller raised (superscript) or lowered (subscript) suffix.
    @param arg1_tok_glyphs_array Left-to-right sorted glyph dictionaries inside a single token.
    @return Tuple (main_glyphs, script_glyphs, script_kind) or None if no trailing script exists.
    """
    #Convert from parameters
    tok_glyphs_array = arg1_tok_glyphs_array

    if not tok_glyphs_array or len(tok_glyphs_array) < 2:
      return None

    #Declare local instance variables
    max_ratio = float(self.tok_cfg.get("script_max_height_ratio", 0.78))
    punct_max_h = int(self.tok_cfg.get("punctuation_max_height_px", 12))
    sub_drop = float(self.tok_cfg.get("subscript_min_drop_px", 3.5))
    sub_top_drop = float(self.tok_cfg.get("subscript_min_top_drop_px", 6.0))
    sup_raise = float(self.tok_cfg.get("superscript_min_raise_px", 5.0))

    base_glyphs = [g for g in tok_glyphs_array if 20 <= g["h"] <= 38]
    if not base_glyphs:
      base_glyphs = [g for g in tok_glyphs_array if g["h"] >= 20]
    if not base_glyphs:
      return None

    cap_glyphs = [g for g in base_glyphs if g["h"] >= 25]
    ref_glyphs = cap_glyphs if cap_glyphs else base_glyphs
    main_h = float(np.median([g["h"] for g in ref_glyphs]))
    main_top = float(np.median([g["top"] for g in ref_glyphs]))
    main_bot = float(np.median([g["bot"] for g in base_glyphs]))

    # Walk backwards from the right end to find the longest valid superscript or subscript suffix
    sup_start = None
    for i in range(len(tok_glyphs_array) - 1, 0, -1):
      g = tok_glyphs_array[i]
      is_sup_char = (
        g["h"] <= main_h*max_ratio
        and g["bot"] <= main_bot - sup_raise
        and g["bot"] <= main_top + main_h*0.76
      )
      is_sup_punct = (
        g["h"] <= punct_max_h
        and g["bot"] <= main_bot - sup_raise
      )
      if is_sup_char or is_sup_punct:
        sup_start = i
      else:
        break

    if sup_start is not None:
      main_part = tok_glyphs_array[:sup_start]
      script_part = tok_glyphs_array[sup_start:]
      if any(g["h"] >= 20 for g in main_part) and any(g["h"] >= 11 and (g["w"] >= 4 or (g["w"] >= 3 and g["h"] >= 14)) for g in script_part):
        if len(script_part) == 1 and script_part[0]["w"] <= 6 and script_part[0]["h"] <= 12:
          return None
        return (main_part, script_part, "superscript")

    sub_start = None
    for i in range(len(tok_glyphs_array) - 1, 0, -1):
      g = tok_glyphs_array[i]
      is_sub_char = (
        13 <= g["h"] <= main_h*max_ratio
        and g["top"] >= main_top + sub_top_drop
        and g["bot"] >= main_bot + sub_drop
      )
      is_sub_punct = (
        g["h"] <= punct_max_h
        and g["top"] >= main_top + sub_top_drop
        and i < len(tok_glyphs_array) - 1
      )
      if is_sub_char or is_sub_punct:
        sub_start = i
      else:
        break

    if sub_start is not None:
      main_part = tok_glyphs_array[:sub_start]
      script_part = tok_glyphs_array[sub_start:]
      if any(g["h"] >= 20 for g in main_part) and any(g["h"] >= 13 and g["w"] >= 5 for g in script_part):
        return (main_part, script_part, "subscript")

    #Return statement
    return None


  def splitWideTokenBox (self, arg1_bw_mask, arg2_wx, arg3_wy, arg4_ww, arg5_wh):
    """
    @brief Split an unusually wide multi-column box only at genuine wide whitespace gaps, never mid-word.
    @param arg1_bw_mask Dust-filtered binary mask.
    @param arg2_wx Left x of box.
    @param arg3_wy Top y of box.
    @param arg4_ww Width of box.
    @param arg5_wh Height of box.
    @return List of (x, y, w, h) sub-boxes.
    """
    #Convert from parameters
    bw_mask = arg1_bw_mask
    wx = int(arg2_wx)
    wy = int(arg3_wy)
    ww = int(arg4_ww)
    wh = int(arg5_wh)

    #Declare local instance variables
    col_sums = None
    cuts_array = [0]
    in_zero = False
    min_gap = int(self.tok_cfg.get("wide_split_min_gap_px", 18))
    patch = bw_mask[wy:wy + wh, wx:wx + ww]
    sub_boxes_array = []
    zero_start = 0

    col_sums = np.sum(patch > 0, axis=0)
    for i in range(ww):
      if col_sums[i] == 0:
        if not in_zero:
          in_zero = True
          zero_start = i
      else:
        if in_zero:
          zero_len = i - zero_start
          if zero_len >= min_gap and (zero_start - cuts_array[-1]) >= 24:
            cuts_array.append((zero_start + i)//2)
          in_zero = False

    cuts_array.append(ww)
    for i in range(len(cuts_array) - 1):
      gx0 = cuts_array[i]
      gx1 = cuts_array[i + 1]
      if gx1 - gx0 < 4:
        continue
      sub_p = patch[:, gx0:gx1]
      ys, xs = np.where(sub_p > 0)
      if len(xs) > 0:
        bx = wx + gx0 + int(xs.min())
        by = wy + int(ys.min())
        bw_s = int(xs.max() - xs.min()) + 1
        bh_s = int(ys.max() - ys.min()) + 1
        sub_boxes_array.append((bx, by, bw_s, bh_s))

    #Return statement
    return sub_boxes_array if sub_boxes_array else [(wx, wy, ww, wh)]
