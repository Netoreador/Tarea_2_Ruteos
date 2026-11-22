DROP TABLE IF EXISTS enlaces CASCADE;

CREATE TABLE enlaces AS
SELECT row_number() OVER () AS id, t.capa, t.id_original, t.geom
FROM (
    SELECT 'fibra'     AS capa, id::text AS id_original, geom FROM fibra
    UNION ALL SELECT 'postacion', id::text, geom FROM postacion
    UNION ALL SELECT 'camino',    id::text, geom FROM camino
    UNION ALL SELECT 'ferry',     id::text, geom FROM ferry
) t;

ALTER TABLE enlaces ADD PRIMARY KEY (id);
ALTER TABLE enlaces ADD COLUMN longitud_km double precision;
UPDATE enlaces SET longitud_km = ST_Length(geom::geography) / 1000;
CREATE INDEX enlaces_geom_idx ON enlaces USING gist (geom);

SELECT capa, count(*) AS tramos, round(sum(longitud_km)) AS km
FROM enlaces GROUP BY capa ORDER BY capa;