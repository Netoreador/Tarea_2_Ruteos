DROP FUNCTION IF EXISTS cortes_por_km(double precision, double precision);
DROP FUNCTION IF EXISTS pgv_worden2012(double precision);
DROP FUNCTION IF EXISTS mmi_allen2012(double precision, double precision);
DROP FUNCTION IF EXISTS param(text);
DROP TABLE IF EXISTS parametros_modelo CASCADE;
DROP TABLE IF EXISTS factor_capa CASCADE;

CREATE TABLE parametros_modelo (
    parametro text PRIMARY KEY,
    valor     double precision NOT NULL,
    unidad    text,
    fuente    text
);

INSERT INTO parametros_modelo VALUES
    ('M',       (SELECT magnitud FROM sismo),       'Mw',   'USGS, evento official20100227063411530_30'),
    ('H',       (SELECT profundidad_km FROM sismo), 'km',   'USGS, profundidad del hipocentro'),
    ('c0',      2.085,  '-',    'Allen, Wald y Worden (2012), version Rhypo, coeficientes de OpenQuake AllenEtAl2012Rhypo'),
    ('c1',      1.428,  '-',    'Allen, Wald y Worden (2012)'),
    ('c2',     -1.402,  '-',    'Allen, Wald y Worden (2012)'),
    ('c4',      0.078,  '-',    'Allen, Wald y Worden (2012), termino para R > 50 km'),
    ('m1',     -0.209,  'km',   'Allen, Wald y Worden (2012)'),
    ('m2',      2.042,  'km',   'Allen, Wald y Worden (2012)'),
    ('s1',      0.82,   'MMI',  'Allen, Wald y Worden (2012), desviacion estandar'),
    ('s2',      0.37,   'MMI',  'Allen, Wald y Worden (2012), desviacion estandar'),
    ('s3',      22.9,   'km',   'Allen, Wald y Worden (2012), desviacion estandar'),
    ('w_c1',    3.78,   '-',    'Worden et al. (2012), GMICE PGV, tramo bajo'),
    ('w_c2',    1.47,   '-',    'Worden et al. (2012), GMICE PGV, tramo bajo'),
    ('w_c3',    2.89,   '-',    'Worden et al. (2012), GMICE PGV, tramo alto'),
    ('w_c4',    3.16,   '-',    'Worden et al. (2012), GMICE PGV, tramo alto'),
    ('w_t2',    4.56,   'MMI',  'Worden et al. (2012), quiebre entre tramos'),
    ('hz_a',    0.0001, 'rep/km', 'Hazus 4.2, Ecuacion 8-1 (O''Rourke y Ayala 1993)'),
    ('hz_b',    2.25,   '-',    'Hazus 4.2, Ecuacion 8-1'),
    ('f_corte', 0.2,    '-',    'Hazus 4.2, seccion 8.1.4.2, 20 % de roturas por propagacion de ondas'),
    ('mmi_min', 6.0,    'MMI',  'Escala de Mercalli Modificada (USGS): el dano a estructuras empieza en VI'),
    ('dx_km',   1.0,    'km',   'Paso de integracion a lo largo del enlace (decision propia)');

CREATE TABLE factor_capa (
    capa      text PRIMARY KEY,
    montaje   text NOT NULL,
    k         double precision NOT NULL,
    k_fragil  double precision NOT NULL,
    criterio  text NOT NULL
);

INSERT INTO factor_capa VALUES
    ('fibra',     'aereo',     0.3, 1.0, 'Cable de fibra continuo y flexible: tuberia ductil de Hazus (0,3). Sensibilidad: soporte de postes fragil (1,0)'),
    ('postacion', 'aereo',     0.3, 1.0, 'Ruta con postes donde el cable iria colgado, mismo criterio que fibra'),
    ('camino',    'soterrado', 0.3, 0.3, 'Cable en ducto de HDPE, plastico clasificado como ductil por Hazus (0,3)'),
    ('empalme',   'soterrado', 0.3, 0.3, 'Enlace sintetico, se supone soterrado'),
    ('acceso',    'soterrado', 0.3, 0.3, 'Enlace sintetico urbano, se supone en ducto'),
    ('urbano',    'soterrado', 0.3, 0.3, 'Enlace sintetico urbano de Santiago, se supone en ducto'),
    ('ferry',     'maritimo',  0.0, 0.0, 'Sin cable terrestre que se dane por vibracion');

CREATE FUNCTION param(nombre text) RETURNS double precision
LANGUAGE sql STABLE AS $$
    SELECT valor FROM parametros_modelo WHERE parametro = nombre
$$;

CREATE FUNCTION mmi_allen2012(r_hipo_km double precision, n_sigma double precision DEFAULT 0)
RETURNS double precision
LANGUAGE sql STABLE AS $$
    SELECT param('c0') + param('c1') * param('M')
         + param('c2') * ln(sqrt(r_hipo_km ^ 2 + (param('m1') + param('m2') * exp(param('M') - 5)) ^ 2))
         + CASE WHEN r_hipo_km > 50 THEN param('c4') * ln(r_hipo_km / 50) ELSE 0 END
         + n_sigma * (param('s1') + param('s2') / (1 + (r_hipo_km / param('s3')) ^ 2))
$$;

CREATE FUNCTION pgv_worden2012(mmi double precision)
RETURNS double precision
LANGUAGE sql STABLE AS $$
    SELECT CASE WHEN mmi <= param('w_t2')
                THEN 10 ^ ((mmi - param('w_c1')) / param('w_c2'))
                ELSE 10 ^ ((mmi - param('w_c3')) / param('w_c4')) END
$$;

CREATE FUNCTION cortes_por_km(mmi double precision, k double precision)
RETURNS double precision
LANGUAGE sql STABLE AS $$
    SELECT CASE WHEN mmi < param('mmi_min') THEN 0
                ELSE param('f_corte') * k * param('hz_a') * pgv_worden2012(mmi) ^ param('hz_b') END
$$;

SELECT parametro, valor, unidad, fuente FROM parametros_modelo ORDER BY ctid;
SELECT * FROM factor_capa ORDER BY k DESC, capa;

SELECT r AS r_hipo_km,
       round(mmi_allen2012(r)::numeric, 2) AS mmi,
       round(pgv_worden2012(mmi_allen2012(r))::numeric, 1) AS pgv_cms,
       round(cortes_por_km(mmi_allen2012(r), 1.0)::numeric, 5) AS cortes_km_aereo,
       round(cortes_por_km(mmi_allen2012(r), 0.3)::numeric, 5) AS cortes_km_soterrado
FROM unnest(ARRAY[25, 50, 100, 200, 300, 400, 500, 600, 1000]::double precision[]) AS r;
