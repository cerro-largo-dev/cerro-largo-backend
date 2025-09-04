# src/routes/report.py
from __future__ import annotations

"""
Endpoint de descarga de reporte:
- Usa la clase ReporteEstadoMunicipios de pdf_generator.py (logo, títulos, tabla, leyenda).
- Inserta el mapa estático renderizado (vía render_map_png llamado desde pdf_generator).
- Busca el GeoJSON en src/static/assets o por la variable de entorno GEOJSON_PATH.
"""

import os
import logging
from datetime import datetime
from pathlib import Path
from glob import glob
from tempfile import NamedTemporaryFile
from typing import Dict

from flask import Blueprint, send_file, jsonify

# Estados desde la DB
from src.models.zone_state import ZoneState

# Generador de PDF con estructura completa (logo + tabla + leyenda + mapa)
from src.pdf_generator import ReporteEstadoMunicipios

log = logging.getLogger(__name__)
report_bp = Blueprint("report", __name__)

# Opcionales por ENV
LOGO_PATH = os.getenv("REPORT_LOGO_PATH", "alexlogo.png").strip()  # p.ej.: "src/static/assets/logo.png"
GEOJSON_PATH_ENV = os.getenv("GEOJSON_PATH", "").strip()


# --------------------------- Utilidades de datos ---------------------------

def _build_states_simple_map() -> Dict[str, str]:
    """
    Devuelve { 'ZONA': 'green|yellow|red', ... } a partir del modelo ZoneState.
    Soporta {'ZONA': 'green'} o {'ZONA': {'state': 'green', ...}}.
    """
    raw = ZoneState.get_all_states() or {}
    out: Dict[str, str] = {}
    for name, data in raw.items():
        if isinstance(data, dict):
            st = data.get("state") or data.get("color") or "green"
        else:
            st = str(data)
        out[name] = str(st).lower()
    return out

def _seed_if_empty():
    """
    Si la tabla está vacía, inicializa todas las zonas en 'green'.
    (Lista en mayúsculas, con Mangrullo / La Micaela.)
    """
    if ZoneState.get_all_states():
        return
    zonas = [
        'ACEGUÁ','ARBOLITO','ARÉVALO','BAÑADO DE MEDINA','CENTURIÓN',
        'CERRO DE LAS CUENTAS','FRAILE MUERTO','ISIDORO NOBLÍA',
        'LA MICAELA','LAGUNA MERÍN','LAS CAÑAS','MANGRULLO',
        'PLÁCIDO ROSAS','QUEBRACHO','RAMÓN TRIGO','RÍO BRANCO',
        'TRES ISLAS','TUPAMBAÉ','MELO (GBA)','MELO (GBB)','MELO (GBC)',
    ]
    for z in zonas:
        ZoneState.update_zone_state(z, 'green', updated_by='sistema')

def _pick_geojson_file() -> str:
    """
    Selecciona el GeoJSON a usar para el render del mapa.

    Prioriza:
      1) GEOJSON_PATH (env).
      2) combined_polygons.geojson (asset del frontend copiado al backend).
      3) series_cerro_largo*.geojson
      4) cerro_largo_municipios*.geojson
      5) cualquier *.geojson bajo static/assets (incluye subcarpetas).
    """
    # 1) ENV
    if GEOJSON_PATH_ENV and Path(GEOJSON_PATH_ENV).exists():
        log.info(f"[report] GEOJSON_PATH={GEOJSON_PATH_ENV}")
        return GEOJSON_PATH_ENV

    # 2) Buscar en rutas típicas del proyecto/deploy
    here = Path(__file__).resolve()
    bases = [
        here.parents[1] / "static" / "assets",           # src/static/assets
        here.parents[2] / "src" / "static" / "assets",   # /opt/render/project/src/src/static/assets
        here.parents[2] / "static" / "assets",           # /opt/render/project/src/static/assets
    ]

    patterns = [
        "combined_polygons.geojson",
        "*.geojson",
    ]

    found = []
    for base in bases:
        if base.exists():
            for pat in patterns:
                found += glob(str(base / pat))
                found += glob(str(base / "**" / pat), recursive=True)

    if found:
        found = sorted(set(found))
        log.info(f"[report] GEOJSON encontrados: {found}")
        return found[0]

    raise FileNotFoundError(
        "No se encontró GeoJSON. Copiá 'combined_polygons.geojson' a src/static/assets "
        "o seteá GEOJSON_PATH con la ruta absoluta."
    )


# --------------------------------- Ruta API ---------------------------------

@report_bp.route("/download", methods=["GET"])
def download_report():
    """
    Genera y descarga un PDF usando ReporteEstadoMunicipios:
    - Logo (REPORT_LOGO_PATH o alexlogo.png)
    - Título / Subtítulo / Fecha
    - Tabla de estados por zona
    - Leyenda
    - Mapa estático (con labels y leyenda dentro de la imagen)
    """
    try:
        # Asegurar datos base y obtener estados
        _seed_if_empty()
        states_map = _build_states_simple_map()

        # Resolver GeoJSON
        geojson_path = _pick_geojson_file()

        # Generar PDF con tu clase (usa internamente render_map_png)
        with NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_pdf:
            gen = ReporteEstadoMunicipios(logo_path=LOGO_PATH)
            gen.generar_pdf(
                nombre_archivo=tmp_pdf.name,
                municipios=None,            # si querés, podés pasar tu propio listado
                states_map=states_map,      # estados reales de DB
                geojson_path=geojson_path,  # el geojson seleccionado
                draw_labels=True,
                draw_legend=True,
            )
            pdf_path = tmp_pdf.name

        return send_file(
            pdf_path,
            as_attachment=True,
            download_name=f'reporte_camineria_cerro_largo_{datetime.now():%Y%m%d_%H%M%S}.pdf',
            mimetype='application/pdf'
        )

    except FileNotFoundError as e:
        # GeoJSON ausente → texto con diagnóstico
        return jsonify({"success": False, "message": str(e)}), 500

    except Exception as e:
        # Cualquier otro error
        return jsonify({"success": False, "message": f"Error generando reporte: {e}"}), 500
