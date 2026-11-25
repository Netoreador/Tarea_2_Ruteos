# Tarea 2: la red Yafún frente al M8.8 del Maule

## Requisitos

- Docker Desktop abierto
- Python 3.10 o superior

## Ejecución

```bash
git clone https://github.com/Netoreador/Tarea_2_Ruteos.git
cd Tarea_2_Ruteos
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

`main.py` levanta la base de datos con Docker (puerto 5440), carga los datos y calcula todo, en cerca de 100 segundos. No hay que crear la base de datos a mano. Al final sirve el mapa en `http://localhost:8765/mapa.html` y lo abre en el navegador. El servidor queda activo hasta que se presiona Ctrl+C.

Opciones:
- `--iter N`: iteraciones de Monte Carlo (por defecto 20000)
- `--semilla S`: semilla (por defecto 42)
- `--sin-navegador`: no levanta el servidor ni abre el mapa
- `--puerto P`: puerto del servidor del mapa (por defecto 8765)

## Qué genera

- `main.sql`: infraestructura y probabilidades de falla. Se carga en cualquier BD con PostGIS con `psql -d <bd> -f main.sql`.
- `salida/mapa.html`: mapa Leaflet.
- `salida/resultados.json`: ATTR antes y después.
