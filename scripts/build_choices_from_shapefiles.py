"""
Rebuilds the `choices` sheet (and, optionally, union boundary geometry) for the
Bangladesh Division -> District -> Upazila -> Union XLSForm directly from the
official administrative boundary shapefiles, instead of hand-maintaining a
choice list that can silently drift out of sync with the source geometry.

Input shapefiles (not included in this repo -- see README "Data source"):
  bgd_adm1_*.shp  Division   columns: DIV_N_E, DIV_C_E
  bgd_adm2_*.shp  District   columns: DIS_N_E, DIS_C_E, DIV_C_E
  bgd_adm3_*.shp  Upazila    columns: UP_TH_N_E, UP_TH_C_E, DIS_C_E
  bgd_adm4_*.shp  Union      columns: U_M_N_E, UNI_MUN_T, GEO_CODE, UP_TH_C_E

Output: a `choices_df` (list_name, name, label, div_filter, dis_filter,
upa_filter, latitude, longitude[, geometry]) ready to write into the xlsx's
`choices` sheet with openpyxl/pandas.

Usage:
    python build_choices_from_shapefiles.py --adm-dir /path/to/shapefiles \
        --out choices.csv [--with-boundaries] [--simplify-tolerance 0.001]
"""

import argparse

import geopandas as gpd
import pandas as pd


def load_level(path: str, name_col: str, code_col: str, parent_code_col: str | None) -> gpd.GeoDataFrame:
    """Load one admin level, dissolving duplicate GEO_CODE rows into one geometry.

    The source shapefiles genuinely contain a handful of admin units split
    across two rows sharing the same code (disconnected exclave/char pieces
    stored as separate features, e.g. Barishal Sadar (Kotwali) upazila,
    GEO_CODE 100651, as a MultiPolygon row plus a separate Polygon row).
    pyxform's choice-name-uniqueness validator rejects duplicate `name`
    values, so every level is dissolved by its code before use -- this
    merges same-code fragments into one geometry per unit and is what
    surfaced the data-quality issue in the first place.
    """
    gdf = gpd.read_file(path)
    keep_cols = [name_col, code_col, "geometry"]
    if parent_code_col:
        keep_cols.append(parent_code_col)
    gdf = gdf[keep_cols].dissolve(by=code_col, as_index=False, aggfunc="first")
    return gdf


def largest_polygon(geom):
    """MultiPolygon -> its largest-area member Polygon.

    79 of 4,926 unions are MultiPolygons (real disconnected river-char
    pieces). geoshape only supports a single simple ring, so this keeps the
    main body and drops smaller exclave fragments -- a documented, visible
    simplification, not a silent one.
    """
    if geom.geom_type == "Polygon":
        return geom
    return max(geom.geoms, key=lambda p: p.area)


def to_geoshape(geom, tolerance: float) -> str:
    """Polygon -> XForms geoshape string: 'lat lon alt acc;...;lat lon alt acc'
    with the ring closed (first point repeated as the last).

    Format confirmed against the ODK XForms spec (getodk.github.io/xforms-spec)
    and cross-checked against KoboToolbox's own worked examples (Warsaw
    52.2297 21.0122, Paris 48.8566 2.3522) -- both real cities, and in both,
    the first number is latitude. Altitude/accuracy are always 0 here since
    these are reference boundaries, not GPS fixes.
    """
    simplified = geom.simplify(tolerance, preserve_topology=True)
    poly = largest_polygon(simplified)
    coords = list(poly.exterior.coords)
    if coords[0] != coords[-1]:
        coords.append(coords[0])
    return ";".join(f"{lat:.6f} {lon:.6f} 0 0" for lon, lat in coords)


def build_choices(adm_dir: str, with_boundaries: bool, simplify_tolerance: float) -> pd.DataFrame:
    div = load_level(f"{adm_dir}/bgd_adm1.shp", "DIV_N_E", "DIV_C_E", None)
    dis = load_level(f"{adm_dir}/bgd_adm2.shp", "DIS_N_E", "DIS_C_E", "DIV_C_E")
    upa = load_level(f"{adm_dir}/bgd_adm3.shp", "UP_TH_N_E", "UP_TH_C_E", "DIS_C_E")
    uni = load_level(f"{adm_dir}/bgd_adm4.shp", "U_M_N_E", "GEO_CODE", "UP_TH_C_E")

    rows = []

    def add_level(gdf, level_prefix, name_col, code_col, parent_col, parent_prefix, extra_label_col=None):
        for _, r in gdf.iterrows():
            pt = r.geometry.representative_point()  # guaranteed inside the polygon, unlike raw .centroid
            label = r[name_col]
            if extra_label_col and r.get(extra_label_col) == "Municipality":
                label = f"{label} (Municipality)"
            row = {
                "list_name": f"{level_prefix}_",
                "name": f"{level_prefix}_{r[code_col]}",
                "label": label,
                "latitude": round(pt.y, 6),
                "longitude": round(pt.x, 6),
            }
            if parent_col:
                row[f"{parent_prefix}_filter"] = f"{parent_prefix}_{r[parent_col]}"
            if with_boundaries and level_prefix == "uni":
                row["geometry"] = to_geoshape(r.geometry, simplify_tolerance)
            rows.append(row)

    add_level(div, "div", "DIV_N_E", "DIV_C_E", None, None)
    add_level(dis, "dis", "DIS_N_E", "DIS_C_E", "DIV_C_E", "div")
    add_level(upa, "upa", "UP_TH_N_E", "UP_TH_C_E", "DIS_C_E", "dis")
    add_level(uni, "uni", "U_M_N_E", "GEO_CODE", "UP_TH_C_E", "upa", extra_label_col="UNI_MUN_T")

    return pd.DataFrame(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--adm-dir", required=True, help="Directory containing bgd_adm1..4 shapefiles")
    parser.add_argument("--out", required=True, help="Output CSV path")
    parser.add_argument("--with-boundaries", action="store_true", help="Include union-level geoshape geometry")
    parser.add_argument("--simplify-tolerance", type=float, default=0.001, help="Degrees; ~0.001 = ~111m")
    args = parser.parse_args()

    df = build_choices(args.adm_dir, args.with_boundaries, args.simplify_tolerance)
    df.to_csv(args.out, index=False)
    print(f"Wrote {len(df)} choice rows to {args.out}")
