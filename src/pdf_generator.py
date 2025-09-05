#!/usr/bin/env python3
"""
Generador de PDF para reportes de estado de municipios de Cerro Largo
- Inserta mapa estático renderizado desde GeoJSON (via map_renderer.render_map_png)
- Carga TODAS las zonas desde states_map si no se provee 'municipios'
- Resuelve ruta del logo (alexlogo.png por defecto) de forma robusta
"""

import os
import json
from datetime import datetime
from tempfile import NamedTemporaryFile
from pathlib import Path
from zoneinfo import ZoneInfo

from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

# Render del mapa
try:
    from src.map_renderer import render_map_png
except Exception:
    # Fallback si se ejecuta standalone en el mismo directorio
    from map_renderer import render_map_png

# Permite indicar logo/geojson por ENV
REPORT_LOGO_PATH = os.getenv("REPORT_LOGO_PATH", "alexlogo.png").strip()
REPORT_TZ = os.getenv("REPORT_TZ", "America/Montevideo").strip()
GEOJSON_PATH = os.getenv("GEOJSON_PATH", "").strip()


def _resolve_asset_path(candidate_path: str) -> str:
    """
    Resuelve una ruta de asset (logo, etc.) buscando en ubicaciones típicas del backend.
    Acepta nombre de archivo, ruta relativa o absoluta.
    """
    cand = Path(candidate_path)
    if cand.is_absolute() and cand.exists():
        return str(cand)

    # si es relativo, probamos donde está este archivo y en rutas típicas
    here = Path(__file__).resolve()
    candidates = [
        here.parent / cand,                                            # mismo dir que este script
        here.parent / "static" / "assets" / cand.name,                 # src/static/assets
        here.parent.parent / "static" / "assets" / cand.name,          # <root>/static/assets
        here.parent.parent / "src" / "static" / "assets" / cand.name,  # /opt/render/project/src/src/static/assets
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return str(cand)  # devolvemos lo pedido (por si luego existe en runtime)


def _state_to_label(s: str) -> str:
    s = (s or "").lower()
    if s == "green":  return "Habilitado"
    if s == "yellow": return "Precaución"
    if s == "red":    return "Cerrado"
    return "Desconocido"


class ReporteEstadoMunicipios:
    def __init__(self, logo_path: str = REPORT_LOGO_PATH, caminos_data=None):
        # Resolver logo de forma robusta
        self.logo_path = _resolve_asset_path(logo_path or "alexlogo.png")
        self.caminos_data = caminos_data if caminos_data is not None else {}
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()

    def _setup_custom_styles(self):
        """Configurar estilos personalizados para el PDF"""
        # Título
        self.styles.add(ParagraphStyle(
            name='TituloReporte',
            parent=self.styles['Title'],
            fontSize=18,
            spaceAfter=20,
            alignment=TA_CENTER,
            textColor=colors.HexColor('#1f4e79')
        ))
        # Subtítulo
        self.styles.add(ParagraphStyle(
            name='Subtitulo',
            parent=self.styles['Heading2'],
            fontSize=14,
            spaceAfter=12,
            textColor=colors.HexColor('#2e75b6')
        ))
        # Texto normal
        self.styles.add(ParagraphStyle(
            name='TextoNormal',
            parent=self.styles['Normal'],
            fontSize=11,
            spaceAfter=6,
            alignment=TA_LEFT
        ))
        # ⬇️ NUEVO: Texto centrado para ubicar debajo del mapa
        self.styles.add(ParagraphStyle(
            name='TextoMapa',
            parent=self.styles['Normal'],
            fontSize=10,
            spaceAfter=8,
            alignment=TA_CENTER,
            textColor=colors.HexColor('#333333')
        ))
        # Fecha/hora
        self.styles.add(ParagraphStyle(
            name='FechaHora',
            parent=self.styles['Normal'],
            fontSize=10,
            alignment=TA_RIGHT,
            textColor=colors.grey
        ))
        # Lista de caminos
        self.styles.add(ParagraphStyle(
            name='ListaCaminos',
            parent=self.styles['Normal'],
            fontSize=10,
            leftIndent=0.5*cm,
            spaceBefore=3,
            spaceAfter=3,
        ))

    def _tabla_municipios(self, municipios):
        """Crear tabla con el estado de los municipios"""
        data = [['Municipio / Zona', 'Estado']]
        for m in municipios:
            data.append([
                m.get('nombre', ''),
                m.get('estado', '')
            ])

        table = Table(data, colWidths=[10*cm, 6*cm])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4e79')),
            ('TEXTCOLOR',  (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN',      (0, 0), (-1, 0), 'CENTER'),
            ('FONTNAME',   (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE',   (0, 0), (-1, 0), 12),

            ('FONTNAME',   (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE',   (0, 1), (-1, -1), 10),
            ('ALIGN',      (0, 1), (-1, -1), 'LEFT'),
            ('GRID',       (0, 0), (-1, -1), 0.6, colors.black),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.Color(0.96,0.96,0.96)]),
        ]))
        return table

    def generar_pdf(
        self,
        nombre_archivo="reporte_municipios.pdf",
        municipios=None,
        *,
        # Si no se pasan municipios, se construyen desde states_map (TODOS)
        states_map: dict | None = None,     # {'ACEGUÁ':'green', 'MANGRULLO':'yellow', ...}
        geojson_path: str | None = None,    # ruta al GeoJSON (series/municipios/combined)
        mapa_ancho_cm: float = 16.0,
        mapa_alto_cm: float = 11.0,
        draw_labels: bool = True,
        draw_legend: bool = True,
    ):
        """
        Genera el PDF (logo, cabecera, tabla, leyenda y mapa).
        Si 'municipios' es None y hay 'states_map', arma la tabla con TODAS las zonas de states_map.
        """
        # --- Construir la lista de municipios si no la pasan ---
        if municipios is None:
            if states_map:
                # Tomar TODOS los nombres/estados de la DB (o caller) y traducir etiquetas
                municipios = [
                    {"nombre": n, "estado": _state_to_label(v), "color": "", "alerta": ""}
                    for n, v in sorted(states_map.items(), key=lambda kv: kv[0])
                ]
            else:
                # Fallback mínimo si no llegó nada
                municipios = []

        # Documento
        doc = SimpleDocTemplate(
            nombre_archivo,
            pagesize=A4,
            rightMargin=2*cm, leftMargin=2*cm,
            topMargin=2*cm, bottomMargin=2*cm
        )
        elems = []

        # Logo (si existe)
        if os.path.exists(self.logo_path):
            try:
                logo = Image(self.logo_path, width=8*cm, height=3*cm)
                logo.hAlign = 'CENTER'
                elems += [logo, Spacer(1, 0.5*cm)]
            except Exception as e:
                print(f"[pdf_generator] Error al cargar logo {self.logo_path}: {e}")

        # Titulado
        elems += [
            Paragraph("Reporte Camineria por Municipios.", self.styles['TituloReporte']),
            Spacer(1, 0.3*cm),
            Paragraph(f"Generado el: {datetime.now():%d/%m/%Y %H:%M:%S}", self.styles['FechaHora']),
            Spacer(1, 0.8*cm),
        ]

        # Mapa (si hay datos y ruta válida)
        _geojson = geojson_path or (GEOJSON_PATH if GEOJSON_PATH else None)
        if states_map and _geojson and os.path.exists(_geojson):
            try:
                with NamedTemporaryFile(suffix=".png", delete=False) as tmp_img:
                    render_map_png(
                        geojson_path=_geojson,
                        states_map=states_map,
                        out_png_path=tmp_img.name,
                        figsize=(8.27, 5.8),  # ~A5 apaisado
                        dpi=200,
                        draw_labels=draw_labels,
                        draw_legend=draw_legend
                    )
                    mapa_img = Image(tmp_img.name, width=mapa_ancho_cm*cm, height=mapa_alto_cm*cm)
                    mapa_img.hAlign = 'CENTER'
                    elems += [Spacer(1, 0.4*cm), mapa_img, Spacer(1, 0.6*cm)]
            except Exception as e:
                elems += [Paragraph(f"[Aviso] No se pudo insertar el mapa: {e}", self.styles['TextoNormal']),
                          Spacer(1, 0.4*cm)]

            # ⬇️ Texto solicitado DEBAJO del mapa
            elems += [
                Paragraph(
                    "Este reporte muestra el estado actual de todos los municipios y zonas del departamento de "
                    "Cerro Largo, incluyendo estados de tránsito pesado y alertas vigentes.",
                    self.styles['TextoMapa']
                ),
                Spacer(1, 0.6*cm)
            ]

        # Tabla de municipios (TODOS los de states_map si no pasaron explícitos)
        elems += [self._tabla_municipios(municipios), Spacer(1, 1*cm)]

        # Caminos por municipio (opcional)
        if self.caminos_data:
            elems.append(Paragraph("Caminos por Municipio:", self.styles['Subtitulo']))
            for muni, caminos in self.caminos_data.items():
                caminos_str = ", ".join(caminos)
                elems.append(Paragraph(f"<b>{muni}:</b> {caminos_str}", self.styles['ListaCaminos']))
                elems.append(Spacer(1, 0.2*cm))
            elems.append(Spacer(1, 1*cm))

        # Leyenda de estados
        elems += [
            Paragraph("Leyenda de Estados:", self.styles['Subtitulo']),
            Paragraph("• <b>Verde:</b> Habilitado el tránsito pesado", self.styles['TextoNormal']),
            Paragraph("• <b>Amarillo:</b> Precaución / posible cierre", self.styles['TextoNormal']),
            Paragraph("• <b>Rojo:</b> Prohibido el tránsito pesado por lluvias", self.styles['TextoNormal']),
            Spacer(1, 1*cm),
        ]

        # Pie
        elems.append(Paragraph(
            "Para más información, consulte el mapa interactivo en línea o contacte a las autoridades locales.",
            self.styles['TextoNormal']
        ))

        # Construir PDF
        doc.build(elems)
        print(f"[pdf_generator] PDF generado: {nombre_archivo}")
        return nombre_archivo


# --------------------- Utilidad local para pruebas ---------------------

def _pick_geojson_local() -> str | None:
    """
    Devuelve la mejor ruta de GeoJSON disponible para el render del mapa (modo local).
    Prioriza:
      1) GEOJSON_PATH (env)
      2) src/static/assets/combined_polygons.geojson
      3) src/static/assets/series_cerro_largo-*.geojson
      4) src/static/assets/cerro_largo_municipios-*.geojson
    """
    if GEOJSON_PATH and os.path.exists(GEOJSON_PATH):
        return GEOJSON_PATH

    candidates = [
        "src/static/assets/combined_polygons.geojson",
        "src/static/assets/series_cerro_largo-CsPIPpgW.geojson",
        "src/static/assets/cerro_largo_municipios_2025-XyT-VvXO.geojson",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


def main():
    """Ejecución local de ejemplo"""
    # (opcional) cargar datos de caminos
    caminos_json_path = "/home/ubuntu/upload/Caminos_Cerro_Largo_por_Municipio.json"
    caminos_data = {}
    if os.path.exists(caminos_json_path):
        with open(caminos_json_path, 'r', encoding='utf-8') as f:
            caminos_data = json.load(f)

    # Estados de ejemplo: en producción vendrán de DB (report.py)
    states_map = {
        "ACEGUÁ": "green",
        "MANGRULLO": "yellow",
        "LA MICAELA": "red",
        "RÍO BRANCO": "green",
    }

    geojson_path = _pick_geojson_local()

    gen = ReporteEstadoMunicipios(logo_path=REPORT_LOGO_PATH, caminos_data=caminos_data)
    gen.generar_pdf(
        nombre_archivo="reporte_ejemplo_municipios_con_mapa.pdf",
        municipios=None,                # 👈 se arma desde states_map (TODAS las zonas)
        states_map=states_map,
        geojson_path=geojson_path
    )


if __name__ == "__main__":
    main()
