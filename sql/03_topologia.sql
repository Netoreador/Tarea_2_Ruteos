DROP VIEW  IF EXISTS enlaces_topo_cc;
DROP TABLE IF EXISTS enlaces_topo CASCADE;
DROP TABLE IF EXISTS enlaces_topo_vertices_pgr;

-- 1) Noding: parte cada tramo en los puntos donde se cruza con otro
CREATE TABLE enlaces_topo AS
SELECT (row_number() OVER ())::integer AS id,
       ST_SetSRID(d.geom, 4326)::geometry(LineString, 4326) AS geom
FROM (
    SELECT (ST_Dump(ST_Node(ST_Collect(geom)))).geom AS geom
    FROM enlaces
) d;

ALTER TABLE enlaces_topo ADD PRIMARY KEY (id);
ALTER TABLE enlaces_topo
    ADD COLUMN capa text,
    ADD COLUMN longitud_km double precision,
    ADD COLUMN source integer,
    ADD COLUMN target integer;
CREATE INDEX enlaces_topo_geom_idx ON enlaces_topo USING gist (geom);

-- 2) Recuperar la capa de origen (el noding la pierde): se usa el punto medio de cada tramo
UPDATE enlaces_topo t
SET capa = (
    SELECT e.capa FROM enlaces e
    WHERE ST_DWithin(e.geom, ST_LineInterpolatePoint(t.geom, 0.5), 0.000001)
    ORDER BY CASE e.capa WHEN 'fibra' THEN 1 WHEN 'postacion' THEN 2
                         WHEN 'camino' THEN 3 ELSE 4 END
    LIMIT 1
);
UPDATE enlaces_topo SET capa = 'sin_capa' WHERE capa IS NULL;
UPDATE enlaces_topo SET longitud_km = ST_Length(geom::geography) / 1000;

-- 3) Topologia: asigna source/target y crea la tabla de vertices.
--    Tolerancia 0.001 grados (~100 m): extremos mas cercanos se funden en un vertice.
SELECT pgr_createTopology('enlaces_topo', 0.001, 'geom', 'id', 'source', 'target', clean := true);

CREATE INDEX IF NOT EXISTS enlaces_topo_vert_geom_idx
    ON enlaces_topo_vertices_pgr USING gist (the_geom);

-- Vista con el formato que pide pgRouting (id, source, target, cost, reverse_cost)
CREATE VIEW enlaces_topo_cc AS
SELECT id, source, target, longitud_km AS cost, longitud_km AS reverse_cost
FROM enlaces_topo;

-- 4) Pegar cada nodo clave a su vertice mas cercano
ALTER TABLE nodos_clave
    ADD COLUMN IF NOT EXISTS vertice_id bigint,
    ADD COLUMN IF NOT EXISTS dist_vertice_km double precision;

UPDATE nodos_clave n
SET vertice_id = (SELECT v.id FROM enlaces_topo_vertices_pgr v
                  ORDER BY v.the_geom <-> n.geom LIMIT 1);

UPDATE nodos_clave n
SET dist_vertice_km = ST_Distance(n.geom::geography, v.the_geom::geography) / 1000
FROM enlaces_topo_vertices_pgr v
WHERE v.id = n.vertice_id;

-- 5) Reportes
SELECT count(*) AS tramos,
       (SELECT count(*) FROM enlaces_topo_vertices_pgr) AS vertices
FROM enlaces_topo;

SELECT capa, count(*) AS tramos, round(sum(longitud_km)) AS km
FROM enlaces_topo GROUP BY capa ORDER BY capa;

SELECT count(DISTINCT component) AS componentes
FROM pgr_connectedComponents('SELECT id, source, target, cost, reverse_cost FROM enlaces_topo_cc');

SELECT c.component, n.nombre, n.rol, round(n.dist_vertice_km::numeric, 2) AS km_al_vertice
FROM nodos_clave n
JOIN pgr_connectedComponents('SELECT id, source, target, cost, reverse_cost FROM enlaces_topo_cc') c
  ON c.node = n.vertice_id
ORDER BY c.component, n.id;