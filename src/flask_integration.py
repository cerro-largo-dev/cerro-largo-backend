#!/usr/bin/env python3
"""
Integración Flask para la funcionalidad de generación de PDF
(versión saneada para no servir HTML ni estáticos)
"""

import os
import tempfile
from flask import Flask, jsonify, send_file, request
from flask_cors import CORS
from pdf_generator import ReporteEstadoMunicipios

# Deshabilitar carpeta estática para evitar servir /static/*
app = Flask(__name__, static_folder=None, static_url_path=None)
CORS(app)  # Permitir CORS para todas las rutas

# -------------------- Rutas API PDF --------------------

@app.route('/api/generar-reporte', methods=['POST'])
def generar_reporte():
    """
    Genera PDF de reporte de municipios.
    Espera JSON: {"municipios": [ ... ]}
    """
    try:
        data = request.get_json(silent=True) or {}
        municipios = data.get('municipios')
        generador = ReporteEstadoMunicipios()

        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
            archivo_pdf = generador.generar_pdf(tmp_file.name, municipios)
            return send_file(
                archivo_pdf,
                as_attachment=True,
                download_name='reporte_municipios.pdf',
                mimetype='application/pdf'
            )
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/generar-reporte-ejemplo', methods=['GET'])
def generar_reporte_ejemplo():
    """Genera un PDF de ejemplo con datos ficticios."""
    try:
        generador = ReporteEstadoMunicipios()
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
            archivo_pdf = generador.generar_pdf(tmp_file.name)
            return send_file(
                archivo_pdf,
                as_attachment=True,
                download_name='reporte_ejemplo_municipios.pdf',
                mimetype='application/pdf'
            )
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/health', methods=['GET'])
def health_check():
    """Verificación de salud del servicio."""
    return jsonify({'ok': True, 'service': 'pdf'}), 200

# -------------------- Endpoints no-HTML --------------------

@app.route('/', methods=['GET'])
def root():
    # Nunca servir HTML aquí
    return jsonify({'name': 'cerro-largo-backend', 'component': 'pdf', 'ok': True}), 200

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def catch_all(path):
    # Si alguien pega a /api/... inexistente → JSON 404 (no HTML)
    if path.startswith('api/'):
        return jsonify({'ok': False, 'error': 'not found', 'path': f'/{path}'}), 404
    # Para cualquier otra ruta fuera de /api → JSON simple
    return jsonify({'message': 'Servicio PDF activo'}), 200

# -------------------- Errores en JSON dentro de /api/* --------------------

@app.errorhandler(404)
def _not_found(e):
    if request.path.startswith('/api/'):
        return jsonify({'ok': False, 'error': 'not found', 'path': request.path}), 404
    return e, 404  # fuera de /api, comportamiento por defecto (o cambia si querés)

@app.errorhandler(405)
def _method_not_allowed(e):
    if request.path.startswith('/api/'):
        return jsonify({'ok': False, 'error': 'method not allowed', 'path': request.path}), 405
    return e, 405

# Nota: no incluimos app.run(...) para evitar un segundo servidor en producción.
# Si querés probar local:
#   FLASK_APP=flask_integration.py flask run --port 5001
