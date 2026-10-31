"""@brief WGS84 Equirectangular scanline polygon rasteriser and lossless PNG exporter."""

import math
import os
import sys
import cv2
import numpy as np
from PIL import Image
from shapely.geometry import MultiPolygon, Point, Polygon, box, shape
from shapely.ops import unary_union


class EquirectangularRasteriser:
  """@brief Scanline-rasterises WGS84 GeoJSON/Shapely geometries onto a 4320x2160 Equirectangular grid."""

  def __init__ (self, arg1_grid_config_obj=None):
    """
    @brief Initialise EquirectangularRasteriser with target pixel dimensions and supersampling factor.
    @param arg1_grid_config_obj Grid configuration dictionary from areal_mask_config.json5.
    """
    #Convert from parameters
    grid_config_obj = arg1_grid_config_obj if isinstance(arg1_grid_config_obj, dict) else {}

    #Declare local instance variables
    self.crs = str(grid_config_obj.get("crs", "EPSG:4326"))
    self.height = int(grid_config_obj.get("height", 2160))
    self.pixels_per_degree = float(grid_config_obj.get("pixels_per_degree", 12.0))
    self.supersample = max(1, int(grid_config_obj.get("supersample_factor", 2)))
    self.total_pixels = self.getConfiguredWidth(grid_config_obj)*self.height
    self.width = self.getConfiguredWidth(grid_config_obj)


  def A_rasteriseGeometry (self, arg1_geometry_obj, arg2_options=None):
    """
    @brief Step A: Scanline-rasterise a GeoJSON dict, Shapely geometry, or list of geometries to sorted flat pixel indices.
    @param arg1_geometry_obj GeoJSON geometry dict, Feature dict, Shapely geometry, or list thereof.
    @param arg2_options Optional dictionary with fallback_lonlat and ensure_min_pixel (default True).
    @return Sorted 1D numpy int32 array of flat pixel indices (y*width + x).
    """
    #Convert from parameters
    geometry_obj = arg1_geometry_obj
    options = arg2_options if isinstance(arg2_options, dict) else {}

    #Initialise options
    if "ensure_min_pixel" not in options:
      options["ensure_min_pixel"] = True
    if "fallback_lonlat" not in options:
      options["fallback_lonlat"] = None

    #Declare local instance variables
    empty_array = np.zeros(0, dtype=np.int32)
    fallback_pt = options["fallback_lonlat"]
    flat_indices_list = []
    merged_geom = None
    poly_list = []
    rep_point = None

    poly_list = self.extractPolygons(geometry_obj)
    if not poly_list:
      if fallback_pt is not None and len(fallback_pt) >= 2:
        return self.rasterisePointDisc(float(fallback_pt[0]), float(fallback_pt[1]), 0.04)
      sys.stderr.write("Console error: empty geometry passed to A_rasteriseGeometry.\n")
      return empty_array

    for i in range(len(poly_list)):
      local_poly = poly_list[i]
      local_parts = self.splitAntimeridianPolygon(local_poly)
      for x in range(len(local_parts)):
        local_idx = self.rasteriseSinglePolygon(local_parts[x])
        if local_idx.size > 0:
          flat_indices_list.append(local_idx)

    if flat_indices_list:
      combined_array = np.unique(np.concatenate(flat_indices_list))
    else:
      combined_array = empty_array

    if combined_array.size == 0 and options["ensure_min_pixel"]:
      try:
        merged_geom = unary_union(poly_list)
        rep_point = merged_geom.representative_point()
        combined_array = self.lonLatToFlatIndexArray(rep_point.x, rep_point.y)
      except Exception:
        if fallback_pt is not None and len(fallback_pt) >= 2:
          combined_array = self.lonLatToFlatIndexArray(float(fallback_pt[0]), float(fallback_pt[1]))
        else:
          local_b = poly_list[0].bounds
          combined_array = self.lonLatToFlatIndexArray(0.5*(local_b[0] + local_b[2]), 0.5*(local_b[1] + local_b[3]))

    #Return statement
    return combined_array


  def B_exportRgbPng (self, arg1_rgb_buffer, arg2_output_path):
    """
    @brief Step B: Export a (height, width, 3) uint8 RGB numpy buffer as a lossless PNG image.
    @param arg1_rgb_buffer Numpy uint8 array of shape (2160, 4320, 3).
    @param arg2_output_path Destination .png file path.
    @return Boolean True upon successful write.
    """
    #Convert from parameters
    rgb_buffer = arg1_rgb_buffer
    output_path = str(arg2_output_path or "")

    #Declare local instance variables
    img_obj = None
    parent_dir = ""

    if not isinstance(rgb_buffer, np.ndarray) or rgb_buffer.shape != (self.height, self.width, 3):
      sys.stderr.write(f"Console error: invalid RGB buffer shape for PNG export: {getattr(rgb_buffer, 'shape', None)}\n")
      return False
    if not output_path:
      sys.stderr.write("Console error: empty output_path passed to B_exportRgbPng.\n")
      return False

    parent_dir = os.path.dirname(os.path.abspath(output_path))
    os.makedirs(parent_dir, exist_ok=True)
    img_obj = Image.fromarray(rgb_buffer, mode="RGB")
    img_obj.save(output_path, format="PNG", compress_level=6)

    #Return statement
    return True


  def computeMaskMetrics (self, arg1_flat_indices):
    """
    @brief Compute pixel count, pixel bounding box, WGS84 bounding box, and WGS84 centroid from flat pixel indices.
    @param arg1_flat_indices Sorted 1D numpy int32 array of flat pixel indices.
    @return Dictionary containing pixel_count, bbox_px, bbox_wgs84, and centroid_wgs84.
    """
    #Convert from parameters
    flat_indices = arg1_flat_indices

    #Declare local instance variables
    cx_deg = 0.0
    cy_deg = 0.0
    east_deg = 0.0
    max_x = 0
    max_y = 0
    min_x = 0
    min_y = 0
    north_deg = 0.0
    south_deg = 0.0
    west_deg = 0.0
    xs = None
    ys = None

    if not isinstance(flat_indices, np.ndarray) or flat_indices.size == 0:
      return {
        "bbox_px": [0, 0, 0, 0],
        "bbox_wgs84": [0.0, 0.0, 0.0, 0.0],
        "centroid_wgs84": [0.0, 0.0],
        "pixel_count": 0
      }

    ys = flat_indices // self.width
    xs = flat_indices % self.width
    min_x = int(xs.min())
    max_x = int(xs.max())
    min_y = int(ys.min())
    max_y = int(ys.max())

    west_deg = round(min_x/self.pixels_per_degree - 180.0, 5)
    east_deg = round((max_x + 1)/self.pixels_per_degree - 180.0, 5)
    north_deg = round(90.0 - min_y/self.pixels_per_degree, 5)
    south_deg = round(90.0 - (max_y + 1)/self.pixels_per_degree, 5)
    cx_deg = round((float(xs.mean()) + 0.5)/self.pixels_per_degree - 180.0, 5)
    cy_deg = round(90.0 - (float(ys.mean()) + 0.5)/self.pixels_per_degree, 5)

    #Return statement
    return {
      "bbox_px": [min_x, min_y, max_x, max_y],
      "bbox_wgs84": [west_deg, south_deg, east_deg, north_deg],
      "centroid_wgs84": [cx_deg, cy_deg],
      "pixel_count": int(flat_indices.size)
    }


  def extractPolygons (self, arg1_geometry_obj):
    """
    @brief Recursively unpack GeoJSON dicts, Feature dicts, or Shapely geometries into valid Shapely Polygons.
    @param arg1_geometry_obj Input geometry container.
    @return List of Shapely Polygon objects.
    """
    #Convert from parameters
    geometry_obj = arg1_geometry_obj

    #Declare local instance variables
    geom = None
    polygons_array = []

    if geometry_obj is None:
      return polygons_array

    if isinstance(geometry_obj, list):
      for i in range(len(geometry_obj)):
        polygons_array.extend(self.extractPolygons(geometry_obj[i]))
      return polygons_array

    if isinstance(geometry_obj, dict):
      if geometry_obj.get("type") == "FeatureCollection":
        local_feats = geometry_obj.get("features", [])
        for i in range(len(local_feats)):
          polygons_array.extend(self.extractPolygons(local_feats[i]))
        return polygons_array
      elif geometry_obj.get("type") == "Feature":
        return self.extractPolygons(geometry_obj.get("geometry"))
      else:
        try:
          geom = shape(geometry_obj)
        except Exception:
          return polygons_array
    else:
      geom = geometry_obj

    if geom is None or geom.is_empty:
      return polygons_array

    if not geom.is_valid:
      try:
        geom = geom.buffer(0)
      except Exception:
        pass

    if isinstance(geom, Polygon):
      if not geom.is_empty:
        polygons_array.append(geom)
    elif isinstance(geom, MultiPolygon):
      local_geoms = list(geom.geoms)
      for i in range(len(local_geoms)):
        if not local_geoms[i].is_empty:
          polygons_array.append(local_geoms[i])
    elif hasattr(geom, "geoms"):
      local_geoms = list(geom.geoms)
      for i in range(len(local_geoms)):
        polygons_array.extend(self.extractPolygons(local_geoms[i]))
    elif isinstance(geom, Point):
      polygons_array.append(geom.buffer(0.05))

    #Return statement
    return polygons_array


  def lonLatToFlatIndexArray (self, arg1_lon, arg2_lat):
    """
    @brief Convert a single WGS84 (lon, lat) coordinate into a 1-element int32 flat pixel index array.
    @param arg1_lon Longitude in degrees [-180, 180].
    @param arg2_lat Latitude in degrees [-90, 90].
    @return 1D numpy int32 array with 1 pixel index.
    """
    #Convert from parameters
    lon = float(arg1_lon)
    lat = float(arg2_lat)

    #Declare local instance variables
    px_x = 0
    px_y = 0
    wrapped_lon = ((lon + 180.0) % 360.0) - 180.0

    px_x = min(self.width - 1, max(0, int(math.floor((wrapped_lon + 180.0)*self.pixels_per_degree))))
    px_y = min(self.height - 1, max(0, int(math.floor((90.0 - lat)*self.pixels_per_degree))))

    #Return statement
    return np.array([px_y*self.width + px_x], dtype=np.int32)


  def rasteriseBbox (self, arg1_west, arg2_south, arg3_east, arg4_north):
    """
    @brief Rasterise a WGS84 bounding box [west, south, east, north] directly to flat pixel indices.
    @param arg1_west Western longitude in degrees.
    @param arg2_south Southern latitude in degrees.
    @param arg3_east Eastern longitude in degrees.
    @param arg4_north Northern latitude in degrees.
    @return Sorted 1D numpy int32 array of flat pixel indices.
    """
    #Convert from parameters
    west = float(arg1_west)
    south = float(arg2_south)
    east = float(arg3_east)
    north = float(arg4_north)

    #Declare local instance variables
    bbox_poly = None

    if east < west:
      part_a = box(west, south, 180.0, north)
      part_b = box(-180.0, south, east, north)
      return self.A_rasteriseGeometry([part_a, part_b], {"fallback_lonlat": [west, 0.5*(south + north)]})

    bbox_poly = box(max(-180.0, west), max(-90.0, south), min(180.0, east), min(90.0, north))

    #Return statement
    return self.A_rasteriseGeometry(bbox_poly, {"fallback_lonlat": [0.5*(west + east), 0.5*(south + north)]})


  def rasterisePointDisc (self, arg1_lon, arg2_lat, arg3_radius_deg=0.09):
    """
    @brief Rasterise an equirectangular urban disc centred at (lon, lat) with latitude cosine compensation.
    @param arg1_lon Longitude in degrees [-180, 180].
    @param arg2_lat Latitude in degrees [-90, 90].
    @param arg3_radius_deg Angular radius in degrees of latitude (default 0,09 deg ~ 10 km).
    @return Sorted 1D numpy int32 array of flat pixel indices (guaranteed >= 1 pixel).
    """
    #Convert from parameters
    lon = float(arg1_lon)
    lat = float(arg2_lat)
    radius_deg = max(0.02, float(arg3_radius_deg))

    #Declare local instance variables
    angles = np.linspace(0.0, 2.0*math.pi, 24, endpoint=False)
    cos_lat = max(0.2, math.cos(math.radians(max(-80.0, min(80.0, lat)))))
    disc_indices = None
    lon_radius = min(3.0, radius_deg/cos_lat)
    ring_coords = []

    for i in range(len(angles)):
      local_ang = float(angles[i])
      local_x = max(-179.999, min(179.999, lon + lon_radius*math.cos(local_ang)))
      local_y = max(-89.999, min(89.999, lat + radius_deg*math.sin(local_ang)))
      ring_coords.append((local_x, local_y))
    ring_coords.append(ring_coords[0])

    disc_indices = self.A_rasteriseGeometry(Polygon(ring_coords), {"fallback_lonlat": [lon, lat]})
    if disc_indices.size == 0:
      disc_indices = self.lonLatToFlatIndexArray(lon, lat)

    #Return statement
    return np.unique(np.concatenate([disc_indices, self.lonLatToFlatIndexArray(lon, lat)]))


  def rasteriseSinglePolygon (self, arg1_polygon):
    """
    @brief Scanline-rasterise a single non-dateline-crossing Shapely Polygon (exterior minus interior holes).
    @param arg1_polygon Shapely Polygon within [-180, 180] x [-90, 90].
    @return Sorted 1D numpy int32 array of flat pixel indices.
    """
    #Convert from parameters
    polygon = arg1_polygon

    #Declare local instance variables
    bounds = None
    crop_h = 0
    crop_mask = None
    crop_w = 0
    empty_array = np.zeros(0, dtype=np.int32)
    ext_coords = None
    ext_pts = None
    hit_x = None
    hit_y = None
    hole_pts_list = []
    max_gx = 0
    max_gy = 0
    min_gx = 0
    min_gy = 0
    scale = self.pixels_per_degree*self.supersample
    ss = self.supersample
    sub_h = 0
    sub_mask = None
    sub_w = 0

    if polygon is None or polygon.is_empty:
      return empty_array

    bounds = polygon.bounds
    min_gx = max(0, int(math.floor((bounds[0] + 180.0)*self.pixels_per_degree)) - 1)
    max_gx = min(self.width - 1, int(math.ceil((bounds[2] + 180.0)*self.pixels_per_degree)) + 1)
    min_gy = max(0, int(math.floor((90.0 - bounds[3])*self.pixels_per_degree)) - 1)
    max_gy = min(self.height - 1, int(math.ceil((90.0 - bounds[1])*self.pixels_per_degree)) + 1)

    if max_gx < min_gx or max_gy < min_gy:
      return empty_array

    crop_w = max_gx - min_gx + 1
    crop_h = max_gy - min_gy + 1
    sub_w = crop_w*ss
    sub_h = crop_h*ss
    sub_mask = np.zeros((sub_h, sub_w), dtype=np.uint8)

    ext_coords = np.asarray(polygon.exterior.coords, dtype=np.float64)
    if ext_coords.shape[0] < 3:
      return empty_array

    ext_pts = np.empty((ext_coords.shape[0], 2), dtype=np.int32)
    ext_pts[:, 0] = np.round((ext_coords[:, 0] + 180.0)*scale - min_gx*ss).astype(np.int32)
    ext_pts[:, 1] = np.round((90.0 - ext_coords[:, 1])*scale - min_gy*ss).astype(np.int32)
    cv2.fillPoly(sub_mask, [ext_pts], 1)

    if len(polygon.interiors) > 0:
      for i in range(len(polygon.interiors)):
        local_ring = np.asarray(polygon.interiors[i].coords, dtype=np.float64)
        if local_ring.shape[0] >= 3:
          local_pts = np.empty((local_ring.shape[0], 2), dtype=np.int32)
          local_pts[:, 0] = np.round((local_ring[:, 0] + 180.0)*scale - min_gx*ss).astype(np.int32)
          local_pts[:, 1] = np.round((90.0 - local_ring[:, 1])*scale - min_gy*ss).astype(np.int32)
          hole_pts_list.append(local_pts)
      if hole_pts_list:
        cv2.fillPoly(sub_mask, hole_pts_list, 0)

    if ss > 1:
      crop_mask = sub_mask.reshape(crop_h, ss, crop_w, ss).any(axis=(1, 3))
    else:
      crop_mask = sub_mask > 0

    hit_y, hit_x = np.nonzero(crop_mask)
    if hit_y.size == 0:
      return empty_array

    #Return statement
    return ((hit_y.astype(np.int32) + min_gy)*self.width + (hit_x.astype(np.int32) + min_gx))


  def splitAntimeridianPolygon (self, arg1_polygon):
    """
    @brief Split polygons that wrap across the +-180 degree antimeridian into valid [-180, 180] parts.
    @param arg1_polygon Input Shapely Polygon.
    @return List of Shapely Polygons strictly within [-180, 180] longitude.
    """
    #Convert from parameters
    polygon = arg1_polygon

    #Declare local instance variables
    coords = None
    diffs = None
    east_clip = box(-180.0, -90.0, 180.0, 90.0)
    parts_array = []

    if polygon is None or polygon.is_empty:
      return parts_array

    coords = np.asarray(polygon.exterior.coords, dtype=np.float64)
    if coords.shape[0] < 3:
      return parts_array

    if coords[:, 0].min() >= -180.001 and coords[:, 0].max() <= 180.001:
      diffs = np.abs(np.diff(coords[:, 0]))
      if diffs.max() < 180.0:
        return [polygon]

    # Unwrap longitudes to [0, 360] when jump > 180 deg occurs (e.g. Chukotka, Fiji, Kiribati)
    try:
      unwrapped_ext = coords.copy()
      unwrapped_ext[:, 0] = np.where(unwrapped_ext[:, 0] < 0.0, unwrapped_ext[:, 0] + 360.0, unwrapped_ext[:, 0])
      unwrapped_holes = []
      for i in range(len(polygon.interiors)):
        local_h = np.asarray(polygon.interiors[i].coords, dtype=np.float64).copy()
        local_h[:, 0] = np.where(local_h[:, 0] < 0.0, local_h[:, 0] + 360.0, local_h[:, 0])
        unwrapped_holes.append(local_h)
      poly_360 = Polygon(unwrapped_ext, unwrapped_holes).buffer(0)
      east_half = poly_360.intersection(box(0.0, -90.0, 180.0, 90.0))
      west_half_360 = poly_360.intersection(box(180.0, -90.0, 360.0, 90.0))
      parts_array.extend(self.extractPolygons(east_half))
      west_polys = self.extractPolygons(west_half_360)
      for i in range(len(west_polys)):
        local_wp = west_polys[i]
        local_ext = np.asarray(local_wp.exterior.coords, dtype=np.float64).copy()
        local_ext[:, 0] = local_ext[:, 0] - 360.0
        local_int = []
        for x in range(len(local_wp.interiors)):
          local_ih = np.asarray(local_wp.interiors[x].coords, dtype=np.float64).copy()
          local_ih[:, 0] = local_ih[:, 0] - 360.0
          local_int.append(local_ih)
        parts_array.extend(self.extractPolygons(Polygon(local_ext, local_int)))
    except Exception:
      parts_array.extend(self.extractPolygons(polygon.intersection(east_clip)))

    #Return statement
    return parts_array if parts_array else [polygon]


  def getConfiguredWidth (self, arg1_grid_config_obj):
    """
    @brief Read validated grid width from configuration dictionary.
    @param arg1_grid_config_obj Grid configuration dictionary.
    @return Positive integer width (default 4320).
    """
    #Convert from parameters
    grid_config_obj = arg1_grid_config_obj if isinstance(arg1_grid_config_obj, dict) else {}

    #Return statement
    return int(grid_config_obj.get("width", 4320))
