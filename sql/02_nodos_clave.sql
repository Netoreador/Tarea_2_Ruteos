DROP TABLE IF EXISTS nodos_clave CASCADE;

CREATE TABLE nodos_clave (
    id              integer PRIMARY KEY,
    nombre          text NOT NULL,
    region          text NOT NULL,
    genera          boolean NOT NULL,
    intercambia     boolean NOT NULL,
    recibe          boolean NOT NULL,
    infraestructura text NOT NULL,
    incluir         boolean NOT NULL DEFAULT true,
    geom            geometry(Point, 4326) NOT NULL
);

INSERT INTO nodos_clave (id, nombre, region, genera, intercambia, recibe, infraestructura, incluir, geom)
SELECT id, nombre, region, g, i, r, infra, incluir, ST_SetSRID(ST_MakePoint(lon, lat), 4326)
FROM (VALUES
    (1,  'Santiago',     'Metropolitana', true,  true,  true,  'IXP PIT Chile y NAP Chile, data centers, capital nacional', true, -70.6693, -33.4489),
    (2,  'Quilicura',    'Metropolitana', true,  false, false, 'Campus de data centers (Google, 2015) en la periferia norte de Santiago', true, -70.7290, -33.3600),
    (3,  'Valparaíso',   'Valparaíso',    false, true,  true,  'Aterrizaje de Curie, SAm-1, SAC, SPCS/Mistral y Prat', true, -71.6127, -33.0472),
    (4,  'Arica',        'Arica y Parinacota', false, true, true, 'Aterrizaje de SAm-1, SPCS/Mistral y Prat', true, -70.3126, -18.4783),
    (5,  'Iquique',      'Tarapacá',      false, false, true,  'Capital regional, aterrizaje del cable doméstico Prat', true, -70.1357, -20.2307),
    (6,  'Antofagasta',  'Antofagasta',   false, false, true,  'Capital regional, aterrizaje del cable doméstico Prat', true, -70.3975, -23.6509),
    (7,  'Copiapó',      'Atacama',       false, false, true,  'Capital regional', true, -70.3323, -27.3668),
    (8,  'La Serena',    'Coquimbo',      false, false, true,  'Capital regional, aterrizaje del cable doméstico Prat', true, -71.2489, -29.9045),
    (9,  'Rancagua',     'O''Higgins',      false, false, true,  'Capital regional', true, -70.7444, -34.1708),
    (10, 'Talca',        'Maule',         false, false, true,  'Capital regional', true, -71.6554, -35.4264),
    (11, 'Chillán',      'Ñuble',         false, false, true,  'Capital regional', true, -72.1034, -36.6063),
    (12, 'Concepción',   'Biobío',        false, false, true,  'Capital regional, nodo troncal del sur, Prat aterriza en San Pedro de la Paz', true, -73.0444, -36.8201),
    (13, 'Temuco',       'Araucanía',     false, false, true,  'Capital regional', true, -72.5904, -38.7359),
    (14, 'Valdivia',     'Los Ríos',      false, false, true,  'Capital regional', true, -73.2459, -39.8142),
    (15, 'Puerto Montt', 'Los Lagos',     false, true,  true,  'Aterrizaje de Fibra Óptica Austral y Prat', true, -72.9424, -41.4693),
    (16, 'Coyhaique',    'Aysén',         false, false, true,  'Capital regional', true, -72.0685, -45.5712),
    (17, 'Punta Arenas', 'Magallanes',    false, true,  true,  'Aterrizaje de Fibra Óptica Austral', true, -70.9171, -53.1638),
    (18, 'Hanga Roa',    'Valparaíso (Rapa Nui)', false, false, true, 'Sin enlace con el continente en los datos', false, -109.4333, -27.1500)
) AS v(id, nombre, region, g, i, r, infra, incluir, lon, lat);

CREATE INDEX nodos_clave_geom_idx ON nodos_clave USING gist (geom);

SELECT n.id, n.nombre,
       concat_ws(', ', CASE WHEN genera THEN 'genera' END, CASE WHEN intercambia THEN 'intercambia' END,
                 CASE WHEN recibe THEN 'recibe' END) AS rol,
       n.incluir,
       round(ST_Y(n.geom)::numeric, 4) AS lat, round(ST_X(n.geom)::numeric, 4) AS lon,
       round((e.d / 1000)::numeric, 2) AS km_a_la_linea_mas_cercana
FROM nodos_clave n
CROSS JOIN LATERAL (
    SELECT ST_Distance(n.geom::geography, ee.geom::geography) AS d
    FROM enlaces ee ORDER BY ee.geom <-> n.geom LIMIT 1
) e
ORDER BY n.id;
