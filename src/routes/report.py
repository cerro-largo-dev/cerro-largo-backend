# src/routes/report.py
from __future__ import annotations

"""
Endpoint de descarga de reporte:
- Usa ReporteEstadoMunicipios de pdf_generator.py (logo, títulos, tabla, leyenda).
- Inserta mapa estático (render_map_png llamado desde pdf_generator).
- Busca el GeoJSON en src/static/assets o por GEOJSON_PATH (ENV).
- Normaliza y fusiona alias de zonas (MELO (GEB)->MANGRULLO, MELO (GCB)->LA MICAELA).
- Usa zona horaria America/Montevideo para el nombre del archivo (REPORT_TZ).
"""

import os
import logging
import unicodedata
import re
from datetime import datetime
from zoneinfo import ZoneInfo
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
LOGO_PATH = os.getenv("REPORT_LOGO_PATH", "alexlogo.png").strip()
GEOJSON_PATH_ENV = os.getenv("GEOJSON_PATH", "").strip()
REPORT_TZ = os.getenv("REPORT_TZ", "America/Montevideo").strip()


# --------------------------- Utilidades de nombres ---------------------------

def _norm_key(s: str) -> str:
    s = (s or "").strip()
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = s.upper()
    s = re.sub(r"\s+", " ", s)
    return s

def _alias_name(name: str) -> str:
    """Mapea alias antiguos a nombres nuevos y retorna en MAYÚSCULAS."""
    k = _norm_key(name)
    if k == "MELO (GEB)":
        return "MANGRULLO"
    if k == "MELO (GCB)":
        return "LA MICAELA"
    return k


# --------------------------- Utilidades de datos ---------------------------

def _build_states_simple_map() -> Dict[str, str]:
    """
    Devuelve { 'ZONA': 'green|yellow|red', ... } a partir del modelo ZoneState.
    - Soporta {'ZONA': 'green'} o {'ZONA': {'state': 'green', ...}}.
    - Normaliza nombres y fusiona alias (GEB/GCB).
    - Si hay duplicados, prioriza el estado más restrictivo: red > yellow > green.
    """
    raw = ZoneState.get_all_states() or {}
    merged: Dict[str, str] = {}
    rank = {"red": 3, "yellow": 2, "green": 1}
    for name, data in raw.items():
        st = (data.get("state") if isinstance(data, dict) else str(data) or "green").lower()
        aliased = _alias_name(name)
        if aliased in merged:
            if rank.get(st, 0) > rank.get(merged[aliased], 0):
                merged[aliased] = st
        else:
            merged[aliased] = st
    return merged

def _seed_if_empty():
    """Si la tabla está vacía, inicializa todas las zonas en 'green'."""
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
    """Selecciona el GeoJSON a usar para el render del mapa."""
    if GEOJSON_PATH_ENV and Path(GEOJSON_PATH_ENV).exists():
        log.info(f"[report] GEOJSON_PATH={GEOJSON_PATH_ENV}")
        return GEOJSON_PATH_ENV

    here = Path(__file__).resolve()
    bases = [
        here.parents[1] / "static" / "assets",           # src/static/assets
        here.parents[2] / "src" / "static" / "assets",   # /opt/render/project/src/src/static/assets
        here.parents[2] / "static" / "assets",           # /opt/render/project/src/static/assets
    ]
    patterns = ["combined_polygons.geojson", "*.geojson"]

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
    - Logo
    - Título / Subtítulo / Fecha
    - Tabla de estados (TODOS los municipios)
    - Leyenda
    - Mapa estático
    """
    try:
        _seed_if_empty()
        states_map = _build_states_simple_map()
        geojson_path = _pick_geojson_file()

        # Construir lista de municipios a partir de DB (ya deduplicada)
        def _state_label(s: str) -> str:
            return (
                "Habilitado" if s == "green" else
                "Precaución" if s == "yellow" else
                "Cerrado" if s == "red" else
                "Desconocido"
            )

        municipios = [
            {"nombre": nombre, "estado": _state_label(estado), "color": "", "alerta": ""}
            for nombre, estado in sorted(states_map.items(), key=lambda kv: kv[0])
        ]

        # Generar PDF con tu clase
        with NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_pdf:
            gen = ReporteEstadoMunicipios(logo_path=LOGO_PATH)
            gen.generar_pdf(
                nombre_archivo=tmp_pdf.name,
                municipios=municipios,      # TODOS los municipios reales (ya fusionados)
                states_map=states_map,
                geojson_path=geojson_path,
                draw_labels=True,
                draw_legend=True,
            )
            pdf_path = tmp_pdf.name

        # Nombre de archivo con TZ local
        now = datetime.now(ZoneInfo(REPORT_TZ))
        return send_file(
            pdf_path,
            as_attachment=True,
            download_name=f'reporte_camineria_cerro_largo_{now:%Y%m%d_%H%M%S}.pdf',
            mimetype='application/pdf'
        )

    except FileNotFoundError as e:
        return jsonify({"success": False, "message": str(e)}), 500

    except Exception as e:
        return jsonify({"success": False, "message": f"Error generando reporte: {e}"}), 500
