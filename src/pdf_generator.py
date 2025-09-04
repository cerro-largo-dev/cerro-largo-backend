#!/usr/bin/env python3
"""
Generador de PDF para reportes de estado de municipios de Cerro Largo
(con mapa estático renderizado desde GeoJSON)
"""

import os
import json
from datetime import datetime
from tempfile import NamedTemporaryFile

from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

# 👇 importar el renderizador de mapa
# Si corrés dentro del proyecto Flask:
try:
    from src.map_renderer import render_map_png
except Exception:
    # Fallback si ejecutás este script standalone en la misma carpeta
    from map_renderer import render_map_png

# Permite indicar el GeoJSON por variable de entorno
GEOJSON_PATH = os.getenv("GEOJSON_PATH", "").strip()


class ReporteEstadoMunicipios:
    def __init__(self, logo_path="alexlogo.png", caminos_data=None):
        self.logo_path = logo_path
        self.caminos_data = caminos_data if caminos_data is not None else {}
        self.styles = getSampleStyleSheet()
        self.setup_custom_styles()

    def setup_custom_styles(self):
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

    def generar_datos_ejemplo(self):
        """Generar datos de ejemplo para los municipios (si no se pasan)"""
        return [
            {"nombre": "Melo", "estado": "Habilitado", "color": "Verde", "alerta": "Sin restricciones"},
            {"nombre": "Río Branco", "estado": "Habilitado", "color": "Verde", "alerta": "Sin restricciones"},
            {"nombre": "Fraile Muerto", "estado": "Habilitado", "color": "Verde", "alerta": "Sin restricciones"},
            {"nombre": "Isidoro Noblía", "estado": "Precaución", "color": "Amarillo", "alerta": "Posible cierre de caminería"},
            {"nombre": "Aceguá", "estado": "Habilitado", "color": "Verde", "alerta": "Sin restricciones"},
            {"nombre": "Tupambaé", "estado": "Habilitado", "color": "Verde", "alerta": "Sin restricciones"},
            {"nombre": "Arbolito", "estado": "Habilitado", "color": "Verde", "alerta": "Sin restricciones"},
            {"nombre": "Plácido Rosas", "estado": "Habilitado", "color": "Verde", "alerta": "Sin restricciones"},
            {"nombre": "Ramón Trigo", "estado": "Habilitado", "color": "Verde", "alerta": "Sin restricciones"},
            {"nombre": "Laguna Merín", "estado": "Habilitado", "color": "Verde", "alerta": "Sin restricciones"},
        ]

    def crear_tabla_municipios(self, municipios):
        """Crear tabla con el estado de los municipios"""
        data = [['Municipio', 'Estado', 'Color', 'Alerta']]
        for m in municipios:
            data.append([
                m.get('nombre', ''),
                m.get('estado', ''),
                m.get('color', ''),
                m.get('alerta', '')
            ])

        tabla = Table(data, colWidths=[4*cm, 3*cm, 2.5*cm, 6*cm])
        tabla.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4e79')),
            ('TEXTCOLOR',  (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN',      (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME',   (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE',   (0, 0), (-1, 0), 12),

            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('TEXTCOLOR',  (0, 1), (-1, -1), colors.black),
            ('FONTNAME',   (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE',   (0, 1), (-1, -1), 10),
            ('GRID',       (0, 0), (-1, -1), 1, colors.black),

            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
        ]))
        return tabla

    def generar_pdf(
        self,
        nombre_archivo="reporte_municipios.pdf",
        municipios=None,
        *,
        # Nuevos parámetros para incluir el mapa
        states_map: dict | None = None,     # {'ACEGUÁ':'green', 'MANGRULLO':'yellow', ...}
        geojson_path: str | None = None,    # ruta al GeoJSON (series/municipios/combined)
        mapa_ancho_cm: float = 16.0,
        mapa_alto_cm: float = 11.0,
        draw_labels: bool = True,
        draw_legend: bool = True,
    ):
        """Generar el PDF del reporte (con mapa si se provee states_map y geojson_path)."""
        if municipios is None:
            municipios = self.generar_datos_ejemplo()

        # Documento
        doc = SimpleDocTemplate(
            nombre_archivo,
            pagesize=A4,
            rightMargin=2*cm, leftMargin=2*cm,
            topMargin=2*cm, bottomMargin=2*cm
        )
        elementos = []

        # Logo
        if os.path.exists(self.logo_path):
            try:
                logo = Image(self.logo_path, width=8*cm, height=2*cm)
                logo.hAlign = 'CENTER'
                elementos.append(logo)
                elementos.append(Spacer(1, 0.5*cm))
            except Exception as e:
                print(f"Error al cargar el logo: {e}")

        # Titulado
        elementos.append(Paragraph("Reporte de Estado de Municipios", self.styles['TituloReporte']))
        elementos.append(Spacer(1, 0.3*cm))
        elementos.append(Paragraph("Departamento de Cerro Largo", self.styles['Subtitulo']))
        elementos.append(Spacer(1, 0.5*cm))

        # Fecha/hora
        fecha_hora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        elementos.append(Paragraph(f"Generado el: {fecha_hora}", self.styles['FechaHora']))
        elementos.append(Spacer(1, 0.8*cm))

        # Descripción
        elementos.append(Paragraph(
            "Este reporte muestra el estado actual de todos los municipios del departamento de Cerro Largo, "
            "incluyendo el estado de tránsito pesado y las alertas vigentes.",
            self.styles['TextoNormal']
        ))
        elementos.append(Spacer(1, 0.5*cm))

        # Mapa (si hay datos y ruta válida)
        if states_map and geojson_path and os.path.exists(geojson_path):
            try:
                with NamedTemporaryFile(suffix=".png", delete=False) as tmp_img:
                    render_map_png(
                        geojson_path=geojson_path,
                        states_map=states_map,
                        out_png_path=tmp_img.name,
                        figsize=(8.27, 5.8),  # ~A5 apaisado
                        dpi=200,
                        draw_labels=draw_labels,
                        draw_legend=draw_legend
                    )
                    mapa_img = Image(tmp_img.name, width=mapa_ancho_cm*cm, height=mapa_alto_cm*cm)
                    mapa_img.hAlign = 'CENTER'
                    elementos.append(Spacer(1, 0.4*cm))
                    elementos.append(mapa_img)
                    elementos.append(Spacer(1, 0.6*cm))
            except Exception as e:
                elementos.append(Paragraph(f"[Aviso] No se pudo insertar el mapa: {e}", self.styles['TextoNormal']))
                elementos.append(Spacer(1, 0.4*cm))

        # Tabla de municipios
        elementos.append(self.crear_tabla_municipios(municipios))
        elementos.append(Spacer(1, 1*cm))

        # Caminos por municipio (opcional)
        if self.caminos_data:
            elementos.append(Paragraph("Caminos por Municipio:", self.styles['Subtitulo']))
            for muni, caminos in self.caminos_data.items():
                caminos_str = ", ".join(caminos)
                elementos.append(Paragraph(f"<b>{muni}:</b> {caminos_str}", self.styles['ListaCaminos']))
                elementos.append(Spacer(1, 0.2*cm))
            elementos.append(Spacer(1, 1*cm))

        # Leyenda
        elementos.append(Paragraph("Leyenda de Estados:", self.styles['Subtitulo']))
        elementos.append(Paragraph("• <b>Verde:</b> Habilitado el tránsito pesado", self.styles['TextoNormal']))
        elementos.append(Paragraph("• <b>Amarillo:</b> Precaución / posible cierre", self.styles['TextoNormal']))
        elementos.append(Paragraph("• <b>Rojo:</b> Prohibido el tránsito pesado por lluvias", self.styles['TextoNormal']))
        elementos.append(Spacer(1, 1*cm))

        # Pie
        elementos.append(Paragraph(
            "Para más información, consulte el mapa interactivo en línea o contacte a las autoridades locales.",
            self.styles['TextoNormal']
        ))

        # Construir PDF
        doc.build(elementos)
        print(f"PDF generado exitosamente: {nombre_archivo}")
        return nombre_archivo


def _pick_geojson_local():
    """
    Devuelve la mejor ruta de GeoJSON disponible para el render del mapa.
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
    """Función principal para generar el PDF de ejemplo"""
    # (opcional) cargar datos de caminos
    caminos_json_path = "/home/ubuntu/upload/Caminos_Cerro_Largo_por_Municipio.json"
    caminos_data = {}
    if os.path.exists(caminos_json_path):
        with open(caminos_json_path, 'r', encoding='utf-8') as f:
            caminos_data = json.load(f)

    # Estados de ejemplo (en producción traelos de tu API/DB)
    states_map = {
        "ACEGUÁ": "green",
        "MANGRULLO": "yellow",
        "LA MICAELA": "red",
        "RÍO BRANCO": "green",
    }

    geojson_path = _pick_geojson_local()

    generador = ReporteEstadoMunicipios(caminos_data=caminos_data)
    generador.generar_pdf(
        nombre_archivo="reporte_ejemplo_municipios_con_mapa.pdf",
        municipios=None,
        states_map=states_map if geojson_path else None,
        geojson_path=geojson_path
    )


if __name__ == "__main__":
    main()
