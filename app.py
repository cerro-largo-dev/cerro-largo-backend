import os
import logging
from flask import Flask, jsonify, request
from flask_cors import CORS
from src.models import db
from src.models.user import User, ph
from src.models.zone_state import ZoneState
from datetime import datetime, timedelta
from functools import wraps
import jwt

# ------- App & Config --------
def create_app():
    app = Flask(__name__)

    # 🔒 SECRET_KEY: debe venir del entorno (Render: Settings → Environment)
    # Ej.: SECRET_KEY=cerrolargo2025
    try:
        app.config["SECRET_KEY"] = os.environ["SECRET_KEY"]
    except KeyError:
        raise RuntimeError(
            "SECRET_KEY no seteada en el entorno. Define SECRET_KEY=cerrolargo2025 en Render."
        )

    # Base de datos (igual que tenías)
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{os.path.join(os.path.dirname(__file__), 'database', 'app.db')}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # CORS: lista explícita de orígenes (evitar '*'+credentials)
    CORS(
        app,
        supports_credentials=True,
        resources={r"/api/*": {"origins": [
            "https://cerro-largo-frontend.onrender.com",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]}}
    )

    # Init DB
    db.init_app(app)

    # Ensure database dir
    os.makedirs(os.path.join(os.path.dirname(__file__), 'database'), exist_ok=True)

    # Datos iniciales
    with app.app_context():
        db.create_all()

        if ZoneState.query.count() == 0:
            municipios_default = [
                'ACEGUÁ', 'ARBOLITO', 'BAÑADO DE MEDINA', 'CERRO DE LAS CUENTAS',
                'FRAILE MUERTO', 'ISIDORO NOBLÍA', 'LAGO MERÍN', 'LAS CAÑAS',
                'MELO', 'PLÁCIDO ROSAS', 'RÍO BRANCO', 'TUPAMBAÉ',
                'ARÉVALO', 'NOBLÍA', 'Melo (GBB)', 'Melo (GCB)'
            ]
            for municipio in municipios_default:
                ZoneState.update_zone_state(municipio, 'green', 'sistema')
            print(f"Inicializados {len(municipios_default)} municipios con estado 'green'")

        if not User.query.filter_by(email='admin@cerrolargo.gub.uy').first():
            admin_user = User(
                email='admin@cerrolargo.gub.uy',
                nombre='Administrador Principal',
                role='ADMIN',
                municipio_id=None,
                force_password_reset=False,
                is_active=True
            )
            admin_user.set_password('admin2025')
            db.session.add(admin_user)
            db.session.commit()
            print('Usuario ADMIN inicial creado.')

    # ------- Helpers JWT/RBAC --------
    logger = logging.getLogger(__name__)

    def _extract_token():
        """Obtiene el token del header Authorization.
        Acepta 'Bearer <token>' o el token sin prefijo."""
        auth = request.headers.get("Authorization", "").strip()
        if not auth:
            return None
        if auth.lower().startswith("bearer "):
            return auth.split(" ", 1)[1].strip()
        return auth

    def _decode_jwt(token):
        """Decodifica JWT con pequeña tolerancia de reloj (leeway)."""
        return jwt.decode(
            token,
            app.config["SECRET_KEY"],
            algorithms=["HS256"],
            leeway=30  # 30s de margen
        )

    def generate_token(user):
        payload = {
            "sub": user.id,
            "email": user.email,
            "role": user.role,
            "municipio_id": user.municipio_id,
            "exp": datetime.utcnow() + timedelta(hours=12)
        }
        return jwt.encode(payload, app.config["SECRET_KEY"], algorithm="HS256")

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
        user = request.current_user
        if user.role == "ALCALDE" and user.municipio_id:
            if hasattr(model_class, 'zone_name'):
                return query.filter(model_class.zone_name == user.municipio_id)
            elif hasattr(model_class, 'municipio_id'):
                return query.filter(model_class.municipio_id == user.municipio_id)
        return query

    # ------- Rutas --------
    @app.route("/api/admin/login", methods=["POST"])
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

    @app.route("/api/admin/check-auth", methods=["GET"])
    @token_required
    def check_auth():
        user = request.current_user
        return jsonify({
            "authenticated": True,
            "role": user.role,
            "municipio_id": user.municipio_id
        }), 200

    @app.route("/api/admin/zones/states", methods=["GET"])
    @require_roles("ADMIN", "ALCALDE")
    def get_zone_states():
        try:
            query = ZoneState.query
            query = alcalde_scope(query, ZoneState)
            states = {zone.zone_name: zone.to_dict() for zone in query.all()}
            return jsonify({"success": True, "states": states}), 200
        except Exception as e:
            return jsonify({"success": False, "message": f"Error al obtener estados: {str(e)}"}), 500

    @app.route("/api/admin/zones/update-state", methods=["POST"])
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
            else:
                return jsonify({"success": False, "message": "Error al actualizar o crear la zona"}), 500
        except Exception as e:
            return jsonify({"success": False, "message": f"Error al actualizar estado: {str(e)}"}), 500

    @app.route("/api/admin/zones/bulk-update", methods=["POST"])
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
                if zone_name and state and state in ["green", "yellow", "red"]:
                    updated_zone = ZoneState.update_zone_state(zone_name, state, user.email)
                    if updated_zone:
                        updated_zones.append(updated_zone.to_dict())
            return jsonify({"success": True, "message": f"Se actualizaron {len(updated_zones)} zonas", "updated_zones": updated_zones}), 200
        except Exception as e:
            return jsonify({"success": False, "message": f"Error en actualización masiva: {str(e)}"}), 500

    @app.route("/api/admin/users/alcalde", methods=["POST"])
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

    @app.route("/api/admin/users", methods=["GET"])
    @require_roles("ADMIN")
    def get_all_users():
        users = User.query.all()
        return jsonify([user.to_dict() for user in users]), 200

    @app.route("/api/admin/users/<int:user_id>", methods=["PUT"])
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

    @app.route("/api/admin/users/<int:user_id>", methods=["DELETE"])
    @require_roles("ADMIN")
    def delete_user(user_id):
        user = User.query.get_or_404(user_id)
        db.session.delete(user)
        db.session.commit()
        return jsonify({"message": "User deleted successfully"}), 200

    @app.route("/api/admin/password-reset", methods=["POST"])
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

    @app.route("/api/health")
    def health_check():
        return jsonify({"status": "healthy", "service": "cerro-largo-backend"}), 200

    return app


# Render ejecuta 'app'
app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
