DROP TABLE IF EXISTS nodos_clave;

CREATE TABLE nodos_clave (
    id       serial PRIMARY KEY,
    nombre   text NOT NULL,
    rol      text NOT NULL,      -- genera | intercambia | recibe
    incluir  boolean DEFAULT true,
    geom     geometry(Point, 4326)
);

INSERT INTO nodos_clave (nombre, rol, incluir, geom)
SELECT nombre, rol, incluir, ST_SetSRID(ST_MakePoint(lon, lat), 4326)
FROM (VALUES
    ('Santiago',      'genera+intercambia', true,  -70.6693, -33.4489),
    ('Valparaiso',    'intercambia',        true,  -71.6127, -33.0472),
    ('Arica',         'intercambia',        true,  -70.3126, -18.4783),
    ('Iquique',       'recibe',             true,  -70.1357, -20.2307),
    ('Antofagasta',   'recibe',             true,  -70.3975, -23.6509),
    ('Copiapo',       'recibe',             true,  -70.3323, -27.3668),
    ('La Serena',     'recibe',             true,  -71.2489, -29.9045),
    ('Rancagua',      'recibe',             true,  -70.7444, -34.1708),
    ('Talca',         'recibe',             true,  -71.6554, -35.4264),
    ('Chillan',       'recibe',             true,  -72.1034, -36.6063),
    ('Concepcion',    'recibe',             true,  -73.0444, -36.8201),
    ('Temuco',        'recibe',             true,  -72.5904, -38.7359),
    ('Valdivia',      'recibe',             true,  -73.2459, -39.8142),
    ('Puerto Montt',  'recibe',             true,  -72.9424, -41.4693),
    ('Coyhaique',     'recibe',             true,  -72.0685, -45.5712),
    ('Punta Arenas',  'recibe',             true,  -70.9171, -53.1638),
    ('Hanga Roa (Rapa Nui)', 'recibe',      false, -109.4333, -27.1500)
) AS v(nombre, rol, incluir, lon, lat);

CREATE INDEX nodos_clave_geom_idx ON nodos_clave USING gist (geom);

SELECT n.nombre, n.rol, n.incluir, round((e.d / 1000)::numeric, 2) AS km_a_la_red
FROM nodos_clave n
CROSS JOIN LATERAL (
    SELECT ST_Distance(n.geom::geography, ee.geom::geography) AS d
    FROM enlaces ee ORDER BY ee.geom <-> n.geom LIMIT 1
) e
ORDER BY n.id;