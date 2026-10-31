"""@brief End-to-end orchestrator and verifier for BR Mitchell WGS84 Equirectangular (4320x2160) areal masks."""

import os
import sys
import time
import numpy as np
import orjson
from PIL import Image

from core.AdminDivisionMaskResolver import AdminDivisionMaskResolver
from core.CityMaskResolver import CityMaskResolver
from core.ConfigLoader import ConfigLoader
from core.CountryMaskResolver import CountryMaskResolver
from core.EquirectangularRasteriser import EquirectangularRasteriser
from core.GeoJsonFetcher import GeoJsonFetcher
from core.ProvinceMapSynthesizer import ProvinceMapSynthesizer


class ArealMaskPipeline:
  """@brief Orchestrates online vector fetching, country/subadmin/city resolution, provinces.png synthesis and 100% corpus verification."""

  def __init__ (self, arg1_root_dir=None, arg2_options=None):
    """
    @brief Initialise ArealMaskPipeline and load all /common/areal_masks/*.json5 configuration files.
    @param arg1_root_dir Repository root path.
    @param arg2_options Optional dictionary with locale ('en_gb', 'fr', 'de').
    """
    #Convert from parameters
    root_dir = arg1_root_dir
    options = arg2_options if isinstance(arg2_options, dict) else {}

    #Initialise options
    if "locale" not in options or not options["locale"]:
      options["locale"] = "en_gb"

    #Declare local instance variables
    default_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    masks_cfg_dir = ""
    self.admin_resolver = None
    self.admin_rules_obj = {}
    self.city_resolver = None
    self.city_rules_obj = {}
    self.config_loader = None
    self.config_obj = {}
    self.corpus_sections_map = {}
    self.country_resolver = None
    self.country_rules_obj = {}
    self.fetcher = None
    self.rasteriser = None
    self.root_dir = os.path.abspath(root_dir) if root_dir else default_root
    self.synthesizer = None

    self.config_loader = ConfigLoader(self.root_dir, {"locale": options["locale"]})
    masks_cfg_dir = os.path.join(self.root_dir, "common", "areal_masks")
    self.config_obj = self.config_loader.loadJson5File(os.path.join(masks_cfg_dir, "areal_mask_config.json5"))
    self.country_rules_obj = self.config_loader.loadJson5File(os.path.join(masks_cfg_dir, "country_rules.json5"))
    self.admin_rules_obj = self.config_loader.loadJson5File(os.path.join(masks_cfg_dir, "admin_division_rules.json5"))
    self.city_rules_obj = self.config_loader.loadJson5File(os.path.join(masks_cfg_dir, "city_rules.json5"))

    self.fetcher = GeoJsonFetcher(self.root_dir, self.config_obj)
    self.rasteriser = EquirectangularRasteriser(self.config_obj.get("grid", {}))
    self.country_resolver = CountryMaskResolver(self.fetcher, self.rasteriser, self.country_rules_obj)
    self.city_resolver = CityMaskResolver(self.fetcher, self.city_rules_obj)
    self.admin_resolver = AdminDivisionMaskResolver(self.fetcher, self.rasteriser, self.country_resolver, self.admin_rules_obj)
    self.synthesizer = ProvinceMapSynthesizer(self.root_dir, self.config_obj, self.rasteriser)


  def A_loadCorpusSections (self):
    """
    @brief Step A: Load all digitised IHS section JSON files across africa_asia_oceania, americas and europe.
    @return Dictionary mapping volume_id -> {section_id -> unwrapped section dictionary}.
    """
    #Declare local instance variables
    input_rel = self.config_obj.get("paths", {}).get("input_json_dir", os.path.join("output", "json"))
    json_root = os.path.join(self.root_dir, input_rel)
    vol_names = []

    self.corpus_sections_map = {}
    if not os.path.exists(json_root):
      sys.stderr.write(f"Console error: corpus JSON directory missing: {json_root}\n")
      return self.corpus_sections_map

    vol_names = sorted(d for d in os.listdir(json_root) if os.path.isdir(os.path.join(json_root, d)))
    for i in range(len(vol_names)):
      local_vol = vol_names[i]
      vol_dir = os.path.join(json_root, local_vol)
      self.corpus_sections_map[local_vol] = {}
      sec_files = sorted(f for f in os.listdir(vol_dir) if f.endswith(".json"))
      for x in range(len(sec_files)):
        sec_file = sec_files[x]
        sec_id = os.path.splitext(sec_file)[0]
        sec_path = os.path.join(vol_dir, sec_file)
        with open(sec_path, "rb") as local_fh:
          raw_json = orjson.loads(local_fh.read())
        if isinstance(raw_json, dict) and sec_id in raw_json and isinstance(raw_json[sec_id], dict):
          self.corpus_sections_map[local_vol][sec_id] = raw_json[sec_id]
        elif isinstance(raw_json, dict):
          self.corpus_sections_map[local_vol][sec_id] = raw_json

    #Return statement
    return self.corpus_sections_map


  def B_resolveAllEntities (self):
    """
    @brief Step B: Resolve all whole countries, individual city [lng, lat] points and sub-national administrative divisions.
    @return Dictionary containing resolved countries, cities, divisions and groups.
    """
    #Declare local instance variables
    a3_sections_map = {}
    all_city_keys = set()
    delegated_cities = []
    non_spillover_group_cnt = 0
    resolved_admin = {}
    resolved_cities = {}
    resolved_countries = {}

    resolved_countries = self.country_resolver.A_resolveAllCountries()
    print(self.config_loader.formatLocalisedString("masks_countries_resolved", [len(resolved_countries)]))

    for local_vol, secs_map in sorted(self.corpus_sections_map.items()):
      if "A3" in secs_map:
        a3_sections_map[local_vol] = secs_map["A3"]
      if "A4" in secs_map:
        for local_k in secs_map["A4"].keys():
          if local_k in ("name", "subtitle"):
            continue
          if not self.city_resolver.isNonCityCorpusKey(local_vol, "A4", local_k):
            all_city_keys.add(local_k)

    delegated_cities = self.admin_resolver.A_discoverDelegatedCityKeys(a3_sections_map)
    for i in range(len(delegated_cities)):
      all_city_keys.add(delegated_cities[i])

    resolved_cities = self.city_resolver.A_resolveAllCities(sorted(all_city_keys))
    print(self.config_loader.formatLocalisedString("masks_cities_resolved", [len(resolved_cities)]))

    resolved_admin = self.admin_resolver.B_resolveAllAdminDivisions(a3_sections_map)
    for _, local_g in resolved_admin["groups"].items():
      if not local_g.get("is_city_spillover_group"):
        non_spillover_group_cnt = non_spillover_group_cnt + 1
    print(self.config_loader.formatLocalisedString(
      "masks_divisions_resolved",
      [len(resolved_admin["divisions"]), non_spillover_group_cnt]
    ))

    #Return statement
    return {
      "cities": resolved_cities,
      "countries": resolved_countries,
      "divisions": resolved_admin["divisions"],
      "groups": resolved_admin["groups"]
    }


  def C_synthesiseRasters (self, arg1_resolved_bundle):
    """
    @brief Step C: Synthesise provinces.png (4320x2160 RGB) and register parent A3 group colourcode lists.
    @param arg1_resolved_bundle Output dictionary from B_resolveAllEntities.
    @return Dictionary summarising exported provinces.png path and atomic province count.
    """
    #Convert from parameters
    resolved_bundle = arg1_resolved_bundle if isinstance(arg1_resolved_bundle, dict) else {}

    #Declare local instance variables
    prov_res = {}

    prov_res = self.synthesizer.A_synthesiseProvincesPng(resolved_bundle["countries"], resolved_bundle["divisions"])
    self.synthesizer.B_registerAdminGroupMasks(resolved_bundle["groups"])

    print(self.config_loader.formatLocalisedString("masks_synthesised", [prov_res["province_count"]]))

    #Return statement
    return prov_res


  def D_buildFlatMaskMaps (self, arg1_resolved_bundle):
    """
    @brief Step D: Construct the 3 flat dictionaries: country_masks_map, subadmin_masks_map and city_masks_map.
    @param arg1_resolved_bundle Output dictionary from B_resolveAllEntities.
    @return Tuple (country_masks_map, subadmin_masks_map, city_masks_map).
    """
    #Convert from parameters
    resolved_bundle = arg1_resolved_bundle if isinstance(arg1_resolved_bundle, dict) else {}

    #Declare local instance variables
    cities_map = resolved_bundle.get("cities", {})
    city_masks_map = {}
    countries_map = resolved_bundle.get("countries", {})
    country_key_per_vol = {}
    country_masks_map = {}
    groups_map = resolved_bundle.get("groups", {})
    subadmin_masks_map = {}

    # 1. Populate all canonical modern & historical country IDs (1750-2025)
    for local_cid in sorted(countries_map.keys()):
      rgb_list = self.synthesizer.entity_rgb_lookup.get(local_cid, [])
      if rgb_list:
        country_masks_map[local_cid] = rgb_list

    # 2. Populate all corpus country keys across all sections (including non-city A4 spillovers)
    for local_vol, secs_map in sorted(self.corpus_sections_map.items()):
      for local_sec, sec_dict in sorted(secs_map.items()):
        if local_sec == "A3":
          continue
        for local_k, local_val in sorted(sec_dict.items()):
          if local_k in ("name", "subtitle"):
            continue
          if local_sec == "A4" and not self.city_resolver.isNonCityCorpusKey(local_vol, local_sec, local_k):
            continue
          c_ids = self.country_resolver.B_resolveCorpusCountryKey(local_vol, local_sec, local_k, local_val)
          rgb_list = self.mergeEntityRgbLists(c_ids)
          if rgb_list:
            country_key_per_vol.setdefault(local_k, {})[local_vol] = (tuple(c_ids), rgb_list)

    for local_k, vol_dict in sorted(country_key_per_vol.items()):
      distinct_id_sets = set(v[0] for v in vol_dict.values())
      if len(distinct_id_sets) == 1:
        only_rgbs = next(iter(vol_dict.values()))[1]
        country_masks_map[local_k] = only_rgbs
      else:
        union_tuples = set()
        for local_vol, (_, vol_rgbs) in sorted(vol_dict.items()):
          country_masks_map[f"{local_vol}.{local_k}"] = vol_rgbs
          for i in range(len(vol_rgbs)):
            union_tuples.add(tuple(vol_rgbs[i]))
        country_masks_map[local_k] = [[t[0], t[1], t[2]] for t in sorted(union_tuples)]

    # 3. Populate canonical city [lng, lat] coordinates (clean city keys only; never A3 spillover headers)
    for local_cid, lng_lat in sorted(cities_map.items()):
      city_masks_map[local_cid] = lng_lat

    # 4. Populate subadmin_masks_map (<parent>, <parent>.<division>, <parent>.<raw_key>)
    for local_vgk, g_rec in sorted(groups_map.items()):
      local_gk = local_vgk.split(":", 1)[1]
      stem_entities = g_rec.get("stem_to_entity_id", {})
      raw_to_stem = g_rec.get("raw_keys_to_stem", {})

      if not g_rec.get("is_city_spillover_group"):
        g_rgbs = self.synthesizer.entity_rgb_lookup.get(g_rec["entity_id"], [])
        if g_rgbs:
          subadmin_masks_map[local_gk] = g_rgbs

      for local_stem, child_eid in sorted(stem_entities.items()):
        c_rgbs = self.synthesizer.entity_rgb_lookup.get(child_eid, [])
        if c_rgbs:
          subadmin_masks_map[f"{local_gk}.{local_stem}"] = c_rgbs

      for local_rk, local_stem in sorted(raw_to_stem.items()):
        if local_stem in stem_entities:
          child_eid = stem_entities[local_stem]
          c_rgbs = self.synthesizer.entity_rgb_lookup.get(child_eid, [])
          if c_rgbs:
            subadmin_masks_map[f"{local_gk}.{local_rk}"] = c_rgbs

    #Return statement
    return (country_masks_map, subadmin_masks_map, city_masks_map)


  def E_runFullPipeline (self):
    """
    @brief Step E: Execute the full areal mask synthesis pipeline, export the 3 flat JSON maps and verify 100% coverage.
    @return Verification summary dictionary.
    """
    #Declare local instance variables
    audit_res = {}
    city_masks_map = {}
    country_masks_map = {}
    elapsed_sec = 0.0
    grid_cfg = self.config_obj.get("grid", {})
    prov_summary = {}
    resolved_bundle = {}
    start_ts = time.time()
    subadmin_masks_map = {}
    written_json = {}

    print(self.config_loader.formatLocalisedString(
      "masks_initialised",
      [grid_cfg.get("width", 4320), grid_cfg.get("height", 2160), grid_cfg.get("crs", "EPSG:4326")]
    ))

    self.A_loadCorpusSections()
    resolved_bundle = self.B_resolveAllEntities()
    prov_summary = self.C_synthesiseRasters(resolved_bundle)
    country_masks_map, subadmin_masks_map, city_masks_map = self.D_buildFlatMaskMaps(resolved_bundle)
    written_json = self.synthesizer.C_exportFlatJsonMaps(country_masks_map, subadmin_masks_map, city_masks_map)
    audit_res = self.verifyCompleteDeliverables(prov_summary["png_path"], written_json)

    elapsed_sec = round(time.time() - start_ts, 2)
    print(self.config_loader.formatLocalisedString(
      "masks_verified_done",
      [
        audit_res["top_locations_accounted"],
        audit_res["top_locations_total"],
        len(audit_res["unaccounted_locations"]),
        audit_res["section_files_count"],
        elapsed_sec
      ]
    ))

    #Return statement
    return audit_res


  def mergeEntityRgbLists (self, arg1_entity_ids):
    """
    @brief Merge and sort unique [R, G, B] triplets across one or more canonical entity IDs.
    @param arg1_entity_ids List of canonical entity IDs.
    @return Sorted list of [R, G, B] integer triplets.
    """
    #Convert from parameters
    entity_ids = arg1_entity_ids if isinstance(arg1_entity_ids, list) else []

    #Declare local instance variables
    rgb_tuples_set = set()

    for i in range(len(entity_ids)):
      rgbs = self.synthesizer.entity_rgb_lookup.get(entity_ids[i], [])
      for x in range(len(rgbs)):
        rgb_tuples_set.add(tuple(rgbs[x]))

    #Return statement
    return [[int(t[0]), int(t[1]), int(t[2])] for t in sorted(rgb_tuples_set)]


  def verifyCompleteDeliverables (self, arg1_png_path, arg2_written_json):
    """
    @brief Reload provinces.png and the 3 exported flat JSON maps from disk and verify 100% of output/json locations.
    @param arg1_png_path Path to provinces.png on disk.
    @param arg2_written_json Dictionary of paths to country_masks.json, subadmin_masks.json and city_masks.json.
    @return Verification audit dictionary.
    """
    #Convert from parameters
    png_path = str(arg1_png_path or "")
    written_json = arg2_written_json if isinstance(arg2_written_json, dict) else {}

    #Declare local instance variables
    a3_series_accounted = 0
    a3_series_total = 0
    city_disk = {}
    country_disk = {}
    png_codes_set = set()
    section_count = 0
    subadmin_disk = {}
    top_accounted = 0
    top_total = 0
    unaccounted_list = []

    with Image.open(png_path) as local_im:
      arr = np.asarray(local_im)
      codes = (arr[:, :, 0].astype(np.uint32) << 16) | (arr[:, :, 1].astype(np.uint32) << 8) | arr[:, :, 2].astype(np.uint32)
      nz = np.unique(codes[codes > 0])
      png_codes_set = set(nz.tolist())

    with open(written_json["country_masks_json"], "rb") as local_fh:
      country_disk = orjson.loads(local_fh.read())
    with open(written_json["subadmin_masks_json"], "rb") as local_fh:
      subadmin_disk = orjson.loads(local_fh.read())
    with open(written_json["city_masks_json"], "rb") as local_fh:
      city_disk = orjson.loads(local_fh.read())

    for local_vol, secs_map in sorted(self.corpus_sections_map.items()):
      for local_sec, sec_dict in sorted(secs_map.items()):
        section_count = section_count + 1
        for local_k, local_val in sorted(sec_dict.items()):
          if local_k in ("name", "subtitle"):
            continue
          top_total = top_total + 1

          if local_sec == "A3":
            if local_k in subadmin_disk:
              rgbs = subadmin_disk[local_k]
              if rgbs and all(((c[0] << 16) | (c[1] << 8) | c[2]) in png_codes_set for c in rgbs):
                top_accounted = top_accounted + 1
              else:
                unaccounted_list.append(f"{local_vol}:A3:{local_k}")
            elif local_k in city_disk and len(city_disk[local_k]) == 2:
              top_accounted = top_accounted + 1
            else:
              unaccounted_list.append(f"{local_vol}:A3:{local_k}")

            if isinstance(local_val, dict):
              for local_rk in sorted(local_val.keys()):
                if local_rk in ("name", "subtitle"):
                  continue
                a3_series_total = a3_series_total + 1
                comp_key = f"{local_k}.{local_rk}"
                clean_stem, _ = self.admin_resolver.cleanDivisionStem(local_rk)
                if comp_key in subadmin_disk:
                  s_rgbs = subadmin_disk[comp_key]
                  if s_rgbs and all(((c[0] << 16) | (c[1] << 8) | c[2]) in png_codes_set for c in s_rgbs):
                    a3_series_accounted = a3_series_accounted + 1
                  else:
                    unaccounted_list.append(f"{local_vol}:A3:{comp_key}")
                elif clean_stem in city_disk and len(city_disk[clean_stem]) == 2:
                  s_pt = city_disk[clean_stem]
                  if not (abs(s_pt[0]) < 0.01 and abs(s_pt[1]) < 0.01):
                    a3_series_accounted = a3_series_accounted + 1
                  else:
                    unaccounted_list.append(f"{local_vol}:A3:{comp_key}")
                else:
                  unaccounted_list.append(f"{local_vol}:A3:{comp_key}")

          elif local_sec == "A4" and not self.city_resolver.isNonCityCorpusKey(local_vol, local_sec, local_k):
            pt = city_disk.get(local_k)
            if isinstance(pt, list) and len(pt) == 2 and not (abs(pt[0]) < 0.01 and abs(pt[1]) < 0.01):
              top_accounted = top_accounted + 1
            else:
              unaccounted_list.append(f"{local_vol}:A4:{local_k}")

          else:
            lookup_k = f"{local_vol}.{local_k}" if f"{local_vol}.{local_k}" in country_disk else local_k
            rgbs = country_disk.get(lookup_k, [])
            if rgbs and all(((c[0] << 16) | (c[1] << 8) | c[2]) in png_codes_set for c in rgbs):
              top_accounted = top_accounted + 1
            else:
              unaccounted_list.append(f"{local_vol}:{local_sec}:{local_k}")

    #Return statement
    return {
      "a3_series_accounted": a3_series_accounted,
      "a3_series_total": a3_series_total,
      "section_files_count": section_count,
      "top_locations_accounted": top_accounted,
      "top_locations_total": top_total,
      "unaccounted_locations": unaccounted_list
    }
