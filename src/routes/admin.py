from flask import Blueprint, request, jsonify, current_app
from src.models.zone_state import ZoneState, db
from src.models.user import User, ph
from datetime import datetime, timedelta
from functools import wraps
import logging
import jwt

logger = logging.getLogger(__name__)

admin_bp = Blueprint("admin", __name__)

# ---------------- JWT helpers ----------------

def _extract_token():
    """Obtiene el token desde Authorization. Acepta 'Bearer <token>' o el token directo."""
    auth = request.headers.get("Authorization", "").strip()
    if not auth:
        return None
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    return auth

def _decode_jwt(token):
    """Decodifica con pequeña tolerancia de reloj para evitar falsos expirados."""
    return jwt.decode(
        token,
        current_app.config["SECRET_KEY"],
        algorithms=["HS256"],
        leeway=30,  # segundos
    )

def generate_token(user: User):
    payload = {
        "sub": user.id,
        "email": user.email,
        "role": user.role,
        "municipio_id": user.municipio_id,  # None para ADMIN
        "exp": datetime.utcnow() + timedelta(hours=12),
    }
    return jwt.encode(payload, current_app.config["SECRET_KEY"], algorithm="HS256")

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = _extract_token()
        if not token:
            return jsonify({"message": "Token is missing!"}), 401
        try:
            data = _decode_jwt(token)
            current_user = User.query.get(data.get("sub"))
            if not current_user:
                return jsonify({"message": "User not found!"}), 401
            request.current_user = current_user
        except jwt.ExpiredSignatureError:
            logger.warning("JWT expired")
            return jsonify({"message": "Token has expired!"}), 401
        except jwt.InvalidTokenError as e:
            logger.warning(f"JWT invalid: {e}")
            return jsonify({"message": "Token is invalid!"}), 401
        return f(*args, **kwargs)
    return decorated

def require_roles(*roles):
    def wrapper(fn):
        @wraps(fn)
        @token_required
        def inner(*args, **kwargs):
            if request.current_user.role not in roles:
                return jsonify({"message": "Forbidden: Insufficient permissions"}), 403
            return fn(*args, **kwargs)
        return inner
    return wrapper

def alcalde_scope(query, model_class):
    """Restringe datos a su municipio si el usuario es ALCALDE."""
    user = request.current_user
    if user.role == "ALCALDE" and user.municipio_id:
        if hasattr(model_class, "zone_name"):
            return query.filter(model_class.zone_name == user.municipio_id)
        if hasattr(model_class, "municipio_id"):
            return query.filter(model_class.municipio_id == user.municipio_id)
    return query

# ---------------- Rutas Auth ----------------

@admin_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    email = data.get("email")
    password = data.get("password")

    if not email or not password:
        return jsonify({"message": "Email and password are required"}), 400

    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(password):
        return jsonify({"message": "Invalid credentials"}), 401
    if not user.is_active:
        return jsonify({"message": "User account is inactive"}), 401

    token = generate_token(user)
    return jsonify({"token": token, "role": user.role, "municipio_id": user.municipio_id}), 200

@admin_bp.route("/check-auth", methods=["GET"])
@token_required
def check_auth():
    user = request.current_user
    return jsonify({
        "authenticated": True,
        "role": user.role,
        "municipio_id": user.municipio_id
    }), 200

# ---------------- Zonas ----------------

@admin_bp.route("/zones/states", methods=["GET"])
@require_roles("ADMIN", "ALCALDE")
def get_zone_states():
    try:
        query = ZoneState.query
        query = alcalde_scope(query, ZoneState)
        states = {zone.zone_name: zone.to_dict() for zone in query.all()}
        return jsonify({"success": True, "states": states}), 200
    except Exception as e:
        logger.exception("Error al obtener estados")
        return jsonify({"success": False, "message": f"Error al obtener estados: {str(e)}"}), 500

@admin_bp.route("/zones/update-state", methods=["POST"])
@require_roles("ADMIN", "ALCALDE")
def update_zone_state():
    try:
        data = request.get_json() or {}
        zone_name = data.get("zone_name")
        state = data.get("state")

        if not zone_name or not state:
            return jsonify({"success": False, "message": "Nombre de zona y estado son requeridos"}), 400
        if state not in ["green", "yellow", "red"]:
            return jsonify({"success": False, "message": "Estado debe ser green, yellow o red"}), 400

        user = request.current_user
        if user.role == "ALCALDE" and user.municipio_id != zone_name:
            return jsonify({"success": False, "message": "Forbidden: Alcalde can only update their assigned municipality"}), 403

        updated_zone = ZoneState.update_zone_state(zone_name, state, user.email)
        if updated_zone:
            return jsonify({"success": True, "message": "Estado actualizado correctamente", "zone": updated_zone.to_dict()}), 200
        return jsonify({"success": False, "message": "Error al actualizar o crear la zona"}), 500

    except Exception as e:
        logger.exception("Error al actualizar estado")
        return jsonify({"success": False, "message": f"Error al actualizar estado: {str(e)}"}), 500

@admin_bp.route("/zones/bulk-update", methods=["POST"])
@require_roles("ADMIN", "ALCALDE")
def bulk_update_zones():
    try:
        data = request.get_json() or {}
        updates = data.get("updates", [])
        if not updates:
            return jsonify({"success": False, "message": "No se proporcionaron actualizaciones"}), 400

        user = request.current_user
        updated_zones = []
        for update in updates:
            zone_name = update.get("zone_name")
            state = update.get("state")

            if user.role == "ALCALDE" and user.municipio_id != zone_name:
                return jsonify({"success": False, "message": "Forbidden: Alcalde can only bulk update their assigned municipality"}), 403

            if zone_name and state in ["green", "yellow", "red"]:
                updated_zone = ZoneState.update_zone_state(zone_name, state, user.email)
                if updated_zone:
                    updated_zones.append(updated_zone.to_dict())

        return jsonify({"success": True, "message": f"Se actualizaron {len(updated_zones)} zonas", "updated_zones": updated_zones}), 200
    except Exception as e:
        logger.exception("Error en bulk update")
        return jsonify({"success": False, "message": f"Error en actualización masiva: {str(e)}"}), 500

# ---------------- Usuarios ----------------

@admin_bp.route("/users/alcalde", methods=["POST"])
@require_roles("ADMIN")
def create_alcalde_user():
    data = request.get_json() or {}
    email = data.get("email")
    nombre = data.get("nombre")
    municipio_id = data.get("municipio_id")
    password = data.get("password")

    if not all([email, nombre, municipio_id, password]):
        return jsonify({"message": "Email, nombre, municipio_id and password are required"}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({"message": "User with this email already exists"}), 409

    if not ZoneState.query.filter_by(zone_name=municipio_id).first():
        return jsonify({"message": "Invalid municipio_id"}), 400

    new_user = User(
        email=email,
        nombre=nombre,
        role="ALCALDE",
        municipio_id=municipio_id,
        force_password_reset=True,
        is_active=True
    )
    new_user.set_password(password)

    db.session.add(new_user)
    db.session.commit()

    return jsonify({"message": "Alcalde user created successfully", "user": new_user.to_dict()}), 201

@admin_bp.route("/users", methods=["GET"])
@require_roles("ADMIN")
def get_all_users():
    users = User.query.all()
    return jsonify([user.to_dict() for user in users]), 200

@admin_bp.route("/users/<int:user_id>", methods=["PUT"])
@require_roles("ADMIN")
def update_user(user_id):
    user = User.query.get_or_404(user_id)
    data = request.get_json() or {}

    user.email = data.get("email", user.email)
    user.nombre = data.get("nombre", user.nombre)
    user.role = data.get("role", user.role)
    user.municipio_id = data.get("municipio_id", user.municipio_id)
    user.is_active = data.get("is_active", user.is_active)

    if user.role == "ALCALDE" and not user.municipio_id:
        return jsonify({"message": "municipio_id is required for ALCALDE role"}), 400

    if "password" in data and data["password"]:
        user.set_password(data["password"])
        user.force_password_reset = True

    db.session.commit()
    return jsonify({"message": "User updated successfully", "user": user.to_dict()}), 200

@admin_bp.route("/users/<int:user_id>", methods=["DELETE"])
@require_roles("ADMIN")
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    return jsonify({"message": "User deleted successfully"}), 200

# ---------------- Password ----------------

@admin_bp.route("/password-reset", methods=["POST"])
@token_required
def password_reset():
    user = request.current_user
    data = request.get_json() or {}
    new_password = data.get("new_password")

    if not new_password:
        return jsonify({"message": "New password is required"}), 400

    user.set_password(new_password)
    user.force_password_reset = False
    db.session.commit()

    return jsonify({"message": "Password reset successfully"}), 200
