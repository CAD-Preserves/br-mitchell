"""@brief Canonical geographic place-key normaliser, OCR artefact healer and non-place indicator filter."""

import re
import unicodedata


class PlaceKeyNormaliser:
  """@brief Normalises country, province and city names into snake_case keys and rejects numeric, unit or indicator strings."""

  def __init__ (self, arg1_config_obj):
    """
    @brief Initialise PlaceKeyNormaliser with configured administrative, region, unit and indicator vocabularies.
    @param arg1_config_obj Pipeline configuration dictionary loaded from /common/digitiser/.
    """
    #Convert from parameters
    config_obj = arg1_config_obj if isinstance(arg1_config_obj, dict) else {}

    #Declare local instance variables
    flat_cfg = config_obj.get("series_flattening", {})
    self.admin_nouns_set = {str(a).lower() for a in flat_cfg.get("admin_division_nouns", [])}
    self.country_sup_stems_set = {
      "algeria", "angola", "argentina", "australia", "austria", "bolivia", "bulgaria", "burma",
      "canada", "china", "colombia", "cuba", "ghana", "guatemala", "guyana", "india", "indonesia",
      "italy", "jamaica", "kenya", "korea", "malaysia", "nicaragua", "nigeria", "panama",
      "romania", "russia", "syria", "tunisia", "uganda", "venezuela", "yugoslavia", "zambia"
    }
    self.incomplete_geo_prefixes_set = {
      "burkina", "central", "costa", "east", "eastern", "ei", "el", "hong", "inner", "lower",
      "new", "north", "northern", "outer", "papua", "puerto", "saint", "san", "santa", "santo",
      "sao", "saudi", "sierra", "south", "southern", "sri", "st", "upper", "west", "western"
    }
    self.indicator_vocab_set = {str(w).lower() for w in flat_cfg.get("pure_sector_and_indicator_vocab", [])}
    self.macro_regions_set = {str(m).lower() for m in flat_cfg.get("macro_regions", [])}
    self.prose_verbs_set = {
      "are", "bases", "cubic", "estimated", "excluded", "given", "had", "has", "have",
      "included", "is", "metres", "output", "predominated", "refer", "refers", "round",
      "shown", "was", "were"
    }
    self.reserved_keys_set = {"name", "subtitle"}
    self.stopwords_set = {
      "a", "all", "an", "and", "as", "at", "by", "etc", "except", "follows", "for", "from", "in",
      "indicated", "of", "on", "or", "other", "others", "otherwise", "over", "per", "stated", "the",
      "to", "total", "totals", "under", "unknown", "unless", "with"
    }
    self.unit_vocab_set = {str(u).lower() for u in flat_cfg.get("unit_vocab", [])}
    self.valid_two_letter_places_set = {"gb", "uk", "us"}
    self.whole_qualifiers_set = {str(q).lower() for q in flat_cfg.get("whole_entity_qualifiers", [])}


  def A_normalisePlaceKey (self, arg1_raw_place_str):
    """
    @brief Step A: Heal OCR artefacts, strip footnote numbers, units and admin scopes, and return a validated place key.
    @param arg1_raw_place_str Raw place heading, column label or row stub string.
    @return Clean snake_case place key, or empty string if invalid.
    """
    #Convert from parameters
    work = str(arg1_raw_place_str or "").strip()

    if not work:
      return ""

    # 1. Reject footnotes, legends and prose clauses immediately
    if re.match(r"^(?:NOTES|FOOTNOTES|Key\b|Abbreviations|circa\b|Date\b|See\s*pp?\.|Seep\.|The\s+population\b|Included\s+from\b|Superior\s+figure)", work, re.IGNORECASE):
      return ""
    if re.search(r"\b(?:as\s+follows|following\s+earlier|otherwise\s+indicated|unless\s+otherwise|per\s+1[\s,_]*000|under\s+one\s+year|censuses\s+in|migrations?\s+in|migrants\s+in|vital\s+statistics|population\s+estimates|population\s+of\s+countries|of\s+countries\s+in)\b", work, re.IGNORECASE):
      return ""
    if "=" in work:
      return ""

    work = re.sub(r"\s*\((?:continued|cont['’]?d?\.?)\)\s*", " ", work, flags=re.IGNORECASE).strip()

    # 2. Heal OCR '0' -> 'O' on apostrophe place names (e.g. "0'Higgins" -> "O'Higgins")
    work = re.sub(r"\b0(['`‘’\s]+)(Higgins|Donnell|Connor|Brien|Neill)\b", r"O'\2", work, flags=re.IGNORECASE)
    work = re.sub(r"^0['`‘’]([A-Za-z])", r"O'\1", work)

    # 3. Strip leading footnote/list numbers ('1 Chile', '6 Austria', '2. Northern Ireland')
    work = re.sub(r"^\d{1,2}[.):\-]?\s+(?=[A-Za-z])", "", work).strip()

    # 4. Strip whole-country numbered notes ('Ireland 1. The Whole Country' -> 'Ireland') and inline footnote numbers
    work = re.sub(r"\s+\d{1,2}[.)]?\s+(?:the\s+)?whole\s+country\b.*$", "", work, flags=re.IGNORECASE).strip()
    work = re.sub(r"(?<=[A-Za-z,(\s])\b\d{1,3}[.)]?\s+(?=[A-Z])", " ", work)

    # 5. Collapse spaced/dotted sovereign initialisms ('U. K.' / 'U K' / 'Ukk' -> 'UK', 'U. S. A.' -> 'USA')
    work = re.sub(r"\bU\.?\s*S\.?\s*S\.?\s*R\.?(?=\b|\s|$|\d)", "USSR", work)
    work = re.sub(r"\bU\.?\s*S\.?\s*A\.?(?=\b|\s|$|\d)", "USA", work)
    work = re.sub(r"\bU\.?\s*A\.?\s*R\.?(?=\b|\s|$|\d)", "UAR", work)
    work = re.sub(r"\bU\.?\s*A\.?\s*E\.?(?=\b|\s|$|\d)", "UAE", work)
    work = re.sub(r"\bU\.?\s*[Kk]{1,2}\.?(?=\b|\s|$|\d)", "UK", work)
    work = re.sub(r"\b(?:[A-Za-z]\.\s*){2,}", lambda m: re.sub(r"[.\s]+", "", m.group(0)), work)

    # 6. Strip administrative-division scope suffixes in A3 ('ARGENTINA (provinces)' -> 'ARGENTINA', 'USA (states)' -> 'USA')
    paren_m = re.search(r"\(([^()]+)\)\s*$", work)
    if paren_m:
      inside_slug = self.toSnakeSlug(paren_m.group(1))
      inside_words = [w for w in inside_slug.split("_") if w and not w.isdigit()]
      allowed_admin = self.admin_nouns_set | {"all", "and", "country", "in", "major", "of", "the", "whole"}
      if inside_words and all(w in allowed_admin for w in inside_words):
        work = work[:paren_m.start()].strip()

    # 7. Reject pure unit strings and strip trailing unit/currency sub-headers concatenated onto country titles
    if re.match(r"^(?:in\s+)?(?:thousands?|millions?|billions?|hundreds?|metric\s+tons?|rates?\s+per)\b", work, re.IGNORECASE):
      return ""
    work = re.sub(r"\s*\((?:in\s+|per\s+)[^()]*\)\s*$", "", work, flags=re.IGNORECASE).strip()
    work = re.sub(
      r"\s+(?:\d{1,2}\s+)?(?:in\s+)?(?:thousands?|millions?|billions?|hundreds?|metric\s+tons?|tons?|tonnes?|shillings?|pounds?|dollars?|francs?|marks?|kroner|kronor|kronen|lire|pesetas|pesos|lei|dinars|yen|yuan|rupees|roubles|rubles|florins|guilders|escudos|australes|cruzeiros|bolivares|guaranies|soles|sucres|cordobas|quetzales|colones|lempiras|gourdes|baht|won|ringgit|zaires)\b.*$",
      "",
      work,
      flags=re.IGNORECASE
    ).strip()

    # 8. Strip attached superscript footnote digits ('Russia4 USSR' -> 'Russia USSR', 'India 2' -> 'India')
    work = re.sub(r"([A-Za-z]{2,})['`‘’*?]*\d{1,2}[oOlIzZsS]?(?=\b|\s|$|/|,)", r"\1", work)
    work = re.sub(r"\s+\d{1,2}(?:,\s*\d{1,2})*$", "", work).strip()
    work = re.sub(r"([A-Za-z]{3,}?)[zZ]{2}$", r"\1", work).strip()

    slug = self.toSnakeSlug(work)
    if slug == "ukk":
      slug = "uk"
    elif slug == "us":
      slug = "usa"
    elif len(slug) >= 5 and slug[-1] in ["l", "t"] and slug[:-1] in self.country_sup_stems_set:
      slug = slug[:-1]

    # Heal compound slugs where first token had trailing superscript 'l'/'t' (e.g. 'austrial_hungary' -> 'austria_hungary')
    if "_" in slug:
      parts = slug.split("_")
      fixed_parts = []
      for i in range(len(parts)):
        p = parts[i]
        if p == "ukk":
          p = "uk"
        elif len(p) >= 5 and p[-1] in ["l", "t"] and p[:-1] in self.country_sup_stems_set:
          p = p[:-1]
        if not p.isdigit():
          fixed_parts.append(p)
      slug = "_".join(fixed_parts)

    #Return statement
    return slug if self.B_isValidPlaceKey(slug) else ""


  def B_isValidPlaceKey (self, arg1_slug_str):
    """
    @brief Step B: Strictly validate a candidate snake_case place key against numbers, years, prices, units and sectors.
    @param arg1_slug_str Candidate snake_case place slug.
    @return Boolean True if slug is a valid geographic place identifier.
    """
    #Convert from parameters
    slug = str(arg1_slug_str or "").strip()

    if not slug or slug in self.reserved_keys_set:
      return False
    if len(slug) <= 1:
      return False
    if len(slug) == 2 and slug not in self.valid_two_letter_places_set:
      return False
    if re.match(r"^\d", slug):
      return False
    if re.match(r"^[a-c]_\d{4}_100$", slug) or "price" in slug:
      return False
    if slug in self.incomplete_geo_prefixes_set or slug in self.admin_nouns_set or slug in self.macro_regions_set:
      return False
    if slug.startswith(("both_sexes_", "females_", "males_")):
      return False
    if re.match(r"^[a-d]_(?:africa|america|americas|asia|oceania|europe|north_america|central_america|south_america)\b", slug):
      return False
    if slug in self.indicator_vocab_set or slug in self.stopwords_set or slug in self.unit_vocab_set:
      return False

    prose_markers = (
      "_in_thousand", "_in_million", "_metric_ton", "_per_1_000", "_per_1000",
      "as_follows", "following_earlier", "otherwise_indicated", "stated_unit",
      "linear_metres", "square_metres", "round_wood"
    )
    for i in range(len(prose_markers)):
      if prose_markers[i] in slug:
        return False

    parts = [p for p in slug.split("_") if p]
    if not parts or len(parts) > 8:
      return False
    if any(p in self.prose_verbs_set for p in parts):
      return False

    non_place_words = self.indicator_vocab_set | self.unit_vocab_set | self.stopwords_set
    if all((p in non_place_words or p.isdigit()) for p in parts):
      return False

    #Return statement
    return True


  def C_classifySubtableHeading (self, arg1_subtable_title):
    """
    @brief Step C: Classify a sub-table heading as either a geographic place_key or a commodity/price indicator_prefix.
    @param arg1_subtable_title Raw subtable_title string or None.
    @return Dictionary with 'place_key' and 'indicator_prefix' (at most one non-None).
    """
    #Convert from parameters
    raw_t = str(arg1_subtable_title or "").strip()

    if not raw_t:
      return {"indicator_prefix": None, "place_key": None}

    # Ignore regional divider banners ('SOUTH AMERICA: WHOLESALE PRICE INDICES 1955-2005', 'A. ASIA: OUTPUT OF WOOD')
    if re.match(r"^(?:[A-D]\.\s*)?(?:AFRICA|ASIA|OCEANIA|EUROPE|NORTH\s+AMERICA|CENTRAL\s+AMERICA|SOUTH\s+AMERICA)\b", raw_t, re.IGNORECASE):
      return {"indicator_prefix": None, "place_key": None}

    work = re.sub(r"\s*\((?:continued|cont['’]?d?\.?)\)\s*", " ", raw_t, flags=re.IGNORECASE).strip()
    work = re.sub(r"^[A-D]\.\s+", "", work).strip()
    if " - " in work:
      segments = [s.strip() for s in work.split(" - ") if s.strip()]
      for i in range(len(segments)):
        cand_place = self.A_normalisePlaceKey(segments[i])
        if cand_place and cand_place not in self.macro_regions_set:
          return {"indicator_prefix": None, "place_key": cand_place}
      work = segments[0] if segments else ""

    place_slug = self.A_normalisePlaceKey(work)
    if place_slug and place_slug not in self.macro_regions_set:
      return {"indicator_prefix": None, "place_key": place_slug}

    # Check if heading is a commodity or price-scope sub-table title (e.g. 'BAUXITE (in thousands of metric tons)', 'COFFEE')
    stripped = re.sub(r"\([^()]*\)", " ", work)
    stripped = re.sub(r"\b(?:in\s+)?(?:thousands?|millions?|billions?|metric\s+tons?|tons?|tonnes?)\b.*$", "", stripped, flags=re.IGNORECASE).strip()
    stripped = re.sub(r"pricess\b", "prices", stripped, flags=re.IGNORECASE)
    ind_slug = self.toSnakeSlug(stripped)
    if ind_slug:
      ind_parts = [p for p in ind_slug.split("_") if p]
      if 1 <= len(ind_parts) <= 4 and all(p in self.indicator_vocab_set or (p.isdigit() and "prices" in ind_parts) for p in ind_parts):
        return {"indicator_prefix": ind_slug, "place_key": None}

    #Return statement
    return {"indicator_prefix": None, "place_key": None}


  def isIndicatorPhrase (self, arg1_text_str):
    """
    @brief Check whether a column header or row phrase consists solely of economic sector, commodity or demographic words.
    @param arg1_text_str Candidate phrase string.
    @return Boolean True if phrase is a pure non-geographic indicator.
    """
    #Convert from parameters
    slug = self.toSnakeSlug(arg1_text_str)

    if not slug:
      return True
    if slug in self.indicator_vocab_set or "price" in slug:
      return True

    parts = [p for p in slug.split("_") if p]
    allowed = self.indicator_vocab_set | self.unit_vocab_set | self.stopwords_set

    #Return statement
    return bool(parts) and all((p in allowed or p.isdigit()) for p in parts)


  def isMacroRegion (self, arg1_text_str):
    """
    @brief Check whether a header segment is a continent/macro-region label (e.g. 'NORTH AMERICA', 'EUROPE').
    @param arg1_text_str Candidate segment string.
    @return Boolean True if macro-region slug.
    """
    #Convert from parameters
    slug = self.toSnakeSlug(arg1_text_str)

    #Return statement
    return slug in self.macro_regions_set


  def toSnakeSlug (self, arg1_raw_str):
    """
    @brief Transliterate Latin diacritics to ASCII and convert any phrase into clean lowercase snake_case.
    @param arg1_raw_str Arbitrary label string.
    @return Clean snake_case identifier string.
    """
    #Convert from parameters
    raw_str = str(arg1_raw_str or "").strip()

    if not raw_str:
      return ""

    work = raw_str.replace("ß", "ss").replace("Æ", "AE").replace("æ", "ae").replace("Œ", "OE").replace("œ", "oe")
    work = work.replace("&", " and ")
    norm = unicodedata.normalize("NFKD", work)
    ascii_str = "".join(ch for ch in norm if not unicodedata.combining(ch))
    slug = re.sub(r"[^A-Za-z0-9]+", "_", ascii_str.lower())
    slug = re.sub(r"_+", "_", slug).strip("_")

    #Return statement
    return slug

