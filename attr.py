"""attr.py - ATTR (All-Terminal Reliability) de la red sobre los nodos clave.

Dos variantes:
  * ATTR_pares    : fraccion de pares de nodos clave que siguen conectados
                    (definicion del paper de Boettcher et al., ec. 8).
  * ATTR_estricto : probabilidad de que TODOS los nodos clave sigan en una
                    misma componente conexa (lo que pide el enunciado).

Cada enlace (tramo de enlaces_topo) falla de forma independiente con
probabilidad p. Sin fallas (p = 0) el calculo es determinista.
"""
import argparse

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

DB_URL = "postgresql+psycopg2://postgres:postgres@localhost:5432/yafun"


# --------------------------------------------------------------------------
# Carga desde la base de datos
# --------------------------------------------------------------------------
def cargar_grafo(db_url=DB_URL, col_p=None):
    """Lee aristas y nodos clave desde PostGIS.

    col_p: nombre de la columna de enlaces_topo con la probabilidad de falla.
           None -> red en operacion (p = 0 en todos los enlaces).
    """
    import pandas as pd
    from sqlalchemy import create_engine, inspect

    engine = create_engine(db_url)
    columnas = [c["name"] for c in inspect(engine).get_columns("enlaces_topo")]
    if col_p is None:
        expr = "0.0"
    elif col_p in columnas:
        expr = f"COALESCE({col_p}, 0.0)"
    else:
        raise ValueError(f"La columna '{col_p}' no existe en enlaces_topo")

    aristas = pd.read_sql(
        f"SELECT id, source, target, longitud_km, capa, {expr} AS p "
        "FROM enlaces_topo ORDER BY id", engine)
    claves = pd.read_sql(
        "SELECT nombre, rol, vertice_id FROM nodos_clave WHERE incluir ORDER BY id",
        engine)

    # ids de vertice -> indices 0..n-1 (necesario para la matriz dispersa)
    ids = np.unique(np.concatenate([aristas.source.values, aristas.target.values]))
    indice = {v: i for i, v in enumerate(ids)}
    src = aristas.source.map(indice).to_numpy()
    dst = aristas.target.map(indice).to_numpy()
    clave_idx = claves.vertice_id.map(indice).to_numpy()
    return {
        "aristas": aristas, "claves": claves, "n": len(ids),
        "src": src, "dst": dst, "p": aristas.p.to_numpy(float),
        "clave_idx": clave_idx,
    }


# --------------------------------------------------------------------------
# Nucleo del calculo (no depende de la base de datos)
# --------------------------------------------------------------------------
def _evaluar(src, dst, vivos, n, clave_idx):
    """Devuelve (fraccion de pares conectados, todos conectados?) para un estado."""
    m = coo_matrix((np.ones(vivos.sum()), (src[vivos], dst[vivos])), shape=(n, n))
    _, etiqueta = connected_components(m, directed=False)
    _, cuenta = np.unique(etiqueta[clave_idx], return_counts=True)
    k = len(clave_idx)
    pares = (cuenta * (cuenta - 1) / 2).sum() / (k * (k - 1) / 2)
    return pares, len(cuenta) == 1


def monte_carlo(src, dst, p, clave_idx, n, n_iter=10000, seed=42):
    """ATTR por simulacion Monte Carlo. Con p = 0 en todo, evalua una sola vez."""
    if not np.any(p > 0):
        pares, todos = _evaluar(src, dst, np.ones(len(src), bool), n, clave_idx)
        return {"attr_pares": pares, "attr_estricto": float(todos),
                "ic_pares": 0.0, "ic_estricto": 0.0, "n_iter": 1}

    rng = np.random.default_rng(seed)
    pares = np.empty(n_iter)
    todos = np.empty(n_iter)
    for i in range(n_iter):
        vivos = rng.random(len(p)) >= p          # el enlace sobrevive si no falla
        pares[i], todos[i] = _evaluar(src, dst, vivos, n, clave_idx)

    def ic95(x):                                  # intervalo de confianza 95 %
        return 1.96 * x.std(ddof=1) / np.sqrt(len(x))

    return {"attr_pares": pares.mean(), "attr_estricto": todos.mean(),
            "ic_pares": ic95(pares), "ic_estricto": ic95(todos), "n_iter": n_iter}


def calcular_attr(col_p=None, p_uniforme=None, n_iter=10000, seed=42,
                  db_url=DB_URL):
    """Carga el grafo y calcula el ATTR. p_uniforme sirve solo para pruebas."""
    g = cargar_grafo(db_url, col_p)
    p = g["p"] if p_uniforme is None else np.full(len(g["p"]), p_uniforme)
    r = monte_carlo(g["src"], g["dst"], p, g["clave_idx"], g["n"], n_iter, seed)
    r.update(n_vertices=g["n"], n_aristas=len(g["src"]), n_claves=len(g["claves"]))
    return r


def mostrar(r, titulo):
    print(f"\n=== {titulo} ===")
    print(f"Grafo: {r['n_vertices']} vertices, {r['n_aristas']} aristas, "
          f"{r['n_claves']} nodos clave | iteraciones: {r['n_iter']}")
    print(f"ATTR (pares, paper)  : {r['attr_pares']:.4f}  (+/- {r['ic_pares']:.4f})")
    print(f"ATTR (estricto)      : {r['attr_estricto']:.4f}  (+/- {r['ic_estricto']:.4f})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="ATTR de la red sobre los nodos clave")
    ap.add_argument("--col", help="columna de enlaces_topo con p de falla "
                                  "(omitir = red en operacion)")
    ap.add_argument("--p-uniforme", type=float,
                    help="p igual para todos los enlaces (solo para probar)")
    ap.add_argument("--iter", type=int, default=10000, help="iteraciones Monte Carlo")
    a = ap.parse_args()

    if a.p_uniforme is not None:
        titulo = f"PRUEBA con p uniforme = {a.p_uniforme}"
    elif a.col:
        titulo = f"Con fallas (columna {a.col})"
    else:
        titulo = "Red en operacion (sin fallas)"
    mostrar(calcular_attr(a.col, a.p_uniforme, a.iter), titulo)