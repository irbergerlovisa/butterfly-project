"""
Butterfly phenology & distribution analysis
--------------------------------------------
Recreates three things from Artportalen CSV exports for two (or more) species:
  1. Monthly flight-period ("phenology") comparison between species
  2. Seasonal timing split by latitude band (South / Central / North Sweden)
  3. An interactive map of observation density

HOW TO USE
----------
1. Export your species' observations from Artportalen as CSV (one file per species).
2. Put the CSV file paths in SPECIES_FILES below.
3. Check SOURCE_CRS (see note below) -- this trips people up more than anything else.
4. Run:  python analyze_butterflies.py
5. Look at the .png charts and open observation_map.html in a browser.

Requires: pandas, matplotlib, pyproj, geopandas
  pip install pandas matplotlib pyproj geopandas

The map needs a Sweden outline to plot on top of. This script downloads a
free one automatically the first time you run it (from a public GitHub repo)
and caches it locally as sweden.geojson. If you're offline or the download
fails, put your own Sweden boundary GeoJSON/shapefile at that path instead.
"""

import os
import urllib.request

import pandas as pd
import matplotlib.pyplot as plt
from pyproj import Transformer
import geopandas as gpd

# ---------------------------------------------------------------------------
# CONFIG -- edit this section for your own data
# ---------------------------------------------------------------------------

SPECIES_FILES = {
    "Rovfjäril": "rovfjäril25.csv",
    "Rapsfjäril": "rapsfjäril2025.csv",
}

# Artportalen exports give coordinates in "Ost" (easting) / "Nord" (northing)
# columns, but WHICH coordinate system depends on your export settings:
#
#   RT90 2.5 gon V  -> EPSG:3021   Ost ~1,200,000-1,900,000 / Nord ~6,100,000-7,600,000
#   SWEREF99 TM     -> EPSG:3006   Ost ~260,000-920,000     / Nord ~6,100,000-7,700,000
#
# Easiest way to check: look at the size of your "Ost" values. If they are
# roughly 1.2-1.9 million, you have RT90. If they are roughly 260,000-920,000,
# you have SWEREF99 TM. Get this wrong and every point lands in the wrong
# place (often not even in Sweden), so it's worth double-checking once with
# a known reference point (e.g. Stockholm Central Station is approximately
# Ost=1629381, Nord=6581596 in RT90, or Ost=674032, Nord=6580822 in SWEREF99TM).
SOURCE_CRS = "EPSG:3021"  # <-- change to "EPSG:3006" if your export is SWEREF99 TM

# Latitude bands used to compare seasonal timing across the country.
# Adjust the breakpoints to whatever regional split makes sense for your question.
LAT_BANDS = [
    (0, 57.5, "South"),
    (57.5, 60.5, "Central"),
    (60.5, 90, "North"),
]

MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# ---------------------------------------------------------------------------
# LOAD & CLEAN
# ---------------------------------------------------------------------------

def load_species(path):
    """Read one Artportalen CSV export and do basic cleaning."""
    df = pd.read_csv(path, encoding="utf-8")

    # Defensive: if multiple exports were concatenated into one file, or the
    # file was re-saved in Excel, the header row sometimes ends up repeated
    # as an ordinary data row further down. Drop any such rows.
    header_leak = df["Startdatum"] == "Startdatum"
    if header_leak.any():
        print(f"{path}: dropping {header_leak.sum()} duplicated header row(s) found inside the file")
        df = df[~header_leak]

    df["Startdatum"] = pd.to_datetime(df["Startdatum"], errors="coerce")
    bad_dates = df["Startdatum"].isna()
    if bad_dates.any():
        print(f"{path}: dropping {bad_dates.sum()} row(s) with unparseable dates")
        df = df[~bad_dates]

    df["month"] = df["Startdatum"].dt.month
    df["Ost"] = pd.to_numeric(df["Ost"], errors="coerce")
    df["Nord"] = pd.to_numeric(df["Nord"], errors="coerce")
    df = df.dropna(subset=["Ost", "Nord"])
    return df


def add_latlon(df, source_crs=SOURCE_CRS):
    """Convert Ost/Nord to standard WGS84 latitude/longitude for mapping."""
    transformer = Transformer.from_crs(source_crs, "EPSG:4326", always_xy=True)
    lon, lat = transformer.transform(df["Ost"].values, df["Nord"].values)
    df = df.copy()
    df["lat"] = lat
    df["lon"] = lon
    return df


def latitude_band(lat):
    for lo, hi, label in LAT_BANDS:
        if lo <= lat < hi:
            return label
    return "Unknown"


# ---------------------------------------------------------------------------
# ANALYSIS
# ---------------------------------------------------------------------------

def monthly_share(df):
    """% of a group's total records falling in each calendar month."""
    counts = df["month"].value_counts().reindex(range(1, 13), fill_value=0)
    return 100 * counts / counts.sum()


def monthly_share_by_band(df):
    result = {}
    for _, _, label in LAT_BANDS:
        sub = df[df["band"] == label]
        if len(sub) == 0:
            continue
        result[label] = (monthly_share(sub), len(sub))
    return result


# ---------------------------------------------------------------------------
# PLOTTING
# ---------------------------------------------------------------------------

def plot_phenology_comparison(shares_by_species, outfile):
    plt.figure(figsize=(9, 5))
    for species, share in shares_by_species.items():
        plt.plot(MONTH_NAMES, share.values, marker="o", label=species)
    plt.ylabel("% of species' annual records")
    plt.title("Flight period comparison")
    plt.legend()
    plt.tight_layout()
    plt.savefig(outfile, dpi=150)
    plt.close()


def plot_latitude_bands(species, band_shares, outfile):
    plt.figure(figsize=(9, 5))
    for label, (share, n) in band_shares.items():
        plt.plot(MONTH_NAMES, share.values, marker="o", label=f"{label} (n={n})")
    plt.ylabel("% of band's annual records")
    plt.title(f"{species}: seasonal timing by latitude band")
    plt.legend()
    plt.tight_layout()
    plt.savefig(outfile, dpi=150)
    plt.close()


# ---------------------------------------------------------------------------
# MAP (static PNG, plotted over a Sweden outline)
# ---------------------------------------------------------------------------

SWEDEN_GEOJSON_PATH = "sweden.geojson"
NATURAL_EARTH_URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
    "master/geojson/ne_50m_admin_0_countries.geojson"
)


def get_sweden_outline():
    """
    Downloads (once) a Sweden boundary and caches it locally as
    sweden.geojson. Uses the Natural Earth 1:50m countries dataset, which
    has enough coastal detail to include islands like Gotland and Öland
    properly -- a coarser boundary makes real coastal/island observations
    appear to fall outside the coastline.
    """
    if not os.path.exists(SWEDEN_GEOJSON_PATH):
        # Downloaded with urllib (not geopandas' own URL reader) since
        # GDAL's bundled libcurl can choke on some corporate/sandbox
        # network proxies even when plain HTTPS works fine otherwise.
        tmp_path = "_natural_earth_countries.geojson"
        urllib.request.urlretrieve(NATURAL_EARTH_URL, tmp_path)
        world = gpd.read_file(tmp_path)
        sweden = world[world["ADMIN"] == "Sweden"]
        sweden.to_file(SWEDEN_GEOJSON_PATH, driver="GeoJSON")
        os.remove(tmp_path)
    return gpd.read_file(SWEDEN_GEOJSON_PATH)


def build_density_map(dfs_by_species, outfile, cell_size=0.4):
    """
    Aggregates points into a grid before plotting -- with thousands of raw
    points the map becomes unreadable. cell_size is in degrees (0.4 degrees
    is roughly 40-45 km in Sweden). Marker area scales with record count.
    Saves a static PNG.
    """
    sweden = get_sweden_outline()
    palette = ["#d62728", "#2ca02c", "#1f77b4", "#9467bd", "#ff7f0e"]
    # Fix each species' color by its original (input dict) order, so colors
    # stay consistent no matter which species has more records this run.
    color_map = {sp: palette[i % len(palette)] for i, sp in enumerate(dfs_by_species)}

    fig, ax = plt.subplots(figsize=(6, 9))
    sweden.plot(ax=ax, color="#f0f0f0", edgecolor="#888888", linewidth=0.8)

    # Draw the species with the most records first, so a smaller/rarer
    # species' markers aren't hidden underneath a larger species' markers.
    ordered = sorted(dfs_by_species.items(), key=lambda kv: -len(kv[1]))

    for species, df in ordered:
        color = color_map[species]
        grid = (
            df.assign(
                glat=(df["lat"] / cell_size).round() * cell_size,
                glon=(df["lon"] / cell_size).round() * cell_size,
            )
            .groupby(["glat", "glon"])
            .size()
            .reset_index(name="count")
        )
        # marker area (not radius) scales with count so size is a fair visual cue
        sizes = 15 + grid["count"] * 6
        ax.scatter(
            grid["glon"], grid["glat"],
            s=sizes, color=color, alpha=0.55,
            edgecolor="white", linewidth=0.4,
            label=species,
        )

    ax.set_xlim(sweden.total_bounds[0] - 1, sweden.total_bounds[2] + 1)
    ax.set_ylim(sweden.total_bounds[1] - 0.5, sweden.total_bounds[3] + 0.5)
    ax.set_axis_off()
    ax.set_title("Observation density")
    ax.legend(loc="lower left", frameon=False)
    plt.tight_layout()
    plt.savefig(outfile, dpi=180)
    plt.close()


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    dfs = {}
    shares = {}

    for species, path in SPECIES_FILES.items():
        df = load_species(path)
        df = add_latlon(df)
        df["band"] = df["lat"].apply(latitude_band)
        dfs[species] = df
        shares[species] = monthly_share(df)

        band_shares = monthly_share_by_band(df)
        plot_latitude_bands(species, band_shares, f"{species}_latitude_bands.png")

    plot_phenology_comparison(shares, "phenology_comparison.png")
    build_density_map(dfs, "observation_map.png")

    print("Done. Files written:")
    print(" - phenology_comparison.png")
    for species in SPECIES_FILES:
        print(f" - {species}_latitude_bands.png")
    print(" - observation_map.png")


if __name__ == "__main__":
    main()
