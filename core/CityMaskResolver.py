"""@brief Resolves individual city [lng, lat] coordinates via Wikipedia GeoHack, Photon (OpenStreetMap) and Nominatim."""

import sys


class CityMaskResolver:
  """@brief Geocodes all corpus cities to WGS84 [lng, lat] coordinates using GeoHack, Photon OSM and Nominatim."""

  def __init__ (self, arg1_fetcher, arg2_city_rules_obj):
    """
    @brief Initialise CityMaskResolver with GeoJsonFetcher and parsed city_rules.json5.
    @param arg1_fetcher GeoJsonFetcher instance.
    @param arg2_city_rules_obj Parsed city_rules.json5 dictionary.
    """
    #Convert from parameters
    fetcher = arg1_fetcher
    city_rules_obj = arg2_city_rules_obj if isinstance(arg2_city_rules_obj, dict) else {}

    #Declare local instance variables
    self.cities_cfg = city_rules_obj.get("cities", {})
    self.country_suffixes_cfg = city_rules_obj.get("country_suffixes", {})
    self.fetcher = fetcher
    self.non_city_keys_set = set(city_rules_obj.get("non_city_keys", []))
    self.resolved_cities_obj = {}
    self.sorted_suffixes = sorted(self.country_suffixes_cfg.keys(), key=lambda local_s: len(local_s), reverse=True)
    self.western_iso2_set = {
      "AR", "BO", "BR", "CA", "CL", "CO", "CR", "CU", "DO", "EC", "GT", "HN", "HT",
      "JM", "MX", "NI", "PA", "PE", "PR", "PY", "SV", "TT", "US", "UY", "VE"
    }


  def A_resolveAllCities (self, arg1_city_keys_array):
    """
    @brief Step A: Geocode all unique city keys via Wikipedia GeoHack and Photon OSM into [lng, lat] coordinates.
    @param arg1_city_keys_array List of unique canonical city_id keys across A4 and spilled europe/A3 entries.
    @return Dictionary mapping city_id -> [lng, lat] float coordinate pair.
    """
    #Convert from parameters
    city_keys_array = arg1_city_keys_array if isinstance(arg1_city_keys_array, list) else []

    #Declare local instance variables
    photon_results_map = {}
    plans_map = {}
    unique_keys = sorted(set(str(k).strip() for k in city_keys_array if str(k).strip()))
    wiki_results_map = {}
    wiki_titles = []

    for i in range(len(unique_keys)):
      local_cid = unique_keys[i]
      local_plan = self.buildCityQueryPlan(local_cid)
      plans_map[local_cid] = local_plan
      if local_plan["wiki"] and local_plan["wiki"] not in wiki_titles:
        wiki_titles.append(local_plan["wiki"])
      if local_plan["wiki_fallback"] and local_plan["wiki_fallback"] not in wiki_titles:
        wiki_titles.append(local_plan["wiki_fallback"])

    wiki_results_map = self.fetcher.C_fetchWikipediaCoordinatesBatch(wiki_titles)
    photon_results_map = self.fetchPhotonForMissing(plans_map, wiki_results_map)

    for i in range(len(unique_keys)):
      local_cid = unique_keys[i]
      local_plan = plans_map[local_cid]
      local_coord = self.selectBestCoordinates(local_cid, local_plan, wiki_results_map, photon_results_map.get(local_cid))
      self.resolved_cities_obj[local_cid] = [
        round(float(local_coord["lon"]), 5),
        round(float(local_coord["lat"]), 5)
      ]

    #Return statement
    return self.resolved_cities_obj


  def buildCityQueryPlan (self, arg1_city_id):
    """
    @brief Construct Wikipedia GeoHack title and Photon OpenStreetMap query parameters for a city key.
    @param arg1_city_id Canonical city key (e.g. 'constantinople', 'akron_usa', 'bradford').
    @return Dictionary containing name, query, wiki, wiki_fallback and iso2.
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


  def fetchPhotonForMissing (self, arg1_plans_map, arg2_wiki_map):
    """
    @brief Query Photon OpenStreetMap API sequentially for cities unresolved by Wikipedia GeoHack and persist disk cache.
    @param arg1_plans_map Dictionary mapping city_id -> query plan dictionary.
    @param arg2_wiki_map Batch Wikipedia GeoHack coordinate dictionary.
    @return Dictionary mapping city_id -> Photon hit dictionary (or None).
    """
    #Convert from parameters
    plans_map = arg1_plans_map if isinstance(arg1_plans_map, dict) else {}
    wiki_map = arg2_wiki_map if isinstance(arg2_wiki_map, dict) else {}

    #Declare local instance variables
    city_ids = sorted(plans_map.keys())
    dirty_cache = False
    results_map = {}

    for i in range(len(city_ids)):
      local_cid = city_ids[i]
      local_plan = plans_map[local_cid]
      cache_key = f"{local_plan['query']}||{local_plan['iso2']}"
      w_hit = wiki_map.get(local_plan.get("wiki", "")) or wiki_map.get(local_plan.get("wiki_fallback", ""))
      if w_hit is not None and local_plan.get("iso2") in self.western_iso2_set and float(w_hit["lon"]) > -30.0:
        w_hit = None

      if cache_key in self.fetcher.photon_cache_obj:
        results_map[local_cid] = self.fetcher.photon_cache_obj[cache_key]
      elif w_hit is None:
        hit, http_ok = self.queryPhotonSingle(local_plan["query"], local_plan["iso2"])
        results_map[local_cid] = hit
        if http_ok:
          self.fetcher.photon_cache_obj[cache_key] = hit
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


  def queryPhotonSingle (self, arg1_query_str, arg2_expected_iso2):
    """
    @brief Perform a single HTTP GET against Photon OSM API and indicate whether HTTP 200 succeeded.
    @param arg1_query_str Search string.
    @param arg2_expected_iso2 Optional two-letter ISO country code filter.
    @return Tuple of (parsed_hit_or_None, http_ok_bool).
    """
    #Convert from parameters
    query_str = str(arg1_query_str or "").strip()
    expected_iso2 = str(arg2_expected_iso2 or "").strip().upper()

    #Declare local instance variables
    best_feat = None
    feats = []
    http_ok = False
    parsed_hit = None
    resp = None

    if not query_str:
      return (None, False)

    try:
      resp = self.fetcher.session.get(
        self.fetcher.photon_url,
        params={"lang": "en", "limit": 8, "q": query_str},
        timeout=8
      )
      if resp.status_code == 200:
        http_ok = True
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
              "lat": float(coords[1]),
              "lon": float(coords[0]),
              "name": str(props.get("name") or "")
            }
    except Exception:
      parsed_hit = None

    #Return statement
    return (parsed_hit, http_ok)


  def selectBestCoordinates (self, arg1_city_id, arg2_plan_obj, arg3_wiki_map, arg4_photon_hit):
    """
    @brief Cross-validate Wikipedia GeoHack and Photon OSM coordinates for a city, falling back to Nominatim point lookup if needed.
    @param arg1_city_id Canonical city identifier.
    @param arg2_plan_obj City query plan dictionary.
    @param arg3_wiki_map Batch Wikipedia GeoHack coordinate dictionary.
    @param arg4_photon_hit Photon OSM result dictionary or None.
    @return Dictionary containing lon and lat floats.
    """
    #Convert from parameters
    city_id = str(arg1_city_id or "")
    plan_obj = arg2_plan_obj if isinstance(arg2_plan_obj, dict) else {}
    wiki_map = arg3_wiki_map if isinstance(arg3_wiki_map, dict) else {}
    photon_hit = arg4_photon_hit if isinstance(arg4_photon_hit, dict) else None

    #Declare local instance variables
    nom_pt = None
    w_hit = wiki_map.get(plan_obj.get("wiki", "")) or wiki_map.get(plan_obj.get("wiki_fallback", ""))

    if w_hit is not None and plan_obj.get("iso2") in self.western_iso2_set and float(w_hit["lon"]) > -30.0:
      w_hit = None

    if w_hit is not None and photon_hit is not None:
      dlon = abs(float(w_hit["lon"]) - float(photon_hit["lon"]))
      dlat = abs(float(w_hit["lat"]) - float(photon_hit["lat"]))
      if dlon <= 1.5 and dlat <= 1.5:
        return {"lat": float(w_hit["lat"]), "lon": float(w_hit["lon"])}
      if plan_obj.get("iso2") and str(photon_hit.get("countrycode") or "").upper() == plan_obj["iso2"]:
        if plan_obj["iso2"] in ("US", "CA", "BR", "MX", "AR", "CO", "VE", "PE", "CL") and city_id not in self.cities_cfg:
          return {"lat": float(photon_hit["lat"]), "lon": float(photon_hit["lon"])}
      return {"lat": float(w_hit["lat"]), "lon": float(w_hit["lon"])}

    if w_hit is not None:
      return {"lat": float(w_hit["lat"]), "lon": float(w_hit["lon"])}

    if photon_hit is not None:
      return {"lat": float(photon_hit["lat"]), "lon": float(photon_hit["lon"])}

    nom_pt = self.fetcher.F_fetchNominatimCityPoint(plan_obj.get("query", city_id))
    if nom_pt is not None:
      return {"lat": float(nom_pt["lat"]), "lon": float(nom_pt["lon"])}

    sys.stderr.write(f"Console error: failed geocoding city '{city_id}' ({plan_obj.get('query')})\n")

    #Return statement
    return {"lat": 0.0, "lon": 0.0}
