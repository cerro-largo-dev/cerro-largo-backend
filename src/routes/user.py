from flask import Blueprint, jsonify
from src.models.zone_state import ZoneState

user_bp = Blueprint("user", __name__)

# Rutas públicas de consulta (sin auth)
@user_bp.route("/zones", methods=["GET"])
def list_zones_public():
    zones = ZoneState.query.all()
    return jsonify([z.to_dict() for z in zones]), 200
