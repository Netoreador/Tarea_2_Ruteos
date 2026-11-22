"""Carga los 4 shapefiles de Yafún a PostGIS."""
from pathlib import Path

import geopandas as gpd
from sqlalchemy import create_engine, text

DB_URL = "postgresql+psycopg2://postgres:postgres@localhost:5432/yafun"
DATA = Path(__file__).parent / "data"

CAPAS = {
    "fibra_optica_detectada": "fibra",
    "postacion_electrica_detectada": "postacion",
    "camino_sin_postacion_detectado": "camino",
    "trayecto_en_ferry": "ferry",
}


def main():
    engine = create_engine(DB_URL)

    with engine.begin() as con:
        con.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        con.execute(text("CREATE EXTENSION IF NOT EXISTS pgrouting"))

    for archivo, tabla in CAPAS.items():
        gdf = gpd.read_file(DATA / f"{archivo}.shp").rename_geometry("geom")
        gdf.to_postgis(tabla, engine, if_exists="replace", index=False)
        print(f"{tabla:10s} {len(gdf):5d} filas  (CRS {gdf.crs})")

    with engine.connect() as con:
        v = con.execute(text("SELECT postgis_version(), pgr_version()")).one()
        print("PostGIS:", v[0], "| pgRouting:", v[1])


if __name__ == "__main__":
    main()