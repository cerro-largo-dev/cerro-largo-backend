# src/routes/report.py
from __future__ import annotations

"""
Reporte de caminería con mapa estático:
- Busca el GeoJSON en src/static/assets (o vía env GEOJSON_PATH).
- Renderiza PNG del mapa con src.map_renderer.render_map_png.
- Incrusta la imagen en un PDF (ReportLab) y lo devuelve.
- Fallback: TXT si no hay ReportLab o falla el render.
"""

import os
import logging
import tempfile
from glob import glob
from datetime import datetime
from pathlib import Path
from typing import Dict

from flask import Blueprint, jsonify, send_file

# Estados desde la DB
from src.models.zone_state import ZoneState

# Render del mapa (PNG)
from src.map_renderer import render_map_png

# PDF (ReportLab) opcional
try:
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.utils import ImageReader
    PDF_AVAILABLE = True
except Exception:
    PDF_AVAILABLE = False

log = logging.getLogger(__name__)
report_bp = Blueprint("report", __name__)

# ---------------------------------------------------------------------
# Utils
# ---------------------------------------------------------------------

def _build_states_simple_map() -> Dict[str, str]:
    """
    Devuelve { 'NOMBRE ZONA': 'green|yellow|red', ... } a partir del modelo.
    """
    states_raw = ZoneState.get_all_states() or {}
    out: Dict[str, str] = {}
    for name, data in states_raw.items():
        if isinstance(data, dict):
            st = data.get("state") or data.get("color") or "green"
        else:
            st = str(data)
        out[name] = str(st).lower()
    return out

def _seed_if_empty():
    """
    Si la tabla está vacía, inicializa todas las zonas en 'green'.
    (Lista en mayúsculas, orden alfabético, con Mangrullo/La Micaela)
    """
    current = ZoneState.get_all_states()
    if current:
        return

    municipios = [
        'ACEGUÁ',
        'ARBOLITO',
        'ARÉVALO',
        'BAÑADO DE MEDINA',
        'CENTURIÓN',
        'CERRO DE LAS CUENTAS',
        'FRAILE MUERTO',
        'ISIDORO NOBLÍA',
        'LA MICAELA',
        'LAGUNA MERÍN',
        'LAS CAÑAS',
        'MANGRULLO',
        'PLÁCIDO ROSAS',
        'QUEBRACHO',
        'RAMÓN TRIGO',
        'RÍO BRANCO',
        'TRES ISLAS',
        'TUPAMBAÉ',
        'MELO (GBA)',
        'MELO (GBB)',
        'MELO (GBC)',
    ]
    for m in municipios:
        ZoneState.update_zone_state(m, 'green', updated_by='sistema')

def _pick_geojson_file() -> str:
    """
    Selecciona el GeoJSON a usar para el render del mapa.

    Prioriza:
      1) RUTA en variable de entorno GEOJSON_PATH.
      2) combined_polygons.geojson (tu asset del frontend copiado a backend).
      3) series_cerro_largo*.geojson
      4) cerro_largo_municipios*.geojson
      5) cualquier *.geojson bajo static/assets (incl. subcarpetas)
    """
    # 1) ENV explícito
    env_path = os.getenv("GEOJSON_PATH")
    if env_path and Path(env_path).exists():
        log.info(f"[report] GEOJSON_PATH={env_path}")
        return env_path

    here = Path(__file__).resolve()

    # Carpetas candidatas típicas en Render/Flask
    bases = [
        here.parents[1] / "static" / "assets",           # src/static/assets
        here.parents[2] / "src" / "static" / "assets",   # /opt/render/project/src/src/static/assets
        here.parents[2] / "static" / "assets",           # /opt/render/project/src/static/assets
    ]

    patterns = [
        "combined_polygons.geojson",      # 👈 tu archivo real del frontend copiado al backend
        "series_cerro_largo*.geojson",
        "cerro_largo_municipios*.geojson",
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

def _draw_pdf_with_map(img_path: str, out_pdf_path: str, states_map: Dict[str, str]):
    """
    Crea un PDF A4 con la imagen del mapa y un resumen simple.
    """
    c = canvas.Canvas(out_pdf_path, pagesize=A4)
    w, h = A4

    # Encabezado
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, h - 50, "Reporte de Estado de Zonas – Cerro Largo")

    # Fecha/hora
    c.setFont("Helvetica", 9)
    c.drawString(40, h - 66, datetime.now().strftime("Generado el %d/%m/%Y %H:%M"))

    # Imagen del mapa
    try:
        c.drawImage(ImageReader(img_path), 40, 170, width=w - 80, height=h - 260,
                    preserveAspectRatio=True, anchor='n')
    except Exception as e:
        # no romper el PDF si falla la imagen
        c.setFont("Helvetica", 10)
        c.drawString(40, 170, f"[Aviso] No se pudo insertar el mapa: {e}")

    # Resumen por estado
    green = sum(1 for v in states_map.values() if v == 'green')
    yellow = sum(1 for v in states_map.values() if v == 'yellow')
    red = sum(1 for v in states_map.values() if v == 'red')

    c.setFont("Helvetica-Bold", 10)
    c.drawString(40, 140, "Resumen general")
    c.setFont("Helvetica", 10)
    c.drawString(40, 124, f"🟩 Habilitadas: {green}")
    c.drawString(200, 124, f"🟨 Precaución: {yellow}")
    c.drawString(360, 124, f"🟥 Cerradas: {red}")

    # Pie
    c.setFont("Helvetica", 9)
    c.drawString(40, 100, "Sistema de Gestión de Caminería – Gobierno de Cerro Largo")
    c.showPage()
    c.save()

def _download_text_report(states_map: Dict[str, str], error: str | None = None):
    """
    Fallback TXT con detalle de estados por zona (si falla PDF o no hay ReportLab).
    """
    now = datetime.now()
    tf = tempfile.NamedTemporaryFile(delete=False, suffix='.txt', mode='w', encoding='utf-8')

    tf.write("REPORTE DE ESTADOS DE CAMINERÍA - CERRO LARGO\n")
    tf.write("=" * 50 + "\n\n")
    tf.write(f"Generado el: {now.strftime('%d/%m/%Y %H:%M:%S')}\n")
    if error:
        tf.write(f"\n[AVISO] Render PDF deshabilitado o con error: {error}\n")
    tf.write("\n")

    total = len(states_map)
    green = sum(1 for v in states_map.values() if v == 'green')
    yellow = sum(1 for v in states_map.values() if v == 'yellow')
    red = sum(1 for v in states_map.values() if v == 'red')

    tf.write("RESUMEN GENERAL\n")
    tf.write("-" * 20 + "\n")
    tf.write(f"Total de Zonas: {total}\n")
    tf.write(f"🟩 Habilitadas: {green}\n")
    tf.write(f"🟨 Precaución: {yellow}\n")
    tf.write(f"🟥 Cerradas: {red}\n\n")

    tf.write("DETALLE POR ZONA/MUNICIPIO\n")
    tf.write("-" * 30 + "\n")
    for name in sorted(states_map.keys()):
        state = states_map[name]
        label = '🟩 Habilitado' if state == 'green' else (
            '🟨 Precaución' if state == 'yellow' else (
                '🟥 Cerrado' if state == 'red' else 'Desconocido'
            )
        )
        tf.write(f"\nZona: {name}\nEstado: {label}\n")
        tf.write("-" * 40 + "\n")

    tf.write("\n\nSistema de Gestión de Caminería - Cerro Largo\n")
    tf.write("Departamento de Cerro Largo - Uruguay\n")
    tf.close()

    return send_file(
        tf.name,
        as_attachment=True,
        download_name=f'reporte_camineria_cerro_largo_{now.strftime("%Y%m%d_%H%M%S")}.txt',
        mimetype='text/plain'
    )

# ---------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------

@report_bp.route("/download", methods=["GET"])
def download_report():
    """
    Genera y descarga un PDF con el mapa estático y resumen de estados.
    (Normalmente expuesto como /api/report/download al registrar el blueprint)
    """
    try:
        # Asegurar datos base
        _seed_if_empty()

        # Mapa simple de estados
        states_map = _build_states_simple_map()

        if not PDF_AVAILABLE:
            return _download_text_report(states_map, error="ReportLab no disponible")

        # Buscar GeoJSON
        geojson_path = _pick_geojson_file()

        # Render PNG del mapa
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_img:
            render_map_png(
                geojson_path=geojson_path,
                states_map=states_map,
                out_png_path=tmp_img.name,
                figsize=(8.27, 5.8),  # Aprox A5 apaisado
                dpi=200,
                draw_labels=True,
                draw_legend=True,
            )
            png_path = tmp_img.name

        # Construir PDF final con la imagen
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_pdf:
            _draw_pdf_with_map(png_path, tmp_pdf.name, states_map)
            pdf_path = tmp_pdf.name

        return send_file(
            pdf_path,
            as_attachment=True,
            download_name=f'reporte_camineria_cerro_largo_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf',
            mimetype='application/pdf'
        )

    except FileNotFoundError as e:
        # GeoJSON no encontrado → TXT de respaldo + mensaje
        try:
            states_map = _build_states_simple_map()
        except Exception:
            states_map = {}
        return _download_text_report(states_map, error=str(e))

    except Exception as e:
        # Cualquier otro error → TXT de respaldo
        try:
            states_map = _build_states_simple_map()
        except Exception:
            states_map = {}
        return _download_text_report(states_map, error=f"Error generando PDF: {e}")
