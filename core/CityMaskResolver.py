"""@brief Resolves individual city areal masks via Wikipedia GeoHack, Photon (OpenStreetMap), and Natural Earth 10m urban footprints."""

from concurrent.futures import ThreadPoolExecutor
import math
import sys
import numpy as np
from shapely.geometry import Point, box


class CityMaskResolver:
  """@brief Geocodes and rasterises all corpus cities using GeoHack + Photon OSM + Voronoi-partitioned urban polygons."""

  def __init__ (self, arg1_fetcher, arg2_rasteriser, arg3_city_rules_obj):
    """
    @brief Initialise CityMaskResolver with GeoJsonFetcher, EquirectangularRasteriser, and parsed city_rules.json5.
    @param arg1_fetcher GeoJsonFetcher instance.
    @param arg2_rasteriser EquirectangularRasteriser instance.
    @param arg3_city_rules_obj Parsed city_rules.json5 dictionary.
    """
    #Convert from parameters
    fetcher = arg1_fetcher
    rasteriser = arg2_rasteriser
    city_rules_obj = arg3_city_rules_obj if isinstance(arg3_city_rules_obj, dict) else {}

    #Declare local instance variables
    self.cities_cfg = city_rules_obj.get("cities", {})
    self.country_suffixes_cfg = city_rules_obj.get("country_suffixes", {})
    self.fetcher = fetcher
    self.non_city_keys_set = set(city_rules_obj.get("non_city_keys", []))
    self.rasteriser = rasteriser
    self.resolved_cities_obj = {}
    self.sorted_suffixes = sorted(self.country_suffixes_cfg.keys(), key=lambda local_s: len(local_s), reverse=True)
    self.urban_polys_list = []


  def A_resolveAllCities (self, arg1_city_keys_array):
    """
    @brief Step A: Geocode all unique city keys via Wikipedia GeoHack and Photon OSM, then rasterise urban masks.
    @param arg1_city_keys_array List of unique canonical city_id keys across A4 and europe/A3.
    @return Dictionary mapping city_id -> resolved city entity dictionary with flat_indices and metrics.
    """
    #Convert from parameters
    city_keys_array = arg1_city_keys_array if isinstance(arg1_city_keys_array, list) else []

    #Declare local instance variables
    city_coords_map = {}
    photon_results_map = {}
    plans_map = {}
    unique_keys = sorted(set(str(k).strip() for k in city_keys_array if str(k).strip()))
    urban_assignments = {}
    wiki_results_map = {}
    wiki_titles = []

    self.loadUrbanPolygons()

    for i in range(len(unique_keys)):
      local_cid = unique_keys[i]
      local_plan = self.buildCityQueryPlan(local_cid)
      plans_map[local_cid] = local_plan
      if local_plan["wiki"] and local_plan["wiki"] not in wiki_titles:
        wiki_titles.append(local_plan["wiki"])
      if local_plan["wiki_fallback"] and local_plan["wiki_fallback"] not in wiki_titles:
        wiki_titles.append(local_plan["wiki_fallback"])

    wiki_results_map = self.fetcher.C_fetchWikipediaCoordinatesBatch(wiki_titles)
    photon_results_map = self.fetchPhotonBatch(plans_map)

    for i in range(len(unique_keys)):
      local_cid = unique_keys[i]
      local_plan = plans_map[local_cid]
      local_coord = self.selectBestCoordinates(local_cid, local_plan, wiki_results_map, photon_results_map.get(local_cid))
      city_coords_map[local_cid] = local_coord

    urban_assignments = self.buildUrbanPolygonAssignments(city_coords_map)

    for i in range(len(unique_keys)):
      local_cid = unique_keys[i]
      local_plan = plans_map[local_cid]
      local_coord = city_coords_map[local_cid]
      local_photon = photon_results_map.get(local_cid)
      local_urban_idx = urban_assignments.get(local_cid)
      self.resolved_cities_obj[local_cid] = self.rasteriseCityEntity(
        local_cid,
        local_plan,
        local_coord,
        local_photon,
        local_urban_idx
      )

    #Return statement
    return self.resolved_cities_obj


  def buildCityQueryPlan (self, arg1_city_id):
    """
    @brief Construct Wikipedia GeoHack title and Photon OpenStreetMap query parameters for a city key.
    @param arg1_city_id Canonical city key (e.g. 'constantinople', 'akron_usa', 'bradford').
    @return Dictionary containing name, query, wiki, wiki_fallback, and iso2.
    """
    #Convert from parameters
    city_id = str(arg1_city_id or "").strip()

    #Declare local instance variables
    base_slug = city_id
    country_name = ""
    display_name = ""
    iso2_code = ""
    query_str = ""
    rule_obj = {}
    wiki_fallback = ""
    wiki_title = ""

    if city_id in self.cities_cfg:
      rule_obj = self.cities_cfg[city_id]
      display_name = str(rule_obj.get("name") or city_id.replace("_", " ").title())
      wiki_title = str(rule_obj.get("wiki") or display_name)
      query_str = str(rule_obj.get("query") or display_name)
      iso2_code = str(rule_obj.get("iso2") or "").upper()
      return {
        "iso2": iso2_code,
        "name": display_name,
        "query": query_str,
        "wiki": wiki_title,
        "wiki_fallback": query_str.split(",")[0].strip()
      }

    for i in range(len(self.sorted_suffixes)):
      local_sfx = self.sorted_suffixes[i]
      if city_id.endswith(f"_{local_sfx}") and len(city_id) > len(local_sfx) + 1:
        base_slug = city_id[:-(len(local_sfx) + 1)]
        sfx_meta = self.country_suffixes_cfg[local_sfx]
        country_name = str(sfx_meta.get("country") or "")
        iso2_code = str(sfx_meta.get("iso2") or "").upper()
        break

    base_title = base_slug.replace("_", " ").title()
    base_title = base_title.replace(" De ", " de ").replace(" Del ", " del ").replace(" Do ", " do ").replace(" Au ", "-au-")
    if country_name:
      display_name = f"{base_title}, {country_name}"
      query_str = f"{base_title}, {country_name}"
      wiki_title = f"{base_title}, {country_name}" if iso2_code in ("US", "CA") else base_title
      wiki_fallback = base_title if wiki_title != base_title else f"{base_title}, {country_name}"
    else:
      display_name = base_title
      query_str = base_title
      wiki_title = base_title
      wiki_fallback = ""

    #Return statement
    return {
      "iso2": iso2_code,
      "name": display_name,
      "query": query_str,
      "wiki": wiki_title,
      "wiki_fallback": wiki_fallback
    }


  def buildUrbanPolygonAssignments (self, arg1_city_coords_map):
    """
    @brief Match geocoded cities to Natural Earth 10m urban polygons and Voronoi-split shared conurbation polygons.
    @param arg1_city_coords_map Dictionary mapping city_id -> {'lon': float, 'lat': float, ...}.
    @return Dictionary mapping city_id -> 1D numpy int32 array of assigned urban pixel indices.
    """
    #Convert from parameters
    city_coords_map = arg1_city_coords_map if isinstance(arg1_city_coords_map, dict) else {}

    #Declare local instance variables
    assignments_map = {}
    city_ids = sorted(city_coords_map.keys())
    poly_to_cities = {}

    for i in range(len(city_ids)):
      local_cid = city_ids[i]
      local_c = city_coords_map[local_cid]
      lon = float(local_c["lon"])
      lat = float(local_c["lat"])
      pt = Point(lon, lat)
      best_poly_idx = -1
      best_dist = 0.035

      for x in range(len(self.urban_polys_list)):
        minx, miny, maxx, maxy, local_poly = self.urban_polys_list[x]
        if (lon >= minx - 0.04) and (lon <= maxx + 0.04) and (lat >= miny - 0.04) and (lat <= maxy + 0.04):
          if local_poly.contains(pt):
            best_poly_idx = x
            best_dist = 0.0
            break
          d_deg = local_poly.distance(pt)
          if d_deg < best_dist:
            best_dist = d_deg
            best_poly_idx = x

      if best_poly_idx >= 0:
        if best_poly_idx not in poly_to_cities:
          poly_to_cities[best_poly_idx] = []
        poly_to_cities[best_poly_idx].append(local_cid)

    for local_pidx, group_cids in poly_to_cities.items():
      _, _, _, _, u_poly = self.urban_polys_list[local_pidx]
      if len(group_cids) == 1:
        only_cid = group_cids[0]
        c_lon = float(city_coords_map[only_cid]["lon"])
        c_lat = float(city_coords_map[only_cid]["lat"])
        cos_lat = max(0.25, math.cos(math.radians(max(-80.0, min(80.0, c_lat)))))
        clip_box = box(c_lon - 0.42/cos_lat, c_lat - 0.42, c_lon + 0.42/cos_lat, c_lat + 0.42)
        clipped = u_poly.intersection(clip_box)
        assignments_map[only_cid] = self.rasteriser.A_rasteriseGeometry(clipped, {"fallback_lonlat": [c_lon, c_lat]})
      else:
        poly_flat = self.rasteriser.A_rasteriseGeometry(u_poly, {"ensure_min_pixel": False})
        if poly_flat.size > 0:
          pys = poly_flat // self.rasteriser.width
          pxs = poly_flat % self.rasteriser.width
          plons = (pxs.astype(np.float64) + 0.5)/self.rasteriser.pixels_per_degree - 180.0
          plats = 90.0 - (pys.astype(np.float64) + 0.5)/self.rasteriser.pixels_per_degree
          dist_matrix = np.empty((len(group_cids), poly_flat.size), dtype=np.float64)
          for x in range(len(group_cids)):
            gc = city_coords_map[group_cids[x]]
            glon = float(gc["lon"])
            glat = float(gc["lat"])
            cos_f = max(0.25, math.cos(math.radians(max(-80.0, min(80.0, glat)))))
            dx = (plons - glon)*cos_f
            dy = plats - glat
            dist_matrix[x, :] = dx*dx + dy*dy
          nearest_owner = np.argmin(dist_matrix, axis=0)
          min_d2 = np.min(dist_matrix, axis=0)
          for x in range(len(group_cids)):
            owned_mask = (nearest_owner == x) & (min_d2 <= 0.42*0.42)
            assignments_map[group_cids[x]] = poly_flat[owned_mask]

    #Return statement
    return assignments_map


  def fetchPhotonBatch (self, arg1_plans_map):
    """
    @brief Query Photon OpenStreetMap API across uncached cities with bounded thread concurrency and persist disk cache.
    @param arg1_plans_map Dictionary mapping city_id -> query plan dictionary.
    @return Dictionary mapping city_id -> Photon hit dictionary (or None).
    """
    #Convert from parameters
    plans_map = arg1_plans_map if isinstance(arg1_plans_map, dict) else {}

    #Declare local instance variables
    city_ids = sorted(plans_map.keys())
    dirty_cache = False
    results_map = {}
    uncached_tasks = []

    for i in range(len(city_ids)):
      local_cid = city_ids[i]
      local_plan = plans_map[local_cid]
      cache_key = f"{local_plan['query']}||{local_plan['iso2']}"
      if cache_key in self.fetcher.photon_cache_obj:
        results_map[local_cid] = self.fetcher.photon_cache_obj[cache_key]
      else:
        uncached_tasks.append((local_cid, local_plan["query"], local_plan["iso2"], cache_key))

    if uncached_tasks:
      def _worker (local_task):
        t_cid, t_q, t_iso2, t_ck = local_task
        hit = self.queryPhotonSingleStateless(t_q, t_iso2)
        return (t_cid, t_ck, hit)

      with ThreadPoolExecutor(max_workers=6) as local_pool:
        fetched_list = list(local_pool.map(_worker, uncached_tasks))

      for i in range(len(fetched_list)):
        t_cid, t_ck, hit = fetched_list[i]
        self.fetcher.photon_cache_obj[t_ck] = hit
        results_map[t_cid] = hit
        dirty_cache = True

      if dirty_cache:
        self.fetcher.saveJsonCache(self.fetcher.photon_cache_path, self.fetcher.photon_cache_obj)

    #Return statement
    return results_map


  def isNonCityCorpusKey (self, arg1_volume_id, arg2_section_id, arg3_raw_key):
    """
    @brief Check whether an A4 corpus key is an explicit country spillover (e.g. americas:A4:canada).
    @param arg1_volume_id Volume identifier.
    @param arg2_section_id Section identifier.
    @param arg3_raw_key Raw location key.
    @return Boolean True if key is a non-city spillover handled by CountryMaskResolver.
    """
    #Convert from parameters
    volume_id = str(arg1_volume_id or "").strip()
    section_id = str(arg2_section_id or "").strip()
    raw_key = str(arg3_raw_key or "").strip()

    #Return statement
    return f"{volume_id}:{section_id}:{raw_key}" in self.non_city_keys_set


  def loadUrbanPolygons (self):
    """
    @brief Load and index Natural Earth 10m urban area polygons with bounding boxes for fast spatial lookup.
    """
    #Declare local instance variables
    fc_obj = {}
    feats = []
    polys = []

    if self.urban_polys_list:
      return

    fc_obj = self.fetcher.A_fetchBaseLayer("ne_urban")
    feats = fc_obj.get("features", [])
    for i in range(len(feats)):
      polys = self.rasteriser.extractPolygons(feats[i])
      for x in range(len(polys)):
        b = polys[x].bounds
        self.urban_polys_list.append((b[0], b[1], b[2], b[3], polys[x]))


  def queryPhotonSingleStateless (self, arg1_query_str, arg2_expected_iso2):
    """
    @brief Perform a single stateless HTTP GET against Photon OSM API (safe for concurrent ThreadPoolExecutor calls).
    @param arg1_query_str Search string.
    @param arg2_expected_iso2 Optional two-letter ISO country code filter.
    @return Parsed Photon result dictionary or None.
    """
    #Convert from parameters
    query_str = str(arg1_query_str or "").strip()
    expected_iso2 = str(arg2_expected_iso2 or "").strip().upper()

    #Declare local instance variables
    best_feat = None
    feats = []
    parsed_hit = None
    resp = None

    if not query_str:
      return None

    try:
      resp = self.fetcher.session.get(
        self.fetcher.photon_url,
        params={"lang": "en", "limit": 8, "q": query_str},
        timeout=25
      )
      if resp.status_code == 200:
        feats = resp.json().get("features", [])
        for i in range(len(feats)):
          local_f = feats[i]
          local_p = local_f.get("properties") or {}
          local_cc = str(local_p.get("countrycode") or "").upper()
          local_val = str(local_p.get("osm_value") or "").lower()
          if expected_iso2 and local_cc and local_cc != expected_iso2:
            continue
          if local_val in ("city", "town", "municipality", "administrative", "borough", "suburb", "village", "county", "state"):
            best_feat = local_f
            break
          if best_feat is None:
            best_feat = local_f
        if best_feat is None and feats and not expected_iso2:
          best_feat = feats[0]
        if best_feat is not None:
          coords = best_feat.get("geometry", {}).get("coordinates", [])
          props = best_feat.get("properties") or {}
          if len(coords) >= 2:
            parsed_hit = {
              "countrycode": str(props.get("countrycode") or ""),
              "extent": props.get("extent"),
              "lat": float(coords[1]),
              "lon": float(coords[0]),
              "name": str(props.get("name") or ""),
              "osm_id": props.get("osm_id"),
              "osm_type": str(props.get("osm_type") or ""),
              "osm_value": str(props.get("osm_value") or "")
            }
    except Exception:
      parsed_hit = None

    #Return statement
    return parsed_hit


  def rasteriseCityEntity (self, arg1_city_id, arg2_plan_obj, arg3_coord_obj, arg4_photon_obj, arg5_urban_indices):
    """
    @brief Rasterise a geocoded city using its Natural Earth urban polygon, clamped Photon OSM extent, or urban disc.
    @param arg1_city_id Canonical city identifier.
    @param arg2_plan_obj City query plan dictionary.
    @param arg3_coord_obj Selected coordinate dictionary {'lon', 'lat', 'coord_source'}.
    @param arg4_photon_obj Optional Photon OSM hit dictionary.
    @param arg5_urban_indices Optional 1D int32 array from Voronoi-partitioned ne_urban polygon.
    @return Resolved city entity record dictionary.
    """
    #Convert from parameters
    city_id = str(arg1_city_id or "").strip()
    plan_obj = arg2_plan_obj if isinstance(arg2_plan_obj, dict) else {}
    coord_obj = arg3_coord_obj if isinstance(arg3_coord_obj, dict) else {"coord_source": "none", "lat": 0.0, "lon": 0.0}
    photon_obj = arg4_photon_obj if isinstance(arg4_photon_obj, dict) else None
    urban_indices = arg5_urban_indices

    #Declare local instance variables
    centre_px = None
    flat_idx = None
    footprint_source = ""
    lat = float(coord_obj.get("lat", 0.0))
    lon = float(coord_obj.get("lon", 0.0))
    metrics_obj = {}

    centre_px = self.rasteriser.lonLatToFlatIndexArray(lon, lat)

    if isinstance(urban_indices, np.ndarray) and urban_indices.size > 0:
      flat_idx = np.unique(np.concatenate([urban_indices, centre_px]))
      footprint_source = f"{coord_obj.get('coord_source', 'geohack')}+ne_10m_urban_areas"
    elif photon_obj is not None and isinstance(photon_obj.get("extent"), list) and len(photon_obj["extent"]) == 4:
      ext = photon_obj["extent"]
      w_lon, n_lat, e_lon, s_lat = float(ext[0]), float(ext[1]), float(ext[2]), float(ext[3])
      min_lon = max(lon - 0.16, min(w_lon, e_lon))
      max_lon = min(lon + 0.16, max(w_lon, e_lon))
      min_lat = max(lat - 0.14, min(s_lat, n_lat))
      max_lat = min(lat + 0.14, max(s_lat, n_lat))
      if max_lon - min_lon >= 0.03 and max_lat - min_lat >= 0.03:
        bbox_idx = self.rasteriser.rasteriseBbox(min_lon, min_lat, max_lon, max_lat)
        flat_idx = np.unique(np.concatenate([bbox_idx, centre_px]))
        footprint_source = f"{coord_obj.get('coord_source', 'photon')}+photon_osm_extent"
      else:
        flat_idx = self.rasteriser.rasterisePointDisc(lon, lat, 0.085)
        footprint_source = f"{coord_obj.get('coord_source', 'photon')}+urban_disc"
    else:
      flat_idx = self.rasteriser.rasterisePointDisc(lon, lat, 0.085)
      footprint_source = f"{coord_obj.get('coord_source', 'geohack')}+urban_disc"

    metrics_obj = self.rasteriser.computeMaskMetrics(flat_idx)

    #Return statement
    return {
      "category": "city",
      "coord_wgs84": [round(lon, 5), round(lat, 5)],
      "entity_id": f"city:{city_id}",
      "era_type": "modern",
      "flat_indices": flat_idx,
      "metrics": metrics_obj,
      "name": str(plan_obj.get("name", city_id)),
      "raw_city_key": city_id,
      "source_summary": {
        "coord_source": coord_obj.get("coord_source", ""),
        "footprint_source": footprint_source,
        "iso2": plan_obj.get("iso2", ""),
        "osm_id": photon_obj.get("osm_id") if photon_obj else None,
        "osm_type": photon_obj.get("osm_type") if photon_obj else None,
        "wikipedia_title": coord_obj.get("wiki_resolved")
      },
      "valid_years": [1750, 2025]
    }


  def selectBestCoordinates (self, arg1_city_id, arg2_plan_obj, arg3_wiki_map, arg4_photon_hit):
    """
    @brief Cross-validate Wikipedia GeoHack and Photon OSM coordinates for a city, falling back to Nominatim if needed.
    @param arg1_city_id Canonical city identifier.
    @param arg2_plan_obj City query plan dictionary.
    @param arg3_wiki_map Batch Wikipedia GeoHack coordinate dictionary.
    @param arg4_photon_hit Photon OSM result dictionary or None.
    @return Dictionary containing lon, lat, coord_source, and wiki_resolved.
    """
    #Convert from parameters
    city_id = str(arg1_city_id or "")
    plan_obj = arg2_plan_obj if isinstance(arg2_plan_obj, dict) else {}
    wiki_map = arg3_wiki_map if isinstance(arg3_wiki_map, dict) else {}
    photon_hit = arg4_photon_hit if isinstance(arg4_photon_hit, dict) else None

    #Declare local instance variables
    nom_geom = None
    w_hit = wiki_map.get(plan_obj.get("wiki", "")) or wiki_map.get(plan_obj.get("wiki_fallback", ""))

    if w_hit is not None and photon_hit is not None:
      dlon = abs(float(w_hit["lon"]) - float(photon_hit["lon"]))
      dlat = abs(float(w_hit["lat"]) - float(photon_hit["lat"]))
      if dlon <= 1.5 and dlat <= 1.5:
        return {
          "coord_source": "wikipedia_geohack+photon_osm",
          "lat": float(w_hit["lat"]),
          "lon": float(w_hit["lon"]),
          "wiki_resolved": w_hit.get("resolved_title")
        }
      if plan_obj.get("iso2") and str(photon_hit.get("countrycode") or "").upper() == plan_obj["iso2"]:
        if plan_obj["iso2"] in ("US", "CA", "BR", "MX", "AR", "CO", "VE", "PE", "CL") and city_id not in self.cities_cfg:
          return {
            "coord_source": "photon_osm",
            "lat": float(photon_hit["lat"]),
            "lon": float(photon_hit["lon"]),
            "wiki_resolved": None
          }
      return {
        "coord_source": "wikipedia_geohack",
        "lat": float(w_hit["lat"]),
        "lon": float(w_hit["lon"]),
        "wiki_resolved": w_hit.get("resolved_title")
      }

    if w_hit is not None:
      return {
        "coord_source": "wikipedia_geohack",
        "lat": float(w_hit["lat"]),
        "lon": float(w_hit["lon"]),
        "wiki_resolved": w_hit.get("resolved_title")
      }

    if photon_hit is not None:
      return {
        "coord_source": "photon_osm",
        "lat": float(photon_hit["lat"]),
        "lon": float(photon_hit["lon"]),
        "wiki_resolved": None
      }

    nom_geom = self.fetcher.E_fetchNominatimPolygon(plan_obj.get("query", city_id))
    if nom_geom is not None:
      polys = self.rasteriser.extractPolygons(nom_geom)
      if polys:
        rp = polys[0].representative_point()
        return {
          "coord_source": "nominatim_osm",
          "lat": float(rp.y),
          "lon": float(rp.x),
          "wiki_resolved": None
        }

    sys.stderr.write(f"Console error: failed geocoding city '{city_id}' ({plan_obj.get('query')})\n")

    #Return statement
    return {"coord_source": "unresolved", "lat": 0.0, "lon": 0.0, "wiki_resolved": None}
