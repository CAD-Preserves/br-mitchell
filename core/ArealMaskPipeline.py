"""@brief End-to-end orchestrator and verifier for BR Mitchell WGS84 Equirectangular (4320x2160) areal masks."""

from datetime import datetime, timezone
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
  """@brief Orchestrates online vector fetching, country/division/city mask resolution, PNG synthesis, and 100% corpus verification."""

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
    self.city_resolver = CityMaskResolver(self.fetcher, self.rasteriser, self.city_rules_obj)
    self.admin_resolver = AdminDivisionMaskResolver(self.fetcher, self.rasteriser, self.country_resolver, self.admin_rules_obj)
    self.synthesizer = ProvinceMapSynthesizer(self.root_dir, self.config_obj, self.rasteriser)


  def A_loadCorpusSections (self):
    """
    @brief Step A: Load all digitised IHS section JSON files across africa_asia_oceania, americas, and europe.
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
    @brief Step B: Resolve all whole countries, individual cities, and sub-national administrative divisions.
    @return Dictionary containing resolved countries, cities, divisions, and groups.
    """
    #Declare local instance variables
    a3_sections_map = {}
    all_city_keys = set()
    delegated_cities = []
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

    resolved_admin = self.admin_resolver.B_resolveAllAdminDivisions(a3_sections_map, resolved_cities)
    print(self.config_loader.formatLocalisedString(
      "masks_divisions_resolved",
      [len(resolved_admin["divisions"]), len(resolved_admin["groups"])]
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
    @brief Step C: Synthesise provinces.png, cities.png, and the five category visual-inspection 4320x2160 PNG maps.
    @param arg1_resolved_bundle Output dictionary from B_resolveAllEntities.
    @return Dictionary summarising exported PNG paths and atomic zone counts.
    """
    #Convert from parameters
    resolved_bundle = arg1_resolved_bundle if isinstance(arg1_resolved_bundle, dict) else {}

    #Declare local instance variables
    check_maps = {}
    city_res = {}
    prov_res = {}

    prov_res = self.synthesizer.A_synthesiseProvincesPng(resolved_bundle["countries"], resolved_bundle["divisions"])
    city_res = self.synthesizer.B_synthesiseCitiesPng(resolved_bundle["cities"])
    check_maps = self.synthesizer.C_renderCategoryCheckMaps(resolved_bundle["countries"], resolved_bundle["divisions"])
    self.synthesizer.D_registerAdminGroupMasks(resolved_bundle["groups"])

    print(self.config_loader.formatLocalisedString(
      "masks_synthesised",
      [prov_res["province_count"], city_res["city_zone_count"]]
    ))

    #Return statement
    return {
      "check_maps": check_maps,
      "cities": city_res,
      "provinces": prov_res
    }


  def D_indexAllCorpusLocations (self, arg1_resolved_bundle):
    """
    @brief Step D: Map every single location key across all 242 corpus JSON files to exact RGB mask entries.
    @param arg1_resolved_bundle Output dictionary from B_resolveAllEntities.
    @return Tuple (volume_masks_map, counters_dict).
    """
    #Convert from parameters
    resolved_bundle = arg1_resolved_bundle if isinstance(arg1_resolved_bundle, dict) else {}

    #Declare local instance variables
    a3_series_total = 0
    a3_stems_accounted = 0
    a3_stems_total = 0
    cities_map = resolved_bundle.get("cities", {})
    countries_map = resolved_bundle.get("countries", {})
    divisions_map = resolved_bundle.get("divisions", {})
    groups_map = resolved_bundle.get("groups", {})
    section_count = 0
    top_accounted = 0
    top_total = 0
    unaccounted_list = []
    volume_masks_map = {}

    for local_vol, secs_map in sorted(self.corpus_sections_map.items()):
      volume_masks_map[local_vol] = {}
      for local_sec, sec_dict in sorted(secs_map.items()):
        section_count = section_count + 1
        sec_out = {}
        loc_keys = sorted(k for k in sec_dict.keys() if k not in ("name", "subtitle"))

        for i in range(len(loc_keys)):
          local_k = loc_keys[i]
          local_val = sec_dict[local_k]
          top_total = top_total + 1

          if local_sec == "A3":
            g_rec = groups_map.get(f"{local_vol}:{local_k}")
            g_mask = self.synthesizer.entity_mask_lookup.get(g_rec["entity_id"]) if g_rec else None
            stems_out = {}
            for local_stem, child_eid in sorted((g_rec or {}).get("stem_to_entity_id", {}).items()):
              a3_stems_total = a3_stems_total + 1
              c_mask = self.synthesizer.entity_mask_lookup.get(child_eid, {})
              child_ent = divisions_map.get(child_eid) or cities_map.get(child_eid.replace("city:", ""))
              px_cnt = child_ent["metrics"]["pixel_count"] if child_ent else 0
              if c_mask.get("rgb_masks") and px_cnt > 0:
                a3_stems_accounted = a3_stems_accounted + 1
              else:
                unaccounted_list.append(f"{local_vol}:A3:{local_k}:{local_stem}")
              stems_out[local_stem] = {
                "entity_id": child_eid,
                "hex_masks": c_mask.get("hex_masks", []),
                "pixel_count": px_cnt,
                "raster_file": c_mask.get("raster_file", ""),
                "rgb_masks": c_mask.get("rgb_masks", []),
                "valid_years": child_ent.get("valid_years", [1750, 2025]) if child_ent else [1750, 2025],
                "zone_ids": c_mask.get("zone_ids", [])
              }
            raw_to_stem = (g_rec or {}).get("raw_keys_to_stem", {})
            a3_series_total = a3_series_total + len(raw_to_stem)
            if g_rec and g_mask and g_mask.get("rgb_masks") and g_rec["metrics"]["pixel_count"] > 0:
              top_accounted = top_accounted + 1
            else:
              unaccounted_list.append(f"{local_vol}:A3:{local_k}")
            group_entry = {
              "category": "admin_group",
              "entity_ids": [g_rec["entity_id"]] if g_rec else [],
              "hex_masks": g_mask.get("hex_masks", []) if g_mask else [],
              "pixel_count": g_rec["metrics"]["pixel_count"] if g_rec else 0,
              "raster_file": g_mask.get("raster_file", "") if g_mask else "",
              "rgb_masks": g_mask.get("rgb_masks", []) if g_mask else [],
              "series_keys": raw_to_stem,
              "stems": stems_out,
              "zone_ids": g_mask.get("zone_ids", []) if g_mask else []
            }
            if g_mask and "secondary_city_masks" in g_mask:
              group_entry["secondary_city_masks"] = g_mask["secondary_city_masks"]
            sec_out[local_k] = group_entry

          elif local_sec == "A4" and not self.city_resolver.isNonCityCorpusKey(local_vol, local_sec, local_k):
            c_ent = cities_map.get(local_k)
            c_eid = c_ent["entity_id"] if c_ent else f"city:{local_k}"
            c_mask = self.synthesizer.entity_mask_lookup.get(c_eid, {})
            px_cnt = c_ent["metrics"]["pixel_count"] if c_ent else 0
            if c_mask.get("rgb_masks") and px_cnt > 0:
              top_accounted = top_accounted + 1
            else:
              unaccounted_list.append(f"{local_vol}:A4:{local_k}")
            sec_out[local_k] = {
              "category": "city",
              "coord_wgs84": c_ent.get("coord_wgs84", [0.0, 0.0]) if c_ent else [0.0, 0.0],
              "entity_ids": [c_eid],
              "hex_masks": c_mask.get("hex_masks", []),
              "pixel_count": px_cnt,
              "raster_file": c_mask.get("raster_file", "cities.png"),
              "rgb_masks": c_mask.get("rgb_masks", []),
              "zone_ids": c_mask.get("zone_ids", [])
            }

          else:
            c_ids = self.country_resolver.B_resolveCorpusCountryKey(local_vol, local_sec, local_k, local_val)
            entry_obj = self.buildCountryLocationEntry(c_ids, countries_map)
            if entry_obj["rgb_masks"] and entry_obj["pixel_count"] > 0:
              top_accounted = top_accounted + 1
            else:
              unaccounted_list.append(f"{local_vol}:{local_sec}:{local_k}")
            sec_out[local_k] = entry_obj

        volume_masks_map[local_vol][local_sec] = sec_out

    #Return statement
    return (
      volume_masks_map,
      {
        "a3_series_keys_total": a3_series_total,
        "a3_stems_accounted": a3_stems_accounted,
        "a3_stems_total": a3_stems_total,
        "section_files_count": section_count,
        "top_locations_accounted": top_accounted,
        "top_locations_total": top_total,
        "unaccounted_locations": unaccounted_list
      }
    )


  def E_runFullPipeline (self):
    """
    @brief Step E: Execute the full areal mask synthesis pipeline and verify 100% PNG and JSON location coverage.
    @return Summary and verification report dictionary.
    """
    #Declare local instance variables
    all_entities_list = []
    counters = {}
    elapsed_sec = 0.0
    grid_cfg = self.config_obj.get("grid", {})
    png_audit = {}
    raster_summary = {}
    resolved_bundle = {}
    start_ts = time.time()
    summary_obj = {}
    volume_masks_map = {}

    print(self.config_loader.formatLocalisedString(
      "masks_initialised",
      [grid_cfg.get("width", 4320), grid_cfg.get("height", 2160), grid_cfg.get("crs", "EPSG:4326")]
    ))

    self.A_loadCorpusSections()
    resolved_bundle = self.B_resolveAllEntities()
    raster_summary = self.C_synthesiseRasters(resolved_bundle)
    volume_masks_map, counters = self.D_indexAllCorpusLocations(resolved_bundle)
    png_audit = self.verifyExportedPngRasters(raster_summary)

    for _, v in resolved_bundle["countries"].items():
      all_entities_list.append(v)
    for _, v in resolved_bundle["divisions"].items():
      all_entities_list.append(v)
    for _, v in resolved_bundle["groups"].items():
      all_entities_list.append(v)
    for _, v in resolved_bundle["cities"].items():
      all_entities_list.append(v)

    elapsed_sec = round(time.time() - start_ts, 2)
    summary_obj = {
      "counts": {
        "a3_admin_divisions_resolved": len(resolved_bundle["divisions"]),
        "a3_groups_resolved": len(resolved_bundle["groups"]),
        "a3_raw_series_keys_indexed": counters["a3_series_keys_total"],
        "a3_stems_accounted": counters["a3_stems_accounted"],
        "a3_stems_total": counters["a3_stems_total"],
        "atomic_city_zones_count": raster_summary["cities"]["city_zone_count"],
        "atomic_provinces_count": raster_summary["provinces"]["province_count"],
        "canonical_countries_resolved": len(resolved_bundle["countries"]),
        "cities_resolved": len(resolved_bundle["cities"]),
        "corpus_section_files": counters["section_files_count"],
        "top_level_locations_accounted": counters["top_locations_accounted"],
        "top_level_locations_total": counters["top_locations_total"],
        "unaccounted_count": len(counters["unaccounted_locations"])
      },
      "elapsed_seconds": elapsed_sec,
      "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
      "grid": grid_cfg,
      "png_verification": png_audit,
      "unaccounted_locations": counters["unaccounted_locations"]
    }

    self.synthesizer.E_exportJsonRegistries(all_entities_list, volume_masks_map, summary_obj)

    print(self.config_loader.formatLocalisedString(
      "masks_verified_done",
      [
        counters["top_locations_accounted"],
        counters["top_locations_total"],
        len(counters["unaccounted_locations"]),
        counters["section_files_count"],
        elapsed_sec
      ]
    ))

    #Return statement
    return summary_obj


  def buildCountryLocationEntry (self, arg1_country_ids, arg2_countries_map):
    """
    @brief Build a complete provinces.png RGB mask record (including temporal_eras masks) for 1+ canonical country IDs.
    @param arg1_country_ids List of canonical country IDs.
    @param arg2_countries_map Dictionary of resolved canonical country entities.
    @return Location mask dictionary.
    """
    #Convert from parameters
    country_ids = arg1_country_ids if isinstance(arg1_country_ids, list) else []
    countries_map = arg2_countries_map if isinstance(arg2_countries_map, dict) else {}

    #Declare local instance variables
    flat_parts = []
    hex_map = {}
    pixel_count = 0
    temporal_out = []
    zids_set = set()

    for i in range(len(country_ids)):
      cid = country_ids[i]
      c_ent = countries_map.get(cid)
      c_mask = self.synthesizer.entity_mask_lookup.get(cid, {})
      if c_ent is not None and c_ent["flat_indices"].size > 0:
        flat_parts.append(c_ent["flat_indices"])
      for x in range(len(c_mask.get("hex_masks", []))):
        hx = c_mask["hex_masks"][x]
        hex_map[hx] = c_mask["rgb_masks"][x]
      for x in range(len(c_mask.get("zone_ids", []))):
        zids_set.add(c_mask["zone_ids"][x])

      if len(country_ids) == 1 and c_ent and c_ent.get("temporal_eras"):
        for x in range(len(c_ent["temporal_eras"])):
          era_item = c_ent["temporal_eras"][x]
          era_eid = era_item.get("entity_id", "")
          era_mask = self.synthesizer.entity_mask_lookup.get(era_eid, {})
          temporal_out.append({
            "end_year": era_item.get("end_year"),
            "entity_id": era_eid,
            "hex_masks": era_mask.get("hex_masks", []),
            "label": era_item.get("label", ""),
            "rgb_masks": era_mask.get("rgb_masks", []),
            "start_year": era_item.get("start_year"),
            "zone_ids": era_mask.get("zone_ids", [])
          })

    if flat_parts:
      pixel_count = int(np.unique(np.concatenate(flat_parts)).size)

    sorted_hex = sorted(hex_map.keys())
    out_obj = {
      "category": "country",
      "entity_ids": country_ids,
      "hex_masks": sorted_hex,
      "pixel_count": pixel_count,
      "raster_file": str(self.config_obj.get("outputs", {}).get("provinces_png", "provinces.png")),
      "rgb_masks": [hex_map[h] for h in sorted_hex],
      "zone_ids": sorted(zids_set)
    }
    if temporal_out:
      out_obj["temporal_eras"] = temporal_out

    #Return statement
    return out_obj


  def verifyExportedPngRasters (self, arg1_raster_summary):
    """
    @brief Read back every exported PNG image on disk to verify 4320x2160 RGB dimensions and non-zero RGB presence.
    @param arg1_raster_summary Output dictionary from C_synthesiseRasters.
    @return Verification audit dictionary per PNG file.
    """
    #Convert from parameters
    raster_summary = arg1_raster_summary if isinstance(arg1_raster_summary, dict) else {}

    #Declare local instance variables
    all_png_paths = []
    audit_map = {}
    expected_h = self.rasteriser.height
    expected_w = self.rasteriser.width

    if "provinces" in raster_summary:
      all_png_paths.append(raster_summary["provinces"]["png_path"])
    if "cities" in raster_summary:
      all_png_paths.append(raster_summary["cities"]["png_path"])
    for _, local_p in sorted(raster_summary.get("check_maps", {}).items()):
      all_png_paths.append(local_p)

    for i in range(len(all_png_paths)):
      p_path = all_png_paths[i]
      bname = os.path.basename(p_path)
      if not os.path.exists(p_path):
        audit_map[bname] = {"exists": False, "valid": False}
        continue
      with Image.open(p_path) as local_im:
        arr = np.asarray(local_im)
        codes = (arr[:, :, 0].astype(np.uint32) << 16) | (arr[:, :, 1].astype(np.uint32) << 8) | arr[:, :, 2].astype(np.uint32)
        nz_codes = np.unique(codes[codes > 0])
        audit_map[bname] = {
          "dimensions_px": [int(local_im.size[0]), int(local_im.size[1])],
          "exists": True,
          "file_size_bytes": int(os.path.getsize(p_path)),
          "mode": local_im.mode,
          "non_zero_pixels": int(np.count_nonzero(codes)),
          "unique_non_zero_rgb_count": int(nz_codes.size),
          "valid": (local_im.size == (expected_w, expected_h) and local_im.mode == "RGB" and nz_codes.size > 0)
        }

    #Return statement
    return audit_map
