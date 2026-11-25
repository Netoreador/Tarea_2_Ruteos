from conexion import RAIZ, conectar

TABLAS = [
    ("sismo", "id_evento",
     "id_evento text PRIMARY KEY, titulo text, magnitud double precision, tipo_magnitud text, "
     "fecha_utc timestamptz, profundidad_km double precision, consulta_usgs text, geom geometry(Point, 4326)",
     "id_evento, titulo, magnitud, tipo_magnitud, fecha_utc::text, profundidad_km, consulta_usgs, ST_AsEWKT(geom)"),
    ("parametros_modelo", "ctid",
     "parametro text PRIMARY KEY, valor double precision, unidad text, fuente text",
     "parametro, valor, unidad, fuente"),
    ("factor_capa", "capa",
     "capa text PRIMARY KEY, montaje text, k double precision, k_fragil double precision, criterio text",
     "capa, montaje, k, k_fragil, criterio"),
    ("nodos_clave", "id",
     "id integer PRIMARY KEY, nombre text, region text, genera boolean, intercambia boolean, recibe boolean, "
     "infraestructura text, incluir boolean, vertice_id bigint, vertice_red bigint, dist_vertice_km double precision, "
     "geom geometry(Point, 4326)",
     "id, nombre, region, genera, intercambia, recibe, infraestructura, incluir, vertice_id, vertice_red, "
     "dist_vertice_km, ST_AsEWKT(geom)"),
    ("enlaces_topo_vertices_pgr", "id",
     "id bigint PRIMARY KEY, the_geom geometry(Point, 4326)",
     "id, ST_AsEWKT(ST_SnapToGrid(the_geom, 0.000001))"),
    ("enlaces_topo", "id",
     "id integer PRIMARY KEY, source integer, target integer, capa text, sintetico boolean, "
     "longitud_km double precision, dist_epicentro_km double precision, mmi_max double precision, "
     "pgv_max_cms double precision, cortes_esperados double precision, "
     "p_falla double precision CHECK (p_falla BETWEEN 0 AND 1), p_falla_menos_sigma double precision, "
     "p_falla_mas_sigma double precision, p_falla_aereo_fragil double precision, p_falla_shakemap double precision, "
     "geom geometry(LineString, 4326)",
     "id, source, target, capa, sintetico, longitud_km, dist_epicentro_km, mmi_max, pgv_max_cms, cortes_esperados, "
     "p_falla, p_falla_menos_sigma, p_falla_mas_sigma, p_falla_aereo_fragil, p_falla_shakemap, "
     "'SRID=4326;' || ST_AsText(geom, 6)"),
]

GEOMETRIAS = {"geom", "the_geom"}


def literal(v):
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return repr(round(v, 12))
    return "'" + str(v).replace("'", "''") + "'"


def escribir(ruta=RAIZ / "main.sql", lote=500):
    con = conectar()
    lineas = [
        "BEGIN;",
        "CREATE EXTENSION IF NOT EXISTS postgis;",
    ]
    for tabla, _, _, _ in reversed(TABLAS):
        lineas.append(f"DROP TABLE IF EXISTS {tabla} CASCADE;")
    filas_por_tabla = {}
    with con.cursor() as cur:
        for tabla, orden, definicion, columnas in TABLAS:
            cur.execute(f"SELECT {columnas} FROM {tabla} ORDER BY {orden}")
            filas = cur.fetchall()
            filas_por_tabla[tabla] = len(filas)
            nombres = [c.split()[0] for c in definicion.split(", ") if c.split()[0].isidentifier()]
            lineas.append("")
            lineas.append(f"CREATE TABLE {tabla} ({definicion});")
            for i in range(0, len(filas), lote):
                valores = []
                for fila in filas[i:i + lote]:
                    partes = []
                    for nombre, v in zip(nombres, fila):
                        partes.append(f"ST_GeomFromEWKT({literal(v)})" if nombre in GEOMETRIAS else literal(v))
                    valores.append("(" + ", ".join(partes) + ")")
                lineas.append(f"INSERT INTO {tabla} ({', '.join(nombres)}) VALUES\n" + ",\n".join(valores) + ";")
    con.close()
    lineas += [
        "",
        "CREATE INDEX enlaces_topo_geom_idx ON enlaces_topo USING gist (geom);",
        "CREATE INDEX enlaces_topo_source_idx ON enlaces_topo (source);",
        "CREATE INDEX enlaces_topo_target_idx ON enlaces_topo (target);",
        "COMMIT;",
        "",
        "SELECT capa, sintetico, count(*) AS enlaces, round(sum(longitud_km)::numeric, 1) AS km,",
        "       round(max(p_falla)::numeric, 4) AS p_max, round(avg(p_falla)::numeric, 4) AS p_media",
        "FROM enlaces_topo GROUP BY capa, sintetico ORDER BY sintetico, capa;",
        "",
    ]
    ruta.write_text("\n".join(lineas), encoding="utf-8")
    return ruta, filas_por_tabla


if __name__ == "__main__":
    ruta, filas = escribir()
    print(ruta, filas)
