import json

from conexion import RAIZ, SALIDA, consulta

PLANTILLA = RAIZ / "plantilla_mapa.html"


def _geojson(sql):
    _, filas = consulta(sql)
    return filas[0][0]


def generar(g, r, attr_antes, escenarios, sim):
    iteracion, vivos, etq = sim
    cortados = set(g["aristas"].id[~vivos].tolist())
    enlaces = _geojson("""
        SELECT json_build_object('type', 'FeatureCollection', 'features', json_agg(json_build_object(
            'type', 'Feature',
            'geometry', ST_AsGeoJSON(ST_SimplifyPreserveTopology(geom, 0.0002), 5)::json,
            'properties', json_build_object(
                'id', id, 'c', capa, 's', sintetico,
                'l', round(longitud_km::numeric, 3), 'd', round(dist_epicentro_km::numeric, 1),
                'm', round(mmi_max::numeric, 2), 'v', round(pgv_max_cms::numeric, 1),
                'p', round(p_falla::numeric, 5))) ORDER BY id))
        FROM enlaces_topo""")
    for f in enlaces["features"]:
        f["properties"]["x"] = 1 if f["properties"]["id"] in cortados else 0
    mmi = _geojson("""
        SELECT json_build_object('type', 'FeatureCollection', 'features', json_agg(json_build_object(
            'type', 'Feature', 'geometry', ST_AsGeoJSON(geom, 4)::json,
            'properties', json_build_object('mmi', mmi)) ORDER BY mmi))
        FROM sismo_mmi_shakemap WHERE mmi >= 4""")
    _, filas = consulta("""
        SELECT id, nombre, genera, intercambia, recibe, infraestructura, incluir,
               ST_Y(geom), ST_X(geom), COALESCE(dist_vertice_km, 0)
        FROM nodos_clave ORDER BY id""")
    _, sismo = consulta("""
        SELECT id_evento, titulo, magnitud, to_char(fecha_utc AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI "UTC"'),
               profundidad_km, ST_Y(geom), ST_X(geom) FROM sismo""")
    ids = g["claves"].id.tolist()
    santiago = ids.index(int(g["claves"].loc[g["claves"].nombre == "Santiago", "id"].iloc[0]))
    grupos = {e: i for i, e in enumerate(dict.fromkeys(etq.tolist()))}
    nodos = []
    for (nid, nombre, ge, it, re, infra, incl, lat, lon, km) in filas:
        n = {"nombre": nombre, "genera": ge, "intercambia": it, "recibe": re, "infra": infra,
             "incluir": incl, "lat": round(lat, 5), "lon": round(lon, 5), "km": round(km, 2),
             "p_stgo": 0.0, "grupo": 8}
        if incl:
            i = ids.index(nid)
            n["p_stgo"] = round(float(r["pares"][i, santiago]), 4)
            n["grupo"] = grupos[int(etq[i])]
        nodos.append(n)
    s = sismo[0]
    k = r["n_claves"]
    datos = {
        "resumen": {
            "enlaces": r["n_aristas"], "vertices": r["n_vertices"], "claves": k, "pares": k * (k - 1) // 2,
            "attr_antes": round(attr_antes, 4), "attr_despues": round(r["attr"], 4), "ic95": round(r["ic95"], 4),
            "n_iter": r["n_iter"], "semilla": r["semilla"],
        },
        "sismo": {"id": s[0], "titulo": s[1], "mag": s[2], "fecha": s[3], "prof": s[4],
                  "lat": s[5], "lon": s[6]},
        "sim": {"iteracion": iteracion + 1, "attr": round(float(r["muestras"][iteracion]), 4),
                "cortados": len(cortados)},
        "escenarios": [{"nombre": e["nombre"], "attr": round(e["attr"], 4)} for e in escenarios],
        "nodos": nodos,
        "enlaces": enlaces,
        "mmi": mmi,
    }
    SALIDA.mkdir(exist_ok=True)
    ruta = SALIDA / "mapa.html"
    html = PLANTILLA.read_text(encoding="utf-8").replace(
        "/*DATOS*/", json.dumps(datos, ensure_ascii=False, separators=(",", ":")))
    ruta.write_text(html, encoding="utf-8")
    return ruta, len(cortados)
