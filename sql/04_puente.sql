-- Cierra el hueco entre el norte (componente de Santiago) y el sur (componente de Rancagua)
DELETE FROM enlaces_topo WHERE capa = 'puente';   -- hace el script repetible
DROP TABLE IF EXISTS puentes;

CREATE TABLE puentes AS
WITH cc AS (
    SELECT node, component
    FROM pgr_connectedComponents('SELECT id, source, target, cost, reverse_cost FROM enlaces_topo_cc')
),
a AS (
    SELECT v.id, v.the_geom
    FROM enlaces_topo_vertices_pgr v
    JOIN cc ON cc.node = v.id
    WHERE cc.component = (SELECT c.component FROM nodos_clave n
                          JOIN cc c ON c.node = n.vertice_id WHERE n.nombre = 'Santiago')
),
b AS (
    SELECT v.id, v.the_geom
    FROM enlaces_topo_vertices_pgr v
    JOIN cc ON cc.node = v.id
    WHERE cc.component = (SELECT c.component FROM nodos_clave n
                          JOIN cc c ON c.node = n.vertice_id WHERE n.nombre = 'Rancagua')
)
SELECT a.id AS vertice_a, b.id AS vertice_b,
       'norte (Santiago) <-> sur (Rancagua)'::text AS descripcion,
       ST_MakeLine(a.the_geom, b.the_geom) AS geom,
       ST_Distance(a.the_geom::geography, b.the_geom::geography) / 1000 AS longitud_km
FROM a, b
ORDER BY ST_Distance(a.the_geom, b.the_geom)
LIMIT 1;

INSERT INTO enlaces_topo (id, geom, capa, longitud_km, source, target)
SELECT (SELECT max(id) + 1 FROM enlaces_topo), geom, 'puente', longitud_km, vertice_a, vertice_b
FROM puentes;

-- Donde quedo el puente (revisalo en un mapa)
SELECT vertice_a, vertice_b, round(longitud_km::numeric, 2) AS km,
       round(ST_X(ST_StartPoint(geom))::numeric, 4) AS lon_a,
       round(ST_Y(ST_StartPoint(geom))::numeric, 4) AS lat_a,
       round(ST_X(ST_EndPoint(geom))::numeric, 4)   AS lon_b,
       round(ST_Y(ST_EndPoint(geom))::numeric, 4)   AS lat_b
FROM puentes;

-- Verificacion
SELECT count(DISTINCT component) AS componentes
FROM pgr_connectedComponents('SELECT id, source, target, cost, reverse_cost FROM enlaces_topo_cc');

SELECT c.component, n.nombre, n.incluir
FROM nodos_clave n
JOIN pgr_connectedComponents('SELECT id, source, target, cost, reverse_cost FROM enlaces_topo_cc') c
  ON c.node = n.vertice_id
ORDER BY c.component, n.id;