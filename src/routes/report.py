# src/routes/report.py
from __future__ import annotations

from flask import Blueprint, request, jsonify, send_file, session
from datetime import datetime
from pathlib import Path
from glob import glob
import os
import tempfile

from src.models.zone_state import ZoneState

# Generación de mapa estático (PNG)
from src.map_renderer import render_map_png

# PDF (ReportLab)
try:
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.utils import ImageReader
    PDF_AVAILABLE = True
except Exception:
    PDF_AVAILABLE = False

report_bp = Blueprint('report', __name__)

# ------------------------------- Utils ---------------------------------

def _build_states_simple_map() -> dict[str, str]:
    """
    Convierte la respuesta de ZoneState.get_all_states() a {zone_name: 'green|yellow|red'}.
    """
    states_raw = ZoneState.get_all_states() or {}
    out = {}
    for name, data in states_raw.items():
        if isinstance(data, dict):
            st = data.get('state') or data.get('color') or 'green'
        else:
            st = str(data)
        out[name] = str(st).lower()
    return out

def _seed_if_empty():
    """
    Si no hay estados, inicializa todas las zonas en 'green' (habilitado).
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
    Preferimos la capa de series; si no existe, usamos municipios.
    """
    base = Path(__file__).resolve().parents[1] / "static" / "assets"
    # series primero
    candidates = sorted(glob(str(base / "series_cerro_largo*.geojson")))
    if not candidates:
        # fallback a municipios
        candidates = sorted(glob(str(base / "cerro_largo_municipios*.geojson")))
    if not candidates:
        raise FileNotFoundError("No se encontró GeoJSON en static/assets/")
    return candidates[0]

def _draw_pdf_with_map(img_path: str, out_pdf_path: str, states_map: dict[str, str]):
    """
    Crea un PDF A4 con la imagen del mapa y un resumen simple.
    """
    w, h = A4
    c = canvas.Canvas(out_pdf_path, pagesize=A4)

    # Encabezado
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, h - 50, "Reporte de Estado de Zonas – Cerro Largo")

    # Fecha/hora
    c.setFont("Helvetica", 9)
    c.drawString(40, h - 66, datetime.now().strftime("Generado el %d/%m/%Y %H:%M"))

    # Imagen del mapa
    try:
        c.drawImage(ImageReader(img_path), 40, 170, width=w - 80, height=h - 260, preserveAspectRatio=True, anchor='n')
    except Exception:
        # si fallara la imagen por alguna razón, continuamos sin romper el PDF
        pass

    # Resumen (contador por estado)
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

# ------------------------------- Rutas ---------------------------------

@report_bp.route('/download', methods=['GET'])
def download_report():
    """
    Generar y descargar PDF con screenshot estático del mapa (render vectorial)
    y resumen de estados. Disponible para cualquier usuario.
    """
    try:
        # Asegurar datos básicos
        _seed_if_empty()

        # Mapa simple de estados
        states_map = _build_states_simple_map()

        if PDF_AVAILABLE:
            # Elegir GeoJSON (series o municipios)
            geojson_path = _pick_geojson_file()

            # Render PNG del mapa con colores por estado y etiquetas
            with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp_img:
                render_map_png(
                    geojson_path=geojson_path,
                    states_map=states_map,
                    out_png_path=tmp_img.name,
                    figsize=(8.27, 5.8),   # ~A5 horizontal
                    dpi=200,
                    draw_labels=True,
                    draw_legend=True
                )
                png_path = tmp_img.name

            # Construir PDF final con la imagen
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_pdf:
                _draw_pdf_with_map(png_path, tmp_pdf.name, states_map)
                pdf_path = tmp_pdf.name

            return send_file(
                pdf_path,
                as_attachment=True,
                download_name=f'reporte_camineria_cerro_largo_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf',
                mimetype='application/pdf'
            )

        # Fallback si no hay reportlab
        return _download_text_report(states_map)

    except Exception as e:
        # Fallback de emergencia (texto)
        try:
            states_map = _build_states_simple_map()
            return _download_text_report(states_map, error=str(e))
        except Exception as e2:
            return jsonify({
                'success': False,
                'message': f'Error generando reporte: {e2}'
            }), 500

def _download_text_report(states_map: dict[str, str], error: str | None = None):
    """
    Genera un TXT de respaldo con detalle de estados por zona.
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
    tf.write(f"🟨 En Alerta: {yellow}\n")
    tf.write(f"🟥 Suspendidas: {red}\n\n")

    tf.write("DETALLE POR ZONA/MUNICIPIO\n")
    tf.write("-" * 30 + "\n")
    for name in sorted(states_map.keys()):
        state = states_map[name]
        label = '🟩 Habilitado' if state == 'green' else ('🟨 Precaución' if state == 'yellow' else ('🟥 Cerrado' if state == 'red' else 'Desconocido'))
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

@report_bp.route('/generate-data', methods=['GET'])
def generate_report_data():
    """
    Devuelve datos resumidos del reporte para el frontend.
    """
    try:
        _seed_if_empty()
        states_map = _build_states_simple_map()
        state_counts = {'green': 0, 'yellow': 0, 'red': 0}
        for v in states_map.values():
            if v in state_counts:
                state_counts[v] += 1

        report_data = {
            'generated_at': datetime.utcnow().isoformat(),
            'total_zones': len(states_map),
            'state_summary': state_counts,
            'zones': states_map
        }
        return jsonify({'success': True, 'report': report_data}), 200

    except Exception as e:
        return jsonify({'success': False, 'message': f'Error al generar datos del reporte: {str(e)}'}), 500

