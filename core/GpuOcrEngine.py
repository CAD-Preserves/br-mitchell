"""@brief High-throughput CUDA fp16 Optical Character Recognition engine wrapping DocTR PARSeq/CRNN."""

import re
import sys
import torch
from doctr.models import recognition_predictor


class GpuOcrEngine:
  """@brief Batched GPU word/token recogniser with post-OCR footnote and numeric token normalisation."""

  def __init__ (self, arg1_config_obj):
    """
    @brief Initialise GpuOcrEngine and load the configured PyTorch recognition model onto CUDA/CPU.
    @param arg1_config_obj Pipeline configuration dictionary loaded from /common/digitiser/.
    """
    #Convert from parameters
    config_obj = arg1_config_obj if isinstance(arg1_config_obj, dict) else {}

    #Declare local instance variables
    self.model = None
    self.ocr_cfg = config_obj.get("ocr", {})
    self.sym_cfg = config_obj.get("symbols", {})
    self.use_cuda = False

    self.A_loadModel()


  def A_loadModel (self):
    """
    @brief Step A: Load pretrained DocTR recognition model onto target device (fp16 on CUDA when available).
    @return Loaded predictor instance.
    """
    #Declare local instance variables
    arch = str(self.ocr_cfg.get("architecture", "parseq"))
    batch_size = int(self.ocr_cfg.get("batch_size", 512))
    req_device = str(self.ocr_cfg.get("device", "cuda"))
    use_fp16 = bool(self.ocr_cfg.get("use_fp16", True))

    predictor = recognition_predictor(arch, pretrained=True, batch_size=batch_size)
    if req_device == "cuda" and torch.cuda.is_available():
      predictor = predictor.cuda()
      if use_fp16:
        predictor = predictor.half()
      self.use_cuda = True
    else:
      self.use_cuda = False

    self.model = predictor

    #Return statement
    return self.model


  def B_recogniseCropsBatch (self, arg1_crops_array):
    """
    @brief Step B: Execute batched neural text recognition across an arbitrary list of RGB token crops.
    @param arg1_crops_array List of uint8 RGB numpy arrays.
    @return List of (recognised_string, confidence_float) tuples matching input order.
    """
    #Convert from parameters
    crops_array = arg1_crops_array if isinstance(arg1_crops_array, list) else []

    if not crops_array:
      return []
    if self.model is None:
      sys.stderr.write("Console error: OCR model not initialised before B_recogniseCropsBatch.\n")
      return [("", 0.0) for _ in range(len(crops_array))]

    #Declare local instance variables
    valid_crops_array = []
    valid_indices_array = []
    results_array = [("", 0.0) for _ in range(len(crops_array))]

    for i in range(len(crops_array)):
      c = crops_array[i]
      if c is not None and c.ndim == 3 and c.shape[0] >= 2 and c.shape[1] >= 2:
        valid_crops_array.append(c)
        valid_indices_array.append(i)

    if valid_crops_array:
      with torch.inference_mode():
        preds = self.model(valid_crops_array)
      for i in range(len(valid_indices_array)):
        orig_idx = valid_indices_array[i]
        txt, conf = preds[i]
        results_array[orig_idx] = (str(txt).strip(), float(conf))

    #Return statement
    return results_array


  def C_populatePageTokens (self, arg1_pages_seg_array):
    """
    @brief Step C: Batch-recognise all OCR jobs across multiple segmented pages in one GPU call and populate tokens.
    @param arg1_pages_seg_array List of segmented page dictionaries (each having tokens and ocr_jobs).
    @return Updated list of segmented page dictionaries with recognised text and parsed footnotes.
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
    @brief Step D: Normalise OCR text, attach script footnotes, and repair residual comma-group superscript merges.
    @param arg1_token_obj Single token dictionary modified in place.
    @return Normalised token dictionary.
    """
    #Convert from parameters
    tok = arg1_token_obj

    #Declare local instance variables
    footnotes_array = list(tok.get("footnotes", []))
    raw_txt = str(tok.get("text", "")).strip()
    script_raw = str(tok.get("script_raw", "")).strip()

    if script_raw:
      cleaned_notes = self.parseScriptFootnoteString(script_raw)
      for i in range(len(cleaned_notes)):
        if cleaned_notes[i] not in footnotes_array:
          footnotes_array.append(cleaned_notes[i])

    # Safety check: thousands-comma numbers never have >3 digits after the final comma (e.g. 13,93464 -> 13,934 + note 64)
    comma_overflow = re.match(r"^([+\-\[]?\d{1,3}(?:,\d{3})+)(\d{1,2})(\]?)$", raw_txt)
    if comma_overflow:
      raw_txt = f"{comma_overflow.group(1)}{comma_overflow.group(3)}"
      extra_fn = comma_overflow.group(2)
      if extra_fn not in footnotes_array:
        footnotes_array.append(extra_fn)

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
    @param arg1_script_str Raw OCR string from a script crop (e.g. '69,71', "'63", '11', '*').
    @return List of cleaned marker strings.
    """
    #Convert from parameters
    script_str = str(arg1_script_str).strip()

    #Declare local instance variables
    notes_array = []

    if not script_str:
      return []

    # Preserve italic census year markers like '63 or `63
    if re.match(r"^['`‘’]\d{2}$", script_str):
      return [ "'" + script_str[-2:] ]

    parts = re.split(r"[,.;\s]+", script_str)
    for i in range(len(parts)):
      p = parts[i].strip()
      if not p:
        continue
      # Common OCR confusions on tiny superscripts: l/I -> 1, O -> 0, S -> 5
      if any(ch.isdigit() for ch in p) or p in ["l", "I"]:
        p = p.replace("l", "1").replace("I", "1").replace("O", "0")
      p_clean = re.sub(r"[^0-9A-Za-z*†‡'/-]", "", p)
      if p_clean:
        notes_array.append(p_clean)

    #Return statement
    return notes_array

