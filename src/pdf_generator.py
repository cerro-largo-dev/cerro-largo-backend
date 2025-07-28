
#!/usr/bin/env python3
"""
Generador de PDF para reportes de estado de municipios de Cerro Largo
"""

from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, cm
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from datetime import datetime
import os
import json

class ReporteEstadoMunicipios:
    def __init__(self, logo_path="alexlogo.png", caminos_data=None):
        self.logo_path = logo_path
        self.caminos_data = caminos_data if caminos_data is not None else {}
        self.styles = getSampleStyleSheet()
        self.setup_custom_styles()
        
    def setup_custom_styles(self):
        """Configurar estilos personalizados para el PDF"""
        # Estilo para el título principal
        self.styles.add(ParagraphStyle(
            name='TituloReporte',
            parent=self.styles['Title'],
            fontSize=18,
            spaceAfter=20,
            alignment=TA_CENTER,
            textColor=colors.HexColor('#1f4e79')
        ))
        
        # Estilo para subtítulos
        self.styles.add(ParagraphStyle(
            name='Subtitulo',
            parent=self.styles['Heading2'],
            fontSize=14,
            spaceAfter=12,
            textColor=colors.HexColor('#2e75b6')
        ))
        
        # Estilo para texto normal
        self.styles.add(ParagraphStyle(
            name='TextoNormal',
            parent=self.styles['Normal'],
            fontSize=11,
            spaceAfter=6,
            alignment=TA_LEFT
        ))
        
        # Estilo para fecha y hora
        self.styles.add(ParagraphStyle(
            name='FechaHora',
            parent=self.styles['Normal'],
            fontSize=10,
            alignment=TA_RIGHT,
            textColor=colors.grey
        ))

        # Estilo para lista de caminos (ahora para una sola línea)
        self.styles.add(ParagraphStyle(
            name='ListaCaminos',
            parent=self.styles['Normal'],
            fontSize=10,
            leftIndent=0.5*cm,
            spaceBefore=3,
            spaceAfter=3,
        ))

    def generar_datos_ejemplo(self):
        """Generar datos de ejemplo para los municipios"""
        municipios = [
            {"nombre": "Melo", "estado": "Habilitado", "color": "Verde", "alerta": "Sin restricciones"},
            {"nombre": "Río Branco", "estado": "Habilitado", "color": "Verde", "alerta": "Sin restricciones"},
            {"nombre": "Fraile Muerto", "estado": "Habilitado", "color": "Verde", "alerta": "Sin restricciones"},
            {"nombre": "Isidoro Noblía", "estado": "Precaución", "color": "Amarillo", "alerta": "Posible cierre de caminería"},
            {"nombre": "Aceguá", "estado": "Habilitado", "color": "Verde", "alerta": "Sin restricciones"},
            {"nombre": "Tupambaé", "estado": "Habilitado", "color": "Verde", "alerta": "Sin restricciones"},
            {"nombre": "Arbolito", "estado": "Habilitado", "color": "Verde", "alerta": "Sin restricciones"},
            {"nombre": "Placido Rosas", "estado": "Habilitado", "color": "Verde", "alerta": "Sin restricciones"},
            {"nombre": "Ramón Trigo", "estado": "Habilitado", "color": "Verde", "alerta": "Sin restricciones"},
            {"nombre": "Lago Merín", "estado": "Habilitado", "color": "Verde", "alerta": "Sin restricciones"}
        ]
        return municipios

    def crear_tabla_municipios(self, municipios):
        """Crear tabla con el estado de los municipios"""
        # Encabezados de la tabla
        data = [['Municipio', 'Estado', 'Color', 'Alerta']]
        
        # Agregar datos de municipios
        for municipio in municipios:
            data.append([
                municipio['nombre'],
                municipio['estado'],
                municipio['color'],
                municipio['alerta']
            ])
        
        # Crear tabla
        tabla = Table(data, colWidths=[4*cm, 3*cm, 2.5*cm, 6*cm])
        
        # Estilo de la tabla
        tabla.setStyle(TableStyle([
            # Encabezado
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4e79')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            
            # Cuerpo de la tabla
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            
            # Alternar colores de filas
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
        ]))
        
        return tabla

    def generar_pdf(self, nombre_archivo="reporte_municipios.pdf", municipios=None):
        """Generar el PDF del reporte"""
        if municipios is None:
            municipios = self.generar_datos_ejemplo()
        
        # Crear documento
        doc = SimpleDocTemplate(
            nombre_archivo,
            pagesize=A4,
            rightMargin=2*cm,
            leftMargin=2*cm,
            topMargin=2*cm,
            bottomMargin=2*cm
        )
        
        # Lista de elementos del documento
        elementos = []
        
        # Logo del gobierno (si existe)
        if os.path.exists(self.logo_path):
            try:
                logo = Image(self.logo_path, width=8*cm, height=2*cm)
                logo.hAlign = 'CENTER'
                elementos.append(logo)
                elementos.append(Spacer(1, 0.5*cm))
            except Exception as e:
                print(f"Error al cargar el logo: {e}")
        
        # Título del reporte
        titulo = Paragraph("Reporte de Estado de Municipios", self.styles['TituloReporte'])
        elementos.append(titulo)
        elementos.append(Spacer(1, 0.3*cm))
        
        # Subtítulo con departamento
        subtitulo = Paragraph("Departamento de Cerro Largo", self.styles['Subtitulo'])
        elementos.append(subtitulo)
        elementos.append(Spacer(1, 0.5*cm))
        
        # Fecha y hora de generación
        fecha_hora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        fecha_texto = Paragraph(f"Generado el: {fecha_hora}", self.styles['FechaHora'])
        elementos.append(fecha_texto)
        elementos.append(Spacer(1, 1*cm))
        
        # Descripción del reporte
        descripcion = Paragraph(
            "Este reporte muestra el estado actual de todos los municipios del departamento de Cerro Largo, "
            "incluyendo el estado de tránsito pesado y las alertas vigentes.",
            self.styles['TextoNormal']
        )
        elementos.append(descripcion)
        elementos.append(Spacer(1, 0.5*cm))
        
        # Tabla con el estado de los municipios
        tabla = self.crear_tabla_municipios(municipios)
        elementos.append(tabla)
        elementos.append(Spacer(1, 1*cm))

        # Sección de Caminos por Municipio
        if self.caminos_data:
            elementos.append(Paragraph("Caminos por Municipio:", self.styles['Subtitulo']))
            for municipio_nombre, caminos in self.caminos_data.items():
                caminos_str = ", ".join(caminos)
                elementos.append(Paragraph(f"<b>{municipio_nombre}:</b> {caminos_str}", self.styles['ListaCaminos']))
                elementos.append(Spacer(1, 0.2*cm))
            elementos.append(Spacer(1, 1*cm))
        
        # Leyenda de colores
        leyenda_titulo = Paragraph("Leyenda de Estados:", self.styles['Subtitulo'])
        elementos.append(leyenda_titulo)
        
        leyenda_verde = Paragraph("• <b>Verde:</b> Habilitado el tránsito pesado", self.styles['TextoNormal'])
        leyenda_amarillo = Paragraph("• <b>Amarillo:</b> Posible cierre de caminería", self.styles['TextoNormal'])
        leyenda_rojo = Paragraph("• <b>Rojo:</b> Prohibido el tránsito pesado por lluvias", self.styles['TextoNormal'])
        
        elementos.append(leyenda_verde)
        elementos.append(leyenda_amarillo)
        elementos.append(leyenda_rojo)
        elementos.append(Spacer(1, 1*cm))
        
        # Pie de página con información adicional
        pie_info = Paragraph(
            "Para más información, consulte el mapa interactivo en línea o contacte a las autoridades locales.",
            self.styles['TextoNormal']
        )
        elementos.append(pie_info)
        
        # Construir el PDF
        doc.build(elementos)
        print(f"PDF generado exitosamente: {nombre_archivo}")
        return nombre_archivo

def main():
    """Función principal para generar el PDF de ejemplo"""
    # Cargar datos de caminos desde el archivo JSON
    caminos_json_path = "/home/ubuntu/upload/Caminos_Cerro_Largo_por_Municipio.json"
    caminos_data = {}
    if os.path.exists(caminos_json_path):
        with open(caminos_json_path, 'r', encoding='utf-8') as f:
            caminos_data = json.load(f)

    generador = ReporteEstadoMunicipios(caminos_data=caminos_data)
    archivo_pdf = generador.generar_pdf("reporte_ejemplo_municipios_con_caminos_conciso.pdf")
    return archivo_pdf

if __name__ == "__main__":
    main()


