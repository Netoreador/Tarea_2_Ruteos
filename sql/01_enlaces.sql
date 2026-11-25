DROP TABLE IF EXISTS enlaces CASCADE;

CREATE TABLE enlaces AS
SELECT (row_number() OVER (ORDER BY t.orden, ST_XMin(t.geom), ST_YMin(t.geom), ST_NPoints(t.geom), ST_AsText(t.geom)))::integer AS id,
       t.capa,
       t.capa <> 'fibra' AS sintetico,
       t.id_original,
       t.geom::geometry(LineString, 4326) AS geom
FROM (
    SELECT 1 AS orden, 'fibra' AS capa, id::text AS id_original, geom FROM fibra
    UNION ALL SELECT 2, 'postacion', id::text, geom FROM postacion
    UNION ALL SELECT 3, 'camino', id::text, geom FROM camino
    UNION ALL SELECT 4, 'ferry', id::text, geom FROM ferry
) t;

ALTER TABLE enlaces ADD PRIMARY KEY (id);
ALTER TABLE enlaces ADD COLUMN longitud_km double precision;
UPDATE enlaces SET longitud_km = ST_Length(geom::geography) / 1000;
CREATE INDEX enlaces_geom_idx ON enlaces USING gist (geom);

SELECT capa, sintetico, count(*) AS tramos, round(sum(longitud_km)) AS km
FROM enlaces GROUP BY capa, sintetico ORDER BY min(id);
