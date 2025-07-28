#!/usr/bin/env python3
"""
Integración Flask para la funcionalidad de generación de PDF
"""

from flask import Flask, jsonify, send_file, request
from flask_cors import CORS
import os
import tempfile
from pdf_generator import ReporteEstadoMunicipios

app = Flask(__name__)
CORS(app)  # Permitir CORS para todas las rutas

@app.route('/api/generar-reporte', methods=['POST'])
def generar_reporte():
    """
    Endpoint para generar el PDF del reporte de municipios
    
    Espera un JSON con la estructura:
    {
        "municipios": [
            {
                "nombre": "Melo",
                "estado": "Habilitado",
                "color": "Verde",
                "alerta": "Sin restricciones"
            },
            ...
        ]
    }
    """
    try:
        # Obtener datos del request
        data = request.get_json()
        municipios = data.get('municipios', None) if data else None
        
        # Crear generador de PDF
        generador = ReporteEstadoMunicipios()
        
        # Crear archivo temporal para el PDF
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
            archivo_pdf = generador.generar_pdf(tmp_file.name, municipios)
            
            # Enviar el archivo PDF como respuesta
            return send_file(
                archivo_pdf,
                as_attachment=True,
                download_name='reporte_municipios.pdf',
                mimetype='application/pdf'
            )
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/generar-reporte-ejemplo', methods=['GET'])
def generar_reporte_ejemplo():
    """
    Endpoint para generar un PDF de ejemplo con datos ficticios
    """
    try:
        # Crear generador de PDF
        generador = ReporteEstadoMunicipios()
        
        # Crear archivo temporal para el PDF
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
            archivo_pdf = generador.generar_pdf(tmp_file.name)
            
            # Enviar el archivo PDF como respuesta
            return send_file(
                archivo_pdf,
                as_attachment=True,
                download_name='reporte_ejemplo_municipios.pdf',
                mimetype='application/pdf'
            )
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    """Endpoint de verificación de salud del servicio"""
    return jsonify({'status': 'ok', 'message': 'Servicio de generación de PDF funcionando'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

