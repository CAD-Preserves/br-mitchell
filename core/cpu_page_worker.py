"""@brief Multiprocessing CPU worker routines for rendering, deskewing, layout detection, and token cropping."""

import cv2
import numpy as np
import pymupdf
from core.GraphicalElementDetector import GraphicalElementDetector
from core.PagePreprocessor import PagePreprocessor
from core.TokenSegmenter import TokenSegmenter

_WORKER_STATE_OBJ = {
  "doc": None,
  "gfx": None,
  "pdf_path": None,
  "pre": None,
  "seg": None
}


def A_initCpuWorker (arg1_pdf_path, arg2_pipeline_cfg_obj):
  """
  @brief Step A: Initialise persistent PDF handle and CV processors once per spawned CPU worker process.
  @param arg1_pdf_path Absolute path to the volume PDF file.
  @param arg2_pipeline_cfg_obj Pipeline configuration dictionary.
  """
  #Convert from parameters
  pdf_path = arg1_pdf_path
  cfg_obj = arg2_pipeline_cfg_obj

  # Force single OpenCV thread per worker so N workers do not oversubscribe CPU cores
  cv2.setNumThreads(1)

  _WORKER_STATE_OBJ["pdf_path"] = pdf_path
  _WORKER_STATE_OBJ["doc"] = pymupdf.open(pdf_path)
  _WORKER_STATE_OBJ["pre"] = PagePreprocessor(cfg_obj)
  _WORKER_STATE_OBJ["gfx"] = GraphicalElementDetector(cfg_obj)
  _WORKER_STATE_OBJ["seg"] = TokenSegmenter(cfg_obj)


def B_processSinglePageCpu (arg1_page_index):
  """
  @brief Step B: Execute CPU CV stages (render -> orient/deskew -> rules/braces -> glyph/script crops) for one page.
  @param arg1_page_index Zero-based PDF page index.
  @return Compact page payload dictionary ready for batched GPU OCR in the main process.
  """
  #Convert from parameters
  page_index = int(arg1_page_index)

  doc = _WORKER_STATE_OBJ["doc"]
  pre = _WORKER_STATE_OBJ["pre"]
  gfx = _WORKER_STATE_OBJ["gfx"]
  seg = _WORKER_STATE_OBJ["seg"]

  p_obj = pre.E_preprocessPage(doc, page_index)
  if p_obj is None:
    return {
      "is_blank": True,
      "ocr_jobs": [],
      "orientation": "portrait",
      "page_index": page_index,
      "ph_ocr_jobs": [],
      "ph_tokens": [],
      "skew_angle_deg": 0.0,
      "table_blocks": [],
      "tokens": []
    }

  # Fast blank flyleaf check
  if int(np.count_nonzero(p_obj["bw_mask"])) < 250:
    return {
      "is_blank": True,
      "ocr_jobs": [],
      "orientation": p_obj["orientation"],
      "page_index": page_index,
      "ph_ocr_jobs": [],
      "ph_tokens": [],
      "skew_angle_deg": p_obj["skew_angle_deg"],
      "table_blocks": [],
      "tokens": []
    }

  g_obj = gfx.E_detectAllElements(p_obj["bw_mask"])
  s_obj = seg.D_segmentPageTokens(p_obj["rgb_img"], p_obj["bw_mask"], g_obj["erase_boxes"])

  ph_tokens = []
  ph_jobs = []
  if p_obj["portrait_header_rgb"] is not None and p_obj["portrait_header_bw"] is not None:
    ph_seg = seg.D_segmentPageTokens(p_obj["portrait_header_rgb"], p_obj["portrait_header_bw"], [])
    ph_tokens = ph_seg["tokens"]
    ph_jobs = ph_seg["ocr_jobs"]

  # Strip heavy internal rule lists not needed after erase_boxes
  slim_blocks = []
  for i in range(len(g_obj["table_blocks"])):
    b = g_obj["table_blocks"][i]
    slim_blocks.append({
      "braces": b.get("braces", []),
      "cmidrules": b.get("cmidrules", []),
      "underlines": b.get("underlines", []),
      "x1": b["x1"],
      "x2": b["x2"],
      "y_bot": b["y_bot"],
      "y_mid": b["y_mid"],
      "y_top": b["y_top"]
    })

  #Return statement
  return {
    "is_blank": False,
    "ocr_jobs": s_obj["ocr_jobs"],
    "orientation": p_obj["orientation"],
    "page_index": page_index,
    "ph_ocr_jobs": ph_jobs,
    "ph_tokens": ph_tokens,
    "skew_angle_deg": p_obj["skew_angle_deg"],
    "table_blocks": slim_blocks,
    "tokens": s_obj["tokens"]
  }

