"""@brief Resolves modern, colonial, and historical whole-country areal masks (1750-2025) from online vector layers."""

import re
import sys
import numpy as np


class CountryMaskResolver:
  """@brief Resolves canonical country definitions and maps corpus location keys to canonical country entities."""

  def __init__ (self, arg1_fetcher, arg2_rasteriser, arg3_country_rules_obj):
    """
    @brief Initialise CountryMaskResolver with GeoJsonFetcher, EquirectangularRasteriser, and parsed country_rules.json5.
    @param arg1_fetcher GeoJsonFetcher instance.
    @param arg2_rasteriser EquirectangularRasteriser instance.
    @param arg3_country_rules_obj Parsed country_rules.json5 dictionary.
    """
    #Convert from parameters
    fetcher = arg1_fetcher
    rasteriser = arg2_rasteriser
    country_rules_obj = arg3_country_rules_obj if isinstance(arg3_country_rules_obj, dict) else {}

    #Declare local instance variables
    self.aliases_cfg = country_rules_obj.get("aliases", {})
    self.countries_cfg = country_rules_obj.get("countries", {})
    self.fetcher = fetcher
    self.landmask_indices = None
    self.rasteriser = rasteriser
    self.resolved_countries_obj = {}
    self.section_overrides_cfg = country_rules_obj.get("section_key_overrides", {})
    self.sorted_country_keys = sorted(self.countries_cfg.keys(), key=lambda local_k: len(local_k), reverse=True)
    self.subadmin_entities_set = set(country_rules_obj.get("subadmin_entities", []))
    self.wrapper_inner_overrides_cfg = country_rules_obj.get("wrapper_inner_overrides", {})


  def A_resolveAllCountries (self):
    """
    @brief Step A: Rasterise all canonical modern and historical country entities onto the 4320x2160 grid.
    @return Dictionary mapping canonical country_id -> resolved entity record with flat_indices and metrics.
    """
    #Declare local instance variables
    all_country_ids = sorted(self.countries_cfg.keys())

    for i in range(len(all_country_ids)):
      local_cid = all_country_ids[i]
      self.resolveSingleCountry(local_cid, set())

    #Return statement
    return self.resolved_countries_obj


  def B_resolveCorpusCountryKey (self, arg1_volume_id, arg2_section_id, arg3_raw_key, arg4_sub_obj=None):
    """
    @brief Step B: Resolve a raw corpus JSON location key to one or more canonical country IDs.
    @param arg1_volume_id Volume identifier ('africa_asia_oceania', 'americas', 'europe').
    @param arg2_section_id Section code (e.g. 'A1', 'C1', 'J3').
    @param arg3_raw_key Raw snake_case location key from the section JSON.
    @param arg4_sub_obj Optional nested series dictionary under raw_key for sub-key country scanning.
    @return Non-empty list of valid canonical country IDs, or empty list if unresolved.
    """
    #Convert from parameters
    volume_id = str(arg1_volume_id or "").strip()
    section_id = str(arg2_section_id or "").strip()
    raw_key = str(arg3_raw_key or "").strip()
    sub_obj = arg4_sub_obj if isinstance(arg4_sub_obj, dict) else {}

    #Declare local instance variables
    candidates_array = []
    override_key = f"{volume_id}:{section_id}:{raw_key}"
    scanned_ids = []

    if not raw_key:
      return []

    if override_key in self.section_overrides_cfg:
      return self.normaliseTargetList(self.section_overrides_cfg[override_key])

    if raw_key in self.countries_cfg:
      return [raw_key]

    if raw_key in self.aliases_cfg:
      return self.normaliseTargetList(self.aliases_cfg[raw_key])

    candidates_array = self.extractCandidateTokens(raw_key)
    for i in range(len(candidates_array)):
      local_cand = candidates_array[i]
      if local_cand in self.countries_cfg:
        return [local_cand]
      if local_cand in self.aliases_cfg:
        return self.normaliseTargetList(self.aliases_cfg[local_cand])

    scanned_ids = self.scanSubObjectCountries(sub_obj)
    if scanned_ids:
      return scanned_ids

    for i in range(len(self.sorted_country_keys)):
      local_ck = self.sorted_country_keys[i]
      if len(local_ck) >= 4 and (raw_key.startswith(f"{local_ck}_") or raw_key.endswith(f"_{local_ck}")):
        return [local_ck]

    for i in range(len(self.sorted_country_keys)):
      local_ck = self.sorted_country_keys[i]
      if len(local_ck) >= 5 and local_ck in raw_key:
        return [local_ck]

    sys.stderr.write(f"Console error: unresolved country key {volume_id}:{section_id}:{raw_key}\n")

    #Return statement
    return []


  def applySourceModifiers (self, arg1_flat_indices, arg2_source_obj, arg3_visiting_set):
    """
    @brief Apply declarative admin1/GADM additions, subtractions, polygon intersections, and country clips to a country mask.
    @param arg1_flat_indices Initial sorted 1D int32 array of flat pixel indices.
    @param arg2_source_obj Country source specification dictionary.
    @param arg3_visiting_set Set of currently visiting country IDs to prevent cyclic recursion.
    @return Modified sorted 1D int32 array of flat pixel indices.
    """
    #Convert from parameters
    flat_indices = arg1_flat_indices
    source_obj = arg2_source_obj if isinstance(arg2_source_obj, dict) else {}
    visiting_set = arg3_visiting_set if isinstance(arg3_visiting_set, set) else set()

    #Declare local instance variables
    clip_countries = source_obj.get("clip_to", [])
    clip_parts = []
    exclude_countries = source_obj.get("exclude_countries", [])
    extra_admin1 = source_obj.get("extra_admin1", [])
    extra_gadm = source_obj.get("extra_gadm", [])
    extra_layers = source_obj.get("extra_layers", [])
    extra_members = source_obj.get("extra_members", [])
    inter_coords = source_obj.get("intersect_coords", [])
    layer_key = str(source_obj.get("layer") or "")
    non_ne_layers = {"british_india_1948", "cshapes_2", "galicia_habsburg", "germany_1914", "hungary_transleithania", "russia_1897"}
    parts_list = []
    sub_admin1 = source_obj.get("subtract_admin1", [])
    sub_gadm = source_obj.get("subtract_gadm", [])

    if isinstance(extra_admin1, list) and extra_admin1:
      parts_list = [flat_indices] if flat_indices.size > 0 else []
      for i in range(len(extra_admin1)):
        local_feats = self.matchAdmin1Features(extra_admin1[i])
        local_idx = self.rasteriser.A_rasteriseGeometry(local_feats, {"ensure_min_pixel": False})
        if local_idx.size > 0:
          parts_list.append(local_idx)
      flat_indices = np.unique(np.concatenate(parts_list)) if parts_list else flat_indices

    if isinstance(extra_gadm, list) and extra_gadm:
      parts_list = [flat_indices] if flat_indices.size > 0 else []
      for i in range(len(extra_gadm)):
        local_g = extra_gadm[i]
        local_feats = self.matchGadmSubset(
          str(local_g.get("gadm_iso3") or ""),
          int(local_g.get("gadm_level") or 1),
          local_g.get("names", [])
        )
        local_idx = self.rasteriser.A_rasteriseGeometry(local_feats, {"ensure_min_pixel": False})
        if local_g.get("clip_to"):
          local_clip = self.collectCountryUnionIndices(local_g["clip_to"], visiting_set)
          local_idx = self.rasteriser.clipIndicesWithFallback(local_idx, local_clip)
        if local_idx.size > 0:
          parts_list.append(local_idx)
      flat_indices = np.unique(np.concatenate(parts_list)) if parts_list else flat_indices

    if isinstance(extra_layers, list) and extra_layers:
      parts_list = [flat_indices] if flat_indices.size > 0 else []
      for i in range(len(extra_layers)):
        local_l = extra_layers[i]
        local_lk = str(local_l.get("layer") or "")
        if local_l.get("type") == "polygon":
          local_poly = {"coordinates": [local_l.get("coords", [])], "type": "Polygon"}
          local_idx = self.rasteriser.A_rasteriseGeometry(local_poly, {"ensure_min_pixel": False})
        elif local_lk in ("ne_admin0", "ne_map_units", "ne_subunits"):
          local_feats = self.matchAdmin0Features(local_lk, local_l)
          local_idx = self.rasteriser.A_rasteriseGeometry(local_feats, {"ensure_min_pixel": False})
        elif local_lk == "cshapes_2":
          local_feats = self.matchCshapesFeatures(local_l)
          local_idx = self.rasteriser.A_rasteriseGeometry(local_feats, {"ensure_min_pixel": False})
        else:
          local_feats = self.matchHistoricalBasemapFeatures(local_lk, local_l)
          local_idx = self.rasteriser.A_rasteriseGeometry(local_feats, {"ensure_min_pixel": False})
        local_idx = self.applySourceModifiers(local_idx, local_l, visiting_set)
        if local_idx.size > 0:
          parts_list.append(local_idx)
      flat_indices = np.unique(np.concatenate(parts_list)) if parts_list else flat_indices

    if isinstance(inter_coords, list) and len(inter_coords) >= 4:
      poly_geom = {"coordinates": [inter_coords], "type": "Polygon"}
      inter_idx = self.rasteriser.A_rasteriseGeometry(poly_geom, {"ensure_min_pixel": False})
      flat_indices = self.rasteriser.clipIndicesWithFallback(flat_indices, inter_idx)

    if isinstance(sub_admin1, list) and sub_admin1:
      for i in range(len(sub_admin1)):
        local_feats = self.matchAdmin1Features(sub_admin1[i])
        local_sub = self.rasteriser.A_rasteriseGeometry(local_feats, {"ensure_min_pixel": False})
        if local_sub.size > 0 and flat_indices.size > 0:
          flat_indices = np.setdiff1d(flat_indices, local_sub, assume_unique=True)

    if isinstance(sub_gadm, list) and sub_gadm:
      for i in range(len(sub_gadm)):
        local_g = sub_gadm[i]
        local_feats = self.matchGadmSubset(
          str(local_g.get("gadm_iso3") or ""),
          int(local_g.get("gadm_level") or 1),
          local_g.get("names", [])
        )
        local_sub = self.rasteriser.A_rasteriseGeometry(local_feats, {"ensure_min_pixel": False})
        if local_sub.size > 0 and flat_indices.size > 0:
          flat_indices = np.setdiff1d(flat_indices, local_sub, assume_unique=True)

    if isinstance(extra_members, list) and extra_members:
      parts_list = [flat_indices] if flat_indices.size > 0 else []
      for i in range(len(extra_members)):
        local_ex = self.resolveSingleCountry(str(extra_members[i]), visiting_set)
        if local_ex["flat_indices"].size > 0:
          parts_list.append(local_ex["flat_indices"])
      flat_indices = np.unique(np.concatenate(parts_list)) if parts_list else flat_indices

    if (layer_key in non_ne_layers or layer_key.startswith("hist_")) and not source_obj.get("do_not_clip_land"):
      flat_indices = self.rasteriser.clipIndicesWithFallback(flat_indices, self.getLandmaskIndices())

    if isinstance(clip_countries, list) and clip_countries:
      clip_parts = self.collectCountryUnionIndices(clip_countries, visiting_set)
      if clip_parts.size > 0:
        flat_indices = self.rasteriser.clipIndicesWithFallback(flat_indices, clip_parts)

    if isinstance(exclude_countries, list) and exclude_countries:
      excl_idx = self.collectCountryUnionIndices(exclude_countries, visiting_set)
      if excl_idx.size > 0 and flat_indices.size > 0:
        reduced = np.setdiff1d(flat_indices, excl_idx, assume_unique=True)
        if reduced.size > 0:
          flat_indices = reduced

    #Return statement
    return flat_indices


  def collectCountryUnionIndices (self, arg1_country_ids_list, arg2_visiting_set):
    """
    @brief Resolve and union flat pixel index arrays across a list of canonical country IDs.
    @param arg1_country_ids_list List of canonical country IDs.
    @param arg2_visiting_set Active recursion guard set.
    @return Sorted 1D int32 array of unioned pixel indices.
    """
    #Convert from parameters
    country_ids_list = arg1_country_ids_list if isinstance(arg1_country_ids_list, list) else []
    visiting_set = arg2_visiting_set if isinstance(arg2_visiting_set, set) else set()

    #Declare local instance variables
    arrays_list = []

    for i in range(len(country_ids_list)):
      local_cid = str(country_ids_list[i] or "").strip()
      if local_cid and local_cid not in visiting_set:
        local_rec = self.resolveSingleCountry(local_cid, set(visiting_set))
        if local_rec["flat_indices"].size > 0:
          arrays_list.append(local_rec["flat_indices"])

    #Return statement
    return np.unique(np.concatenate(arrays_list)) if arrays_list else np.zeros(0, dtype=np.int32)


  def extractCandidateTokens (self, arg1_raw_key):
    """
    @brief Generate progressive prefix/suffix-stripped slug candidates from an OCR or footnote-suffixed corpus key.
    @param arg1_raw_key Raw snake_case location key.
    @return List of candidate country slugs in priority order.
    """
    #Convert from parameters
    raw_key = str(arg1_raw_key or "").strip().lower()

    #Declare local instance variables
    candidates_array = []
    cleaned = re.sub(r"^(?:hard_|soft_|total_|for_|in_|of_)", "", raw_key)
    noise_suffixes = [
      "_revised", "_imports", "_exports", "_male", "_female", "_both_sexes",
      "_total", "_in", "_thousand", "_thousands", "_thousands_of", "_million",
      "_usdollars", "_francs", "_dinars", "_pesos", "_rupees", "_pounds",
      "_shillings", "_gulden", "_yen", "_lira", "_markkaa", "_kroner",
      "_kronor", "_escudos", "_pesetas", "_zlotys", "_koruna", "_rubles",
      "_rubels", "_leva", "_drachma", "_pengoes", "_schillings", "_birrs",
      "_baht", "_kyats", "_riyals", "_shekels", "_takas", "_dollars",
      "_a", "_b", "_c", "_d", "_e", "_f", "_i", "_ii", "_1", "_2"
    ]
    parts = []

    if cleaned and cleaned != raw_key:
      candidates_array.append(cleaned)

    curr = cleaned
    for _ in range(3):
      changed = False
      for i in range(len(noise_suffixes)):
        local_sfx = noise_suffixes[i]
        if curr.endswith(local_sfx) and len(curr) > len(local_sfx) + 2:
          curr = curr[:-len(local_sfx)]
          candidates_array.append(curr)
          changed = True
          break
      if not changed:
        break

    if len(raw_key) > 4 and raw_key.endswith(("l", "t", "s")):
      candidates_array.append(raw_key[:-1])

    parts = raw_key.split("_")
    if len(parts) >= 2:
      for i in range(len(parts) - 1, 0, -1):
        local_prefix = "_".join(parts[:i])
        if len(local_prefix) >= 3 and local_prefix not in candidates_array:
          candidates_array.append(local_prefix)

    #Return statement
    return candidates_array


  def formatEntityMaskRef (self, arg1_entity_id):
    """
    @brief Format a canonical country/subadmin entity ID into a 'type:key' reference for table_masks.json.
    @param arg1_entity_id Canonical entity ID in country_rules.json5.
    @return String 'subadmin:<entity_id>' or 'country:<entity_id>'.
    """
    #Convert from parameters
    entity_id = str(arg1_entity_id or "").strip()

    #Declare local instance variables
    prefix_str = "subadmin" if self.isSubadminEntity(entity_id) else "country"

    #Return statement
    return f"{prefix_str}:{entity_id}"


  def getLandmaskIndices (self):
    """
    @brief Build and cache the canonical 4320x2160 10m Natural Earth landmask (ne_admin0 union ne_map_units).
    @return Sorted 1D numpy int32 array of global terrestrial pixel indices.
    """
    #Declare local instance variables
    adm0_feats = []
    adm0_idx = None
    mu_feats = []
    mu_idx = None

    if self.landmask_indices is not None:
      return self.landmask_indices

    adm0_feats = self.fetcher.A_fetchBaseLayer("ne_admin0").get("features", [])
    mu_feats = self.fetcher.A_fetchBaseLayer("ne_map_units").get("features", [])
    adm0_idx = self.rasteriser.A_rasteriseGeometry(adm0_feats, {"ensure_min_pixel": False})
    mu_idx = self.rasteriser.A_rasteriseGeometry(mu_feats, {"ensure_min_pixel": False})
    self.landmask_indices = np.unique(np.concatenate([adm0_idx, mu_idx]))

    #Return statement
    return self.landmask_indices


  def isSubadminEntity (self, arg1_entity_id):
    """
    @brief Check whether an entity in country_rules.json5 belongs in subadmin_masks.json rather than country_masks.json.
    @param arg1_entity_id Canonical entity ID.
    @return Boolean True if entity is a constituent, sub-imperial, or sub-national territory.
    """
    #Convert from parameters
    entity_id = str(arg1_entity_id or "").strip()

    #Return statement
    return entity_id in self.subadmin_entities_set


  def matchAdmin0Features (self, arg1_layer_key, arg2_source_obj):
    """
    @brief Match features in ne_admin0, ne_map_units, or ne_subunits using ISO_A3, ADM0_A3, GU_A3, or SU_A3 codes.
    @param arg1_layer_key Base layer key ('ne_admin0', 'ne_map_units', or 'ne_subunits').
    @param arg2_source_obj Country source specification dictionary.
    @return List of matching GeoJSON Feature dictionaries.
    """
    #Convert from parameters
    layer_key = str(arg1_layer_key or "ne_admin0")
    source_obj = arg2_source_obj if isinstance(arg2_source_obj, dict) else {}

    #Declare local instance variables
    adm0_code = str(source_obj.get("adm0_a3") or "").upper()
    adm0_list_set = set(str(x).upper() for x in source_obj.get("adm0_a3_list", []) if x)
    fc_obj = self.fetcher.A_fetchBaseLayer(layer_key)
    feats = fc_obj.get("features", [])
    gu_code = str(source_obj.get("gu_a3") or "").upper()
    iso3_code = str(source_obj.get("iso3") or "").upper()
    matched_array = []
    su_code = str(source_obj.get("su_a3") or "").upper()

    for i in range(len(feats)):
      local_f = feats[i]
      local_p = local_f.get("properties") or {}
      p_iso = str(local_p.get("ISO_A3") or local_p.get("ISO_A3_EH") or "").upper()
      p_adm = str(local_p.get("ADM0_A3") or "").upper()
      p_gu = str(local_p.get("GU_A3") or "").upper()
      p_su = str(local_p.get("SU_A3") or "").upper()

      if adm0_list_set and (p_adm in adm0_list_set or p_gu in adm0_list_set or p_iso in adm0_list_set):
        matched_array.append(local_f)
      elif su_code and p_su == su_code:
        matched_array.append(local_f)
      elif gu_code and (p_gu == gu_code or p_adm == gu_code):
        matched_array.append(local_f)
      elif adm0_code and (p_adm == adm0_code or p_gu == adm0_code or p_iso == adm0_code):
        matched_array.append(local_f)
      elif iso3_code and (p_iso == iso3_code or p_adm == iso3_code or p_gu == iso3_code):
        matched_array.append(local_f)

    if not matched_array and layer_key == "ne_admin0":
      target_code = adm0_code or iso3_code or gu_code
      if target_code:
        mu_fc = self.fetcher.A_fetchBaseLayer("ne_map_units")
        mu_feats = mu_fc.get("features", [])
        for i in range(len(mu_feats)):
          local_f = mu_feats[i]
          local_p = local_f.get("properties") or {}
          if (
            str(local_p.get("GU_A3") or "").upper() == target_code
            or str(local_p.get("ADM0_A3") or "").upper() == target_code
            or str(local_p.get("ISO_A3") or "").upper() == target_code
          ):
            matched_array.append(local_f)

    #Return statement
    return matched_array


  def matchAdmin1Features (self, arg1_source_obj):
    """
    @brief Match state/province features in ne_admin1 for sub-national country entries (e.g. Alaska, Hawaii, Java & Madura).
    @param arg1_source_obj Country source specification dictionary.
    @return List of matching GeoJSON Feature dictionaries.
    """
    #Convert from parameters
    source_obj = arg1_source_obj if isinstance(arg1_source_obj, dict) else {}

    #Declare local instance variables
    adm0_code = str(source_obj.get("adm0_a3") or "").upper()
    fc_obj = self.fetcher.A_fetchBaseLayer("ne_admin1")
    feats = fc_obj.get("features", [])
    matched_array = []
    raw_names = []
    target_slugs = set()

    if "name" in source_obj and source_obj["name"]:
      raw_names.append(str(source_obj["name"]))
    if isinstance(source_obj.get("names"), list):
      for i in range(len(source_obj["names"])):
        raw_names.append(str(source_obj["names"][i]))

    for i in range(len(raw_names)):
      local_s = self.fetcher.normaliseAsciiSlug(raw_names[i]).replace("_", "")
      if local_s:
        target_slugs.add(local_s)

    for i in range(len(feats)):
      local_f = feats[i]
      local_p = local_f.get("properties") or {}
      p_adm = str(local_p.get("adm0_a3") or "").upper()
      p_sov = str(local_p.get("sov_a3") or "").upper()
      if adm0_code and p_adm != adm0_code and p_sov != adm0_code:
        continue
      cand_fields = [
        str(local_p.get("name") or ""),
        str(local_p.get("name_en") or ""),
        str(local_p.get("gn_name") or ""),
        str(local_p.get("woe_name") or "")
      ]
      alt_str = str(local_p.get("name_alt") or "")
      if alt_str:
        cand_fields.extend(alt_str.split("|"))
      for x in range(len(cand_fields)):
        local_cs = self.fetcher.normaliseAsciiSlug(cand_fields[x]).replace("_", "")
        if local_cs and local_cs in target_slugs:
          matched_array.append(local_f)
          break

    #Return statement
    return matched_array


  def matchBritishIndiaFeatures (self, arg1_source_obj):
    """
    @brief Match features from the 1948 British India shapefile layer (e.g. Portuguese Settlements in India).
    @param arg1_source_obj Source dictionary with names_2 or part_of lists.
    @return List of matching GeoJSON Feature dictionaries.
    """
    #Convert from parameters
    source_obj = arg1_source_obj if isinstance(arg1_source_obj, dict) else {}

    #Declare local instance variables
    fc_obj = self.fetcher.A_fetchBaseLayer("british_india_1948")
    feats = fc_obj.get("features", [])
    matched_array = []
    names_2_slugs = set()
    part_slugs = set()

    for i in range(len(source_obj.get("names_2", []))):
      names_2_slugs.add(self.fetcher.normaliseAsciiSlug(source_obj["names_2"][i]).replace("_", ""))
    for i in range(len(source_obj.get("part_of", []))):
      part_slugs.add(self.fetcher.normaliseAsciiSlug(source_obj["part_of"][i]).replace("_", ""))

    for i in range(len(feats)):
      local_f = feats[i]
      local_p = local_f.get("properties") or {}
      n2_slug = self.fetcher.normaliseAsciiSlug(str(local_p.get("NAME_2") or "")).replace("_", "")
      po_slug = self.fetcher.normaliseAsciiSlug(str(local_p.get("PART_OF") or "")).replace("_", "")
      if (n2_slug and n2_slug in names_2_slugs) or (po_slug and po_slug in part_slugs):
        matched_array.append(local_f)

    #Return statement
    return matched_array


  def matchCshapesFeatures (self, arg1_source_obj):
    """
    @brief Match historical sovereign or colonial state polygons in ETH Zürich CShapes 2.0 by gwcode and target year.
    @param arg1_source_obj Source dictionary containing gwcode and year.
    @return List of matching GeoJSON Feature dictionaries.
    """
    #Convert from parameters
    source_obj = arg1_source_obj if isinstance(arg1_source_obj, dict) else {}

    #Declare local instance variables
    best_dist = 999999
    best_feat = None
    exact_matches = []
    fc_obj = self.fetcher.A_fetchBaseLayer("cshapes_2")
    feats = fc_obj.get("features", [])
    target_gw = int(source_obj.get("gwcode", -1))
    target_yr = int(source_obj.get("year", 1950))

    for i in range(len(feats)):
      local_f = feats[i]
      local_p = local_f.get("properties") or {}
      gw = int(local_p.get("gwcode") or -999)
      if gw != target_gw:
        continue
      s_yr = int(local_p.get("gwsyear") or 0)
      e_yr = int(local_p.get("gweyear") or 9999)
      if s_yr <= target_yr <= e_yr:
        exact_matches.append(local_f)
      else:
        local_dist = min(abs(target_yr - s_yr), abs(target_yr - e_yr))
        if local_dist < best_dist:
          best_dist = local_dist
          best_feat = local_f

    if exact_matches:
      return exact_matches
    if best_feat is not None:
      return [best_feat]

    #Return statement
    return []


  def matchGadmSubset (self, arg1_iso3, arg2_level, arg3_names_list):
    """
    @brief Match features in a UC Davis GADM 4.1 country/level layer by compact ASCII name slug.
    @param arg1_iso3 Three-letter ISO3 code.
    @param arg2_level Integer administrative level (1 or 2).
    @param arg3_names_list List of feature names.
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
    var_field = f"VARNAME_{level}"

    for i in range(len(feats)):
      local_f = feats[i]
      local_p = local_f.get("properties") or {}
      cands = [str(local_p.get(name_field) or "")]
      var_txt = str(local_p.get(var_field) or "")
      if var_txt:
        cands.extend(var_txt.split("|"))
      for x in range(len(cands)):
        cs = self.fetcher.normaliseAsciiSlug(cands[x]).replace("_", "")
        if cs and cs in target_slugs:
          matched_array.append(local_f)
          break

    #Return statement
    return matched_array


  def matchHistoricalBasemapFeatures (self, arg1_layer_key, arg2_source_obj):
    """
    @brief Match features from historical world basemap GeoJSONs or single-territory historical layers.
    @param arg1_layer_key Layer key in areal_mask_config.json5.
    @param arg2_source_obj Source specification dictionary.
    @return List of matching GeoJSON Feature dictionaries.
    """
    #Convert from parameters
    layer_key = str(arg1_layer_key or "")
    source_obj = arg2_source_obj if isinstance(arg2_source_obj, dict) else {}

    #Declare local instance variables
    fc_obj = self.fetcher.A_fetchBaseLayer(layer_key)
    feats = fc_obj.get("features", [])
    matched_array = []
    target_slug = self.fetcher.normaliseAsciiSlug(str(source_obj.get("name") or "")).replace("_", "")

    if source_obj.get("all_features"):
      return feats

    for i in range(len(feats)):
      local_f = feats[i]
      local_p = local_f.get("properties") or {}
      for _, local_v in local_p.items():
        if isinstance(local_v, str):
          v_slug = self.fetcher.normaliseAsciiSlug(local_v).replace("_", "")
          if v_slug and v_slug == target_slug:
            matched_array.append(local_f)
            break

    #Return statement
    return matched_array


  def normaliseTargetList (self, arg1_target_val):
    """
    @brief Convert a string or list of country IDs into a validated list of canonical country IDs.
    @param arg1_target_val String or list from aliases or section_key_overrides.
    @return List of valid canonical country ID strings.
    """
    #Convert from parameters
    target_val = arg1_target_val

    #Declare local instance variables
    out_array = []
    raw_list = []

    if isinstance(target_val, str):
      raw_list = [target_val]
    elif isinstance(target_val, list):
      raw_list = target_val

    for i in range(len(raw_list)):
      local_id = str(raw_list[i] or "").strip()
      if local_id in self.countries_cfg and local_id not in out_array:
        out_array.append(local_id)
      elif local_id in self.aliases_cfg:
        alias_targets = self.aliases_cfg[local_id]
        if isinstance(alias_targets, str) and alias_targets in self.countries_cfg and alias_targets not in out_array:
          out_array.append(alias_targets)

    #Return statement
    return out_array


  def resolveSingleCountry (self, arg1_country_id, arg2_visiting_set=None):
    """
    @brief Resolve and rasterise a single canonical country entity (supporting recursive union, difference, polygon, and layer modifiers).
    @param arg1_country_id Canonical country ID key in country_rules.json5.
    @param arg2_visiting_set Set of currently visiting country IDs to guard against cycles.
    @return Resolved country entity dictionary.
    """
    #Convert from parameters
    country_id = str(arg1_country_id or "").strip()
    visiting_set = arg2_visiting_set if isinstance(arg2_visiting_set, set) else set()

    #Declare local instance variables
    cfg = {}
    empty_idx = np.zeros(0, dtype=np.int32)
    fallback_pt = None
    flat_idx = None
    layer_key = ""
    matched_feats = []
    metrics_obj = {}
    poly_coords = []
    record_obj = {}
    source_obj = {}
    source_type = ""

    if country_id in self.resolved_countries_obj:
      return self.resolved_countries_obj[country_id]

    if country_id not in self.countries_cfg or country_id in visiting_set:
      sys.stderr.write(f"Console error: invalid or cyclic country definition: {country_id}\n")
      return {"entity_id": country_id, "flat_indices": empty_idx, "metrics": self.rasteriser.computeMaskMetrics(empty_idx)}

    visiting_set.add(country_id)
    cfg = self.countries_cfg[country_id]
    source_obj = cfg.get("source", {})
    source_type = str(source_obj.get("type") or "layer")
    layer_key = str(source_obj.get("layer") or "")
    fallback_pt = source_obj.get("lonlat_fallback")

    if source_type == "union":
      member_arrays = []
      members = source_obj.get("members", [])
      for i in range(len(members)):
        local_mem = self.resolveSingleCountry(str(members[i]), visiting_set)
        if local_mem["flat_indices"].size > 0:
          member_arrays.append(local_mem["flat_indices"])
      flat_idx = np.unique(np.concatenate(member_arrays)) if member_arrays else empty_idx
      flat_idx = self.applySourceModifiers(flat_idx, source_obj, visiting_set)
    elif source_type == "difference":
      base_rec = self.resolveSingleCountry(str(source_obj.get("base") or ""), visiting_set)
      flat_idx = base_rec["flat_indices"].copy()
      sub_list = source_obj.get("subtract", [])
      for i in range(len(sub_list)):
        local_sub = self.resolveSingleCountry(str(sub_list[i]), visiting_set)
        if local_sub["flat_indices"].size > 0 and flat_idx.size > 0:
          flat_idx = np.setdiff1d(flat_idx, local_sub["flat_indices"], assume_unique=True)
      flat_idx = self.applySourceModifiers(flat_idx, source_obj, visiting_set)
    elif source_type == "polygon":
      poly_coords = source_obj.get("coords", [])
      flat_idx = self.rasteriser.A_rasteriseGeometry({"coordinates": [poly_coords], "type": "Polygon"}, {"fallback_lonlat": fallback_pt})
      flat_idx = self.applySourceModifiers(flat_idx, source_obj, visiting_set)
    elif source_type == "bbox":
      bb = source_obj.get("bbox", [0.0, 0.0, 0.1, 0.1])
      flat_idx = self.rasteriser.rasteriseBbox(bb[0], bb[1], bb[2], bb[3])
      flat_idx = self.applySourceModifiers(flat_idx, source_obj, visiting_set)
    else:
      if layer_key in ("ne_admin0", "ne_map_units", "ne_subunits"):
        matched_feats = self.matchAdmin0Features(layer_key, source_obj)
      elif layer_key == "ne_admin1":
        matched_feats = self.matchAdmin1Features(source_obj)
      elif layer_key == "cshapes_2":
        matched_feats = self.matchCshapesFeatures(source_obj)
      elif layer_key == "british_india_1948":
        matched_feats = self.matchBritishIndiaFeatures(source_obj)
      else:
        matched_feats = self.matchHistoricalBasemapFeatures(layer_key, source_obj)

      flat_idx = self.rasteriser.A_rasteriseGeometry(matched_feats, {"fallback_lonlat": fallback_pt})
      flat_idx = self.applySourceModifiers(flat_idx, source_obj, visiting_set)

    visiting_set.discard(country_id)

    if flat_idx is None or flat_idx.size == 0:
      sys.stderr.write(f"Console error: country '{country_id}' rasterised to 0 pixels!\n")
      flat_idx = empty_idx

    metrics_obj = self.rasteriser.computeMaskMetrics(flat_idx)
    record_obj = {
      "category": "country",
      "entity_id": country_id,
      "era_type": str(cfg.get("era_type", "modern")),
      "flat_indices": flat_idx,
      "metrics": metrics_obj,
      "name": str(cfg.get("name", country_id)),
      "source_summary": source_obj,
      "temporal_eras": cfg.get("temporal_eras", []),
      "valid_years": cfg.get("valid_years", [1750, 2025])
    }
    self.resolved_countries_obj[country_id] = record_obj

    #Return statement
    return record_obj


  def resolveWrapperInnerSeries (self, arg1_volume_id, arg2_section_id, arg3_wrapper_key, arg4_sub_obj):
    """
    @brief Resolve every inner series key inside a multi-country wrapper sub-table to its exact canonical entity ID.
    @param arg1_volume_id Volume identifier.
    @param arg2_section_id Section identifier.
    @param arg3_wrapper_key Top-level wrapper sub-table key.
    @param arg4_sub_obj Inner dictionary of '<country_indicator>_<year>' series.
    @return Dictionary with 'raw_to_entity' and 'stem_to_entity' maps.
    """
    #Convert from parameters
    volume_id = str(arg1_volume_id or "").strip()
    section_id = str(arg2_section_id or "").strip()
    wrapper_key = str(arg3_wrapper_key or "").strip()
    sub_obj = arg4_sub_obj if isinstance(arg4_sub_obj, dict) else {}

    #Declare local instance variables
    inner_keys = sorted(sub_obj.keys())
    raw_to_entity = {}
    stem_to_entity = {}

    for i in range(len(inner_keys)):
      local_ik = str(inner_keys[i] or "").strip()
      if local_ik in ("name", "subtitle") or not local_ik:
        continue
      local_stem = re.sub(r"_(?:1[789]\d{2}|20\d{2}).*$", "", local_ik.lower())
      base_stem = local_stem[:-8] if local_stem.endswith("_revised") and len(local_stem) > 8 else local_stem
      ov_exact = f"{volume_id}:{section_id}:{wrapper_key}:{local_stem}"
      ov_base = f"{volume_id}:{section_id}:{wrapper_key}:{base_stem}"

      if ov_exact in self.wrapper_inner_overrides_cfg:
        resolved_ids = self.normaliseTargetList(self.wrapper_inner_overrides_cfg[ov_exact])
      elif ov_base in self.wrapper_inner_overrides_cfg:
        resolved_ids = self.normaliseTargetList(self.wrapper_inner_overrides_cfg[ov_base])
      else:
        resolved_ids = self.B_resolveCorpusCountryKey(volume_id, section_id, base_stem)

      if len(resolved_ids) == 1:
        raw_to_entity[local_ik] = resolved_ids[0]
        stem_to_entity[local_stem] = resolved_ids[0]
        stem_to_entity[base_stem] = resolved_ids[0]
      else:
        sys.stderr.write(f"Console error: unresolved wrapper inner series {volume_id}:{section_id}:{wrapper_key}.{local_ik}\n")

    #Return statement
    return {
      "raw_to_entity": raw_to_entity,
      "stem_to_entity": stem_to_entity
    }


  def scanSubObjectCountries (self, arg1_sub_obj):
    """
    @brief Extract canonical country IDs embedded in nested time-series sub-keys (e.g. 'austria_1950', 'japan_1970').
    @param arg1_sub_obj Dictionary of inner series keys under a multi-country wrapper table.
    @return Sorted list of detected canonical country IDs.
    """
    #Convert from parameters
    sub_obj = arg1_sub_obj if isinstance(arg1_sub_obj, dict) else {}

    #Declare local instance variables
    found_ids = []
    inner_keys = list(sub_obj.keys())

    for i in range(len(inner_keys)):
      local_ik = str(inner_keys[i] or "").lower()
      local_stem = re.sub(r"_(?:1[789]\d{2}|20\d{2}).*$", "", local_ik)
      local_stem = re.sub(r"^(?:hard_|soft_)", "", local_stem)
      if local_stem in self.countries_cfg and local_stem not in found_ids:
        found_ids.append(local_stem)
      elif local_stem in self.aliases_cfg:
        mapped = self.normaliseTargetList(self.aliases_cfg[local_stem])
        for x in range(len(mapped)):
          if mapped[x] not in found_ids:
            found_ids.append(mapped[x])

    #Return statement
    return sorted(found_ids)
