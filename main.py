import argparse
import functools
import json
import subprocess
import time
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
import psycopg2

import attr
import cargar_datos
import exportar_main_sql
import mapa
from conexion import PARAMS, RAIZ, SALIDA, SQL, conectar, consulta, ejecutar_archivo

SCRIPTS = ["01_enlaces", "02_nodos_clave", "03_topologia", "04_enlaces_sinteticos",
           "05_modelo_falla", "06_probabilidades"]
SIN_CONECTORES = ("empalme", "urbano")
SOLO_FIBRA = ("postacion", "camino", "ferry", "empalme", "urbano")
ESCENARIOS = [
    ("p_falla", "Principal: MMI mediana, cable ductil", ()),
    ("p_falla_menos_sigma", "MMI mediana - 1 sigma", ()),
    ("p_falla_mas_sigma", "MMI mediana + 1 sigma", ()),
    ("p_falla_aereo_fragil", "Tendido aereo fragil (k = 1)", ()),
    ("p_falla_shakemap", "MMI observado (ShakeMap USGS)", ()),
    ("p_falla", "Principal sin empalmes ni red urbana", SIN_CONECTORES),
]
BD_VERIFICACION = "yafun_main_sql"


def titulo(n, texto):
    print(f"\n[{n}] {texto}")
    print("-" * (len(texto) + 4))


def tabla(sql, dbname=None):
    columnas, filas = consulta(sql, dbname=dbname)
    celdas = [[("" if v is None else str(v)) for v in f] for f in filas]
    anchos = [max(len(c), *(len(f[i]) for f in celdas)) if celdas else len(c) for i, c in enumerate(columnas)]
    print("  " + " | ".join(c.ljust(a) for c, a in zip(columnas, anchos)))
    print("  " + "-+-".join("-" * a for a in anchos))
    for f in celdas:
        print("  " + " | ".join(v.ljust(a) for v, a in zip(f, anchos)))


def bd_disponible():
    try:
        conectar("postgres").close()
        return True
    except psycopg2.OperationalError:
        return False


def asegurar_bd():
    if bd_disponible():
        return "ya estaba disponible"
    subprocess.run(["docker", "compose", "up", "-d", "--wait"], cwd=RAIZ, check=True)
    for _ in range(60):
        if bd_disponible():
            return "levantada con docker compose up -d --wait"
        time.sleep(1)
    raise SystemExit("La base de datos no responde en el puerto configurado")


def recrear_bd(nombre):
    con = conectar("postgres")
    with con.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS {nombre} WITH (FORCE)")
        cur.execute(f"CREATE DATABASE {nombre}")
    con.close()


def paso_topologia():
    for nombre in SCRIPTS[:4]:
        avisos = ejecutar_archivo(SQL / f"{nombre}.sql")
        if nombre == "03_topologia":
            for a in avisos:
                if "pgr_createTopology(" in a or "TOPOLOGY CREATED" in a or "Vertices table" in a:
                    print("  NOTICE " + a.replace("NOTICE:", "").strip())


class Silencioso(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def servir_mapa(puerto):
    manejador = functools.partial(Silencioso, directory=str(SALIDA))
    for p in range(puerto, puerto + 20):
        try:
            servidor = ThreadingHTTPServer(("127.0.0.1", p), manejador)
            break
        except OSError:
            continue
    else:
        raise SystemExit("No hay un puerto libre para servir el mapa")
    url = f"http://localhost:{servidor.server_port}/mapa.html"
    print(f"\nMapa en {url} (Ctrl+C para terminar)")
    webbrowser.open(url)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        servidor.server_close()


def resumen_escenarios(n_iter, semilla):
    filas = []
    for col, nombre, sin_capas in ESCENARIOS:
        g, r = attr.calcular(col, n_iter, semilla, sin_capas=sin_capas)
        clave = col if not sin_capas else f"{col}_sin_conectores"
        filas.append({"columna": clave, "nombre": nombre, "g": g, "r": r, "attr": r["attr"]})
    return filas


def main():
    ap = argparse.ArgumentParser(description="Tarea 2: ATTR de la red Yafun antes y despues del sismo M8.8")
    ap.add_argument("--iter", type=int, default=20000, help="iteraciones de Monte Carlo")
    ap.add_argument("--semilla", type=int, default=42)
    ap.add_argument("--sin-navegador", action="store_true", help="no abrir el mapa al final")
    ap.add_argument("--puerto", type=int, default=8765, help="puerto del servidor local del mapa")
    a = ap.parse_args()
    t0 = time.time()

    titulo(0, "Base de datos")
    print(f"  PostgreSQL en {PARAMS['host']}:{PARAMS['port']}: {asegurar_bd()}")
    recrear_bd(PARAMS["dbname"])
    print(f"  BD '{PARAMS['dbname']}' creada desde cero")

    titulo(1, "Carga de datos (Respuesta_T5610 y USGS)")
    filas, versiones = cargar_datos.main()
    for t, n in filas.items():
        print(f"  {t:10s} {n:5d} tramos")
    print(f"  PostGIS {versiones[0]} | pgRouting {versiones[1]}")
    tabla("SELECT id_evento, magnitud, tipo_magnitud, fecha_utc, profundidad_km, "
          "round(ST_Y(geom)::numeric, 3) AS lat, round(ST_X(geom)::numeric, 3) AS lon FROM sismo")

    titulo(2, "Topologia con pgr_createTopology (tolerancia 0.001 grados)")
    paso_topologia()
    tabla("SELECT capa, sintetico, count(*) AS enlaces, round(sum(longitud_km)::numeric, 1) AS km "
          "FROM enlaces_topo GROUP BY capa, sintetico ORDER BY sintetico, capa")
    tabla("SELECT (SELECT count(*) FROM enlaces_topo) AS enlaces, "
          "(SELECT count(*) FROM enlaces_topo_vertices_pgr) AS vertices, "
          "(SELECT count(*) FROM lazos_eliminados) AS lazos_eliminados, "
          "(SELECT count(*) FROM empalmes) AS empalmes, "
          "(SELECT count(*) FROM enlaces_topo WHERE p_falla = 0) AS enlaces_con_p_0, "
          "(SELECT count(DISTINCT component) FROM pgr_connectedComponents("
          "'SELECT id, source, target, cost, reverse_cost FROM enlaces_topo_cc')) AS componentes")

    titulo(3, "Nodos clave ubicados en la topologia")
    tabla("SELECT n.id, n.nombre, concat_ws('+', CASE WHEN genera THEN 'G' END, CASE WHEN intercambia THEN 'I' END, "
          "CASE WHEN recibe THEN 'R' END) AS rol, n.incluir, n.vertice_id, n.vertice_red, "
          "round(n.dist_vertice_km::numeric, 2) AS km_acceso FROM nodos_clave n ORDER BY n.id")

    titulo(4, "ATTR de la infraestructura en operacion")
    g0, r0 = attr.calcular(None)
    attr.mostrar("En operacion (p = 0 en todos los enlaces)", g0, r0)
    for nombre, capas in [("Solo fibra detectada y accesos", SOLO_FIBRA), ("Sin empalmes ni red urbana", SIN_CONECTORES)]:
        gx, rx = attr.calcular(None, sin_capas=capas)
        grupos = attr.componentes_claves(gx, attr.etiquetas_claves(gx, gx["p"] >= 0))
        print(f"  Variante '{nombre}': ATTR = {rx['attr']:.4f}, {len(grupos)} grupos de nodos clave, "
              f"el mayor con {len(grupos[0])}")

    titulo(5, "Modelo de falla y probabilidad de cada enlace")
    for nombre in SCRIPTS[4:]:
        ejecutar_archivo(SQL / f"{nombre}.sql")
    tabla("SELECT r_hipo_km, round(mmi_allen2012(r_hipo_km)::numeric, 2) AS mmi, "
          "round(pgv_worden2012(mmi_allen2012(r_hipo_km))::numeric, 1) AS pgv_cms, "
          "round(cortes_por_km(mmi_allen2012(r_hipo_km), 0.3)::numeric, 5) AS cortes_por_km "
          "FROM unnest(ARRAY[25, 50, 100, 200, 300, 400, 500, 600]::double precision[]) AS r_hipo_km")
    tabla("SELECT count(*) AS enlaces, count(*) FILTER (WHERE p_falla > 0) AS con_p_mayor_0, "
          "round(max(p_falla)::numeric, 4) AS p_max, round(avg(p_falla)::numeric, 4) AS p_media, "
          "round(sum(cortes_esperados)::numeric, 1) AS cortes_esperados, "
          "bool_and(p_falla BETWEEN 0 AND 1) AS todas_en_0_1 FROM enlaces_topo")
    print("\n  MMI del modelo frente al ShakeMap del USGS en los nodos clave")
    tabla("""SELECT n.nombre,
                    round((ST_Distance(n.geom::geography, s.geom::geography) / 1000)::numeric) AS d_epi_km,
                    round(mmi_allen2012(sqrt((ST_Distance(n.geom::geography, s.geom::geography) / 1000) ^ 2
                          + param('H') ^ 2))::numeric, 2) AS mmi_modelo,
                    (SELECT g.mmi FROM sismo_mmi_grilla g WHERE ST_DWithin(g.geom, n.geom, 0.15)
                     ORDER BY g.geom <-> n.geom LIMIT 1) AS mmi_shakemap
             FROM nodos_clave n, sismo s
             WHERE n.incluir AND ST_DWithin(n.geom, s.geom, 7)
             ORDER BY 2""")
    print("\n  Enlaces mas afectados")
    tabla("""SELECT e.id, e.capa, round(e.longitud_km::numeric, 1) AS km, round(e.dist_epicentro_km::numeric, 1) AS d_epi_km,
                    round(e.mmi_max::numeric, 2) AS mmi, round(e.pgv_max_cms::numeric, 1) AS pgv_cms,
                    round(e.p_falla::numeric, 4) AS p_falla, c.nombre AS cerca_de, round(c.km::numeric) AS km_nodo
             FROM enlaces_topo e
             CROSS JOIN LATERAL (SELECT n.nombre, ST_Distance(n.geom::geography, e.geom::geography) / 1000 AS km
                                 FROM nodos_clave n WHERE n.incluir ORDER BY n.geom <-> e.geom LIMIT 1) c
             ORDER BY e.p_falla DESC, e.id LIMIT 10""")
    print("\n  Enlaces menos afectados con p > 0")
    tabla("""SELECT id, capa, round(longitud_km::numeric, 2) AS km, round(dist_epicentro_km::numeric, 1) AS d_epi_km,
                    round(mmi_max::numeric, 2) AS mmi, round(p_falla::numeric, 6) AS p_falla
             FROM enlaces_topo WHERE p_falla > 0 ORDER BY p_falla, id LIMIT 5""")
    tabla("SELECT count(*) FILTER (WHERE p_falla = 0 AND capa <> 'ferry') AS terrestres_con_p_0, "
          "count(*) FILTER (WHERE capa = 'ferry') AS ferry_p_0 FROM enlaces_topo")

    titulo(6, "main.sql")
    ruta_sql, filas_sql = exportar_main_sql.escribir()
    print(f"  {ruta_sql.name}: {ruta_sql.stat().st_size / 1e6:.1f} MB, filas {filas_sql}")
    recrear_bd(BD_VERIFICACION)
    ejecutar_archivo(ruta_sql, BD_VERIFICACION)
    print(f"  Cargado en la BD vacia '{BD_VERIFICACION}':")
    tabla("SELECT count(*) AS enlaces, round(sum(p_falla)::numeric, 4) AS suma_p, "
          "round(max(p_falla)::numeric, 4) AS p_max FROM enlaces_topo", BD_VERIFICACION)

    titulo(7, "ATTR despues del terremoto")
    esc = resumen_escenarios(a.iter, a.semilla)
    g, r = esc[0]["g"], esc[0]["r"]
    attr.mostrar("Despues del sismo, escenario principal (p_falla)", g, r)
    delta = r["attr"] - r0["attr"]
    print(f"\n  ATTR antes = {r0['attr']:.4f} | ATTR despues = {r['attr']:.4f}")
    print(f"  Diferencia = {delta:.4f} ({100 * delta / r0['attr']:.1f} %)")
    _, r_ver = attr.calcular("p_falla", a.iter, a.semilla, dbname=BD_VERIFICACION)
    print(f"  ATTR calculado desde main.sql en '{BD_VERIFICACION}': {r_ver['attr']:.4f} "
          f"({'coincide' if abs(r_ver['attr'] - r['attr']) < 1e-12 else 'NO coincide'})")

    print("\n  Escenarios de sensibilidad")
    print(f"  {'escenario':40s} {'ATTR':>7s} {'IC95':>8s} {'mediana':>8s} {'P(ATTR=1)':>10s}")
    for e in esc:
        x = e["r"]
        print(f"  {e['nombre']:40s} {x['attr']:7.4f} {x['ic95']:8.4f} {x['mediana']:8.4f} {x['p_attr_1']:10.4f}")
    necesarias = max(attr.iteraciones_necesarias(e["r"]["sd"]) for e in esc)
    sin_con = esc[-1]["r"]["attr"]
    print(f"  Efecto de los empalmes y la red urbana: {r['attr'] - sin_con:+.4f} en el ATTR despues del sismo")
    print(f"  Iteraciones necesarias para IC95 de +/- 0.005 en el peor escenario: {necesarias} (se usan {a.iter})")

    print("\n  Nodos clave tras el sismo (escenario principal)")
    nombres = g["claves"].nombre.tolist()
    i_stgo = nombres.index("Santiago")
    media_pares = (r["pares"].sum(axis=1) - 1) / (len(nombres) - 1)
    orden = np.argsort(r["pares"][:, i_stgo])
    print(f"  {'nodo':14s} {'P(con Santiago)':>16s} {'conexion media':>15s}")
    for i in orden:
        print(f"  {nombres[i]:14s} {r['pares'][i, i_stgo]:16.4f} {media_pares[i]:15.4f}")

    sim = attr.estado_representativo(g, r)
    print(f"\n  Simulacion representativa: iteracion {sim[0] + 1}, ATTR = {r['muestras'][sim[0]]:.4f}, "
          f"{int((~sim[1]).sum())} enlaces cortados")
    for grupo in attr.componentes_claves(g, sim[2]):
        print(f"    {len(grupo):2d} nodos: {', '.join(grupo)}")

    titulo(8, "Mapa Leaflet")
    ruta_mapa, n_cortados = mapa.generar(g, r, r0["attr"], esc, sim)
    resultados = {
        "attr_antes": round(r0["attr"], 6),
        "attr_despues": round(r["attr"], 6),
        "diferencia": round(delta, 6),
        "variacion_pct": round(100 * delta / r0["attr"], 2),
        "ic95": round(r["ic95"], 6),
        "n_iter": a.iter,
        "semilla": a.semilla,
        "escenarios": {e["columna"]: round(e["attr"], 6) for e in esc},
        "p_con_santiago": {nombres[i]: round(float(r["pares"][i, i_stgo]), 4) for i in range(len(nombres))},
    }
    (SALIDA / "resultados.json").write_text(json.dumps(resultados, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  {ruta_mapa}")
    print(f"  {SALIDA / 'resultados.json'}")
    print(f"\nListo en {time.time() - t0:.0f} s")
    if not a.sin_navegador:
        servir_mapa(a.puerto)


if __name__ == "__main__":
    main()
