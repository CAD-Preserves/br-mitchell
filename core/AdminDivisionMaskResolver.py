"""@brief Resolves modern and historical administrative divisions (1750-2025) across all 57 IHS A3 sub-tables."""

import re
import sys
import numpy as np


class AdminDivisionMaskResolver:
  """@brief Resolves sub-national states, provinces, crownlands, guberniyas, counties, Bezirke, and princely agencies."""

  def __init__ (self, arg1_fetcher, arg2_rasteriser, arg3_country_resolver, arg4_admin_rules_obj):
    """
    @brief Initialise AdminDivisionMaskResolver with fetcher, rasteriser, CountryMaskResolver, and admin_division_rules.json5.
    @param arg1_fetcher GeoJsonFetcher instance.
    @param arg2_rasteriser EquirectangularRasteriser instance.
    @param arg3_country_resolver CountryMaskResolver instance (with countries already resolved).
    @param arg4_admin_rules_obj Parsed admin_division_rules.json5 dictionary.
    """
    #Convert from parameters
    fetcher = arg1_fetcher
    rasteriser = arg2_rasteriser
    country_resolver = arg3_country_resolver
    admin_rules_obj = arg4_admin_rules_obj if isinstance(arg4_admin_rules_obj, dict) else {}

    #Declare local instance variables
    self.country_resolver = country_resolver
    self.delegated_cities_map = {}
    self.divisions_cfg = admin_rules_obj.get("divisions", {})
    self.fetcher = fetcher
    self.groups_cfg = admin_rules_obj.get("groups", {})
    self.rasteriser = rasteriser
    self.resolved_divisions_obj = {}
    self.resolved_groups_obj = {}


  def A_discoverDelegatedCityKeys (self, arg1_a3_sections_map):
    """
    @brief Step A: Scan all A3 section dictionaries and return city keys delegated to CityMaskResolver (europe/A3 spillovers).
    @param arg1_a3_sections_map Dictionary mapping volume_id -> A3 section dictionary.
    @return Sorted list of canonical city_id strings referenced by A3 groups.
    """
    #Convert from parameters
    a3_sections_map = arg1_a3_sections_map if isinstance(arg1_a3_sections_map, dict) else {}

    #Declare local instance variables
    city_keys_set = set()
    vol_ids = sorted(a3_sections_map.keys())

    for i in range(len(vol_ids)):
      local_vol = vol_ids[i]
      sec_obj = a3_sections_map[local_vol]
      if not isinstance(sec_obj, dict):
        continue
      for local_gk, local_gval in sec_obj.items():
        if local_gk in ("name", "subtitle") or not isinstance(local_gval, dict):
          continue
        g_cfg = self.groups_cfg.get(f"{local_vol}:{local_gk}", {})
        prefix = str(g_cfg.get("prefix") or local_gk)
        default_layer = str(g_cfg.get("default_layer") or "")
        if default_layer == "city_delegate":
          city_keys_set.add(local_gk)
        stems_map = self.extractGroupStems(local_gval)
        for local_stem in stems_map.keys():
          div_rule = self.divisions_cfg.get(f"{prefix}:{local_stem}", {})
          if default_layer == "city_delegate" or div_rule.get("layer") == "city_delegate":
            target_city = str(div_rule.get("city_key") or local_stem)
            city_keys_set.add(target_city)
            self.delegated_cities_map[f"{local_vol}:{local_gk}:{local_stem}"] = target_city

    #Return statement
    return sorted(city_keys_set)


  def B_resolveAllAdminDivisions (self, arg1_a3_sections_map):
    """
    @brief Step B: Resolve and rasterise every administrative division stem and parent A3 group across all three volumes.
    @param arg1_a3_sections_map Dictionary mapping volume_id -> A3 section dictionary.
    @return Dictionary containing 'divisions' and 'groups' resolved entity maps.
    """
    #Convert from parameters
    a3_sections_map = arg1_a3_sections_map if isinstance(arg1_a3_sections_map, dict) else {}

    #Declare local instance variables
    vol_ids = sorted(a3_sections_map.keys())

    for i in range(len(vol_ids)):
      local_vol = vol_ids[i]
      sec_obj = a3_sections_map[local_vol]
      if not isinstance(sec_obj, dict):
        continue
      group_keys = sorted(k for k in sec_obj.keys() if k not in ("name", "subtitle") and isinstance(sec_obj[k], dict))
      for x in range(len(group_keys)):
        local_gk = group_keys[x]
        local_gval = sec_obj[local_gk]
        g_cfg = self.groups_cfg.get(f"{local_vol}:{local_gk}", {
          "country": local_gk.upper()[:3],
          "default_layer": "ne_admin1",
          "era_type": "modern",
          "prefix": local_gk
        })
        stems_map = self.extractGroupStems(local_gval)
        stem_keys = sorted(stems_map.keys())
        group_delegated_cities = {}
        group_member_indices = []
        group_stem_entities = {}

        for y in range(len(stem_keys)):
          local_stem = stem_keys[y]
          years_span = stems_map[local_stem]["years"]
          delegate_key = f"{local_vol}:{local_gk}:{local_stem}"
          if delegate_key in self.delegated_cities_map:
            group_delegated_cities[local_stem] = self.delegated_cities_map[delegate_key]
            continue

          div_rec = self.resolveSingleDivision(local_vol, local_gk, g_cfg, local_stem, years_span)
          group_stem_entities[local_stem] = div_rec["entity_id"]
          if div_rec["flat_indices"].size > 0:
            group_member_indices.append(div_rec["flat_indices"])

        # Also include header-division polygon if the A3 group header itself is a spilled division (e.g. ufa, sardinia, yorkshire)
        extra_header_idx = self.resolveSpilledGroupHeaderMask(local_vol, local_gk, g_cfg)
        if extra_header_idx.size > 0:
          group_member_indices.append(extra_header_idx)

        group_flat = np.unique(np.concatenate(group_member_indices)) if group_member_indices else np.zeros(0, dtype=np.int32)
        group_entity_id = f"admin_group:{local_vol}:{local_gk}"
        self.resolved_groups_obj[f"{local_vol}:{local_gk}"] = {
          "category": "admin_group",
          "delegated_city_stems": group_delegated_cities,
          "entity_id": group_entity_id,
          "era_type": str(g_cfg.get("era_type", "modern")),
          "flat_indices": group_flat,
          "is_city_spillover_group": (str(g_cfg.get("default_layer") or "") == "city_delegate"),
          "metrics": self.rasteriser.computeMaskMetrics(group_flat),
          "name": f"{local_vol} A3 group: {local_gk}",
          "raw_keys_to_stem": {rk: st for st, info in stems_map.items() for rk in info["raw_keys"]},
          "source_summary": {"default_layer": g_cfg.get("default_layer"), "member_count": len(group_stem_entities)},
          "stem_to_entity_id": group_stem_entities,
          "valid_years": [1750, 2025]
        }

    #Return statement
    return {
      "divisions": self.resolved_divisions_obj,
      "groups": self.resolved_groups_obj
    }


  def cleanDivisionStem (self, arg1_raw_inner_key):
    """
    @brief Strip trailing census years, footnotes, leading OCR column numbers, and '_revised' from an A3 series key.
    @param arg1_raw_inner_key Raw inner key from an A3 group dictionary (e.g. '41_46_51_56_queensland_1841_4').
    @return Tuple (clean_stem, parsed_year_or_none).
    """
    #Convert from parameters
    raw_inner_key = str(arg1_raw_inner_key or "").strip().lower()

    #Declare local instance variables
    parsed_year = None
    stem = raw_inner_key
    yr_match = re.search(r"_(1[789]\d{2}|20\d{2})(?:_[0-9a-z]+)*$", stem)

    if yr_match:
      parsed_year = int(yr_match.group(1))
      stem = stem[:yr_match.start()]

    stem = re.sub(r"^41_46_51_56_", "", stem)
    if stem.endswith("_revised") and len(stem) > 8:
      stem = stem[:-8]

    #Return statement
    return (stem, parsed_year)


  def extractGroupStems (self, arg1_group_dict):
    """
    @brief Group all raw census series keys inside an A3 group dictionary into clean division stems and active year spans.
    @param arg1_group_dict Inner dictionary under an A3 group key.
    @return Dictionary mapping clean_stem -> {'raw_keys': [...], 'years': [min_yr, max_yr]}.
    """
    #Convert from parameters
    group_dict = arg1_group_dict if isinstance(arg1_group_dict, dict) else {}

    #Declare local instance variables
    raw_keys = sorted(group_dict.keys())
    stems_map = {}

    for i in range(len(raw_keys)):
      local_rk = raw_keys[i]
      if local_rk in ("name", "subtitle"):
        continue
      clean_stem, yr = self.cleanDivisionStem(local_rk)
      if not clean_stem:
        continue
      if clean_stem not in stems_map:
        stems_map[clean_stem] = {"raw_keys": [], "years_list": []}
      stems_map[clean_stem]["raw_keys"].append(local_rk)
      if yr is not None:
        stems_map[clean_stem]["years_list"].append(yr)

    for _, local_info in stems_map.items():
      yrs = local_info.pop("years_list")
      local_info["years"] = [min(yrs), max(yrs)] if yrs else [1750, 2025]

    #Return statement
    return stems_map


  def matchAdmin1ByNamesOrRegions (self, arg1_adm0_a3, arg2_names_list, arg3_regions_list=None, arg4_fuzzy_stem=""):
    """
    @brief Match features in ne_admin1 by country code and state/province names or region names.
    @param arg1_adm0_a3 Three-letter country code (e.g. 'FRA', 'IND', 'ITA').
    @param arg2_names_list Optional list of feature 'name' strings to match.
    @param arg3_regions_list Optional list of feature 'region' strings to match.
    @param arg4_fuzzy_stem Optional fallback stem slug when explicit names/regions lists are empty.
    @return List of matching GeoJSON Feature dictionaries.
    """
    #Convert from parameters
    adm0_a3 = str(arg1_adm0_a3 or "").strip().upper()
    names_list = arg2_names_list if isinstance(arg2_names_list, list) else []
    regions_list = arg3_regions_list if isinstance(arg3_regions_list, list) else []
    fuzzy_stem = str(arg4_fuzzy_stem or "").strip()

    #Declare local instance variables
    fc_obj = self.fetcher.A_fetchBaseLayer("ne_admin1")
    feats = fc_obj.get("features", [])
    fuzzy_compact = self.fetcher.normaliseAsciiSlug(fuzzy_stem).replace("_", "")
    matched_array = []
    name_slugs = set(self.fetcher.normaliseAsciiSlug(x).replace("_", "") for x in names_list if x)
    prefix_candidates = []
    reg_slugs = set(self.fetcher.normaliseAsciiSlug(x).replace("_", "") for x in regions_list if x)

    for i in range(len(feats)):
      local_f = feats[i]
      local_p = local_f.get("properties") or {}
      p_adm = str(local_p.get("adm0_a3") or "").upper()
      p_sov = str(local_p.get("sov_a3") or "").upper()
      if adm0_a3 and p_adm != adm0_a3 and p_sov != adm0_a3:
        continue

      p_reg_slug = self.fetcher.normaliseAsciiSlug(str(local_p.get("region") or "")).replace("_", "")
      if reg_slugs and p_reg_slug in reg_slugs:
        matched_array.append(local_f)
        continue

      cand_names = [
        str(local_p.get("name") or ""),
        str(local_p.get("name_en") or ""),
        str(local_p.get("gn_name") or ""),
        str(local_p.get("woe_name") or ""),
        str(local_p.get("name_local") or "")
      ]
      alt_txt = str(local_p.get("name_alt") or "")
      if alt_txt:
        cand_names.extend(alt_txt.split("|"))

      cand_slugs = [self.fetcher.normaliseAsciiSlug(c).replace("_", "") for c in cand_names if c]
      if name_slugs and any(cs in name_slugs for cs in cand_slugs if cs):
        matched_array.append(local_f)
      elif fuzzy_compact:
        if fuzzy_compact in cand_slugs or p_reg_slug == fuzzy_compact:
          matched_array.append(local_f)
        elif any(cs.startswith(fuzzy_compact) or fuzzy_compact.startswith(cs) for cs in cand_slugs if len(cs) >= 4):
          prefix_candidates.append(local_f)

    if not matched_array and prefix_candidates:
      matched_array = prefix_candidates

    #Return statement
    return matched_array


  def matchGadmFeatures (self, arg1_iso3, arg2_level, arg3_names_list):
    """
    @brief Match features in a UC Davis GADM 4.1 country/level layer using compact space-insensitive ASCII slugs.
    @param arg1_iso3 Three-letter ISO country code.
    @param arg2_level Integer GADM level (1 or 2).
    @param arg3_names_list List of target GADM feature names.
    @return List of matching GeoJSON Feature dictionaries.
    """
    #Convert from parameters
    iso3 = str(arg1_iso3 or "").strip().upper()
    level = int(arg2_level)
    names_list = arg3_names_list if isinstance(arg3_names_list, list) else []

    #Declare local instance variables
    fc_obj = self.fetcher.B_fetchGadmLayer(iso3, level)
    feats = fc_obj.get("features", [])
    matched_array = []
    name_field = f"NAME_{level}"
    target_slugs = set(self.fetcher.normaliseAsciiSlug(n).replace("_", "") for n in names_list if n)
    varname_field = f"VARNAME_{level}"

    for i in range(len(feats)):
      local_f = feats[i]
      local_p = local_f.get("properties") or {}
      cands = [str(local_p.get(name_field) or "")]
      var_txt = str(local_p.get(varname_field) or "")
      if var_txt:
        cands.extend(var_txt.split("|"))
      for x in range(len(cands)):
        cs = self.fetcher.normaliseAsciiSlug(cands[x]).replace("_", "")
        if cs and cs in target_slugs:
          matched_array.append(local_f)
          break

    #Return statement
    return matched_array


  def matchGermany1914Features (self, arg1_rule_obj, arg2_fallback_stem=""):
    """
    @brief Match 1914 Imperial German constituent states (STAAT_NAME) or Regierungsbezirke (REG_NAME).
    @param arg1_rule_obj Division rule dictionary with staat_names and/or reg_names.
    @param arg2_fallback_stem Optional stem slug fallback.
    @return List of matching GeoJSON Feature dictionaries.
    """
    #Convert from parameters
    rule_obj = arg1_rule_obj if isinstance(arg1_rule_obj, dict) else {}
    fallback_stem = str(arg2_fallback_stem or "")

    #Declare local instance variables
    fc_obj = self.fetcher.A_fetchBaseLayer("germany_1914")
    feats = fc_obj.get("features", [])
    matched_array = []
    reg_slugs = set(self.fetcher.normaliseAsciiSlug(n).replace("_", "") for n in rule_obj.get("reg_names", []))
    staat_slugs = set(self.fetcher.normaliseAsciiSlug(n).replace("_", "") for n in rule_obj.get("staat_names", []))
    stem_slug = self.fetcher.normaliseAsciiSlug(fallback_stem).replace("_", "")

    for i in range(len(feats)):
      local_f = feats[i]
      local_p = local_f.get("properties") or {}
      s_slug = self.fetcher.normaliseAsciiSlug(str(local_p.get("STAAT_NAME") or "")).replace("_", "")
      r_slug = self.fetcher.normaliseAsciiSlug(str(local_p.get("REG_NAME") or "")).replace("_", "")
      if (staat_slugs and s_slug in staat_slugs) or (reg_slugs and r_slug in reg_slugs):
        matched_array.append(local_f)
      elif not staat_slugs and not reg_slugs and stem_slug and (s_slug == stem_slug or r_slug == stem_slug):
        matched_array.append(local_f)

    #Return statement
    return matched_array


  def matchRussia1897Features (self, arg1_english_names_list, arg2_fallback_stem=""):
    """
    @brief Match 1897 Russian Empire governorates / oblasts by source_english property.
    @param arg1_english_names_list List of source_english names in russia_1897.
    @param arg2_fallback_stem Optional fallback stem slug.
    @return List of matching GeoJSON Feature dictionaries.
    """
    #Convert from parameters
    english_names_list = arg1_english_names_list if isinstance(arg1_english_names_list, list) else []
    fallback_stem = str(arg2_fallback_stem or "")

    #Declare local instance variables
    fc_obj = self.fetcher.A_fetchBaseLayer("russia_1897")
    feats = fc_obj.get("features", [])
    matched_array = []
    stem_slug = self.fetcher.normaliseAsciiSlug(fallback_stem).replace("_", "")
    target_slugs = set(self.fetcher.normaliseAsciiSlug(n).replace("_", "") for n in english_names_list if n)

    for i in range(len(feats)):
      local_f = feats[i]
      local_p = local_f.get("properties") or {}
      se_slug = self.fetcher.normaliseAsciiSlug(str(local_p.get("source_english") or "")).replace("_", "")
      if target_slugs and se_slug in target_slugs:
        matched_array.append(local_f)
      elif not target_slugs and stem_slug and se_slug.startswith(stem_slug):
        matched_array.append(local_f)

    #Return statement
    return matched_array


  def matchUkCountiesFeatures (self, arg1_counties_list, arg2_fallback_stem=""):
    """
    @brief Match UK ceremonial / historic counties from uk_counties, with automatic ne_admin1 GBR fallback.
    @param arg1_counties_list Explicit list of county names in uk_counties.
    @param arg2_fallback_stem Optional fallback county stem slug.
    @return List of matching GeoJSON Feature dictionaries.
    """
    #Convert from parameters
    counties_list = arg1_counties_list if isinstance(arg1_counties_list, list) else []
    fallback_stem = str(arg2_fallback_stem or "")

    #Declare local instance variables
    fc_obj = self.fetcher.A_fetchBaseLayer("uk_counties")
    feats = fc_obj.get("features", [])
    matched_array = []
    stem_slug = self.fetcher.normaliseAsciiSlug(fallback_stem).replace("_", "")
    stem_without_shire = stem_slug[:-5] if stem_slug.endswith("shire") and len(stem_slug) > 7 else stem_slug
    target_slugs = set(self.fetcher.normaliseAsciiSlug(c).replace("_", "") for c in counties_list if c)

    for i in range(len(feats)):
      local_f = feats[i]
      local_p = local_f.get("properties") or {}
      c_slug = self.fetcher.normaliseAsciiSlug(str(local_p.get("county") or "")).replace("_", "")
      if target_slugs and c_slug in target_slugs:
        matched_array.append(local_f)
      elif not target_slugs and stem_slug and c_slug in (stem_slug, stem_without_shire):
        matched_array.append(local_f)

    if not matched_array:
      search_names = counties_list if counties_list else [fallback_stem.replace("_", " ")]
      matched_array = self.matchAdmin1ByNamesOrRegions("GBR", search_names, [], fallback_stem)

    #Return statement
    return matched_array


  def resolveRuleGeometryIndices (self, arg1_rule_obj, arg2_group_cfg, arg3_clean_stem):
    """
    @brief Execute the configured geospatial lookup and scanline rasterisation for a single division rule.
    @param arg1_rule_obj Explicit division rule dictionary (or empty dict for default_layer fallback).
    @param arg2_group_cfg Group metadata dictionary from admin_division_rules.json5.
    @param arg3_clean_stem Clean division stem string.
    @return Tuple (flat_indices_array, source_summary_dict).
    """
    #Convert from parameters
    rule_obj = arg1_rule_obj if isinstance(arg1_rule_obj, dict) else {}
    group_cfg = arg2_group_cfg if isinstance(arg2_group_cfg, dict) else {}
    clean_stem = str(arg3_clean_stem or "")

    #Declare local instance variables
    adm0_code = str(rule_obj.get("adm0_a3") or group_cfg.get("country") or "").upper()
    empty_idx = np.zeros(0, dtype=np.int32)
    extra_admin1 = rule_obj.get("extra_ne_admin1", [])
    fallback_pt = rule_obj.get("lonlat_fallback")
    feats = []
    flat_idx = None
    layer_type = str(rule_obj.get("layer") or group_cfg.get("default_layer") or "ne_admin1")

    if layer_type == "country_ref":
      c_ref = str(rule_obj.get("country_ref") or clean_stem)
      c_rec = self.country_resolver.resolveSingleCountry(c_ref, set())
      return (c_rec["flat_indices"].copy(), {"country_ref": c_ref, "layer": "country_ref"})

    if layer_type == "bbox":
      bb = rule_obj.get("bbox", [0.0, 0.0, 0.1, 0.1])
      return (self.rasteriser.rasteriseBbox(bb[0], bb[1], bb[2], bb[3]), {"bbox": bb, "layer": "bbox"})

    if layer_type == "nominatim":
      q_str = str(rule_obj.get("query") or f"{clean_stem.replace('_', ' ').title()}, {adm0_code}")
      nom_geom = self.fetcher.E_fetchNominatimPolygon(q_str)
      if nom_geom is not None:
        flat_idx = self.rasteriser.A_rasteriseGeometry(nom_geom, {"fallback_lonlat": fallback_pt})
      elif fallback_pt is not None:
        flat_idx = self.rasteriser.rasterisePointDisc(float(fallback_pt[0]), float(fallback_pt[1]), 0.15)
      else:
        flat_idx = empty_idx
      return (flat_idx, {"layer": "nominatim_osm", "query": q_str})

    if layer_type == "ne_admin1":
      feats = self.matchAdmin1ByNamesOrRegions(
        adm0_code,
        rule_obj.get("names", []),
        [],
        "" if rule_obj.get("names") else clean_stem
      )
    elif layer_type == "ne_admin1_region":
      feats = self.matchAdmin1ByNamesOrRegions(
        adm0_code,
        rule_obj.get("names", []),
        rule_obj.get("regions", []),
        "" if rule_obj.get("regions") else clean_stem
      )
    elif layer_type == "british_india_1948":
      feats = self.country_resolver.matchBritishIndiaFeatures(rule_obj)
    elif layer_type == "germany_1914":
      feats = self.matchGermany1914Features(rule_obj, clean_stem)
    elif layer_type == "russia_1897":
      feats = self.matchRussia1897Features(rule_obj.get("source_english", []), clean_stem)
    elif layer_type == "galicia_habsburg":
      feats = self.fetcher.A_fetchBaseLayer("galicia_habsburg").get("features", [])
    elif layer_type == "uk_counties":
      feats = self.matchUkCountiesFeatures(rule_obj.get("counties", []), clean_stem)
    elif layer_type == "gadm" or layer_type.startswith("gadm_"):
      if layer_type.startswith("gadm_"):
        parts = layer_type.split("_")
        g_iso = parts[1]
        g_lvl = int(parts[2])
      else:
        g_iso = str(rule_obj.get("gadm_iso3") or adm0_code)
        g_lvl = int(rule_obj.get("gadm_level") or 1)
      g_names = rule_obj.get("names", [clean_stem])
      feats = self.matchGadmFeatures(g_iso, g_lvl, g_names)

    for i in range(len(extra_admin1)):
      ex_item = extra_admin1[i]
      feats.extend(self.matchAdmin1ByNamesOrRegions(ex_item.get("adm0_a3", ""), ex_item.get("names", []), ex_item.get("regions", [])))

    if feats or fallback_pt is not None:
      flat_idx = self.rasteriser.A_rasteriseGeometry(feats, {"fallback_lonlat": fallback_pt})
    else:
      q_fallback = f"{clean_stem.replace('_', ' ').title()}, {adm0_code}"
      nom_geom = self.fetcher.E_fetchNominatimPolygon(q_fallback)
      if nom_geom is not None:
        flat_idx = self.rasteriser.A_rasteriseGeometry(nom_geom)
        layer_type = f"{layer_type}->nominatim_fallback"
      else:
        flat_idx = empty_idx

    #Return statement
    return (flat_idx, {"adm0_a3": adm0_code, "feature_count": len(feats), "layer": layer_type})


  def resolveSingleDivision (self, arg1_volume_id, arg2_group_key, arg3_group_cfg, arg4_clean_stem, arg5_years_span):
    """
    @brief Resolve and cache a single canonical administrative division entity ('admin:<prefix>:<clean_stem>').
    @param arg1_volume_id Volume identifier.
    @param arg2_group_key A3 group key.
    @param arg3_group_cfg Group metadata dictionary.
    @param arg4_clean_stem Clean division stem.
    @param arg5_years_span Two-element [start_year, end_year] list.
    @return Resolved administrative division entity dictionary.
    """
    #Convert from parameters
    volume_id = str(arg1_volume_id or "")
    group_key = str(arg2_group_key or "")
    group_cfg = arg3_group_cfg if isinstance(arg3_group_cfg, dict) else {}
    clean_stem = str(arg4_clean_stem or "")
    years_span = arg5_years_span if isinstance(arg5_years_span, list) else [1750, 2025]

    #Declare local instance variables
    div_lookup_key = ""
    entity_id = ""
    flat_idx = None
    prefix = str(group_cfg.get("prefix") or group_key)
    record_obj = {}
    rule_obj = {}
    src_summary = {}

    div_lookup_key = f"{prefix}:{clean_stem}"
    entity_id = f"admin:{div_lookup_key}"
    if entity_id in self.resolved_divisions_obj:
      return self.resolved_divisions_obj[entity_id]

    rule_obj = self.divisions_cfg.get(div_lookup_key, {})
    flat_idx, src_summary = self.resolveRuleGeometryIndices(rule_obj, group_cfg, clean_stem)

    if flat_idx.size == 0:
      sys.stderr.write(f"Console error: admin division '{entity_id}' ({volume_id}:{group_key}:{clean_stem}) resolved to 0 pixels!\n")

    record_obj = {
      "category": "admin_division",
      "entity_id": entity_id,
      "era_type": str(group_cfg.get("era_type", "modern")),
      "flat_indices": flat_idx,
      "group_key": f"{volume_id}:{group_key}",
      "metrics": self.rasteriser.computeMaskMetrics(flat_idx),
      "name": f"{clean_stem.replace('_', ' ').title()} ({prefix.upper()})",
      "source_summary": src_summary,
      "valid_years": years_span
    }
    self.resolved_divisions_obj[entity_id] = record_obj

    #Return statement
    return record_obj


  def resolveSpilledGroupHeaderMask (self, arg1_volume_id, arg2_group_key, arg3_group_cfg):
    """
    @brief Provide explicit polygon indices when an A3 group key itself is a page-break spilled division (e.g. 'ufa', 'sardinia').
    @param arg1_volume_id Volume identifier.
    @param arg2_group_key Raw A3 group key.
    @param arg3_group_cfg Group metadata dictionary.
    @return 1D numpy int32 array of extra pixel indices (or empty array).
    """
    #Convert from parameters
    volume_id = str(arg1_volume_id or "")
    group_key = str(arg2_group_key or "")
    group_cfg = arg3_group_cfg if isinstance(arg3_group_cfg, dict) else {}

    #Declare local instance variables
    empty_idx = np.zeros(0, dtype=np.int32)
    rec = None

    if volume_id == "europe" and group_key == "ufa":
      rec = self.resolveSingleDivision(volume_id, group_key, group_cfg, "ufa", [1811, 1897])
      return rec["flat_indices"]
    elif volume_id == "europe" and group_key == "sardinia":
      rec = self.resolveSingleDivision(volume_id, group_key, group_cfg, "sardinia", [1770, 1857])
      return rec["flat_indices"]

    #Return statement
    return empty_idx
