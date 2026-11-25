DROP TABLE IF EXISTS empalmes;

CREATE TABLE empalmes (
    orden       integer PRIMARY KEY,
    motivo      text,
    vertice_a   integer,
    vertice_b   integer,
    longitud_km double precision,
    geom        geometry(LineString, 4326)
);

DO $$
DECLARE
    v_a    integer;
    v_b    integer;
    dist   double precision;
    motivo text;
    n      integer := 0;
BEGIN
    LOOP
        CREATE TEMP TABLE cc AS
        SELECT node, component FROM pgr_connectedComponents(
            'SELECT id, source, target, cost, reverse_cost FROM enlaces_topo_cc');
        CREATE TEMP TABLE vv AS
        SELECT v.id, v.the_geom, cc.component
        FROM enlaces_topo_vertices_pgr v JOIN cc ON cc.node = v.id;
        CREATE INDEX ON vv USING gist (the_geom);

        SELECT a.id, b.id, ST_Distance(a.the_geom::geography, b.the_geom::geography) / 1000
        INTO v_a, v_b, dist
        FROM vv a
        CROSS JOIN LATERAL (
            SELECT vv.id, vv.the_geom FROM vv
            WHERE vv.component <> a.component
            ORDER BY vv.the_geom <-> a.the_geom LIMIT 3
        ) b
        ORDER BY 3, a.id, b.id
        LIMIT 1;
        motivo := 'hueco <= 3 km';

        IF dist IS NULL OR dist > 3 THEN
            v_a := NULL;
            SELECT a.id, b.id, ST_Distance(a.the_geom::geography, b.the_geom::geography) / 1000
            INTO v_a, v_b, dist
            FROM vv a
            CROSS JOIN LATERAL (
                SELECT vv.id, vv.the_geom FROM vv
                WHERE vv.component IN (SELECT c.component FROM nodos_clave k JOIN cc c ON c.node = k.vertice_id
                                       WHERE k.incluir)
                  AND vv.component <> a.component
                ORDER BY vv.the_geom <-> a.the_geom LIMIT 3
            ) b
            WHERE a.component = (SELECT c.component FROM nodos_clave k JOIN cc c ON c.node = k.vertice_id
                                 WHERE k.nombre = 'Santiago')
            ORDER BY 3, a.id, b.id
            LIMIT 1;
            motivo := 'union de nodos clave';
        END IF;

        DROP TABLE cc, vv;
        EXIT WHEN v_a IS NULL;
        n := n + 1;

        INSERT INTO empalmes
        SELECT n, motivo, v_a, v_b, dist, ST_MakeLine(a.the_geom, b.the_geom)
        FROM enlaces_topo_vertices_pgr a, enlaces_topo_vertices_pgr b
        WHERE a.id = v_a AND b.id = v_b;

        INSERT INTO enlaces_topo (id, geom, capa, sintetico, longitud_km, source, target)
        SELECT (SELECT max(id) + 1 FROM enlaces_topo), geom, 'empalme', true, longitud_km, vertice_a, vertice_b
        FROM empalmes WHERE orden = n;
    END LOOP;
END $$;

ALTER TABLE nodos_clave ADD COLUMN IF NOT EXISTS vertice_red bigint;
UPDATE nodos_clave SET vertice_red = vertice_id;

INSERT INTO enlaces_topo_vertices_pgr (id, the_geom)
SELECT (SELECT max(id) FROM enlaces_topo_vertices_pgr) + row_number() OVER (ORDER BY n.id), n.geom
FROM nodos_clave n WHERE n.incluir;

UPDATE nodos_clave n
SET vertice_id = (SELECT max(v.id) FROM enlaces_topo_vertices_pgr v WHERE ST_Equals(v.the_geom, n.geom))
WHERE n.incluir;

INSERT INTO enlaces_topo (id, geom, capa, sintetico, longitud_km, source, target)
SELECT (SELECT max(id) FROM enlaces_topo) + row_number() OVER (ORDER BY n.id),
       ST_MakeLine(n.geom, v.the_geom), 'acceso', true,
       ST_Distance(n.geom::geography, v.the_geom::geography) / 1000,
       n.vertice_id, n.vertice_red
FROM nodos_clave n
JOIN enlaces_topo_vertices_pgr v ON v.id = n.vertice_red
WHERE n.incluir;

WITH grado AS (
    SELECT v, count(*) AS g
    FROM (SELECT source AS v FROM enlaces_topo WHERE NOT capa IN ('acceso', 'urbano')
          UNION ALL SELECT target FROM enlaces_topo WHERE NOT capa IN ('acceso', 'urbano')) z
    GROUP BY v
),
extremos AS (
    SELECT n.id AS nodo, n.vertice_id, v.id AS vertice, v.the_geom, n.geom
    FROM nodos_clave n
    JOIN enlaces_topo_vertices_pgr v ON ST_DWithin(v.the_geom::geography, n.geom::geography, 20000)
    JOIN grado g ON g.v = v.id AND g.g = 1
    WHERE n.incluir AND n.dist_vertice_km > 5 AND v.id <> n.vertice_red
)
INSERT INTO enlaces_topo (id, geom, capa, sintetico, longitud_km, source, target)
SELECT (SELECT max(id) FROM enlaces_topo) + row_number() OVER (ORDER BY nodo, vertice),
       ST_MakeLine(geom, the_geom), 'urbano', true,
       ST_Distance(geom::geography, the_geom::geography) / 1000,
       vertice_id, vertice
FROM extremos;


SELECT orden, motivo, round(longitud_km::numeric, 2) AS km,
       round(ST_Y(ST_StartPoint(geom))::numeric, 4) AS lat_a, round(ST_X(ST_StartPoint(geom))::numeric, 4) AS lon_a,
       round(ST_Y(ST_EndPoint(geom))::numeric, 4) AS lat_b, round(ST_X(ST_EndPoint(geom))::numeric, 4) AS lon_b
FROM empalmes ORDER BY orden;

SELECT n.nombre, e.capa, e.target AS vertice_red, round(e.longitud_km::numeric, 2) AS km
FROM nodos_clave n JOIN enlaces_topo e ON e.capa IN ('acceso', 'urbano') AND e.source = n.vertice_id
ORDER BY n.id, e.capa, e.longitud_km;

SELECT capa, sintetico, count(*) AS tramos, round(sum(longitud_km)::numeric, 1) AS km
FROM enlaces_topo GROUP BY capa, sintetico ORDER BY sintetico, capa;

SELECT count(DISTINCT component) AS componentes
FROM pgr_connectedComponents('SELECT id, source, target, cost, reverse_cost FROM enlaces_topo_cc');

SELECT c.component, count(*) AS nodos_clave, string_agg(n.nombre, ', ' ORDER BY n.id) AS nombres
FROM nodos_clave n
JOIN pgr_connectedComponents('SELECT id, source, target, cost, reverse_cost FROM enlaces_topo_cc') c
  ON c.node = n.vertice_id
GROUP BY c.component ORDER BY nodos_clave DESC;
