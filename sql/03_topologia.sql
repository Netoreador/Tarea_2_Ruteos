DROP VIEW  IF EXISTS enlaces_topo_cc;
DROP TABLE IF EXISTS enlaces_topo CASCADE;
DROP TABLE IF EXISTS enlaces_topo_vertices_pgr;
DROP TABLE IF EXISTS lazos_eliminados;

CREATE TABLE enlaces_topo AS
SELECT (row_number() OVER (ORDER BY ST_XMin(d.geom), ST_YMin(d.geom), ST_NPoints(d.geom), ST_AsText(d.geom)))::integer AS id,
       d.geom::geometry(LineString, 4326) AS geom
FROM (
    SELECT (ST_Dump(ST_Node(ST_SnapToGrid(ST_Collect(s.geom), 0.0000001)))).geom AS geom
    FROM (
        SELECT COALESCE(
                   ST_Snap(e.geom,
                           (SELECT ST_Collect(o.geom) FROM enlaces o
                            WHERE o.id <> e.id AND ST_DWithin(o.geom, e.geom, 0.0001)),
                           0.0001),
                   e.geom) AS geom
        FROM enlaces e
    ) s
) d
WHERE ST_GeometryType(d.geom) = 'ST_LineString';

ALTER TABLE enlaces_topo ADD PRIMARY KEY (id);
ALTER TABLE enlaces_topo
    ADD COLUMN capa        text,
    ADD COLUMN sintetico   boolean,
    ADD COLUMN longitud_km double precision,
    ADD COLUMN p_falla     double precision NOT NULL DEFAULT 0 CHECK (p_falla BETWEEN 0 AND 1),
    ADD COLUMN source      integer,
    ADD COLUMN target      integer;
CREATE INDEX enlaces_topo_geom_idx ON enlaces_topo USING gist (geom);

UPDATE enlaces_topo t
SET capa = (
    SELECT e.capa FROM enlaces e
    WHERE ST_DWithin(e.geom, ST_LineInterpolatePoint(t.geom, 0.5), 0.0001)
    ORDER BY ST_Distance(e.geom, ST_LineInterpolatePoint(t.geom, 0.5)) > 0.000001,
             CASE e.capa WHEN 'fibra' THEN 1 WHEN 'postacion' THEN 2 WHEN 'camino' THEN 3 ELSE 4 END,
             ST_Distance(e.geom, ST_LineInterpolatePoint(t.geom, 0.5))
    LIMIT 1
);
UPDATE enlaces_topo SET capa = 'camino' WHERE capa IS NULL;
UPDATE enlaces_topo SET sintetico = capa <> 'fibra',
                        longitud_km = ST_Length(geom::geography) / 1000;

SELECT pgr_createTopology('enlaces_topo', 0.001, 'geom', 'id', 'source', 'target', clean := true);

CREATE TABLE lazos_eliminados AS
SELECT id, capa, longitud_km, geom FROM enlaces_topo WHERE source = target;
DELETE FROM enlaces_topo WHERE source = target;

CREATE INDEX IF NOT EXISTS enlaces_topo_vert_geom_idx
    ON enlaces_topo_vertices_pgr USING gist (the_geom);

CREATE VIEW enlaces_topo_cc AS
SELECT id, source, target, longitud_km AS cost, longitud_km AS reverse_cost
FROM enlaces_topo;

ALTER TABLE nodos_clave
    ADD COLUMN IF NOT EXISTS vertice_id bigint,
    ADD COLUMN IF NOT EXISTS dist_vertice_km double precision;

UPDATE nodos_clave n
SET vertice_id = (
    SELECT v.id FROM enlaces_topo_vertices_pgr v
    WHERE EXISTS (SELECT 1 FROM enlaces_topo e WHERE e.source = v.id OR e.target = v.id)
    ORDER BY v.the_geom <-> n.geom LIMIT 1
);

UPDATE nodos_clave n
SET dist_vertice_km = ST_Distance(n.geom::geography, v.the_geom::geography) / 1000
FROM enlaces_topo_vertices_pgr v
WHERE v.id = n.vertice_id;

SELECT (SELECT count(*) FROM enlaces_topo) AS tramos,
       (SELECT count(*) FROM enlaces_topo_vertices_pgr) AS vertices,
       (SELECT count(*) FROM lazos_eliminados) AS lazos_eliminados,
       (SELECT count(*) FROM enlaces_topo WHERE p_falla = 0) AS tramos_con_p_cero;

SELECT capa, sintetico, count(*) AS tramos, round(sum(longitud_km)) AS km
FROM enlaces_topo GROUP BY capa, sintetico ORDER BY sintetico, capa;

SELECT count(DISTINCT component) AS componentes
FROM pgr_connectedComponents('SELECT id, source, target, cost, reverse_cost FROM enlaces_topo_cc');

SELECT c.component, n.nombre, n.vertice_id, round(n.dist_vertice_km::numeric, 2) AS km_al_vertice
FROM nodos_clave n
JOIN pgr_connectedComponents('SELECT id, source, target, cost, reverse_cost FROM enlaces_topo_cc') c
  ON c.node = n.vertice_id
ORDER BY c.component, n.id;
