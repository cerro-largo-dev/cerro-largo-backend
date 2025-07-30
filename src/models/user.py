from flask import Blueprint, request, jsonify, session
from src.models.zone_state import ZoneState

user_bp = Blueprint('user', __name__)

@user_bp.route('/zones', methods=['GET'])
def get_zones():
    """Obtener todos los estados de zonas - disponible para todos los usuarios"""
    try:
        states = ZoneState.get_all_states()
        return jsonify({
            'success': True,
            'zones': states
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error al obtener zonas: {str(e)}'
        }), 500

@user_bp.route('/zones/<zone_name>', methods=['GET'])
def get_zone_state(zone_name):
    """Obtener el estado de una zona específica"""
    try:
        zone = ZoneState.query.filter_by(zone_name=zone_name).first()
        if zone:
            return jsonify({
                'success': True,
                'zone': zone.to_dict()
            }), 200
        else:
            return jsonify({
                'success': False,
                'message': 'Zona no encontrada'
            }), 404
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error al obtener zona: {str(e)}'
        }), 500
