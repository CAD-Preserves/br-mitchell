"""@brief Page rendering, landscape table orientation correction, deskewing, and shadow-free binarisation."""

import math
import sys
import cv2
import numpy as np
import pymupdf


class PagePreprocessor:
  """@brief Converts a scanned PDF page into an upright, deskewed, shadow-normalised 300 DPI image and binary mask."""

  def __init__ (self, arg1_config_obj):
    """
    @brief Initialise PagePreprocessor with rendering and preprocessing parameters.
    @param arg1_config_obj Pipeline configuration dictionary loaded from /common/digitiser/.
    """
    #Convert from parameters
    config_obj = arg1_config_obj if isinstance(arg1_config_obj, dict) else {}

    #Declare local instance variables
    self.preproc_cfg = config_obj.get("preprocessing", {})
    self.render_cfg = config_obj.get("rendering", {})


  def A_renderPage (self, arg1_pdf_doc, arg2_page_index):
    """
    @brief Step A: Render a PDF page at configured DPI into RGB and greyscale numpy arrays.
    @param arg1_pdf_doc Open pymupdf.Document instance.
    @param arg2_page_index Zero-based PDF page index.
    @return Dictionary containing rgb_img and gray_img, or None if invalid.
    """
    #Convert from parameters
    pdf_doc = arg1_pdf_doc
    page_index = arg2_page_index

    #Declare local instance variables
    dpi = int(self.render_cfg.get("dpi", 300))
    gray_img = None
    pix = None
    rgb_img = None

    if pdf_doc is None or page_index < 0 or page_index >= len(pdf_doc):
      sys.stderr.write(f"Console error: invalid page index {page_index} in A_renderPage.\n")
      return None

    pix = pdf_doc[page_index].get_pixmap(dpi=dpi)
    rgb_img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n).copy()
    if pix.n == 4:
      rgb_img = cv2.cvtColor(rgb_img, cv2.COLOR_RGBA2RGB)
    elif pix.n == 1:
      rgb_img = cv2.cvtColor(rgb_img, cv2.COLOR_GRAY2RGB)
    gray_img = cv2.cvtColor(rgb_img, cv2.COLOR_RGB2GRAY)

    #Return statement
    return {
      "gray_img": gray_img,
      "rgb_img": rgb_img
    }


  def B_detectAndFixLandscape (self, arg1_rgb_img, arg2_gray_img):
    """
    @brief Step B: Detect rotated landscape tables (even beneath upright running headers) and rotate upright.
    @param arg1_rgb_img Rendered RGB page image.
    @param arg2_gray_img Rendered greyscale page image.
    @return Dictionary with upright rgb_img, gray_img, orientation string, and optional portrait_header_rgb.
    """
    #Convert from parameters
    rgb_img = arg1_rgb_img
    gray_img = arg2_gray_img

    #Declare local instance variables
    bg_sigma = float(self.preproc_cfg.get("bg_blur_sigma", 35.0))
    bin_thresh = int(self.preproc_cfg.get("binary_threshold", 22))
    body_bot_ratio = float(self.preproc_cfg.get("landscape_body_bottom_ratio", 0.94))
    body_top_ratio = float(self.preproc_cfg.get("landscape_body_top_ratio", 0.09))
    min_v_rule = int(self.preproc_cfg.get("landscape_min_vertical_rule_px", 950))
    orientation = "portrait"
    portrait_header_rgb = None
    vh_ratio_thresh = float(self.preproc_cfg.get("landscape_vh_ratio_threshold", 1.35))

    if rgb_img is None or gray_img is None:
      sys.stderr.write("Console error: null image passed to B_detectAndFixLandscape.\n")
      return None

    page_h, page_w = gray_img.shape[:2]
    y0 = int(page_h*body_top_ratio)
    y1 = int(page_h*body_bot_ratio)
    x0 = int(page_w*0.04)
    x1 = int(page_w*0.96)

    roi_gray = gray_img[y0:y1, x0:x1]
    roi_bg = self.estimateSmoothBackground(roi_gray, bg_sigma)
    roi_diff = self.computeIlluminationNormalisedDiff(roi_gray, roi_bg)
    _, roi_bw = cv2.threshold(roi_diff, bin_thresh, 255, cv2.THRESH_BINARY)

    h_open = cv2.morphologyEx(roi_bw, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (180, 1)))
    h_bridged = cv2.morphologyEx(h_open, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (20, 3)))
    num_h, _, h_stats, _ = cv2.connectedComponentsWithStats(h_bridged)

    v_open = cv2.morphologyEx(roi_bw, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, 180)))
    v_bridged = cv2.morphologyEx(v_open, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 20)))
    num_v, _, v_stats, _ = cv2.connectedComponentsWithStats(v_bridged)

    sum_h_len = 0
    for i in range(1, num_h):
      local_w = int(h_stats[i, cv2.CC_STAT_WIDTH])
      if local_w >= 320:
        sum_h_len = sum_h_len + local_w

    max_v_len = 0
    sum_v_len = 0
    v_rules_array = []
    for i in range(1, num_v):
      local_x = int(v_stats[i, cv2.CC_STAT_LEFT]) + x0
      local_y = int(v_stats[i, cv2.CC_STAT_TOP]) + y0
      local_h = int(v_stats[i, cv2.CC_STAT_HEIGHT])
      if local_h >= min_v_rule:
        sum_v_len = sum_v_len + local_h
        max_v_len = max(max_v_len, local_h)
        v_rules_array.append((local_x, local_y, local_h))

    if max_v_len >= min_v_rule and sum_v_len > max(sum_h_len*vh_ratio_thresh, float(min_v_rule)):
      v_rules_array.sort(key=lambda item: item[0])
      dedup_xs_array = []
      for i in range(len(v_rules_array)):
        local_rx = v_rules_array[i][0]
        if not dedup_xs_array or abs(local_rx - dedup_xs_array[-1]) > 25:
          dedup_xs_array.append(local_rx)

      min_rule_top_y = min(item[1] for item in v_rules_array)
      header_cut_y = max(0, min_rule_top_y - 14)
      if header_cut_y >= 60:
        portrait_header_rgb = rgb_img[:header_cut_y, :].copy()
        rgb_work = rgb_img.copy()
        gray_work = gray_img.copy()
        fill_rgb = np.median(rgb_img[header_cut_y:min(page_h, header_cut_y + 20), :], axis=(0, 1)).astype(np.uint8)
        fill_gray = int(np.median(gray_img[header_cut_y:min(page_h, header_cut_y + 20), :]))
        rgb_work[:header_cut_y, :] = fill_rgb
        gray_work[:header_cut_y, :] = fill_gray
      else:
        rgb_work = rgb_img
        gray_work = gray_img

      rotate_cw = True
      if len(dedup_xs_array) >= 3:
        left_gap = dedup_xs_array[1] - dedup_xs_array[0]
        right_gap = dedup_xs_array[-1] - dedup_xs_array[-2]
        if right_gap < left_gap*0.65:
          rotate_cw = False

      if rotate_cw:
        rgb_img = cv2.rotate(rgb_work, cv2.ROTATE_90_CLOCKWISE)
        gray_img = cv2.rotate(gray_work, cv2.ROTATE_90_CLOCKWISE)
        orientation = "landscape_cw90"
      else:
        rgb_img = cv2.rotate(rgb_work, cv2.ROTATE_90_COUNTERCLOCKWISE)
        gray_img = cv2.rotate(gray_work, cv2.ROTATE_90_COUNTERCLOCKWISE)
        orientation = "landscape_ccw90"

    #Return statement
    return {
      "gray_img": gray_img,
      "orientation": orientation,
      "portrait_header_rgb": portrait_header_rgb,
      "rgb_img": rgb_img
    }


  def C_deskewPage (self, arg1_rgb_img, arg2_gray_img):
    """
    @brief Step C: Measure sub-degree scan skew from horizontal table rules and text baselines, then deskew.
    @param arg1_rgb_img Upright RGB page image.
    @param arg2_gray_img Upright greyscale page image.
    @return Dictionary with deskewed rgb_img, gray_img, and skew_angle_deg.
    """
    #Convert from parameters
    rgb_img = arg1_rgb_img
    gray_img = arg2_gray_img

    #Declare local instance variables
    angles_array = []
    bg_sigma = float(self.preproc_cfg.get("bg_blur_sigma", 35.0))
    bin_thresh = int(self.preproc_cfg.get("binary_threshold", 22))
    max_angle = float(self.preproc_cfg.get("deskew_max_angle_deg", 3.5))
    min_rule_w = int(self.preproc_cfg.get("deskew_min_rule_width_px", 280))
    skew_deg = 0.0
    weights_array = []

    bg = self.estimateSmoothBackground(gray_img, bg_sigma)
    _, bw = cv2.threshold(self.computeIlluminationNormalisedDiff(gray_img, bg), bin_thresh, 255, cv2.THRESH_BINARY)

    h_open = cv2.morphologyEx(bw, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (75, 1)))
    h_bridged = cv2.morphologyEx(h_open, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (30, 5)))
    num_cc, labels, stats, _ = cv2.connectedComponentsWithStats(h_bridged)

    for i in range(1, num_cc):
      local_x = int(stats[i, cv2.CC_STAT_LEFT])
      local_y = int(stats[i, cv2.CC_STAT_TOP])
      local_w = int(stats[i, cv2.CC_STAT_WIDTH])
      local_h = int(stats[i, cv2.CC_STAT_HEIGHT])
      if local_w >= min_rule_w and local_h <= 45:
        sub_mask = (labels[local_y:local_y + local_h, local_x:local_x + local_w] == i)
        ys, xs = np.where(sub_mask)
        if len(xs) >= 100:
          slope, _ = np.polyfit(xs.astype(np.float64), ys.astype(np.float64), 1)
          deg = math.degrees(math.atan(slope))
          if abs(deg) <= max_angle:
            angles_array.append(deg)
            weights_array.append(float(local_w))

    if angles_array:
      order = np.argsort(angles_array)
      sorted_angles = np.array(angles_array)[order]
      sorted_weights = np.array(weights_array)[order]
      cum_weights = np.cumsum(sorted_weights)
      mid_idx = int(np.searchsorted(cum_weights, 0.5*cum_weights[-1]))
      mid_idx = min(max(0, mid_idx), len(sorted_angles) - 1)
      skew_deg = float(sorted_angles[mid_idx])

    if abs(skew_deg) >= 0.035:
      page_h, page_w = gray_img.shape[:2]
      centre = (page_w*0.5, page_h*0.5)
      rot_mat = cv2.getRotationMatrix2D(centre, skew_deg, 1.0)
      rgb_img = cv2.warpAffine(
        rgb_img,
        rot_mat,
        (page_w, page_h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE
      )
      gray_img = cv2.warpAffine(
        gray_img,
        rot_mat,
        (page_w, page_h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE
      )
      bw = None

    #Return statement
    return {
      "cached_bw": bw,
      "gray_img": gray_img,
      "rgb_img": rgb_img,
      "skew_angle_deg": round(skew_deg, 4)
    }


  def D_binarisePage (self, arg1_gray_img, arg2_cached_bw=None):
    """
    @brief Step D: Normalise book-gutter illumination shadows and produce a crisp binary foreground mask.
    @param arg1_gray_img Deskewed greyscale page image.
    @param arg2_cached_bw Optional pre-thresholded binary mask when deskew rotation was unnecessary.
    @return Binary uint8 foreground mask (255 = ink, 0 = paper), with outer scanner border suppressed.
    """
    #Convert from parameters
    gray_img = arg1_gray_img
    cached_bw = arg2_cached_bw

    #Declare local instance variables
    bg_sigma = float(self.preproc_cfg.get("bg_blur_sigma", 35.0))
    bin_thresh = int(self.preproc_cfg.get("binary_threshold", 22))
    margin_px = int(self.render_cfg.get("margin_crop_px", 14))

    if cached_bw is not None:
      bw_mask = cached_bw
    else:
      bg = self.estimateSmoothBackground(gray_img, bg_sigma)
      diff = self.computeIlluminationNormalisedDiff(gray_img, bg)
      _, bw_mask = cv2.threshold(diff, bin_thresh, 255, cv2.THRESH_BINARY)

    page_h, page_w = bw_mask.shape[:2]
    if margin_px > 0 and page_h > 2*margin_px and page_w > 2*margin_px:
      bw_mask[:margin_px, :] = 0
      bw_mask[page_h - margin_px:, :] = 0
      bw_mask[:, :margin_px] = 0
      bw_mask[:, page_w - margin_px:] = 0

    #Return statement
    return bw_mask


  def E_preprocessPage (self, arg1_pdf_doc, arg2_page_index):
    """
    @brief Step E: Execute full preprocessing pipeline (A -> B -> C -> D) for a single PDF page.
    @param arg1_pdf_doc Open pymupdf.Document instance.
    @param arg2_page_index Zero-based PDF page index.
    @return Complete preprocessed page dictionary, or None upon invalid input.
    """
    #Convert from parameters
    pdf_doc = arg1_pdf_doc
    page_index = arg2_page_index

    rendered_obj = self.A_renderPage(pdf_doc, page_index)
    if rendered_obj is None:
      return None

    oriented_obj = self.B_detectAndFixLandscape(rendered_obj["rgb_img"], rendered_obj["gray_img"])
    deskewed_obj = self.C_deskewPage(oriented_obj["rgb_img"], oriented_obj["gray_img"])
    bw_mask = self.D_binarisePage(deskewed_obj["gray_img"], deskewed_obj.get("cached_bw"))

    portrait_header_bw = None
    if oriented_obj["portrait_header_rgb"] is not None:
      ph_gray = cv2.cvtColor(oriented_obj["portrait_header_rgb"], cv2.COLOR_RGB2GRAY)
      portrait_header_bw = self.D_binarisePage(ph_gray)

    #Return statement
    return {
      "bw_mask": bw_mask,
      "gray_img": deskewed_obj["gray_img"],
      "orientation": oriented_obj["orientation"],
      "page_index": page_index,
      "portrait_header_bw": portrait_header_bw,
      "portrait_header_rgb": oriented_obj["portrait_header_rgb"],
      "rgb_img": deskewed_obj["rgb_img"],
      "skew_angle_deg": deskewed_obj["skew_angle_deg"]
    }


  def computeIlluminationNormalisedDiff (self, arg1_gray_img, arg2_bg_img):
    """
    @brief Compute illumination-compensated ink contrast in native uint8 SIMD without float32 allocations.
    @param arg1_gray_img Greyscale image array.
    @param arg2_bg_img Smoothed local background greyscale estimate.
    @return Normalised uint8 foreground difference image.
    """
    #Convert from parameters
    gray_img = arg1_gray_img
    bg_img = arg2_bg_img

    raw_diff = cv2.subtract(bg_img, gray_img)
    bg_clamped = cv2.max(bg_img, 95)
    norm_diff = cv2.divide(raw_diff, bg_clamped, scale=235.0)

    #Return statement
    return norm_diff


  def estimateSmoothBackground (self, arg1_gray_img, arg2_sigma_px):
    """
    @brief Estimate low-frequency page illumination background via 4x pyramid downsample + Gaussian blur.
    @param arg1_gray_img Full-resolution greyscale image.
    @param arg2_sigma_px Target full-resolution Gaussian sigma in pixels.
    @return Full-resolution uint8 background illumination image.
    """
    #Convert from parameters
    gray_img = arg1_gray_img
    sigma_px = float(arg2_sigma_px)

    h, w = gray_img.shape[:2]
    if h >= 128 and w >= 128:
      small = cv2.resize(gray_img, (max(16, w//4), max(16, h//4)), interpolation=cv2.INTER_AREA)
      small_bg = cv2.GaussianBlur(small, (0, 0), sigmaX=max(1.5, sigma_px*0.25))
      bg_img = cv2.resize(small_bg, (w, h), interpolation=cv2.INTER_LINEAR)
    else:
      bg_img = cv2.GaussianBlur(gray_img, (0, 0), sigmaX=sigma_px)

    #Return statement
    return bg_img

