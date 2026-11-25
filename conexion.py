import os
from pathlib import Path

import psycopg2
from sqlalchemy import create_engine

RAIZ = Path(__file__).resolve().parent
SQL = RAIZ / "sql"
DATOS = RAIZ / "data"
SALIDA = RAIZ / "salida"

PARAMS = {
    "host": os.getenv("TI2_HOST", "localhost"),
    "port": int(os.getenv("TI2_PORT", "5440")),
    "user": os.getenv("TI2_USER", "postgres"),
    "password": os.getenv("TI2_PASSWORD", "postgres"),
    "dbname": os.getenv("TI2_DB", "yafun"),
}


def conectar(dbname=None):
    con = psycopg2.connect(**{**PARAMS, "dbname": dbname or PARAMS["dbname"]})
    con.autocommit = True
    return con


def motor(dbname=None):
    p = {**PARAMS, "dbname": dbname or PARAMS["dbname"]}
    return create_engine(
        f"postgresql+psycopg2://{p['user']}:{p['password']}@{p['host']}:{p['port']}/{p['dbname']}"
    )


def ejecutar_archivo(ruta, dbname=None):
    con = conectar(dbname)
    try:
        with con.cursor() as cur:
            cur.execute(Path(ruta).read_text(encoding="utf-8"))
        return [n.strip() for n in con.notices]
    finally:
        con.close()


def consulta(sql, params=None, dbname=None):
    con = conectar(dbname)
    try:
        with con.cursor() as cur:
            cur.execute(sql, params)
            columnas = [c.name for c in cur.description]
            return columnas, cur.fetchall()
    finally:
        con.close()
