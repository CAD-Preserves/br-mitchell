"""@brief Assembles page-level tables and section banners into simplified per-section JSON files."""

import os
import re
import orjson
from core.TableSeriesFlattener import TableSeriesFlattener


class SectionAssembler:
  """@brief Classifies pages into lettered-and-numbered sections (A1, A2, ...), smooths transitions, and exports flat JSON."""

  def __init__ (self, arg1_config_obj, arg2_volumes_cfg_obj):
    """
    @brief Initialise SectionAssembler with pipeline configuration, chapter titles, and TableSeriesFlattener.
    @param arg1_config_obj Pipeline configuration dictionary.
    @param arg2_volumes_cfg_obj Volumes and chapters configuration dictionary.
    """
    #Convert from parameters
    config_obj = arg1_config_obj if isinstance(arg1_config_obj, dict) else {}
    volumes_cfg_obj = arg2_volumes_cfg_obj if isinstance(arg2_volumes_cfg_obj, dict) else {}

    #Declare local instance variables
    self.chapters_map = volumes_cfg_obj.get("chapters", {})
    self.flattener = TableSeriesFlattener(config_obj)
    self.output_cfg = config_obj.get("output", {})


  def A_extractPageHeaderMetadata (self, arg1_tokens_array, arg2_portrait_header_tokens_array, arg3_table_blocks_array):
    """
    @brief Step A: Parse running header, book page number, chapter hint, and explicit section banner from page tokens.
    @param arg1_tokens_array Main page OCR tokens.
    @param arg2_portrait_header_tokens_array Optional upright running-header tokens from rotated landscape pages.
    @param arg3_table_blocks_array Detected graphical table blocks on the page.
    @return Page header metadata dictionary.
    """
    #Convert from parameters
    tokens_array = arg1_tokens_array if isinstance(arg1_tokens_array, list) else []
    ph_tokens_array = arg2_portrait_header_tokens_array if isinstance(arg2_portrait_header_tokens_array, list) else []
    table_blocks_array = arg3_table_blocks_array if isinstance(arg3_table_blocks_array, list) else []

    #Declare local instance variables
    book_page = None
    chapter_hint = None
    is_continued = False
    raw_section_id = None
    region_header = None
    section_title = None
    unit_str = None

    first_table_y = min([b["y_top"] for b in table_blocks_array], default=99999.0)

    # 1. Inspect upright portrait running header first if present (for rotated landscape pages)
    run_source = ph_tokens_array if ph_tokens_array else [t for t in tokens_array if t["y_centre"] <= 210]
    if run_source:
      run_lines = self.clusterSimpleLines(run_source, 16)
      if run_lines:
        top_run_txt = self.joinBannerLine(run_lines[0])
        book_page = self.extractBookPageNumber(run_lines[0])
        chapter_hint = self.matchChapterTitleToLetter(top_run_txt)

    # 2. Inspect top banner region above the first table block (or top 750 px on non-table pages)
    banner_limit_y = min(first_table_y - 2.0, 720.0) if table_blocks_array else 750.0
    banner_toks = [t for t in tokens_array if t["y_centre"] <= banner_limit_y and t.get("text")]
    banner_lines = self.clusterSimpleLines(banner_toks, 15)

    for i in range(len(banner_lines)):
      ln = banner_lines[i]
      ln_txt = self.joinBannerLine(ln)
      if not ln_txt:
        continue

      if book_page is None and i == 0 and ln[0]["y_centre"] <= 220:
        book_page = self.extractBookPageNumber(ln)
      if chapter_hint is None and ln[0]["y_centre"] <= 260:
        chapter_hint = self.matchChapterTitleToLetter(ln_txt)

      # Never mistake an even-page running header (e.g. '14 International Historical Statistics...') for section 'I4'
      if ln[0]["y_centre"] <= 230 or "international historical statistics" in ln_txt.lower():
        continue

      if raw_section_id is None:
        parsed_sec = self.parseSectionBannerLine(ln_txt, chapter_hint)
        if parsed_sec is not None:
          raw_section_id = parsed_sec["section_id"]
          is_continued = parsed_sec["is_continued"]
          region_header = parsed_sec["region_header"]
          section_title = parsed_sec["section_title"]
          unit_str = parsed_sec["unit"]
          # Append wrapped continuation of section title on immediate next line if above table
          if i + 1 < len(banner_lines):
            nxt_ln = banner_lines[i + 1]
            if (nxt_ln[0]["y_centre"] - ln[0]["y_centre"]) <= 68:
              nxt_txt = self.joinBannerLine(nxt_ln)
              if nxt_txt and not re.match(r"^(NOTES|FOOTNOTES|Key|Abbreviations|\d{4}\s*[-–])", nxt_txt, re.IGNORECASE):
                if section_title and ("(" in section_title and ")" not in section_title or nxt_txt.startswith("(")):
                  section_title = f"{section_title} {nxt_txt}".strip()
                  u_m = re.search(r"\(([^()]+)\)\s*$", section_title)
                  if u_m:
                    unit_str = u_m.group(1).strip()

    #Return statement
    return {
      "book_page": book_page,
      "chapter_hint": chapter_hint,
      "is_continued": is_continued,
      "raw_section_id": raw_section_id,
      "region_header": region_header,
      "section_title": section_title,
      "unit": unit_str
    }


  def B_smoothSectionAssignments (self, arg1_page_records_array):
    """
    @brief Step B: Resolve missing/noisy section IDs across volume pages using chapter monotonicity and lookahead smoothing.
    @param arg1_page_records_array Ordered list of page record dictionaries across a volume.
    @return Updated page_records_array with canonical resolved_section_id on every active section page.
    """
    #Convert from parameters
    pages_array = arg1_page_records_array if isinstance(arg1_page_records_array, list) else []

    if not pages_array:
      return []

    #Declare local instance variables
    active_chap = None
    active_num = 0
    active_sec = None
    active_sfx = ""
    n_pages = len(pages_array)
    raw_ids = [p["header_meta"].get("raw_section_id") for p in pages_array]

    # Pass 1: Sandwich repair — if p-1 and p+1 (or p+2) agree on exact section X, and p disagrees or is None, snap p -> X
    repaired_ids = list(raw_ids)
    for i in range(n_pages):
      prev_id = repaired_ids[i - 1] if i >= 1 else None
      next_1 = raw_ids[i + 1] if i + 1 < n_pages else None
      next_2 = raw_ids[i + 2] if i + 2 < n_pages else None
      if prev_id is not None and (prev_id == next_1 or (next_1 is None and prev_id == next_2)):
        repaired_ids[i] = prev_id

    # Pass 2: Forward monotonic state machine with lookahead outlier guard
    for i in range(n_pages):
      cand = repaired_ids[i]
      chap_hint = pages_array[i]["header_meta"].get("chapter_hint")
      is_cont = pages_array[i]["header_meta"].get("is_continued", False)

      if cand is None and active_chap is not None and chap_hint is not None and ord(chap_hint) == ord(active_chap) + 1:
        for x in range(i + 1, min(n_pages, i + 5)):
          if repaired_ids[x] is not None:
            nx_let, nx_num, nx_sfx = self.splitSectionCode(repaired_ids[x])
            if nx_let == chap_hint and nx_num == 1:
              active_sec, active_chap, active_num, active_sfx = repaired_ids[x], nx_let, nx_num, nx_sfx
            break

      if cand is not None:
        c_let, c_num, c_sfx = self.splitSectionCode(cand)
        if c_let in ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"]:
          if active_chap is None:
            if (c_let == "A" and 1 <= c_num <= 3) or (chap_hint == c_let and 1 <= c_num <= 30) or (not is_cont and c_let != "I" and 1 <= c_num <= 30):
              active_sec, active_chap, active_num, active_sfx = cand, c_let, c_num, c_sfx
          else:
            upcoming = [repaired_ids[k] for k in range(i + 1, min(n_pages, i + 10)) if repaired_ids[k] is not None][:3]
            reverts_back = False
            if (c_let, c_num) > (active_chap, active_num) and upcoming and cand not in upcoming:
              u_let, u_num, _ = self.splitSectionCode(upcoming[0])
              if u_let and (u_let, u_num) < (c_let, c_num):
                reverts_back = True

            if not reverts_back:
              if c_let == active_chap:
                if c_num == active_num:
                  if active_sfx and not c_sfx and is_cont:
                    pass
                  else:
                    active_sec, active_sfx = cand, c_sfx
                elif active_num < c_num <= active_num + 4:
                  active_sec, active_chap, active_num, active_sfx = cand, c_let, c_num, c_sfx
              elif ord(c_let) == ord(active_chap) + 1 and 1 <= c_num <= 3:
                active_sec, active_chap, active_num, active_sfx = cand, c_let, c_num, c_sfx
              elif ord(c_let) > ord(active_chap) and chap_hint == c_let and 1 <= c_num <= 3:
                active_sec, active_chap, active_num, active_sfx = cand, c_let, c_num, c_sfx

      pages_array[i]["resolved_section_id"] = active_sec

    # Pass 3: Re-check sandwich once more after forward propagation
    for i in range(1, n_pages - 1):
      if pages_array[i - 1]["resolved_section_id"] == pages_array[i + 1]["resolved_section_id"] and pages_array[i - 1]["resolved_section_id"] is not None:
        pages_array[i]["resolved_section_id"] = pages_array[i - 1]["resolved_section_id"]

    #Return statement
    return pages_array


  def C_exportVolumeSections (self, arg1_volume_meta_obj, arg2_page_records_array, arg3_root_dir):
    """
    @brief Step C: Flatten all pages per section (A1, A2, ...) into {<table_key>: {name, subtitle, <place_key>: {...}}} JSON files.
    @param arg1_volume_meta_obj Volume metadata dictionary (volume_id, volume_title, pdf_filename).
    @param arg2_page_records_array Ordered page records list for the volume.
    @param arg3_root_dir Repository root path.
    @return List of exported section summary dictionaries.
    """
    #Convert from parameters
    vol_meta = arg1_volume_meta_obj
    pages_array = self.B_smoothSectionAssignments(arg2_page_records_array)
    root_dir = arg3_root_dir

    #Declare local instance variables
    exported_summaries_array = []
    json_rel_dir = self.output_cfg.get("json_dir", os.path.join("output", "json"))
    sections_order_array = []
    sections_store_obj = {}
    vol_id = vol_meta["volume_id"]
    vol_out_dir = os.path.join(root_dir, json_rel_dir, vol_id)

    os.makedirs(vol_out_dir, exist_ok=True)

    for i in range(len(pages_array)):
      pr = pages_array[i]
      sec_id = pr.get("resolved_section_id")
      if not sec_id:
        continue

      h_meta = pr["header_meta"]
      if sec_id not in sections_store_obj:
        chap_let = sec_id[0]
        sections_order_array.append(sec_id)
        sections_store_obj[sec_id] = {
          "chapter_title": self.chapters_map.get(chap_let, ""),
          "pdf_pages": [],
          "section_id": sec_id,
          "section_title": h_meta.get("section_title") or "",
          "tables": [],
          "unit": h_meta.get("unit")
        }

      sec_obj = sections_store_obj[sec_id]
      if pr["pdf_page"] not in sec_obj["pdf_pages"]:
        sec_obj["pdf_pages"].append(pr["pdf_page"])

      cand_title = h_meta.get("section_title")
      if cand_title and "continued" not in cand_title.lower():
        if not sec_obj["section_title"] or (len(cand_title) > len(sec_obj["section_title"]) and len(sec_obj["section_title"]) < 18):
          sec_obj["section_title"] = cand_title
      if not sec_obj["unit"] and h_meta.get("unit"):
        sec_obj["unit"] = h_meta["unit"]

      page_tables = pr.get("tables", [])
      for x in range(len(page_tables)):
        sec_obj["tables"].append(page_tables[x])

    for i in range(len(sections_order_array)):
      sec_id = sections_order_array[i]
      sec_obj = sections_store_obj[sec_id]
      doc_obj, stats_obj = self.flattener.D_buildSectionDocument(
        sec_id,
        sec_obj["section_title"],
        sec_obj["unit"],
        sec_obj["chapter_title"],
        sec_obj["tables"]
      )
      out_path = os.path.join(vol_out_dir, f"{sec_id}.json")
      json_bytes = orjson.dumps(doc_obj, option=orjson.OPT_INDENT_2)
      with open(out_path, "wb") as local_fh:
        local_fh.write(json_bytes)

      exported_summaries_array.append({
        "data_points": stats_obj["data_points"],
        "name": stats_obj["name"],
        "output_path": out_path,
        "page_count": len(sec_obj["pdf_pages"]),
        "place_count": stats_obj["place_count"],
        "section_id": sec_id,
        "subtitle": stats_obj["subtitle"],
        "volume_id": vol_id
      })

    #Return statement
    return exported_summaries_array


  def clusterSimpleLines (self, arg1_tokens_array, arg2_y_tol_px):
    """
    @brief Cluster tokens vertically into reading-order lines sorted left-to-right.
    @param arg1_tokens_array List of token dictionaries.
    @param arg2_y_tol_px Vertical tolerance in pixels.
    @return List of sorted token lists.
    """
    #Convert from parameters
    tokens_array = arg1_tokens_array
    y_tol = float(arg2_y_tol_px)

    if not tokens_array:
      return []

    lines_array = []
    for tok in sorted(tokens_array, key=lambda t: t["y_centre"]):
      placed = False
      for x in range(len(lines_array) - 1, -1, -1):
        if abs(tok["y_centre"] - lines_array[x]["yc"]) <= y_tol:
          n = len(lines_array[x]["tokens"])
          lines_array[x]["yc"] = (lines_array[x]["yc"]*n + tok["y_centre"])/(n + 1)
          lines_array[x]["tokens"].append(tok)
          placed = True
          break
      if not placed:
        lines_array.append({"tokens": [tok], "yc": tok["y_centre"]})

    lines_array.sort(key=lambda item: item["yc"])

    #Return statement
    return [sorted(item["tokens"], key=lambda t: t["x1"]) for item in lines_array]


  def extractBookPageNumber (self, arg1_top_line_tokens):
    """
    @brief Extract printed book page number from either outer margin of the running header line.
    @param arg1_top_line_tokens Left-to-right sorted tokens on the running header line.
    @return String page number or None.
    """
    #Convert from parameters
    ln = arg1_top_line_tokens

    if not ln:
      return None

    for candidate in [ln[0]["text"], ln[-1]["text"]]:
      c_str = str(candidate).strip()
      if re.match(r"^\d{1,4}$", c_str) and not (1750 <= int(c_str) <= 2010 and len(ln) >= 3):
        return c_str

    #Return statement
    return None


  def joinBannerLine (self, arg1_line_tokens_array):
    """
    @brief Join left-to-right banner tokens with single spaces while attaching adjacent punctuation cleanly.
    @param arg1_line_tokens_array Left-to-right sorted tokens on one line.
    @return Clean joined string without false word concatenation.
    """
    #Convert from parameters
    ln = arg1_line_tokens_array

    if not ln:
      return ""

    parts_array = []
    for i in range(len(ln)):
      tok = ln[i]
      txt = str(tok.get("text", "")).strip()
      if not txt:
        continue
      if not parts_array:
        parts_array.append(txt)
        continue
      prev_tok = ln[i - 1]
      prev_txt = parts_array[-1]
      gap = tok["x1"] - prev_tok["x2"]
      if gap <= 12 and (txt in [",", ".", ":", ";", ")", "]"] or prev_txt.endswith(("(", "["))):
        parts_array[-1] = prev_txt + txt
      else:
        parts_array.append(txt)

    #Return statement
    return " ".join(parts_array).strip()


  def matchChapterTitleToLetter (self, arg1_header_text):
    """
    @brief Map a running header string (e.g. 'Agriculture', 'Education') to its canonical chapter letter A..J.
    @param arg1_header_text Running header text string.
    @return Single uppercase letter A..J or None.
    """
    #Convert from parameters
    txt = str(arg1_header_text).lower()

    for letter, title in self.chapters_map.items():
      if title.lower() in txt:
        return letter

    if "population" in txt or "vital" in txt:
      return "A"
    elif "labour" in txt or "labor" in txt:
      return "B"
    elif "agriculture" in txt:
      return "C"
    elif "industry" in txt:
      return "D"
    elif "external trade" in txt:
      return "E"
    elif "transport" in txt or "communication" in txt:
      return "F"
    elif "finance" in txt:
      return "G"
    elif "price" in txt:
      return "H"
    elif "education" in txt:
      return "I"
    elif "national account" in txt:
      return "J"

    #Return statement
    return None


  def parseSectionBannerLine (self, arg1_line_text, arg2_chapter_hint):
    """
    @brief Parse a section banner line (e.g. 'A2 AFRICA: Population... (in thousands)', '12 SOUTH AMERICA: STUDENTS...').
    @param arg1_line_text Joined banner line string.
    @param arg2_chapter_hint Optional chapter letter A..J from running header.
    @return Dictionary with section_id, region_header, section_title, unit, is_continued, or None.
    """
    #Convert from parameters
    txt = str(arg1_line_text).strip()
    chapter_hint = arg2_chapter_hint

    m = re.match(r"^([A-J1lI])([0-9lIi|]{1,2}[a-b]?)(?:_|\.)?\s+(.+)$", txt)
    if not m:
      return None

    raw_let = m.group(1)
    raw_num = m.group(2)
    rest = m.group(3).strip()

    if raw_let in ["1", "l", "I"]:
      norm_let = "I"
    else:
      norm_let = raw_let.upper()

    suffix = ""
    if raw_num[-1:].lower() in ["a", "b"] and len(raw_num) >= 2:
      suffix = raw_num[-1:].lower()
      digit_part = raw_num[:-1]
    else:
      digit_part = raw_num

    digit_part = digit_part.replace("l", "1").replace("I", "1").replace("i", "1").replace("|", "1")
    if not digit_part.isdigit():
      return None
    sec_num = int(digit_part)
    if sec_num < 1 or sec_num > 30:
      return None

    if raw_let == "1" and chapter_hint not in ["I", "H", None]:
      return None
    if norm_let == "I" and sec_num > 4:
      return None

    if re.match(r"^[\d,.\s\-–—]+$", rest):
      return None

    sec_id = f"{norm_let}{sec_num}{suffix}"
    is_cont = bool(re.search(r"\(continued\)", rest, re.IGNORECASE))

    region_hdr = None
    reg_m = re.match(r"^(AFRICA|ASIA|OCEANIA|NORTH\s+AMERICA|SOUTH\s+AMERICA|CENTRAL\s+AMERICA|EUROPE)\s*:\s*(.+)$", rest, re.IGNORECASE)
    if reg_m:
      region_hdr = re.sub(r"\s+", " ", reg_m.group(1).upper()).strip()
      rest = reg_m.group(2).strip()

    unit_str = None
    unit_m = re.search(r"\(([^()]+)\)\s*$", rest)
    if unit_m and "continued" not in unit_m.group(1).lower():
      unit_str = unit_m.group(1).strip()

    #Return statement
    return {
      "is_continued": is_cont,
      "region_header": region_hdr,
      "section_id": sec_id,
      "section_title": rest,
      "unit": unit_str
    }


  def splitSectionCode (self, arg1_sec_id):
    """
    @brief Split a canonical section ID like 'A6a' into ('A', 6, 'a').
    @param arg1_sec_id Canonical section ID string.
    @return Tuple (chapter_letter, section_number_int, suffix_str).
    """
    #Convert from parameters
    sec_id = str(arg1_sec_id)

    m = re.match(r"^([A-J])(\d+)([a-b]?)$", sec_id)
    if not m:
      return ("", 0, "")

    #Return statement
    return (m.group(1), int(m.group(2)), m.group(3))
