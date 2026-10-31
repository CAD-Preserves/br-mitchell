"""@brief End-to-end reusable CV + GPU OCR table digitisation pipeline orchestrator."""

from concurrent.futures import ProcessPoolExecutor
import os
import re
import sys
import time
import orjson
import pymupdf
from core.ConfigLoader import ConfigLoader
from core.cpu_page_worker import A_initCpuWorker, B_processSinglePageCpu
from core.GpuOcrEngine import GpuOcrEngine
from core.SectionAssembler import SectionAssembler
from core.TableStructureReconstructor import TableStructureReconstructor


class TableDigitiserPipeline:
  """@brief Orchestrates parallel CPU CV layout/glyph analysis, batched GPU OCR, structure reconstruction, and JSON export."""

  def __init__ (self, arg1_root_dir=None, arg2_options=None):
    """
    @brief Initialise TableDigitiserPipeline with configuration, localisation, GPU OCR, and structure modules.
    @param arg1_root_dir Repository root path.
    @param arg2_options Optional overrides dictionary (locale, architecture, workers, page_batch_size).
    """
    #Convert from parameters
    root_dir = arg1_root_dir
    options = arg2_options if isinstance(arg2_options, dict) else {}

    #Declare local instance variables
    self.cfg_loader = ConfigLoader(root_dir, {"locale": options.get("locale", "en_gb")})
    self.ocr_engine = None
    self.pipeline_cfg = self.cfg_loader.pipeline_config_obj
    self.reconstructor = None
    self.root_dir = self.cfg_loader.root_dir
    self.section_assembler = None
    self.volumes_cfg = self.cfg_loader.volumes_config_obj

    if "architecture" in options and options["architecture"]:
      self.pipeline_cfg.setdefault("ocr", {})["architecture"] = options["architecture"]
    if "workers" in options and options["workers"]:
      self.pipeline_cfg.setdefault("rendering", {})["num_cpu_workers"] = int(options["workers"])
    if "page_batch_size" in options and options["page_batch_size"]:
      self.pipeline_cfg.setdefault("rendering", {})["page_batch_size"] = int(options["page_batch_size"])

    self.A_initialiseComponents()


  def A_initialiseComponents (self):
    """
    @brief Step A: Instantiate GPU OCR engine, table structure reconstructor, and section assembler.
    @return Dictionary of active pipeline components.
    """
    self.ocr_engine = GpuOcrEngine(self.pipeline_cfg)
    self.reconstructor = TableStructureReconstructor(self.pipeline_cfg)
    self.section_assembler = SectionAssembler(self.pipeline_cfg, self.volumes_cfg)

    dev_name = "cuda" if self.ocr_engine.use_cuda else "cpu"
    arch_name = "easyocr/" + str(self.pipeline_cfg.get("ocr", {}).get("architecture", "english_g2"))
    msg = self.cfg_loader.formatLocalisedString("pipeline_initialised", [dev_name, arch_name])
    print(msg, flush=True)

    #Return statement
    return {
      "ocr_engine": self.ocr_engine,
      "reconstructor": self.reconstructor,
      "section_assembler": self.section_assembler
    }


  def B_resolveTargetVolumes (self, arg1_options=None):
    """
    @brief Step B: Resolve configured BR Mitchell volumes or arbitrary user-supplied PDF file paths.
    @param arg1_options Optional filter dictionary (volume_id, pdf_path, start_page, end_page).
    @return List of normalised volume task dictionaries.
    """
    #Convert from parameters
    options = arg1_options if isinstance(arg1_options, dict) else {}

    #Declare local instance variables
    custom_pdf = options.get("pdf_path")
    target_vol_id = options.get("volume_id")
    tasks_array = []

    if custom_pdf:
      abs_pdf = os.path.abspath(custom_pdf)
      if not os.path.exists(abs_pdf):
        sys.stderr.write(self.cfg_loader.formatLocalisedString("error_missing_file", [abs_pdf]) + "\n")
        return []
      stem = os.path.splitext(os.path.basename(abs_pdf))[0]
      if stem.startswith("br_mitchell_"):
        stem = stem[len("br_mitchell_"):]
      tasks_array.append({
        "end_pdf_page": options.get("end_page"),
        "pdf_filename": os.path.basename(abs_pdf),
        "pdf_path": abs_pdf,
        "start_pdf_page": int(options.get("start_page", 0) or 0),
        "volume_id": target_vol_id or stem,
        "volume_title": stem.replace("_", " ").title()
      })
      return tasks_array

    configured_vols = self.volumes_cfg.get("volumes", [])
    for i in range(len(configured_vols)):
      v = configured_vols[i]
      if target_vol_id and v.get("volume_id") != target_vol_id:
        continue
      abs_pdf = os.path.join(self.root_dir, v["pdf_filename"])
      if not os.path.exists(abs_pdf):
        sys.stderr.write(self.cfg_loader.formatLocalisedString("error_missing_file", [abs_pdf]) + "\n")
        continue
      s_page = int(options["start_page"]) if options.get("start_page") is not None else int(v.get("start_pdf_page", 0))
      e_page = int(options["end_page"]) if options.get("end_page") is not None else v.get("end_pdf_page")
      tasks_array.append({
        "end_pdf_page": e_page,
        "pdf_filename": v["pdf_filename"],
        "pdf_path": abs_pdf,
        "start_pdf_page": s_page,
        "volume_id": v["volume_id"],
        "volume_title": v.get("volume_title", v["volume_id"])
      })

    #Return statement
    return tasks_array


  def C_processVolumePages (self, arg1_volume_task_obj):
    """
    @brief Step C: Run double-buffered multiprocessing CPU CV + batched GPU OCR + table reconstruction across a volume.
    @param arg1_volume_task_obj Single volume task dictionary from Step B.
    @return Ordered list of reconstructed page record dictionaries.
    """
    #Convert from parameters
    vol_task = arg1_volume_task_obj

    #Declare local instance variables
    batch_sz = int(self.pipeline_cfg.get("rendering", {}).get("page_batch_size", 24))
    doc = pymupdf.open(vol_task["pdf_path"])
    total_pdf_pages = len(doc)
    doc.close()

    end_p = min(total_pdf_pages, int(vol_task["end_pdf_page"])) if vol_task.get("end_pdf_page") is not None else total_pdf_pages
    start_p = max(0, int(vol_task.get("start_pdf_page", 0)))
    page_indices = list(range(start_p, end_p))
    num_pages = len(page_indices)
    num_workers = max(1, int(self.pipeline_cfg.get("rendering", {}).get("num_cpu_workers", 6)))

    print(self.cfg_loader.formatLocalisedString("volume_started", [vol_task["volume_id"], num_pages]), flush=True)

    live_state_obj = {
      "chap": None,
      "num": 0,
      "sec_id": None,
      "sfx": ""
    }
    page_records_array = []
    processed_count = 0

    chunks_array = [page_indices[i:i + batch_sz] for i in range(0, num_pages, batch_sz)]

    with ProcessPoolExecutor(
      max_workers=num_workers,
      initializer=A_initCpuWorker,
      initargs=(vol_task["pdf_path"], self.pipeline_cfg)
    ) as executor:
      # Submit first chunk ahead, then overlap CPU chunk k+1 with GPU OCR + reconstruction on chunk k
      pending_futures = [executor.submit(B_processSinglePageCpu, p_idx) for p_idx in chunks_array[0]] if chunks_array else []

      for i in range(len(chunks_array)):
        next_futures = []
        if i + 1 < len(chunks_array):
          next_futures = [executor.submit(B_processSinglePageCpu, p_idx) for p_idx in chunks_array[i + 1]]

        batch_cpu_pages = [fut.result() for fut in pending_futures]
        pending_futures = next_futures

        # Recognise main page tokens and any landscape upright header tokens in batched GPU calls
        active_pages = [p for p in batch_cpu_pages if not p["is_blank"]]
        if active_pages:
          self.ocr_engine.C_populatePageTokens(active_pages)
          ph_wrappers = [
            {"ocr_jobs": p["ph_ocr_jobs"], "tokens": p["ph_tokens"]}
            for p in active_pages if p["ph_tokens"]
          ]
          if ph_wrappers:
            self.ocr_engine.C_populatePageTokens(ph_wrappers)

        for x in range(len(batch_cpu_pages)):
          cp = batch_cpu_pages[x]
          processed_count = processed_count + 1
          pct_complete = float((100.0*processed_count)/max(1, num_pages))
          pdf_page_1based = int(cp["page_index"]) + 1

          if cp["is_blank"]:
            page_lbl = self.cfg_loader.formatLocalisedString("page_label_plain", [pdf_page_1based])
            tbl_lbl = self.cfg_loader.formatLocalisedString("table_label_none", [])
            print(
              self.cfg_loader.formatLocalisedString("table_read_progress", [vol_task["volume_id"], page_lbl, tbl_lbl, pct_complete]),
              flush=True
            )
            continue

          hdr_meta = self.section_assembler.A_extractPageHeaderMetadata(
            cp["tokens"],
            cp["ph_tokens"],
            cp["table_blocks"]
          )
          live_sec_id = self.updateLiveSectionState(live_state_obj, hdr_meta)
          book_folio = hdr_meta.get("book_page")
          if book_folio:
            page_lbl = self.cfg_loader.formatLocalisedString("page_label_with_folio", [pdf_page_1based, book_folio])
          else:
            page_lbl = self.cfg_loader.formatLocalisedString("page_label_plain", [pdf_page_1based])

          p_info = {
            "banner_bottom_y": hdr_meta.get("banner_bottom_y", 0.0),
            "book_page": book_folio,
            "orientation": cp["orientation"],
            "pdf_page": cp["page_index"],
            "region_header": hdr_meta.get("region_header")
          }
          tables = self.reconstructor.D_reconstructPageTables(p_info, cp["table_blocks"], cp["tokens"])
          valid_tables = [t for t in tables if t.get("rows")]

          if valid_tables:
            for y in range(len(valid_tables)):
              tbl_name = self.formatTableDisplayName(live_sec_id, valid_tables[y], y, len(valid_tables))
              tbl_lbl = self.cfg_loader.formatLocalisedString("table_label_named", [tbl_name])
              print(
                self.cfg_loader.formatLocalisedString("table_read_progress", [vol_task["volume_id"], page_lbl, tbl_lbl, pct_complete]),
                flush=True
              )
          else:
            tbl_lbl = self.cfg_loader.formatLocalisedString("table_label_none", [])
            print(
              self.cfg_loader.formatLocalisedString("table_read_progress", [vol_task["volume_id"], page_lbl, tbl_lbl, pct_complete]),
              flush=True
            )

          page_records_array.append({
            "header_meta": hdr_meta,
            "orientation": cp["orientation"],
            "pdf_page": cp["page_index"],
            "tables": tables
          })

    #Return statement
    return page_records_array


  def D_runPipeline (self, arg1_options=None):
    """
    @brief Step D: Execute full digitisation pipeline across resolved volume(s) and write per-section JSON + manifest.
    @param arg1_options Optional execution filter dictionary (volume_id, pdf_path, start_page, end_page, write_manifest).
    @return Dictionary summarising all digitised volumes and exported section JSON files.
    """
    #Convert from parameters
    options = arg1_options if isinstance(arg1_options, dict) else {}

    #Declare local instance variables
    all_volume_summaries_array = []
    t_all_start = time.time()
    tasks_array = self.B_resolveTargetVolumes(options)
    total_sections = 0

    if not tasks_array:
      sys.stderr.write("Console error: no matching PDF volumes found to process.\n")
      return {"total_sections": 0, "volumes": []}

    json_rel_dir = self.pipeline_cfg.get("output", {}).get("json_dir", os.path.join("output", "json"))
    json_root_dir = os.path.join(self.root_dir, json_rel_dir)
    os.makedirs(json_root_dir, exist_ok=True)

    for i in range(len(tasks_array)):
      vt = tasks_array[i]
      t_v0 = time.time()
      page_records = self.C_processVolumePages(vt)
      sec_summaries = self.section_assembler.C_exportVolumeSections(vt, page_records, self.root_dir)
      dt_v = round(time.time() - t_v0, 2)

      vol_out_dir = os.path.join(json_root_dir, vt["volume_id"])
      print(
        self.cfg_loader.formatLocalisedString("volume_completed", [vt["volume_id"], dt_v, len(sec_summaries), vol_out_dir]),
        flush=True
      )
      total_sections = total_sections + len(sec_summaries)
      all_volume_summaries_array.append({
        "elapsed_seconds": dt_v,
        "pdf_filename": vt["pdf_filename"],
        "section_count": len(sec_summaries),
        "sections": sec_summaries,
        "volume_id": vt["volume_id"],
        "volume_title": vt["volume_title"]
      })

    if options.get("write_manifest", True):
      manifest_path = os.path.join(json_root_dir, "manifest.json")
      with open(manifest_path, "wb") as local_fh:
        local_fh.write(orjson.dumps({
          "generated_timezone": "GMT+0",
          "total_sections": total_sections,
          "volumes": all_volume_summaries_array
        }, option=orjson.OPT_INDENT_2))

    dt_total = round(time.time() - t_all_start, 2)
    print(
      self.cfg_loader.formatLocalisedString("summary_all_done", [len(all_volume_summaries_array), total_sections, dt_total]),
      flush=True
    )

    #Return statement
    return {
      "elapsed_seconds": dt_total,
      "total_sections": total_sections,
      "volumes": all_volume_summaries_array
    }


  def formatTableDisplayName (self, arg1_sec_id, arg2_table_obj, arg3_table_idx, arg4_num_tables):
    """
    @brief Build a concise human-readable table identifier (e.g. 'A1 (Algeria)', 'A2 (MALI / NIGERIA)', 'C1') for progress logs.
    @param arg1_sec_id Active section code string or None.
    @param arg2_table_obj Reconstructed table dictionary.
    @param arg3_table_idx Zero-based index of this table on the page.
    @param arg4_num_tables Total valid tables on the page.
    @return Clean table label string.
    """
    #Convert from parameters
    sec_id = str(arg1_sec_id or "").strip()
    tbl = arg2_table_obj if isinstance(arg2_table_obj, dict) else {}
    tbl_idx = int(arg3_table_idx)
    num_tbls = int(arg4_num_tables)

    #Declare local instance variables
    abv_list = [str(p.get("text", "")).strip() for p in tbl.get("above_phrases", []) if str(p.get("text", "")).strip()]
    raw_sub = str(tbl.get("subtable_title") or "").strip()
    reject_re = r"^(?:NOTES|FOOTNOTES|Key\b|circa|Date|See\s+pp?\.|The\s+population\b|Included\s+from\b)"
    sec_prefix = sec_id if sec_id else "?"
    sub_label = ""

    if abv_list:
      sub_label = " / ".join(abv_list)
    elif raw_sub:
      cand = raw_sub
      if " - " in cand:
        parts = [
          p.strip() for p in cand.split(" - ")
          if p.strip() and "=" not in p and len(p.split()) <= 6 and not re.match(reject_re, p.strip(), re.IGNORECASE)
        ]
        cand = parts[0] if parts else ""
      cand = re.sub(r"([A-Za-z.)])[?*'‘’`´]+\d{0,2}$", r"\1", cand).strip()
      cand = re.sub(r"([A-Za-z]{3,}?)[zZ]{2}$", r"\1", cand).strip()
      if cand and "=" not in cand and len(cand.split()) <= 8 and not re.match(reject_re, cand, re.IGNORECASE):
        sub_label = cand

    #Return statement
    if sub_label:
      return f"{sec_prefix} ({sub_label})"
    elif num_tbls > 1:
      return f"{sec_prefix} (#{tbl_idx + 1})"
    else:
      return sec_prefix


  def updateLiveSectionState (self, arg1_live_state_obj, arg2_hdr_meta_obj):
    """
    @brief Maintain live monotonic section state across streaming pages for real-time progress readout.
    @param arg1_live_state_obj Mutable dictionary tracking chap, num, sec_id, and sfx.
    @param arg2_hdr_meta_obj Extracted page header metadata dictionary.
    @return Current active section ID string or None.
    """
    #Convert from parameters
    state = arg1_live_state_obj
    hdr_meta = arg2_hdr_meta_obj if isinstance(arg2_hdr_meta_obj, dict) else {}

    #Declare local instance variables
    cand = hdr_meta.get("raw_section_id")
    chap_hint = hdr_meta.get("chapter_hint")
    is_cont = bool(hdr_meta.get("is_continued", False))
    valid_chaps = {"A", "B", "C", "D", "E", "F", "G", "H", "I", "J"}

    if cand is not None:
      c_let, c_num, c_sfx = self.section_assembler.splitSectionCode(cand)
      if c_let in valid_chaps:
        active_chap = state["chap"]
        active_num = state["num"]
        if active_chap is None:
          if (c_let == "A" and 1 <= c_num <= 3) or (chap_hint == c_let and 1 <= c_num <= 30) or (not is_cont and c_let != "I" and 1 <= c_num <= 30):
            state["sec_id"], state["chap"], state["num"], state["sfx"] = cand, c_let, c_num, c_sfx
        elif c_let == active_chap:
          if c_num == active_num:
            if not (state["sfx"] and not c_sfx and is_cont):
              state["sec_id"], state["sfx"] = cand, c_sfx
          elif active_num < c_num <= active_num + 4:
            state["sec_id"], state["chap"], state["num"], state["sfx"] = cand, c_let, c_num, c_sfx
        elif ord(c_let) == ord(active_chap) + 1 and 1 <= c_num <= 3:
          state["sec_id"], state["chap"], state["num"], state["sfx"] = cand, c_let, c_num, c_sfx
        elif ord(c_let) > ord(active_chap) and chap_hint == c_let and 1 <= c_num <= 3:
          state["sec_id"], state["chap"], state["num"], state["sfx"] = cand, c_let, c_num, c_sfx

    #Return statement
    return state["sec_id"]

