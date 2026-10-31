"""@brief Resolves modern and historical administrative divisions (1750-2025) across all 57 IHS A3 sub-tables."""

import re
import sys
import numpy as np


class AdminDivisionMaskResolver:
  """@brief Resolves sub-national states, provinces, crownlands, guberniyas, counties, Bezirke, and princely agencies."""

  def __init__ (self, arg1_fetcher, arg2_rasteriser, arg3_country_resolver, arg4_city_resolver, arg5_admin_rules_obj):
    """
    @brief Initialise AdminDivisionMaskResolver with fetcher, rasteriser, CountryMaskResolver, CityMaskResolver and admin_division_rules.json5.
    @param arg1_fetcher GeoJsonFetcher instance.
    @param arg2_rasteriser EquirectangularRasteriser instance.
    @param arg3_country_resolver CountryMaskResolver instance (with countries already resolved).
    @param arg4_city_resolver CityMaskResolver instance for canonical city slug normalisation.
    @param arg5_admin_rules_obj Parsed admin_division_rules.json5 dictionary.
    """
    #Convert from parameters
    fetcher = arg1_fetcher
    rasteriser = arg2_rasteriser
    country_resolver = arg3_country_resolver
    city_resolver = arg4_city_resolver
    admin_rules_obj = arg5_admin_rules_obj if isinstance(arg5_admin_rules_obj, dict) else {}

    #Declare local instance variables
    self.city_resolver = city_resolver
    self.country_resolver = country_resolver
    self.delegated_cities_map = {}
    self.divisions_cfg = admin_rules_obj.get("divisions", {})
    self.fetcher = fetcher
    self.groups_cfg = admin_rules_obj.get("groups", {})
    self.partition_sets_cfg = admin_rules_obj.get("partition_sets", [])
    self.rasteriser = rasteriser
    self.resolved_divisions_obj = {}
    self.resolved_groups_obj = {}


  def A_discoverDelegatedCityKeys (self, arg1_a3_sections_map):
    """
    @brief Step A: Scan all A3 section dictionaries and return canonical city keys delegated to CityMaskResolver (europe/A3 spillovers).
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
          city_keys_set.add(self.city_resolver.normaliseCityKey(local_gk))
        stems_map = self.extractGroupStems(local_gval)
        for local_stem in stems_map.keys():
          div_rule = self.divisions_cfg.get(f"{prefix}:{local_stem}", {})
          if default_layer == "city_delegate" or div_rule.get("layer") == "city_delegate":
            raw_city = str(div_rule.get("city_key") or local_stem)
            target_city = self.city_resolver.normaliseCityKey(raw_city)
            city_keys_set.add(target_city)
            self.delegated_cities_map[f"{local_vol}:{local_gk}:{local_stem}"] = target_city

    #Return statement
    return sorted(city_keys_set)


  def B_resolveAllAdminDivisions (self, arg1_a3_sections_map):
    """
    @brief Step B: Resolve, snap partition sets, and rasterise every administrative division stem and parent A3 group across all three volumes.
    @param arg1_a3_sections_map Dictionary mapping volume_id -> A3 section dictionary.
    @return Dictionary containing 'divisions' and 'groups' resolved entity maps.
    """
    #Convert from parameters
    a3_sections_map = arg1_a3_sections_map if isinstance(arg1_a3_sections_map, dict) else {}

    #Declare local instance variables
    group_specs_list = []
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
          "canonical_group": local_gk,
          "country": local_gk.upper()[:3],
          "default_layer": "ne_admin1",
          "era_type": "modern",
          "prefix": local_gk
        })
        stems_map = self.extractGroupStems(local_gval)
        stem_keys = sorted(stems_map.keys())
        group_delegated_cities = {}
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

        self.resolveSpilledGroupHeaderMask(local_vol, local_gk, g_cfg)
        group_specs_list.append((local_vol, local_gk, g_cfg, stems_map, group_delegated_cities, group_stem_entities))

    self.applyPartitionSets()

    for i in range(len(group_specs_list)):
      local_vol, local_gk, g_cfg, stems_map, group_delegated_cities, group_stem_entities = group_specs_list[i]
      group_member_indices = []
      for _, local_eid in sorted(group_stem_entities.items()):
        div_rec = self.resolved_divisions_obj.get(local_eid, {})
        if div_rec.get("flat_indices") is not None and div_rec["flat_indices"].size > 0 and div_rec.get("canonical_key"):
          group_member_indices.append(div_rec["flat_indices"])

      extra_header_idx = self.resolveSpilledGroupHeaderMask(local_vol, local_gk, g_cfg)
      if extra_header_idx.size > 0:
        group_member_indices.append(extra_header_idx)

      group_flat = np.unique(np.concatenate(group_member_indices)) if group_member_indices else np.zeros(0, dtype=np.int32)
      group_entity_id = f"admin_group:{local_vol}:{local_gk}"
      self.resolved_groups_obj[f"{local_vol}:{local_gk}"] = {
        "canonical_group": str(g_cfg.get("canonical_group") or ""),
        "category": "admin_group",
        "delegated_city_stems": group_delegated_cities,
        "entity_id": group_entity_id,
        "era_type": str(g_cfg.get("era_type", "modern")),
        "flat_indices": group_flat,
        "header_target": str(g_cfg.get("header_target") or ""),
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


  def applyDivisionModifiers (self, arg1_flat_indices, arg2_rule_obj, arg3_group_cfg, arg4_layer_type):
    """
    @brief Apply extra GADM/Germany-1914 unions, admin1/Germany-1914 exclusions, 10m landmask clipping, and parent country clipping.
    @param arg1_flat_indices Initial sorted 1D int32 array of flat pixel indices.
    @param arg2_rule_obj Division rule dictionary.
    @param arg3_group_cfg Group metadata dictionary.
    @param arg4_layer_type Resolved primary layer type string.
    @return Modified sorted 1D int32 array of flat pixel indices.
    """
    #Convert from parameters
    flat_indices = arg1_flat_indices
    rule_obj = arg2_rule_obj if isinstance(arg2_rule_obj, dict) else {}
    group_cfg = arg3_group_cfg if isinstance(arg3_group_cfg, dict) else {}
    layer_type = str(arg4_layer_type or "")

    #Declare local instance variables
    clip_countries = []
    excl_admin1 = rule_obj.get("exclude_admin1", [])
    excl_countries = rule_obj.get("exclude_countries", [])
    excl_g14 = rule_obj.get("exclude_germany_1914_states", [])
    extra_g14 = rule_obj.get("extra_germany_1914")
    extra_gadm = rule_obj.get("extra_gadm", [])
    grp_clip = str(group_cfg.get("clip_to_country") or "").strip()
    non_ne_layers = {"british_india_1948", "galicia_habsburg", "germany_1914", "russia_1897", "uk_counties", "uk_historic_counties"}
    parts_list = []

    if isinstance(extra_gadm, list) and extra_gadm:
      parts_list = [flat_indices] if flat_indices.size > 0 else []
      for i in range(len(extra_gadm)):
        local_g = extra_gadm[i]
        local_feats = self.matchGadmFeatures(
          str(local_g.get("gadm_iso3") or ""),
          int(local_g.get("gadm_level") or 1),
          local_g.get("names", []),
          local_g.get("names_1", [])
        )
        local_idx = self.rasteriser.A_rasteriseGeometry(local_feats, {"ensure_min_pixel": False})
        if local_g.get("clip_to_countries"):
          local_clip = self.country_resolver.collectCountryUnionIndices(local_g["clip_to_countries"], set())
          local_idx = self.rasteriser.clipIndicesWithFallback(local_idx, local_clip)
        if local_idx.size > 0:
          parts_list.append(local_idx)
      flat_indices = np.unique(np.concatenate(parts_list)) if parts_list else flat_indices

    if isinstance(extra_g14, dict) and extra_g14:
      g14_feats = self.matchGermany1914Features(extra_g14, "")
      g14_idx = self.rasteriser.A_rasteriseGeometry(g14_feats, {"ensure_min_pixel": False})
      if g14_idx.size > 0:
        flat_indices = np.unique(np.concatenate([flat_indices, g14_idx])) if flat_indices.size > 0 else g14_idx

    if isinstance(excl_g14, list) and excl_g14 and flat_indices.size > 0:
      excl_g14_feats = self.matchGermany1914Features({"staat_names": excl_g14}, "")
      excl_g14_idx = self.rasteriser.A_rasteriseGeometry(excl_g14_feats, {"ensure_min_pixel": False})
      if excl_g14_idx.size > 0:
        reduced_g14 = np.setdiff1d(flat_indices, excl_g14_idx, assume_unique=True)
        if reduced_g14.size > 0:
          flat_indices = reduced_g14

    if isinstance(excl_admin1, list) and excl_admin1 and flat_indices.size > 0:
      for i in range(len(excl_admin1)):
        local_ex = excl_admin1[i]
        local_feats = self.matchAdmin1ByNamesOrRegions(local_ex.get("adm0_a3", ""), local_ex.get("names", []), local_ex.get("regions", []))
        local_sub = self.rasteriser.A_rasteriseGeometry(local_feats, {"ensure_min_pixel": False})
        if local_sub.size > 0:
          reduced_a1 = np.setdiff1d(flat_indices, local_sub, assume_unique=True)
          if reduced_a1.size > 0:
            flat_indices = reduced_a1

    if (layer_type in non_ne_layers or layer_type == "gadm" or layer_type.startswith("gadm_")) and not rule_obj.get("do_not_clip_land"):
      flat_indices = self.rasteriser.clipIndicesWithFallback(flat_indices, self.country_resolver.getLandmaskIndices())

    if isinstance(rule_obj.get("clip_to_countries"), list) and rule_obj["clip_to_countries"]:
      clip_countries = rule_obj["clip_to_countries"]
    elif grp_clip and layer_type != "country_ref" and not rule_obj.get("do_not_clip_group"):
      clip_countries = [grp_clip]

    if clip_countries:
      clip_union = self.country_resolver.collectCountryUnionIndices(clip_countries, set())
      if clip_union.size > 0:
        flat_indices = self.rasteriser.clipIndicesWithFallback(flat_indices, clip_union)

    if isinstance(excl_countries, list) and excl_countries and flat_indices.size > 0:
      excl_union = self.country_resolver.collectCountryUnionIndices(excl_countries, set())
      if excl_union.size > 0:
        reduced_c = np.setdiff1d(flat_indices, excl_union, assume_unique=True)
        if reduced_c.size > 0:
          flat_indices = reduced_c

    #Return statement
    return flat_indices


  def applyPartitionSets (self):
    """
    @brief Snap configured partition_sets in admin_division_rules.json5 onto their canonical parent country or division masks.
    """
    #Declare local instance variables
    num_sets = len(self.partition_sets_cfg) if isinstance(self.partition_sets_cfg, list) else 0

    for i in range(num_sets):
      pset = self.partition_sets_cfg[i]
      if not isinstance(pset, dict):
        continue
      target_country = str(pset.get("target_country") or "").strip()
      target_div = str(pset.get("target_division") or "").strip()
      target_indices = None

      if target_country:
        target_indices = self.country_resolver.resolveSingleCountry(target_country, set())["flat_indices"]
      elif target_div and target_div in self.resolved_divisions_obj:
        target_indices = self.resolved_divisions_obj[target_div]["flat_indices"]

      if target_indices is None or target_indices.size == 0:
        continue

      excl_set = set(str(x) for x in pset.get("exclude_members", []) if x)
      explicit_members = set(str(x) for x in pset.get("members", []) if x)
      prefixes_list = [f"admin:{p}:" for p in pset.get("prefixes", []) if p]
      req_parent = str(pset.get("canonical_parent") or "").strip()

      canon_to_eids = {}
      canon_to_indices = {}
      for local_eid, div_rec in sorted(self.resolved_divisions_obj.items()):
        if local_eid in excl_set or not div_rec.get("canonical_key"):
          continue
        matched_member = (local_eid in explicit_members) or any(local_eid.startswith(pref) for pref in prefixes_list)
        if not matched_member:
          continue
        if req_parent and str(div_rec.get("canonical_parent") or "") != req_parent:
          continue
        ckey = str(div_rec["canonical_key"])
        canon_to_eids.setdefault(ckey, []).append(local_eid)
        if ckey not in canon_to_indices:
          canon_to_indices[ckey] = div_rec["flat_indices"]
        else:
          canon_to_indices[ckey] = np.unique(np.concatenate([canon_to_indices[ckey], div_rec["flat_indices"]]))

      if not canon_to_indices:
        continue

      snapped_map = self.rasteriser.snapPartitionToTargetMask(
        canon_to_indices,
        target_indices,
        {
          "disjoint": bool(pset.get("disjoint", True)),
          "fill_uncovered": bool(pset.get("fill_uncovered", True)),
          "priority_keys": pset.get("priority_keys", [])
        }
      )

      for local_ck, snapped_idx in snapped_map.items():
        local_metrics = self.rasteriser.computeMaskMetrics(snapped_idx)
        for x in range(len(canon_to_eids[local_ck])):
          member_eid = canon_to_eids[local_ck][x]
          self.resolved_divisions_obj[member_eid]["flat_indices"] = snapped_idx
          self.resolved_divisions_obj[member_eid]["metrics"] = local_metrics


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


  def matchGadmFeatures (self, arg1_iso3, arg2_level, arg3_names_list, arg4_names_1_list=None):
    """
    @brief Match features in a UC Davis GADM 4.1 country/level layer using compact space-insensitive ASCII slugs.
    @param arg1_iso3 Three-letter ISO country code.
    @param arg2_level Integer GADM level (1 or 2).
    @param arg3_names_list List of target GADM feature names.
    @param arg4_names_1_list Optional list of parent NAME_1 names to restrict homonymous sub-districts.
    @return List of matching GeoJSON Feature dictionaries.
    """
    #Convert from parameters
    iso3 = str(arg1_iso3 or "").strip().upper()
    level = int(arg2_level)
    names_list = arg3_names_list if isinstance(arg3_names_list, list) else []
    names_1_list = arg4_names_1_list if isinstance(arg4_names_1_list, list) else []

    #Declare local instance variables
    fc_obj = self.fetcher.B_fetchGadmLayer(iso3, level)
    feats = fc_obj.get("features", [])
    matched_array = []
    name_1_slugs = set(self.fetcher.normaliseAsciiSlug(n).replace("_", "") for n in names_1_list if n)
    name_field = f"NAME_{level}"
    target_slugs = set(self.fetcher.normaliseAsciiSlug(n).replace("_", "") for n in names_list if n)
    varname_field = f"VARNAME_{level}"

    for i in range(len(feats)):
      local_f = feats[i]
      local_p = local_f.get("properties") or {}
      if name_1_slugs:
        n1_slug = self.fetcher.normaliseAsciiSlug(str(local_p.get("NAME_1") or "")).replace("_", "")
        if n1_slug not in name_1_slugs:
          continue
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
    @brief Match UK ceremonial / 1974 counties from uk_counties, with automatic ne_admin1 GBR fallback.
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


  def matchUkHistoricCountiesFeatures (self, arg1_counties_list, arg2_fallback_stem=""):
    """
    @brief Match UK historic shires/counties from The Historic County Borders Project (uk_historic_counties).
    @param arg1_counties_list Explicit list of historic county names in uk_historic_counties.
    @param arg2_fallback_stem Optional fallback county stem slug.
    @return List of matching GeoJSON Feature dictionaries.
    """
    #Convert from parameters
    counties_list = arg1_counties_list if isinstance(arg1_counties_list, list) else []
    fallback_stem = str(arg2_fallback_stem or "")

    #Declare local instance variables
    fc_obj = self.fetcher.A_fetchBaseLayer("uk_historic_counties")
    feats = fc_obj.get("features", [])
    matched_array = []
    stem_slug = self.fetcher.normaliseAsciiSlug(fallback_stem).replace("_", "")
    stem_without_shire = stem_slug[:-5] if stem_slug.endswith("shire") and len(stem_slug) > 7 else stem_slug
    target_slugs = set(self.fetcher.normaliseAsciiSlug(c).replace("_", "") for c in counties_list if c)

    for i in range(len(feats)):
      local_f = feats[i]
      local_p = local_f.get("properties") or {}
      n_slug = self.fetcher.normaliseAsciiSlug(str(local_p.get("NAME") or "")).replace("_", "")
      c_slug = self.fetcher.normaliseAsciiSlug(str(local_p.get("COUNTY") or "")).replace("_", "")
      if target_slugs and (n_slug in target_slugs or c_slug in target_slugs):
        matched_array.append(local_f)
      elif not target_slugs and stem_slug and (
        n_slug in (stem_slug, stem_without_shire)
        or c_slug in (stem_slug, stem_without_shire)
      ):
        matched_array.append(local_f)

    #Return statement
    return matched_array


  def resolveRuleGeometryIndices (self, arg1_rule_obj, arg2_group_cfg, arg3_clean_stem):
    """
    @brief Execute the configured geospatial lookup, scanline rasterisation, and parent/landmask clipping for a single division rule.
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
    inter_list = []
    layer_type = str(rule_obj.get("layer") or group_cfg.get("default_layer") or "ne_admin1")

    if layer_type == "country_ref":
      c_ref = str(rule_obj.get("country_ref") or clean_stem)
      c_rec = self.country_resolver.resolveSingleCountry(c_ref, set())
      return (c_rec["flat_indices"].copy(), {"country_ref": c_ref, "layer": "country_ref"})

    if layer_type == "country_intersection":
      inter_list = rule_obj.get("intersect_countries", [])
      for i in range(len(inter_list)):
        c_rec = self.country_resolver.resolveSingleCountry(str(inter_list[i]), set())
        if flat_idx is None:
          flat_idx = c_rec["flat_indices"].copy()
        else:
          flat_idx = np.intersect1d(flat_idx, c_rec["flat_indices"], assume_unique=True)
      flat_idx = flat_idx if flat_idx is not None else empty_idx
      flat_idx = self.applyDivisionModifiers(flat_idx, rule_obj, group_cfg, layer_type)
      return (flat_idx, {"intersect_countries": inter_list, "layer": "country_intersection"})

    if layer_type == "polygon":
      poly_coords = rule_obj.get("coords", [])
      flat_idx = self.rasteriser.A_rasteriseGeometry({"coordinates": [poly_coords], "type": "Polygon"}, {"fallback_lonlat": fallback_pt})
      flat_idx = self.applyDivisionModifiers(flat_idx, rule_obj, group_cfg, layer_type)
      return (flat_idx, {"layer": "polygon"})

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
    elif layer_type == "uk_historic_counties":
      feats = self.matchUkHistoricCountiesFeatures(rule_obj.get("counties", []), clean_stem)
    elif layer_type == "gadm" or layer_type.startswith("gadm_"):
      if layer_type.startswith("gadm_"):
        parts = layer_type.split("_")
        g_iso = parts[1]
        g_lvl = int(parts[2])
      else:
        g_iso = str(rule_obj.get("gadm_iso3") or adm0_code)
        g_lvl = int(rule_obj.get("gadm_level") or 1)
      g_names = rule_obj.get("names", [clean_stem])
      feats = self.matchGadmFeatures(g_iso, g_lvl, g_names, rule_obj.get("names_1", []))

    for i in range(len(extra_admin1)):
      ex_item = extra_admin1[i]
      feats.extend(self.matchAdmin1ByNamesOrRegions(ex_item.get("adm0_a3", ""), ex_item.get("names", []), ex_item.get("regions", [])))

    if feats or fallback_pt is not None:
      flat_idx = self.rasteriser.A_rasteriseGeometry(feats, {"fallback_lonlat": fallback_pt})
    else:
      flat_idx = empty_idx

    flat_idx = self.applyDivisionModifiers(flat_idx, rule_obj, group_cfg, layer_type)

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
    canonical_group = str(group_cfg.get("canonical_group") or group_key)
    canonical_key = ""
    canonical_parent = ""
    div_lookup_key = ""
    entity_id = ""
    explicit_target = ""
    flat_idx = None
    prefix = str(group_cfg.get("prefix") or group_key)
    record_obj = {}
    rule_obj = {}
    src_summary = {}
    target_mask = ""

    div_lookup_key = f"{prefix}:{clean_stem}"
    entity_id = f"admin:{div_lookup_key}"
    if entity_id in self.resolved_divisions_obj:
      return self.resolved_divisions_obj[entity_id]

    rule_obj = self.divisions_cfg.get(div_lookup_key, {})
    explicit_target = str(rule_obj.get("target_mask") or "")
    if explicit_target:
      canonical_key = ""
      canonical_parent = ""
      target_mask = explicit_target
    else:
      canonical_key = str(rule_obj.get("canonical_key") or f"{canonical_group}.{clean_stem}")
      canonical_parent = canonical_key.split(".", 1)[0] if "." in canonical_key else canonical_group
      target_mask = f"subadmin:{canonical_key}"

    flat_idx, src_summary = self.resolveRuleGeometryIndices(rule_obj, group_cfg, clean_stem)

    if flat_idx.size == 0:
      sys.stderr.write(f"Console error: admin division '{entity_id}' ({volume_id}:{group_key}:{clean_stem}) resolved to 0 pixels!\n")

    record_obj = {
      "canonical_key": canonical_key,
      "canonical_parent": canonical_parent,
      "category": "admin_division",
      "entity_id": entity_id,
      "era_type": str(group_cfg.get("era_type", "modern")),
      "flat_indices": flat_idx,
      "group_key": f"{volume_id}:{group_key}",
      "metrics": self.rasteriser.computeMaskMetrics(flat_idx),
      "name": f"{clean_stem.replace('_', ' ').title()} ({prefix.upper()})",
      "source_summary": src_summary,
      "target_mask": target_mask,
      "valid_years": years_span
    }
    self.resolved_divisions_obj[entity_id] = record_obj

    #Return statement
    return record_obj


  def resolveSpilledGroupHeaderMask (self, arg1_volume_id, arg2_group_key, arg3_group_cfg):
    """
    @brief Resolve and return polygon indices when an A3 group header has an explicit extra_header_division (e.g. ufa, sardinia, yorkshire).
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
    extra_div = str(group_cfg.get("extra_header_division") or "")
    rec = None

    if extra_div:
      rec = self.resolveSingleDivision(volume_id, group_key, group_cfg, extra_div, [1750, 2025])
      return rec["flat_indices"]

    #Return statement
    return empty_idx
