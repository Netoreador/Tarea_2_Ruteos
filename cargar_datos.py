import json
import urllib.request

import geopandas as gpd
from sqlalchemy import text

from conexion import DATOS, motor

CAPAS = {
    "fibra_optica_detectada": "fibra",
    "postacion_electrica_detectada": "postacion",
    "camino_sin_postacion_detectado": "camino",
    "trayecto_en_ferry": "ferry",
}

EVENTO_USGS = "official20100227063411530_30"
CONSULTA_USGS = (
    "https://earthquake.usgs.gov/fdsnws/event/1/query"
    f"?eventid={EVENTO_USGS}&format=geojson"
)
ARCHIVO_SISMO = DATOS / "sismo_maule_2010.geojson"
ARCHIVO_SHAKEMAP = DATOS / "shakemap_mmi_maule_2010.geojson"
ARCHIVO_GRILLA = DATOS / "shakemap_mmi_grilla_maule_2010.covjson"


def descargar_si_falta():
    if not ARCHIVO_SISMO.exists():
        urllib.request.urlretrieve(CONSULTA_USGS, ARCHIVO_SISMO)


def cargar_capas(engine):
    filas = {}
    for archivo, tabla in CAPAS.items():
        gdf = gpd.read_file(DATOS / f"{archivo}.shp").rename_geometry("geom")
        gdf.to_postgis(tabla, engine, if_exists="replace", index=False)
        filas[tabla] = len(gdf)
    return filas


def cargar_sismo(engine):
    evento = json.loads(ARCHIVO_SISMO.read_text(encoding="utf-8"))
    p = evento["properties"]
    with engine.begin() as con:
        con.execute(text("DROP TABLE IF EXISTS sismo"))
        con.execute(text("""
            CREATE TABLE sismo (
                id_evento      text PRIMARY KEY,
                titulo         text,
                magnitud       double precision,
                tipo_magnitud  text,
                fecha_utc      timestamptz,
                profundidad_km double precision,
                consulta_usgs  text,
                geojson        jsonb,
                geom           geometry(Point, 4326)
            )"""))
        con.execute(text("""
            INSERT INTO sismo
            SELECT :id, :titulo, :mag, :tipo, to_timestamp(:ms / 1000.0), :prof, :consulta,
                   CAST(:geojson AS jsonb),
                   ST_SetSRID(ST_Force2D(ST_GeomFromGeoJSON(:geom)), 4326)
            """), {
            "id": evento["id"], "titulo": p["title"], "mag": p["mag"], "tipo": p["magType"],
            "ms": p["time"], "prof": evento["geometry"]["coordinates"][2],
            "consulta": CONSULTA_USGS, "geojson": json.dumps(evento),
            "geom": json.dumps(evento["geometry"]),
        })
    contornos = gpd.read_file(ARCHIVO_SHAKEMAP).set_crs(4326, allow_override=True)
    contornos = contornos.rename(columns={"value": "mmi"}).rename_geometry("geom")
    contornos[["mmi", "geom"]].to_postgis("sismo_mmi_shakemap", engine, if_exists="replace", index=False)
    cargar_grilla(engine)


def cargar_grilla(engine):
    cov = json.loads(ARCHIVO_GRILLA.read_text(encoding="utf-8"))
    ejes = cov["domain"]["axes"]
    valores = cov["ranges"]["MMI"]["values"]

    def coordenadas(eje):
        return [eje["start"] + (eje["stop"] - eje["start"]) * i / (eje["num"] - 1) for i in range(eje["num"])]

    xs, ys = coordenadas(ejes["x"]), coordenadas(ejes["y"])
    filas = [{"x": x, "y": y, "mmi": valores[j * len(xs) + i]}
             for j, y in enumerate(ys) for i, x in enumerate(xs) if valores[j * len(xs) + i] is not None]
    with engine.begin() as con:
        con.execute(text("DROP TABLE IF EXISTS sismo_mmi_grilla"))
        con.execute(text("CREATE TABLE sismo_mmi_grilla (mmi double precision, geom geometry(Point, 4326))"))
        con.execute(text("INSERT INTO sismo_mmi_grilla VALUES (:mmi, ST_SetSRID(ST_MakePoint(:x, :y), 4326))"), filas)
        con.execute(text("CREATE INDEX sismo_mmi_grilla_geom_idx ON sismo_mmi_grilla USING gist (geom)"))


def main():
    descargar_si_falta()
    engine = motor()
    with engine.begin() as con:
        con.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        con.execute(text("CREATE EXTENSION IF NOT EXISTS pgrouting"))
    filas = cargar_capas(engine)
    cargar_sismo(engine)
    with engine.connect() as con:
        versiones = con.execute(text("SELECT postgis_lib_version(), pgr_version()")).one()
    return filas, versiones


if __name__ == "__main__":
    filas, versiones = main()
    for tabla, n in filas.items():
        print(f"{tabla:10s} {n:5d} tramos")
    print(f"PostGIS {versiones[0]} | pgRouting {versiones[1]}")
