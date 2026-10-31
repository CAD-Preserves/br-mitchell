"""@brief Synthesises collision-free 4320x2160 RGB province and city PNG rasters and JSON mask registries."""

import os
import sys
import numpy as np
import orjson


class ProvinceMapSynthesizer:
  """@brief Partitions overlapping historical/modern masks into atomic RGB provinces and exports PNG/JSON deliverables."""

  def __init__ (self, arg1_root_dir, arg2_config_obj, arg3_rasteriser):
    """
    @brief Initialise ProvinceMapSynthesizer with workspace root, config dictionary, and EquirectangularRasteriser.
    @param arg1_root_dir Repository root path.
    @param arg2_config_obj Parsed areal_mask_config.json5 dictionary.
    @param arg3_rasteriser EquirectangularRasteriser instance.
    """
    #Convert from parameters
    root_dir = str(arg1_root_dir or "")
    config_obj = arg2_config_obj if isinstance(arg2_config_obj, dict) else {}
    rasteriser = arg3_rasteriser

    #Declare local instance variables
    out_rel = config_obj.get("paths", {}).get("output_dir", os.path.join("output", "areal_masks"))
    self.city_zones_catalog = {}
    self.config_obj = config_obj
    self.entity_mask_lookup = {}
    self.output_dir = os.path.join(root_dir, out_rel)
    self.outputs_cfg = config_obj.get("outputs", {})
    self.provinces_catalog = {}
    self.rasteriser = rasteriser
    self.root_dir = root_dir

    os.makedirs(self.output_dir, exist_ok=True)


  def A_synthesiseProvincesPng (self, arg1_countries_map, arg2_divisions_map):
    """
    @brief Step A: Partition all modern/historical country and admin-division masks into atomic RGB provinces on provinces.png.
    @param arg1_countries_map Dictionary of resolved canonical country entities.
    @param arg2_divisions_map Dictionary of resolved canonical admin-division entities.
    @return Dictionary containing province_count, covered_pixels, and png_path.
    """
    #Convert from parameters
    countries_map = arg1_countries_map if isinstance(arg1_countries_map, dict) else {}
    divisions_map = arg2_divisions_map if isinstance(arg2_divisions_map, dict) else {}

    #Declare local instance variables
    combined_entities = []
    country_ids = sorted(countries_map.keys())
    div_ids = sorted(divisions_map.keys())
    png_filename = str(self.outputs_cfg.get("provinces_png", "provinces.png"))
    png_path = os.path.join(self.output_dir, png_filename)
    synth_res = {}

    for i in range(len(country_ids)):
      combined_entities.append(countries_map[country_ids[i]])
    for i in range(len(div_ids)):
      combined_entities.append(divisions_map[div_ids[i]])

    synth_res = self.partitionEquivalenceClasses(combined_entities, "prov", png_filename, png_path, 104729)
    self.provinces_catalog = synth_res["zones_catalog"]

    for local_eid, local_mask_info in synth_res["entity_masks"].items():
      self.entity_mask_lookup[local_eid] = local_mask_info

    #Return statement
    return {
      "covered_pixels": synth_res["covered_pixels"],
      "png_path": png_path,
      "province_count": len(self.provinces_catalog)
    }


  def B_synthesiseCitiesPng (self, arg1_cities_map):
    """
    @brief Step B: Partition all resolved city footprints into distinct non-zero RGB zones on cities.png.
    @param arg1_cities_map Dictionary of resolved city entities.
    @return Dictionary containing city_zone_count, covered_pixels, and png_path.
    """
    #Convert from parameters
    cities_map = arg1_cities_map if isinstance(arg1_cities_map, dict) else {}

    #Declare local instance variables
    city_entities = []
    city_ids = sorted(cities_map.keys())
    png_filename = str(self.outputs_cfg.get("cities_png", "cities.png"))
    png_path = os.path.join(self.output_dir, png_filename)
    synth_res = {}

    for i in range(len(city_ids)):
      city_entities.append(cities_map[city_ids[i]])

    synth_res = self.partitionEquivalenceClasses(city_entities, "city_zone", png_filename, png_path, 224737)
    self.city_zones_catalog = synth_res["zones_catalog"]

    for local_eid, local_mask_info in synth_res["entity_masks"].items():
      self.entity_mask_lookup[local_eid] = local_mask_info

    #Return statement
    return {
      "city_zone_count": len(self.city_zones_catalog),
      "covered_pixels": synth_res["covered_pixels"],
      "png_path": png_path
    }


  def C_renderCategoryCheckMaps (self, arg1_countries_map, arg2_divisions_map):
    """
    @brief Step C: Render standalone 4320x2160 visual-inspection PNG maps for modern/historical countries and divisions.
    @param arg1_countries_map Dictionary of resolved country entities.
    @param arg2_divisions_map Dictionary of resolved administrative division entities.
    @return Dictionary mapping check-map key -> exported PNG path.
    """
    #Convert from parameters
    countries_map = arg1_countries_map if isinstance(arg1_countries_map, dict) else {}
    divisions_map = arg2_divisions_map if isinstance(arg2_divisions_map, dict) else {}

    #Declare local instance variables
    admin_hist = []
    admin_mod = []
    countries_1914 = []
    countries_1960 = []
    countries_mod = []
    exported_paths = {}

    for _, local_c in countries_map.items():
      era = local_c.get("era_type", "modern")
      vy = local_c.get("valid_years", [1750, 2025])
      if era == "modern":
        countries_mod.append(local_c)
      if vy[0] <= 1914 <= vy[1] and (era == "historical" or not local_c.get("temporal_eras")):
        countries_1914.append(local_c)
      if vy[0] <= 1960 <= vy[1] and (era == "historical" or not local_c.get("temporal_eras")):
        countries_1960.append(local_c)

    for _, local_d in divisions_map.items():
      if local_d.get("era_type") == "historical":
        admin_hist.append(local_d)
      else:
        admin_mod.append(local_d)

    map_specs = [
      ("countries_modern_png", "countries_modern.png", countries_mod, 311),
      ("countries_historical_1914_png", "countries_historical_1914.png", countries_1914, 613),
      ("countries_historical_1960_png", "countries_historical_1960.png", countries_1960, 919),
      ("admin_divisions_modern_png", "admin_divisions_modern.png", admin_mod, 1223),
      ("admin_divisions_historical_png", "admin_divisions_historical.png", admin_hist, 1531)
    ]

    for i in range(len(map_specs)):
      cfg_key, default_name, ent_list, seed_val = map_specs[i]
      out_name = str(self.outputs_cfg.get(cfg_key, default_name))
      out_path = os.path.join(self.output_dir, out_name)
      self.renderLayeredInspectionPng(ent_list, out_path, seed_val)
      exported_paths[cfg_key] = out_path

    #Return statement
    return exported_paths


  def D_registerAdminGroupMasks (self, arg1_groups_map):
    """
    @brief Step D: Aggregate constituent province/city RGB masks for all 57 A3 parent group headers.
    @param arg1_groups_map Dictionary mapping '<volume>:<group_key>' -> resolved admin_group dictionary.
    @return Updated entity_mask_lookup entries for admin_group entities.
    """
    #Convert from parameters
    groups_map = arg1_groups_map if isinstance(arg1_groups_map, dict) else {}

    #Declare local instance variables
    group_keys = sorted(groups_map.keys())

    for i in range(len(group_keys)):
      local_gk = group_keys[i]
      g_rec = groups_map[local_gk]
      g_eid = g_rec["entity_id"]
      stem_entities = g_rec.get("stem_to_entity_id", {})
      prov_hex_set = set()
      prov_rgb_map = {}
      prov_ids_set = set()
      city_hex_set = set()
      city_rgb_map = {}
      city_ids_set = set()

      for _, child_eid in sorted(stem_entities.items()):
        child_mask = self.entity_mask_lookup.get(child_eid)
        if not child_mask:
          continue
        if child_mask["raster_file"] == str(self.outputs_cfg.get("cities_png", "cities.png")):
          for x in range(len(child_mask["hex_masks"])):
            hx = child_mask["hex_masks"][x]
            city_hex_set.add(hx)
            city_rgb_map[hx] = child_mask["rgb_masks"][x]
          for x in range(len(child_mask["zone_ids"])):
            city_ids_set.add(child_mask["zone_ids"][x])
        else:
          for x in range(len(child_mask["hex_masks"])):
            hx = child_mask["hex_masks"][x]
            prov_hex_set.add(hx)
            prov_rgb_map[hx] = child_mask["rgb_masks"][x]
          for x in range(len(child_mask["zone_ids"])):
            prov_ids_set.add(child_mask["zone_ids"][x])

      # Also include any header-only division (e.g. admin:rus_gub:ufa)
      if local_gk == "europe:ufa" and "admin:rus_gub:ufa" in self.entity_mask_lookup:
        u_mask = self.entity_mask_lookup["admin:rus_gub:ufa"]
        for x in range(len(u_mask["hex_masks"])):
          hx = u_mask["hex_masks"][x]
          prov_hex_set.add(hx)
          prov_rgb_map[hx] = u_mask["rgb_masks"][x]
        for x in range(len(u_mask["zone_ids"])):
          prov_ids_set.add(u_mask["zone_ids"][x])

      if prov_hex_set:
        sorted_hex = sorted(prov_hex_set)
        entry_obj = {
          "hex_masks": sorted_hex,
          "raster_file": str(self.outputs_cfg.get("provinces_png", "provinces.png")),
          "rgb_masks": [prov_rgb_map[h] for h in sorted_hex],
          "zone_ids": sorted(prov_ids_set)
        }
        if city_hex_set:
          sorted_chex = sorted(city_hex_set)
          entry_obj["secondary_city_masks"] = {
            "hex_masks": sorted_chex,
            "raster_file": str(self.outputs_cfg.get("cities_png", "cities.png")),
            "rgb_masks": [city_rgb_map[h] for h in sorted_chex],
            "zone_ids": sorted(city_ids_set)
          }
      else:
        sorted_chex = sorted(city_hex_set)
        entry_obj = {
          "hex_masks": sorted_chex,
          "raster_file": str(self.outputs_cfg.get("cities_png", "cities.png")),
          "rgb_masks": [city_rgb_map[h] for h in sorted_chex],
          "zone_ids": sorted(city_ids_set)
        }

      self.entity_mask_lookup[g_eid] = entry_obj

    #Return statement
    return self.entity_mask_lookup


  def E_exportJsonRegistries (self, arg1_all_entities_list, arg2_volume_masks_map, arg3_summary_obj):
    """
    @brief Step E: Write provinces_catalog.json, entities_registry.json, location_index.json, <vol>_masks.json, and summary.json.
    @param arg1_all_entities_list List of all resolved country, admin_division, admin_group, and city records.
    @param arg2_volume_masks_map Dictionary mapping volume_id -> structured section->location mask index.
    @param arg3_summary_obj Pipeline run summary and verification metrics dictionary.
    @return Dictionary of written JSON file paths.
    """
    #Convert from parameters
    all_entities_list = arg1_all_entities_list if isinstance(arg1_all_entities_list, list) else []
    volume_masks_map = arg2_volume_masks_map if isinstance(arg2_volume_masks_map, dict) else {}
    summary_obj = arg3_summary_obj if isinstance(arg3_summary_obj, dict) else {}

    #Declare local instance variables
    entities_out = {}
    grid_meta = self.config_obj.get("grid", {})
    written_paths = {}

    catalog_payload = {
      "background_rgb": [0, 0, 0],
      "city_zones": self.city_zones_catalog,
      "city_zones_png": str(self.outputs_cfg.get("cities_png", "cities.png")),
      "grid": grid_meta,
      "provinces": self.provinces_catalog,
      "provinces_png": str(self.outputs_cfg.get("provinces_png", "provinces.png"))
    }
    p_cat = os.path.join(self.output_dir, str(self.outputs_cfg.get("provinces_catalog_json", "provinces_catalog.json")))
    self.writeJsonFast(p_cat, catalog_payload)
    written_paths["provinces_catalog_json"] = p_cat

    sorted_ents = sorted(all_entities_list, key=lambda local_e: local_e["entity_id"])
    for i in range(len(sorted_ents)):
      ent = sorted_ents[i]
      eid = ent["entity_id"]
      mask_info = self.entity_mask_lookup.get(eid, {"hex_masks": [], "raster_file": "", "rgb_masks": [], "zone_ids": []})
      rec_clean = {
        "category": ent.get("category", ""),
        "entity_id": eid,
        "era_type": ent.get("era_type", "modern"),
        "hex_masks": mask_info.get("hex_masks", []),
        "metrics": ent.get("metrics", {}),
        "name": ent.get("name", eid),
        "raster_file": mask_info.get("raster_file", ""),
        "rgb_masks": mask_info.get("rgb_masks", []),
        "source_summary": ent.get("source_summary", {}),
        "valid_years": ent.get("valid_years", [1750, 2025]),
        "zone_ids": mask_info.get("zone_ids", [])
      }
      if "coord_wgs84" in ent:
        rec_clean["coord_wgs84"] = ent["coord_wgs84"]
      if ent.get("temporal_eras"):
        rec_clean["temporal_eras"] = ent["temporal_eras"]
      if "secondary_city_masks" in mask_info:
        rec_clean["secondary_city_masks"] = mask_info["secondary_city_masks"]
      entities_out[eid] = rec_clean

    p_ent = os.path.join(self.output_dir, str(self.outputs_cfg.get("entities_registry_json", "entities_registry.json")))
    self.writeJsonFast(p_ent, {"entities": entities_out, "grid": grid_meta})
    written_paths["entities_registry_json"] = p_ent

    for local_vol, vol_payload in sorted(volume_masks_map.items()):
      p_vol = os.path.join(self.output_dir, f"{local_vol}_masks.json")
      self.writeJsonFast(p_vol, {"grid": grid_meta, "sections": vol_payload, "volume": local_vol})
      written_paths[f"{local_vol}_masks_json"] = p_vol

    p_idx = os.path.join(self.output_dir, str(self.outputs_cfg.get("location_index_json", "location_index.json")))
    self.writeJsonFast(p_idx, {"grid": grid_meta, "volumes": volume_masks_map})
    written_paths["location_index_json"] = p_idx

    p_sum = os.path.join(self.output_dir, str(self.outputs_cfg.get("summary_json", "summary.json")))
    self.writeJsonFast(p_sum, summary_obj)
    written_paths["summary_json"] = p_sum

    #Return statement
    return written_paths


  def generateDistinctRgbPalette (self, arg1_count, arg2_seed):
    """
    @brief Generate deterministic, collision-free, high-visibility non-zero RGB colours ([R, G, B] != [0, 0, 0]).
    @param arg1_count Number of unique colours required.
    @param arg2_seed Integer seed controlling coprime stride offset.
    @return List of [R, G, B] integer triplets.
    """
    #Convert from parameters
    count = max(0, int(arg1_count))
    seed = int(arg2_seed)

    #Declare local instance variables
    colours_array = []
    state = (seed*2654435761) & 0xFFFFFF
    step = 1046527  # Odd integer coprime to 2^24 = 16,777,216 (bijective full-period cycle!)
    used_codes = set([0])

    for _ in range(count*4 + 64):
      if len(colours_array) >= count:
        break
      state = (state + step) & 0xFFFFFF
      if state in used_codes:
        continue
      r_ch = (state >> 16) & 0xFF
      g_ch = (state >> 8) & 0xFF
      b_ch = state & 0xFF
      if max(r_ch, g_ch, b_ch) < 32:
        continue
      used_codes.add(state)
      colours_array.append([int(r_ch), int(g_ch), int(b_ch)])

    #Return statement
    return colours_array


  def partitionEquivalenceClasses (self, arg1_entities_array, arg2_id_prefix, arg3_png_name, arg4_png_path, arg5_seed):
    """
    @brief Partition pixels across potentially overlapping entities into exact atomic equivalence classes with certified 0 collisions.
    @param arg1_entities_array List of entity dicts with 'entity_id' and sorted 'flat_indices'.
    @param arg2_id_prefix String prefix for generated zone IDs ('prov' or 'city_zone').
    @param arg3_png_name Basename of target PNG file.
    @param arg4_png_path Full path to write target PNG file.
    @param arg5_seed Deterministic palette & Zobrist seed.
    @return Dictionary containing zones_catalog, entity_masks, and covered_pixels.
    """
    #Convert from parameters
    entities_array = arg1_entities_array if isinstance(arg1_entities_array, list) else []
    id_prefix = str(arg2_id_prefix or "prov")
    png_name = str(arg3_png_name or "provinces.png")
    png_path = str(arg4_png_path or "")
    seed = int(arg5_seed)

    #Declare local instance variables
    active_px = None
    deg = np.zeros(self.rasteriser.total_pixels, dtype=np.uint16)
    entity_masks_out = {}
    flat_rgb = np.zeros((self.rasteriser.total_pixels, 3), dtype=np.uint8)
    h1 = np.zeros(self.rasteriser.total_pixels, dtype=np.uint64)
    h2 = np.zeros(self.rasteriser.total_pixels, dtype=np.uint64)
    num_ents = len(entities_array)
    palette = []
    pixel_to_zone = np.zeros(self.rasteriser.total_pixels, dtype=np.int32)
    rng = np.random.default_rng(seed)
    z1 = rng.integers(1, (1 << 63) - 1, size=max(1, num_ents), dtype=np.uint64)
    z2 = rng.integers(1, (1 << 63) - 1, size=max(1, num_ents), dtype=np.uint64)
    zones_catalog = {}

    for i in range(num_ents):
      idx = entities_array[i]["flat_indices"]
      if idx.size > 0:
        h1[idx] ^= z1[i]
        h2[idx] ^= z2[i]
        deg[idx] += 1

    active_px = np.flatnonzero(deg > 0)
    if active_px.size == 0:
      self.rasteriser.B_exportRgbPng(flat_rgb.reshape(self.rasteriser.height, self.rasteriser.width, 3), png_path)
      return {"covered_pixels": 0, "entity_masks": entity_masks_out, "zones_catalog": zones_catalog}

    sig_dtype = np.dtype([("h1", "<u8"), ("h2", "<u8"), ("deg", "<u2")])
    sigs = np.empty(active_px.size, dtype=sig_dtype)
    sigs["h1"] = h1[active_px]
    sigs["h2"] = h2[active_px]
    sigs["deg"] = deg[active_px]

    unique_sigs, inv_idx = np.unique(sigs, return_inverse=True)
    num_zones = int(unique_sigs.size)
    pixel_to_zone[active_px] = inv_idx.astype(np.int32) + 1

    # Group active pixels per zone in O(active_px) via argsort
    order = np.argsort(inv_idx, kind="mergesort")
    sorted_active_px = active_px[order]
    sorted_inv = inv_idx[order]
    zone_splits = np.flatnonzero(np.diff(sorted_inv)) + 1
    zone_pixel_arrays = np.split(sorted_active_px, zone_splits)

    palette = self.generateDistinctRgbPalette(num_zones, seed)
    zone_members = [[] for _ in range(num_zones)]

    for i in range(num_ents):
      eid = entities_array[i]["entity_id"]
      idx = entities_array[i]["flat_indices"]
      if idx.size == 0:
        entity_masks_out[eid] = {"hex_masks": [], "raster_file": png_name, "rgb_masks": [], "zone_ids": []}
        continue
      z_hits = np.unique(pixel_to_zone[idx])
      rgb_list = []
      hex_list = []
      zid_list = []
      for x in range(z_hits.size):
        zi = int(z_hits[x]) - 1
        if zi >= 0:
          zone_members[zi].append(eid)
          rgb_c = palette[zi]
          hx = f"#{rgb_c[0]:02X}{rgb_c[1]:02X}{rgb_c[2]:02X}"
          zid = f"{id_prefix}_{zi + 1:05d}"
          rgb_list.append(rgb_c)
          hex_list.append(hx)
          zid_list.append(zid)
      entity_masks_out[eid] = {
        "hex_masks": hex_list,
        "raster_file": png_name,
        "rgb_masks": rgb_list,
        "zone_ids": zid_list
      }

    for i in range(num_zones):
      expected_d = int(unique_sigs[i]["deg"])
      if len(zone_members[i]) != expected_d:
        sys.stderr.write(f"Console error: Zobrist degree mismatch on zone {i + 1}: {len(zone_members[i])} != {expected_d}\n")
      z_px = np.sort(zone_pixel_arrays[i].astype(np.int32))
      rgb_c = palette[i]
      flat_rgb[z_px, 0] = rgb_c[0]
      flat_rgb[z_px, 1] = rgb_c[1]
      flat_rgb[z_px, 2] = rgb_c[2]
      zid = f"{id_prefix}_{i + 1:05d}"
      hx = f"#{rgb_c[0]:02X}{rgb_c[1]:02X}{rgb_c[2]:02X}"
      z_metrics = self.rasteriser.computeMaskMetrics(z_px)
      zones_catalog[zid] = {
        "bbox_px": z_metrics["bbox_px"],
        "bbox_wgs84": z_metrics["bbox_wgs84"],
        "centroid_wgs84": z_metrics["centroid_wgs84"],
        "hex": hx,
        "member_entities": zone_members[i],
        "pixel_count": z_metrics["pixel_count"],
        "rgb": rgb_c,
        "zone_id": zid
      }

    self.rasteriser.B_exportRgbPng(flat_rgb.reshape(self.rasteriser.height, self.rasteriser.width, 3), png_path)

    #Return statement
    return {
      "covered_pixels": int(active_px.size),
      "entity_masks": entity_masks_out,
      "zones_catalog": zones_catalog
    }


  def renderLayeredInspectionPng (self, arg1_entities_list, arg2_output_path, arg3_seed):
    """
    @brief Render a direct visual-inspection 4320x2160 PNG painting larger territories first and smaller enclaves on top.
    @param arg1_entities_list List of resolved entity records.
    @param arg2_output_path Destination PNG path.
    @param arg3_seed Palette seed integer.
    @return Boolean True on export completion.
    """
    #Convert from parameters
    entities_list = arg1_entities_list if isinstance(arg1_entities_list, list) else []
    output_path = str(arg2_output_path or "")
    seed = int(arg3_seed)

    #Declare local instance variables
    flat_rgb = np.zeros((self.rasteriser.total_pixels, 3), dtype=np.uint8)
    ordered = sorted(entities_list, key=lambda local_e: (-int(local_e["flat_indices"].size), local_e["entity_id"]))
    palette = self.generateDistinctRgbPalette(len(ordered), seed)

    for i in range(len(ordered)):
      idx = ordered[i]["flat_indices"]
      if idx.size > 0:
        rgb_c = palette[i]
        flat_rgb[idx, 0] = rgb_c[0]
        flat_rgb[idx, 1] = rgb_c[1]
        flat_rgb[idx, 2] = rgb_c[2]

    #Return statement
    return self.rasteriser.B_exportRgbPng(flat_rgb.reshape(self.rasteriser.height, self.rasteriser.width, 3), output_path)


  def writeJsonFast (self, arg1_path, arg2_payload_obj):
    """
    @brief Serialise a JSON payload atomically with 2-space indentation using orjson.
    @param arg1_path Destination JSON path.
    @param arg2_payload_obj Dictionary payload to serialise.
    """
    #Convert from parameters
    path = str(arg1_path or "")
    payload_obj = arg2_payload_obj

    #Declare local instance variables
    tmp_path = f"{path}.part"

    if not path:
      return

    try:
      os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
      with open(tmp_path, "wb") as local_fh:
        local_fh.write(orjson.dumps(payload_obj, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS))
      os.replace(tmp_path, path)
    except Exception as local_err:
      sys.stderr.write(f"Console error: failed writing JSON {path}: {local_err}\n")
