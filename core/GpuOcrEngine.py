"""@brief High-throughput CUDA EasyOCR recognition engine with width-bucketed GPU batching."""

import math
import re
import sys
import cv2
import easyocr
from easyocr.recognition import adjust_contrast_grey, custom_mean
import numpy as np
import torch
import torch.nn.functional as F


class GpuOcrEngine:
  """@brief Batched GPU EasyOCR recogniser with contrast-retry fallback and post-OCR token normalisation."""

  def __init__ (self, arg1_config_obj):
    """
    @brief Initialise GpuOcrEngine and load the configured EasyOCR recognition network onto CUDA/CPU.
    @param arg1_config_obj Pipeline configuration dictionary loaded from /common/digitiser/.
    """
    #Convert from parameters
    config_obj = arg1_config_obj if isinstance(arg1_config_obj, dict) else {}

    #Declare local instance variables
    self.converter = None
    self.device = "cpu"
    self.ignore_idx_array = []
    self.img_h = 64
    self.model = None
    self.ocr_cfg = config_obj.get("ocr", {})
    self.reader = None
    self.sym_cfg = config_obj.get("symbols", {})
    self.use_cuda = False
    self.use_fp16 = False

    self.A_loadModel()


  def A_loadModel (self):
    """
    @brief Step A: Load pretrained EasyOCR recognition network onto target device without unused CRAFT weights.
    @return Loaded PyTorch recognition module.
    """
    #Declare local instance variables
    ignore_chars = ""
    langs_array = list(self.ocr_cfg.get("languages", ["en"]))
    req_device = str(self.ocr_cfg.get("device", "cuda"))
    use_gpu = (req_device == "cuda" and torch.cuda.is_available())

    self.img_h = int(self.ocr_cfg.get("img_height_px", 64))
    self.reader = easyocr.Reader(langs_array, gpu=use_gpu, detector=False, verbose=False)
    self.converter = self.reader.converter
    self.device = str(self.reader.device)
    self.use_cuda = use_gpu and self.device.startswith("cuda")
    self.use_fp16 = bool(self.ocr_cfg.get("use_fp16", True)) and self.use_cuda

    raw_model = self.reader.recognizer
    if isinstance(raw_model, torch.nn.DataParallel) and torch.cuda.device_count() <= 1:
      raw_model = raw_model.module
    raw_model.eval()
    self.model = raw_model

    ignore_chars = "".join(set(self.reader.character) - set(self.reader.lang_char))
    self.ignore_idx_array = []
    for i in range(len(ignore_chars)):
      ch = ignore_chars[i]
      if ch in self.reader.character:
        self.ignore_idx_array.append(self.reader.character.index(ch) + 1)

    #Return statement
    return self.model


  def B_recogniseCropsBatch (self, arg1_crops_array):
    """
    @brief Step B: Execute width-bucketed GPU EasyOCR recognition across an arbitrary list of token crops.
    @param arg1_crops_array List of uint8 greyscale or RGB numpy arrays.
    @return List of (recognised_string, confidence_float) tuples matching input order.
    """
    #Convert from parameters
    crops_array = arg1_crops_array if isinstance(arg1_crops_array, list) else []

    if not crops_array:
      return []
    if self.model is None:
      sys.stderr.write("Console error: EasyOCR model not initialised before B_recogniseCropsBatch.\n")
      return [("", 0.0) for _ in range(len(crops_array))]

    #Declare local instance variables
    adj_contrast = float(self.ocr_cfg.get("adjust_contrast", 0.5))
    batch_sz = int(self.ocr_cfg.get("batch_size", 512))
    buckets_cfg = sorted([int(w) for w in self.ocr_cfg.get("width_buckets_px", [128, 256, 512, 768])])
    buckets_map = {w: [] for w in buckets_cfg}
    contrast_ths = float(self.ocr_cfg.get("contrast_ths", 0.1))
    max_bucket_w = buckets_cfg[-1] if buckets_cfg else 512
    results_array = [("", 0.0) for _ in range(len(crops_array))]

    for i in range(len(crops_array)):
      c = crops_array[i]
      if c is None or c.shape[0] < 2 or c.shape[1] < 2:
        continue
      gray = cv2.cvtColor(c, cv2.COLOR_RGB2GRAY) if c.ndim == 3 else c
      gh, gw = gray.shape[:2]
      target_w = max(4, int(math.ceil(self.img_h*(float(gw)/float(gh)))))
      chosen_b = max_bucket_w
      for x in range(len(buckets_cfg)):
        if target_w <= buckets_cfg[x]:
          chosen_b = buckets_cfg[x]
          break
      buckets_map[chosen_b].append((i, gray))

    for i in range(len(buckets_cfg)):
      bw = buckets_cfg[i]
      items = buckets_map[bw]
      if not items:
        continue

      preds_1 = self.runBucketPass(items, bw, batch_sz, 0.0)
      low_conf_items = []
      low_conf_pos = []

      for x in range(len(items)):
        orig_idx = items[x][0]
        txt1, conf1 = preds_1[x]
        results_array[orig_idx] = (txt1, conf1)
        if conf1 < contrast_ths:
          low_conf_items.append(items[x])
          low_conf_pos.append(orig_idx)

      if low_conf_items and adj_contrast > 0.0:
        preds_2 = self.runBucketPass(low_conf_items, bw, batch_sz, adj_contrast)
        for x in range(len(low_conf_pos)):
          orig_idx = low_conf_pos[x]
          txt2, conf2 = preds_2[x]
          if conf2 > results_array[orig_idx][1]:
            results_array[orig_idx] = (txt2, conf2)

    #Return statement
    return results_array


  def C_populatePageTokens (self, arg1_pages_seg_array):
    """
    @brief Step C: Batch-recognise all OCR jobs across multiple segmented pages and populate tokens.
    @param arg1_pages_seg_array List of segmented page dictionaries (each having tokens and ocr_jobs).
    @return Updated list of segmented page dictionaries with recognised text.
    """
    #Convert from parameters
    pages_seg_array = arg1_pages_seg_array if isinstance(arg1_pages_seg_array, list) else []

    #Declare local instance variables
    all_crops_array = []
    job_refs_array = []

    for i in range(len(pages_seg_array)):
      p_seg = pages_seg_array[i]
      jobs = p_seg.get("ocr_jobs", [])
      for x in range(len(jobs)):
        all_crops_array.append(jobs[x]["crop"])
        job_refs_array.append((i, jobs[x]["token_index"], jobs[x]["role"]))

    preds_array = self.B_recogniseCropsBatch(all_crops_array)

    for i in range(len(preds_array)):
      page_idx, tok_idx, role = job_refs_array[i]
      txt, conf = preds_array[i]
      tok = pages_seg_array[page_idx]["tokens"][tok_idx]
      if role == "main":
        tok["text"] = txt
        tok["conf"] = round(conf, 4)
      else:
        tok["script_raw"] = txt

    for i in range(len(pages_seg_array)):
      tokens = pages_seg_array[i].get("tokens", [])
      for x in range(len(tokens)):
        self.D_normaliseSingleToken(tokens[x])
      # Free crop arrays to keep RAM low during 3000-page runs
      pages_seg_array[i]["ocr_jobs"] = []

    #Return statement
    return pages_seg_array


  def D_normaliseSingleToken (self, arg1_token_obj):
    """
    @brief Step D: Normalise OCR text, collapse spurious whitespace, and repair residual comma-group superscript merges.
    @param arg1_token_obj Single token dictionary modified in place.
    @return Normalised token dictionary.
    """
    #Convert from parameters
    tok = arg1_token_obj

    #Declare local instance variables
    footnotes_array = list(tok.get("footnotes", []))
    raw_txt = re.sub(r"\s+", " ", str(tok.get("text", ""))).strip()
    script_raw = str(tok.get("script_raw", "")).strip()

    if script_raw:
      cleaned_notes = self.parseScriptFootnoteString(script_raw)
      for i in range(len(cleaned_notes)):
        if cleaned_notes[i] not in footnotes_array:
          footnotes_array.append(cleaned_notes[i])

    # Safety check: thousands-comma numbers never have >3 digits after the final comma (e.g. 13,93464 -> 13,934)
    comma_overflow = re.match(r"^([+\-\[]?\d{1,3}(?:,\d{3})+)(\d{1,2})(\]?)$", raw_txt)
    if comma_overflow:
      raw_txt = f"{comma_overflow.group(1)}{comma_overflow.group(3)}"
      extra_fn = comma_overflow.group(2)
      if extra_fn not in footnotes_array:
        footnotes_array.append(extra_fn)

    # Normalise mixed-case x-height OCR artefacts on short lowercase stopwords (e.g. 'iS' -> 'is')
    if raw_txt in ["iS", "iN", "oF", "aS", "oN", "aT", "tO", "bY"]:
      raw_txt = raw_txt.lower()

    # Normalise OCR symbol variants
    if tok.get("symbol_kind") is None:
      if raw_txt in self.sym_cfg.get("not_available", ["...", "…", ". . .", "..", "...."]):
        tok["symbol_kind"] = "not_available"
        raw_txt = "..."
      elif raw_txt in self.sym_cfg.get("less_than_half_unit", ["--", "- -", "- - -"]):
        tok["symbol_kind"] = "less_than_half_unit"
        raw_txt = "--"
      elif raw_txt in ["—", "–"]:
        tok["symbol_kind"] = "nil"
        raw_txt = "—"

    tok["text"] = raw_txt
    tok["footnotes"] = footnotes_array

    #Return statement
    return tok


  def parseScriptFootnoteString (self, arg1_script_str):
    """
    @brief Clean a recognised superscript/subscript string into individual footnote/date markers.
    @param arg1_script_str Raw OCR string from a script crop.
    @return List of cleaned marker strings.
    """
    #Convert from parameters
    script_str = str(arg1_script_str).strip()

    #Declare local instance variables
    notes_array = []

    if not script_str:
      return []

    if re.match(r"^['`‘’]\d{2}$", script_str):
      return ["'" + script_str[-2:]]

    parts = re.split(r"[,.;\s]+", script_str)
    for i in range(len(parts)):
      p = parts[i].strip()
      if not p:
        continue
      if any(ch.isdigit() for ch in p) or p in ["l", "I"]:
        p = p.replace("l", "1").replace("I", "1").replace("O", "0")
      p_clean = re.sub(r"[^0-9A-Za-z*†‡'/-]", "", p)
      if p_clean:
        notes_array.append(p_clean)

    #Return statement
    return notes_array


  def runBucketPass (self, arg1_bucket_items_array, arg2_bucket_w, arg3_batch_size, arg4_adjust_contrast):
    """
    @brief Resize, right-border-pad, and run batched EasyOCR CRNN greedy decoding for one width bucket.
    @param arg1_bucket_items_array List of (orig_idx, gray_crop) tuples.
    @param arg2_bucket_w Padded tensor width for this bucket.
    @param arg3_batch_size Maximum batch size per GPU forward pass.
    @param arg4_adjust_contrast Target contrast (0.0 for normal pass, >0.0 for contrast-adjusted retry).
    @return List of (recognised_string, confidence_float) tuples for arg1_bucket_items_array.
    """
    #Convert from parameters
    items_array = arg1_bucket_items_array
    bucket_w = int(arg2_bucket_w)
    batch_sz = max(1, int(arg3_batch_size))
    adj_contrast = float(arg4_adjust_contrast)

    #Declare local instance variables
    batch_max_len = max(1, bucket_w//10)
    n_items = len(items_array)
    out_array = []

    for start_i in range(0, n_items, batch_sz):
      chunk = items_array[start_i:start_i + batch_sz]
      cur_bsz = len(chunk)
      batch_np = np.empty((cur_bsz, 1, self.img_h, bucket_w), dtype=np.float32)

      for x in range(cur_bsz):
        gray = chunk[x][1]
        if adj_contrast > 0.0:
          gray = adjust_contrast_grey(gray, target=adj_contrast)
        gh, gw = gray.shape[:2]
        rw = min(bucket_w, max(1, int(math.ceil(self.img_h*(float(gw)/float(gh))))))
        resized = cv2.resize(gray, (rw, self.img_h), interpolation=cv2.INTER_CUBIC)
        norm = resized.astype(np.float32)*(1.0/127.5) - 1.0
        batch_np[x, 0, :, :rw] = norm
        if rw < bucket_w:
          batch_np[x, 0, :, rw:] = norm[:, rw - 1:rw]

      with torch.inference_mode():
        img_tensor = torch.from_numpy(batch_np).to(self.device, non_blocking=True)
        text_for_pred = torch.zeros((cur_bsz, batch_max_len + 1), dtype=torch.long, device=self.device)

        if self.use_fp16:
          with torch.amp.autocast("cuda", dtype=torch.float16):
            preds = self.model(img_tensor, text_for_pred)
        else:
          preds = self.model(img_tensor, text_for_pred)

        preds_fp32 = preds.float()
        if self.ignore_idx_array:
          preds_fp32[:, :, self.ignore_idx_array] = -1e9
        probs = F.softmax(preds_fp32, dim=2)
        max_vals, max_idx = probs.max(dim=2)

        idx_np = max_idx.cpu().numpy()
        vals_np = max_vals.cpu().numpy()
        preds_size = np.full(cur_bsz, preds_fp32.size(1), dtype=np.int32)
        decoded_strs = self.converter.decode_greedy(idx_np.reshape(-1), preds_size)

      for x in range(cur_bsz):
        fg_mask = idx_np[x] != 0
        fg_probs = vals_np[x][fg_mask]
        conf = float(custom_mean(fg_probs)) if len(fg_probs) > 0 else 0.0
        out_array.append((str(decoded_strs[x]).strip(), conf))

    #Return statement
    return out_array
