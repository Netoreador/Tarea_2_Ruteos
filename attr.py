import argparse

import numpy as np
import pandas as pd
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

from conexion import motor

COLUMNAS_P = {None, "p_falla", "p_falla_menos_sigma", "p_falla_mas_sigma", "p_falla_aereo_fragil", "p_falla_shakemap"}


def cargar_grafo(columna_p=None, dbname=None, sin_capas=()):
    if columna_p not in COLUMNAS_P:
        raise ValueError(f"columna no valida: {columna_p}")
    engine = motor(dbname)
    expr = "0.0" if columna_p is None else f"COALESCE({columna_p}, 0)"
    aristas = pd.read_sql(
        f"SELECT id, source, target, capa, sintetico, {expr} AS p FROM enlaces_topo ORDER BY id", engine)
    claves = pd.read_sql(
        "SELECT id, nombre, vertice_id FROM nodos_clave WHERE incluir ORDER BY id", engine)
    engine.dispose()
    aristas = aristas[~aristas.capa.isin(sin_capas)].reset_index(drop=True)
    ids = np.unique(np.concatenate([aristas.source, aristas.target, claves.vertice_id]))
    indice = pd.Series(np.arange(len(ids)), index=ids)
    return {
        "aristas": aristas,
        "claves": claves,
        "n": len(ids),
        "src": indice[aristas.source].to_numpy(),
        "dst": indice[aristas.target].to_numpy(),
        "p": aristas.p.to_numpy(float),
        "clave_idx": indice[claves.vertice_id].to_numpy(),
    }


def etiquetas_claves(g, vivos):
    m = coo_matrix((np.ones(vivos.sum()), (g["src"][vivos], g["dst"][vivos])), shape=(g["n"], g["n"]))
    return connected_components(m, directed=False)[1][g["clave_idx"]]


def attr_de_etiquetas(etq):
    k = len(etq)
    _, cuenta = np.unique(etq, return_counts=True)
    return float((cuenta * (cuenta - 1)).sum() / (k * (k - 1)))


def sorteo(g, semilla, n_iter):
    rng = np.random.default_rng(semilla)
    for _ in range(n_iter):
        yield rng.random(len(g["p"])) >= g["p"]


def monte_carlo(g, n_iter=20000, semilla=42):
    k = len(g["clave_idx"])
    if not np.any(g["p"] > 0):
        n_iter = 1
    muestras = np.empty(n_iter)
    pares = np.zeros((k, k))
    caidas = np.zeros(len(g["p"]))
    for i, vivos in enumerate(sorteo(g, semilla, n_iter) if n_iter > 1 else [np.ones(len(g["p"]), bool)]):
        etq = etiquetas_claves(g, vivos)
        muestras[i] = attr_de_etiquetas(etq)
        pares += etq[:, None] == etq[None, :]
        caidas += ~vivos
    sd = float(muestras.std(ddof=1)) if n_iter > 1 else 0.0
    return {
        "attr": float(muestras.mean()),
        "sd": sd,
        "ic95": 1.96 * sd / np.sqrt(n_iter),
        "mediana": float(np.median(muestras)),
        "p05": float(np.percentile(muestras, 5)),
        "p_attr_1": float((muestras == 1).mean()),
        "n_iter": n_iter,
        "semilla": semilla,
        "muestras": muestras,
        "pares": pares / n_iter,
        "frec_caida": caidas / n_iter,
    }


def iteraciones_necesarias(sd, semiancho=0.005):
    return int(np.ceil((1.96 * sd / semiancho) ** 2))


def estado_representativo(g, r):
    objetivo = int(np.argmin(np.abs(r["muestras"] - r["attr"])))
    for i, vivos in enumerate(sorteo(g, r["semilla"], objetivo + 1)):
        if i == objetivo:
            return objetivo, vivos, etiquetas_claves(g, vivos)


def componentes_claves(g, etq):
    nombres = g["claves"].nombre.to_numpy()
    grupos = {}
    for nombre, e in zip(nombres, etq):
        grupos.setdefault(int(e), []).append(nombre)
    return sorted(grupos.values(), key=len, reverse=True)


def calcular(columna_p=None, n_iter=20000, semilla=42, dbname=None, sin_capas=()):
    g = cargar_grafo(columna_p, dbname, sin_capas)
    r = monte_carlo(g, n_iter, semilla)
    r.update(n_vertices=g["n"], n_aristas=len(g["p"]), n_claves=len(g["clave_idx"]))
    return g, r


def mostrar(titulo, g, r):
    k = r["n_claves"]
    print(f"\n=== {titulo} ===")
    print(f"Grafo: {r['n_vertices']} vertices, {r['n_aristas']} enlaces, {k} nodos clave, {k * (k - 1) // 2} pares")
    if r["n_iter"] == 1:
        etq = etiquetas_claves(g, np.ones(len(g["p"]), bool))
        print(f"Calculo exacto (todas las p = 0): ATTR = {r['attr']:.4f}")
        for grupo in componentes_claves(g, etq):
            print(f"  componente con {len(grupo)} nodos clave: {', '.join(grupo)}")
        return
    print(f"Monte Carlo: {r['n_iter']} iteraciones, semilla {r['semilla']}")
    print(f"ATTR = {r['attr']:.4f}  IC95 +/- {r['ic95']:.4f}  (desv. est. {r['sd']:.4f})")
    print(f"mediana {r['mediana']:.4f} | percentil 5 {r['p05']:.4f} | P(ATTR = 1) = {r['p_attr_1']:.4f}")
    print(f"iteraciones para IC95 de +/- 0.005: {iteraciones_necesarias(r['sd'])}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="ATTR de la red sobre los nodos clave")
    ap.add_argument("--col", choices=sorted(c for c in COLUMNAS_P if c), help="columna de probabilidad (omitir = en operacion)")
    ap.add_argument("--iter", type=int, default=20000)
    ap.add_argument("--semilla", type=int, default=42)
    a = ap.parse_args()
    g, r = calcular(a.col, a.iter, a.semilla)
    mostrar(f"ATTR con {a.col}" if a.col else "ATTR en operacion", g, r)
