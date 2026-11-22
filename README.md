# Resiliencia de la infraestructura de Internet en Chile frente al terremoto de 8.8

Tarea de Ruteo: calcula el ATTR (All-Terminal Reliability) de la red de fibra
óptica de Chile, antes y después de un terremoto de magnitud 8.8.

## Estado
- [x] Carga de la infraestructura (proyecto Yafún, Subtel) en PostGIS
- [x] Nodos clave y topología con `pgr_createTopology`
- [x] ATTR de la red en operación
- [ ] Sismo 8.8 (USGS), modelo de falla, `main.sql`, ATTR post-terremoto
- [ ] `main.py` y mapa Leaflet

## Datos
Los shapefiles de Yafún se obtuvieron por Ley de Transparencia
(solicitud AN002T0005610, Subtel). No están en el repositorio: copiar los 4
`.shp` (fibra, postación, camino, ferry) en `data/`.

## Cómo reproducir
    docker compose up -d
    pip install -r requirements.txt
    python cargar_datos.py
    docker compose exec db psql -U postgres -d yafun -f /sql/01_enlaces.sql
    docker compose exec db psql -U postgres -d yafun -f /sql/02_nodos_clave.sql
    docker compose exec db psql -U postgres -d yafun -f /sql/03_topologia.sql
    docker compose exec db psql -U postgres -d yafun -f /sql/04_puente.sql
    python attr.py

## Supuestos
- Los nodos clave (capitales regionales, Santiago, Valparaíso, Arica) y sus roles son supuestos propios.
- Santiago está a 9,6 km de la red mapeada; se pega al vértice más cercano.
- Se agrega un puente de 2,6 km (lat -33,60, lon -71,60) para cerrar un hueco del levantamiento.
- Rapa Nui queda fuera del ATTR (sin cable submarino en los datos).