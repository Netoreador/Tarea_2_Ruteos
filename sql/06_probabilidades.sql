ALTER TABLE enlaces_topo
    ADD COLUMN IF NOT EXISTS dist_epicentro_km     double precision,
    ADD COLUMN IF NOT EXISTS mmi_max               double precision,
    ADD COLUMN IF NOT EXISTS pgv_max_cms           double precision,
    ADD COLUMN IF NOT EXISTS cortes_esperados      double precision,
    ADD COLUMN IF NOT EXISTS p_falla_menos_sigma   double precision,
    ADD COLUMN IF NOT EXISTS p_falla_mas_sigma     double precision,
    ADD COLUMN IF NOT EXISTS p_falla_aereo_fragil  double precision,
    ADD COLUMN IF NOT EXISTS p_falla_shakemap      double precision;

DROP TABLE IF EXISTS puntos_evaluacion;

CREATE TABLE puntos_evaluacion AS
WITH epi AS (SELECT geom::geography AS g FROM sismo LIMIT 1),
pts AS (
    SELECT e.id AS enlace_id, e.capa, s.n, i,
           e.longitud_km / s.n AS largo_km,
           CASE WHEN e.longitud_km > 0
                THEN ST_LineInterpolatePoint(e.geom::geography, (i + 0.5) / s.n)
                ELSE ST_StartPoint(e.geom)::geography END AS punto
    FROM enlaces_topo e
    CROSS JOIN LATERAL (SELECT greatest(1, ceil(e.longitud_km / param('dx_km')))::integer AS n) s
    CROSS JOIN LATERAL generate_series(0, s.n - 1) AS i
)
SELECT p.enlace_id, p.i, p.largo_km, p.punto,
       ST_Distance(p.punto, epi.g) / 1000 AS d_epi_km,
       sqrt((ST_Distance(p.punto, epi.g) / 1000) ^ 2 + param('H') ^ 2) AS r_hipo_km,
       f.k, f.k_fragil
FROM pts p
CROSS JOIN epi
JOIN factor_capa f ON f.capa = p.capa;

ALTER TABLE puntos_evaluacion
    ADD COLUMN mmi double precision,
    ADD COLUMN mmi_menos double precision,
    ADD COLUMN mmi_mas double precision,
    ADD COLUMN pgv_cms double precision,
    ADD COLUMN mmi_shakemap double precision;

UPDATE puntos_evaluacion
SET mmi       = mmi_allen2012(r_hipo_km),
    mmi_menos = mmi_allen2012(r_hipo_km, -1),
    mmi_mas   = mmi_allen2012(r_hipo_km, 1),
    pgv_cms   = pgv_worden2012(mmi_allen2012(r_hipo_km));

UPDATE puntos_evaluacion p
SET mmi_shakemap = COALESCE((
    SELECT g.mmi FROM sismo_mmi_grilla g
    WHERE ST_DWithin(g.geom, p.punto::geometry, 0.15)
    ORDER BY g.geom <-> p.punto::geometry LIMIT 1), 0);

WITH agg AS (
    SELECT enlace_id,
           max(mmi) AS mmi_max,
           max(pgv_cms) AS pgv_max,
           sum(cortes_por_km(mmi, k) * largo_km) AS lam,
           sum(cortes_por_km(mmi_menos, k) * largo_km) AS lam_menos,
           sum(cortes_por_km(mmi_mas, k) * largo_km) AS lam_mas,
           sum(cortes_por_km(mmi, k_fragil) * largo_km) AS lam_fragil,
           sum(cortes_por_km(mmi_shakemap, k) * largo_km) AS lam_shakemap
    FROM puntos_evaluacion
    GROUP BY enlace_id
)
UPDATE enlaces_topo e
SET dist_epicentro_km    = ST_Distance(e.geom::geography, (SELECT geom::geography FROM sismo LIMIT 1)) / 1000,
    mmi_max              = a.mmi_max,
    pgv_max_cms          = a.pgv_max,
    cortes_esperados     = a.lam,
    p_falla              = 1 - exp(-a.lam),
    p_falla_menos_sigma  = 1 - exp(-a.lam_menos),
    p_falla_mas_sigma    = 1 - exp(-a.lam_mas),
    p_falla_aereo_fragil = 1 - exp(-a.lam_fragil),
    p_falla_shakemap     = 1 - exp(-a.lam_shakemap)
FROM agg a
WHERE a.enlace_id = e.id;

DROP TABLE IF EXISTS validacion_shakemap;
CREATE TABLE validacion_shakemap AS
WITH epi AS (SELECT geom::geography AS g FROM sismo LIMIT 1),
v AS (
    SELECT s.mmi AS mmi_shakemap,
           mmi_allen2012(sqrt((ST_Distance((d).geom::geography, epi.g) / 1000) ^ 2 + param('H') ^ 2)) AS mmi_modelo,
           ST_Distance((d).geom::geography, epi.g) / 1000 AS d_epi_km
    FROM sismo_mmi_shakemap s
    CROSS JOIN LATERAL ST_DumpPoints(s.geom) AS d
    CROSS JOIN epi
)
SELECT mmi_shakemap,
       count(*) AS puntos,
       round(avg(d_epi_km)::numeric, 0) AS d_epi_media_km,
       round(avg(mmi_modelo)::numeric, 2) AS mmi_modelo_media,
       round(avg(mmi_shakemap - mmi_modelo)::numeric, 2) AS residuo_medio
FROM v
WHERE mmi_shakemap >= 4
GROUP BY mmi_shakemap
ORDER BY mmi_shakemap DESC;

SELECT count(*) AS enlaces,
       count(*) FILTER (WHERE p_falla > 0) AS con_p_mayor_0,
       round(min(p_falla)::numeric, 6) AS p_min,
       round(max(p_falla)::numeric, 4) AS p_max,
       round(avg(p_falla)::numeric, 4) AS p_media,
       round(sum(cortes_esperados)::numeric, 1) AS cortes_esperados_red,
       bool_and(p_falla BETWEEN 0 AND 1) AS todas_en_0_1
FROM enlaces_topo;

SELECT id, capa, round(longitud_km::numeric, 2) AS km, round(dist_epicentro_km::numeric, 1) AS d_epi_km,
       round(mmi_max::numeric, 2) AS mmi, round(pgv_max_cms::numeric, 1) AS pgv_cms,
       round(p_falla::numeric, 4) AS p_falla
FROM enlaces_topo ORDER BY p_falla DESC, id LIMIT 10;

SELECT id, capa, round(longitud_km::numeric, 2) AS km, round(dist_epicentro_km::numeric, 1) AS d_epi_km,
       round(mmi_max::numeric, 2) AS mmi, round(p_falla::numeric, 8) AS p_falla
FROM enlaces_topo WHERE p_falla > 0 ORDER BY p_falla, id LIMIT 5;

SELECT * FROM validacion_shakemap;
