"""@brief End-to-end reusable CV + GPU OCR table digitisation pipeline orchestrator."""

from concurrent.futures import ProcessPoolExecutor
import os
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
    arch_name = self.pipeline_cfg.get("ocr", {}).get("architecture", "parseq")
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

    page_records_array = []
    processed_count = 0
    total_tokens_count = 0
    t_vol_start = time.time()

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
          if cp["is_blank"]:
            continue

          total_tokens_count = total_tokens_count + len(cp["tokens"])
          hdr_meta = self.section_assembler.A_extractPageHeaderMetadata(
            cp["tokens"],
            cp["ph_tokens"],
            cp["table_blocks"]
          )
          p_info = {
            "book_page": hdr_meta.get("book_page"),
            "orientation": cp["orientation"],
            "pdf_page": cp["page_index"],
            "region_header": hdr_meta.get("region_header")
          }
          tables = self.reconstructor.D_reconstructPageTables(p_info, cp["table_blocks"], cp["tokens"])
          nf_obj = self.section_assembler.C_extractNotesAndFootnotes(cp["tokens"], cp["table_blocks"])

          page_records_array.append({
            "header_meta": hdr_meta,
            "notes_and_footnotes": nf_obj,
            "orientation": cp["orientation"],
            "pdf_page": cp["page_index"],
            "tables": tables
          })

        processed_count = processed_count + len(batch_cpu_pages)
        elapsed = max(0.001, time.time() - t_vol_start)
        tok_rate = self.cfg_loader.formatEuropeanNumber(total_tokens_count/elapsed)
        print(
          self.cfg_loader.formatLocalisedString("page_progress", [vol_task["volume_id"], processed_count, num_pages, tok_rate]),
          flush=True
        )

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
      sec_summaries = self.section_assembler.D_exportVolumeSections(vt, page_records, self.root_dir)
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

