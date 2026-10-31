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
    self.admin_resolver = AdminDivisionMaskResolver(
      self.fetcher,
      self.rasteriser,
      self.country_resolver,
      self.city_resolver,
      self.admin_rules_obj
    )
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
    @brief Step C: Synthesise provinces.png (4320x2160 RGB) and register canonical A3 group colourcode lists.
    @param arg1_resolved_bundle Output dictionary from B_resolveAllEntities.
    @return Dictionary summarising exported provinces.png path and atomic province count.
    """
    #Convert from parameters
    resolved_bundle = arg1_resolved_bundle if isinstance(arg1_resolved_bundle, dict) else {}

    #Declare local instance variables
    prov_res = {}

    prov_res = self.synthesizer.A_synthesiseProvincesPng(resolved_bundle["countries"], resolved_bundle["divisions"])
    self.synthesizer.B_registerAdminGroupMasks(resolved_bundle["divisions"], resolved_bundle["groups"])

    print(self.config_loader.formatLocalisedString("masks_synthesised", [prov_res["province_count"]]))

    #Return statement
    return prov_res


  def D_buildFlatMaskMaps (self, arg1_resolved_bundle):
    """
    @brief Step D: Construct canonical country_masks_map, subadmin_masks_map, city_masks_map and flat lookup table_masks_map.
    @param arg1_resolved_bundle Output dictionary from B_resolveAllEntities.
    @return Tuple (country_masks_map, subadmin_masks_map, city_masks_map, table_masks_map).
    """
    #Convert from parameters
    resolved_bundle = arg1_resolved_bundle if isinstance(arg1_resolved_bundle, dict) else {}

    #Declare local instance variables
    canonical_div_eids = {}
    cities_map = resolved_bundle.get("cities", {})
    city_masks_map = {}
    countries_map = resolved_bundle.get("countries", {})
    country_masks_map = {}
    divisions_map = resolved_bundle.get("divisions", {})
    groups_map = resolved_bundle.get("groups", {})
    subadmin_masks_map = {}
    table_masks_map = {}

    # 1. Populate purely canonical whole-country masks (modern, colonial and historical dissolved states)
    for local_cid in sorted(countries_map.keys()):
      rgb_list = self.synthesizer.entity_rgb_lookup.get(local_cid, [])
      if not rgb_list:
        continue
      if self.country_resolver.isSubadminEntity(local_cid):
        subadmin_masks_map[local_cid] = rgb_list
      else:
        country_masks_map[local_cid] = rgb_list

    # 2. Populate purely canonical city [lng, lat] coordinates
    for local_cid, lng_lat in sorted(cities_map.items()):
      city_masks_map[local_cid] = lng_lat

    # 3. Populate canonical <parent>.<division> masks and sub-imperial/constituent A3 parent group unions
    for local_did, div_rec in sorted(divisions_map.items()):
      canon_k = str(div_rec.get("canonical_key") or "")
      if canon_k:
        canonical_div_eids.setdefault(canon_k, []).append(local_did)

    for local_ck, eid_list in sorted(canonical_div_eids.items()):
      merged_rgbs = self.mergeEntityRgbLists(eid_list)
      if merged_rgbs:
        subadmin_masks_map[local_ck] = merged_rgbs

    for local_lk, grp_rgbs in sorted(self.synthesizer.entity_rgb_lookup.items()):
      if not local_lk.startswith("canonical_group:") or not grp_rgbs:
        continue
      canon_parent = local_lk.split(":", 1)[1]
      export_parent = "european_russia" if canon_parent == "russian_empire" else canon_parent
      if export_parent not in country_masks_map and export_parent not in subadmin_masks_map:
        subadmin_masks_map[export_parent] = grp_rgbs

    # 4. Populate flat table_masks_map ('<volume>/<section>:<table_key>' -> '<type>:<canonical_key>')
    for local_vol, secs_map in sorted(self.corpus_sections_map.items()):
      for local_sec, sec_dict in sorted(secs_map.items()):
        for local_k, local_val in sorted(sec_dict.items()):
          if local_k in ("name", "subtitle"):
            continue
          top_table_key = f"{local_vol}/{local_sec}:{local_k}"

          if local_sec == "A3":
            g_rec = groups_map.get(f"{local_vol}:{local_k}", {})
            delegated_stems = g_rec.get("delegated_city_stems", {})
            raw_to_stem = g_rec.get("raw_keys_to_stem", {})
            stem_entities = g_rec.get("stem_to_entity_id", {})

            if g_rec.get("is_city_spillover_group"):
              spill_refs = {f"city:{self.city_resolver.normaliseCityKey(local_k)}"}
              for _, local_city in delegated_stems.items():
                spill_refs.add(f"city:{local_city}")
              table_masks_map[top_table_key] = sorted(spill_refs)
            elif g_rec.get("header_target"):
              table_masks_map[top_table_key] = str(g_rec["header_target"])
            else:
              canon_grp = str(g_rec.get("canonical_group") or local_k)
              grp_prefix = "country" if canon_grp in country_masks_map else "subadmin"
              table_masks_map[top_table_key] = f"{grp_prefix}:{canon_grp}"

            for local_stem, local_city in sorted(delegated_stems.items()):
              table_masks_map[f"{top_table_key}.{local_stem}"] = f"city:{local_city}"

            for local_stem, child_eid in sorted(stem_entities.items()):
              div_rec = divisions_map.get(child_eid, {})
              t_mask = str(div_rec.get("target_mask") or "")
              if t_mask:
                table_masks_map[f"{top_table_key}.{local_stem}"] = t_mask

            for local_rk, local_stem in sorted(raw_to_stem.items()):
              stem_ref = table_masks_map.get(f"{top_table_key}.{local_stem}")
              if stem_ref:
                table_masks_map[f"{top_table_key}.{local_rk}"] = stem_ref

          elif local_sec == "A4" and not self.city_resolver.isNonCityCorpusKey(local_vol, local_sec, local_k):
            canon_city = self.city_resolver.normaliseCityKey(local_k)
            table_masks_map[top_table_key] = f"city:{canon_city}"

          else:
            c_ids = self.country_resolver.B_resolveCorpusCountryKey(local_vol, local_sec, local_k, local_val)
            refs_sorted = sorted(set(self.country_resolver.formatEntityMaskRef(cid) for cid in c_ids))
            if len(refs_sorted) == 1:
              table_masks_map[top_table_key] = refs_sorted[0]
            elif len(refs_sorted) > 1:
              table_masks_map[top_table_key] = refs_sorted
              if isinstance(local_val, dict):
                inner_res = self.country_resolver.resolveWrapperInnerSeries(local_vol, local_sec, local_k, local_val)
                for local_st, eid in sorted(inner_res["stem_to_entity"].items()):
                  table_masks_map[f"{top_table_key}.{local_st}"] = self.country_resolver.formatEntityMaskRef(eid)
                for local_ik, eid in sorted(inner_res["raw_to_entity"].items()):
                  table_masks_map[f"{top_table_key}.{local_ik}"] = self.country_resolver.formatEntityMaskRef(eid)

    #Return statement
    return (country_masks_map, subadmin_masks_map, city_masks_map, table_masks_map)


  def E_runFullPipeline (self):
    """
    @brief Step E: Execute the full areal mask synthesis pipeline, export the 4 flat JSON maps and verify 100% coverage.
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
    table_masks_map = {}
    written_json = {}

    print(self.config_loader.formatLocalisedString(
      "masks_initialised",
      [grid_cfg.get("width", 4320), grid_cfg.get("height", 2160), grid_cfg.get("crs", "EPSG:4326")]
    ))

    self.A_loadCorpusSections()
    resolved_bundle = self.B_resolveAllEntities()
    prov_summary = self.C_synthesiseRasters(resolved_bundle)
    country_masks_map, subadmin_masks_map, city_masks_map, table_masks_map = self.D_buildFlatMaskMaps(resolved_bundle)
    written_json = self.synthesizer.C_exportFlatJsonMaps(
      country_masks_map,
      subadmin_masks_map,
      city_masks_map,
      table_masks_map
    )
    print(self.config_loader.formatLocalisedString("masks_table_lookup_exported", [len(table_masks_map)]))
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


  def validateMaskTargetRef (self, arg1_target_val, arg2_country_disk, arg3_subadmin_disk, arg4_city_disk, arg5_png_codes_set):
    """
    @brief Validate that a table_masks.json value ('type:key' or list of 'type:key') resolves to non-empty on-disk mask data.
    @param arg1_target_val String or list value from table_masks.json.
    @param arg2_country_disk Parsed country_masks.json dictionary.
    @param arg3_subadmin_disk Parsed subadmin_masks.json dictionary.
    @param arg4_city_disk Parsed city_masks.json dictionary.
    @param arg5_png_codes_set Set of 24-bit RGB integer codes present on provinces.png.
    @return Boolean True if every referenced mask exists and is non-empty on disk.
    """
    #Convert from parameters
    target_val = arg1_target_val
    country_disk = arg2_country_disk if isinstance(arg2_country_disk, dict) else {}
    subadmin_disk = arg3_subadmin_disk if isinstance(arg3_subadmin_disk, dict) else {}
    city_disk = arg4_city_disk if isinstance(arg4_city_disk, dict) else {}
    png_codes_set = arg5_png_codes_set if isinstance(arg5_png_codes_set, set) else set()

    #Declare local instance variables
    ref_list = []

    if isinstance(target_val, str) and target_val:
      ref_list = [target_val]
    elif isinstance(target_val, list) and target_val:
      ref_list = target_val
    else:
      return False

    for i in range(len(ref_list)):
      local_ref = str(ref_list[i] or "")
      if ":" not in local_ref:
        return False
      m_type, m_key = local_ref.split(":", 1)
      if m_type == "country":
        rgbs = country_disk.get(m_key, [])
        if not rgbs or not all(((c[0] << 16) | (c[1] << 8) | c[2]) in png_codes_set for c in rgbs):
          return False
      elif m_type == "subadmin":
        rgbs = subadmin_disk.get(m_key, [])
        if not rgbs or not all(((c[0] << 16) | (c[1] << 8) | c[2]) in png_codes_set for c in rgbs):
          return False
      elif m_type == "city":
        pt = city_disk.get(m_key)
        if not isinstance(pt, list) or len(pt) != 2 or (abs(pt[0]) < 0.01 and abs(pt[1]) < 0.01):
          return False
      else:
        return False

    #Return statement
    return True


  def verifyCompleteDeliverables (self, arg1_png_path, arg2_written_json):
    """
    @brief Reload provinces.png and the 4 exported flat JSON maps from disk and verify 100% end-to-end table lookup coverage.
    @param arg1_png_path Path to provinces.png on disk.
    @param arg2_written_json Dictionary of paths to country_masks.json, subadmin_masks.json, city_masks.json and table_masks.json.
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
    table_disk = {}
    top_accounted = 0
    top_total = 0
    unaccounted_list = []
    wrapper_series_accounted = 0
    wrapper_series_total = 0

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
    with open(written_json["table_masks_json"], "rb") as local_fh:
      table_disk = orjson.loads(local_fh.read())

    for local_tk, local_tv in sorted(table_disk.items()):
      if not self.validateMaskTargetRef(local_tv, country_disk, subadmin_disk, city_disk, png_codes_set):
        unaccounted_list.append(f"dangling_table_mask:{local_tk}")

    for local_vol, secs_map in sorted(self.corpus_sections_map.items()):
      for local_sec, sec_dict in sorted(secs_map.items()):
        section_count = section_count + 1
        for local_k, local_val in sorted(sec_dict.items()):
          if local_k in ("name", "subtitle"):
            continue
          top_total = top_total + 1
          top_lookup_k = f"{local_vol}/{local_sec}:{local_k}"
          top_target = table_disk.get(top_lookup_k)

          if self.validateMaskTargetRef(top_target, country_disk, subadmin_disk, city_disk, png_codes_set):
            top_accounted = top_accounted + 1
          else:
            unaccounted_list.append(top_lookup_k)

          if local_sec == "A3" and isinstance(local_val, dict):
            for local_rk in sorted(local_val.keys()):
              if local_rk in ("name", "subtitle"):
                continue
              a3_series_total = a3_series_total + 1
              rk_lookup = f"{top_lookup_k}.{local_rk}"
              rk_target = table_disk.get(rk_lookup)
              if isinstance(rk_target, str) and self.validateMaskTargetRef(
                rk_target,
                country_disk,
                subadmin_disk,
                city_disk,
                png_codes_set
              ):
                a3_series_accounted = a3_series_accounted + 1
              else:
                unaccounted_list.append(rk_lookup)

          elif isinstance(top_target, list) and isinstance(local_val, dict):
            for local_ik in sorted(local_val.keys()):
              if local_ik in ("name", "subtitle"):
                continue
              wrapper_series_total = wrapper_series_total + 1
              ik_lookup = f"{top_lookup_k}.{local_ik}"
              ik_target = table_disk.get(ik_lookup)
              if isinstance(ik_target, str) and self.validateMaskTargetRef(
                ik_target,
                country_disk,
                subadmin_disk,
                city_disk,
                png_codes_set
              ):
                wrapper_series_accounted = wrapper_series_accounted + 1
              else:
                unaccounted_list.append(ik_lookup)

    #Return statement
    return {
      "a3_series_accounted": a3_series_accounted,
      "a3_series_total": a3_series_total,
      "section_files_count": section_count,
      "table_masks_count": len(table_disk),
      "top_locations_accounted": top_accounted,
      "top_locations_total": top_total,
      "unaccounted_locations": unaccounted_list,
      "wrapper_series_accounted": wrapper_series_accounted,
      "wrapper_series_total": wrapper_series_total
    }
