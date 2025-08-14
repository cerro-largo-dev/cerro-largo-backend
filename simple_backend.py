import os
from flask import Flask, jsonify, request
from flask_cors import CORS
from datetime import datetime, timedelta
from functools import wraps
import jwt

app = Flask(__name__)
app.config["SECRET_KEY"] = "super_secret_key"

CORS(app, supports_credentials=True, origins="*")

# In-memory data for demonstration
USERS = {
    "admin@example.com": {"id": 1, "email": "admin@example.com", "password": "admin123", "role": "ADMIN", "municipio_id": None, "is_active": True, "nombre": "Admin User"},
    "alcalde.melo@example.com": {"id": 2, "email": "alcalde.melo@example.com", "password": "alcalde123", "role": "ALCALDE", "municipio_id": "MELO", "is_active": True, "nombre": "Alcalde Melo"},
    "alcalde.arevalo@example.com": {"id": 3, "email": "alcalde.arevalo@example.com", "password": "alcalde123", "role": "ALCALDE", "municipio_id": "ARÉVALO", "is_active": True, "nombre": "Alcalde Arévalo"},
}

ZONE_STATES = {
    "MELO": {"zone_name": "MELO", "state": "green", "updated_at": datetime.now().isoformat(), "updated_by": "system"},
    "ARÉVALO": {"zone_name": "ARÉVALO", "state": "green", "updated_at": datetime.now().isoformat(), "updated_by": "system"},
    "ACEGUÁ": {"zone_name": "ACEGUÁ", "state": "green", "updated_at": datetime.now().isoformat(), "updated_by": "system"},
    "RÍO BRANCO": {"zone_name": "RÍO BRANCO", "state": "green", "updated_at": datetime.now().isoformat(), "updated_by": "system"},
}

# JWT and RBAC functions
def generate_token(user):
    payload = {
        "sub": user["id"],
        "email": user["email"],
        "role": user["role"],
        "municipio_id": user["municipio_id"],
        "exp": datetime.utcnow() + timedelta(hours=12)
    }
    return jwt.encode(payload, app.config["SECRET_KEY"], algorithm="HS256")

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if "Authorization" in request.headers:
            token = request.headers["Authorization"].split(" ")[1]
        if not token:
            return jsonify({"message": "Token is missing!"}), 401
        try:
            data = jwt.decode(token, app.config["SECRET_KEY"], algorithms=["HS256"])
            request.current_user = USERS.get(data["email"])
            if not request.current_user:
                return jsonify({"message": "User not found!"}), 401
        except jwt.ExpiredSignatureError:
            return jsonify({"message": "Token has expired!"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"message": "Token is invalid!"}), 401
        return f(*args, **kwargs)
    return decorated

def require_roles(*roles):
    def wrapper(fn):
        @wraps(fn)
        @token_required
        def inner(*args, **kwargs):
            if request.current_user["role"] not in roles:
                return jsonify({"message": "Forbidden: Insufficient permissions"}), 403
            return fn(*args, **kwargs)
        return inner
    return wrapper

# Routes
@app.route("/api/admin/login", methods=["POST"])
def login():
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")
    user = USERS.get(email)
    if not user or user["password"] != password:
        return jsonify({"message": "Invalid credentials"}), 401
    if not user["is_active"]:
        return jsonify({"message": "User account is inactive"}), 401
    token = generate_token(user)
    return jsonify({"token": token, "role": user["role"], "municipio_id": user["municipio_id"]}), 200

@app.route("/api/admin/check-auth", methods=["GET"])
@token_required
def check_auth():
    user = request.current_user
    return jsonify({
        "authenticated": True,
        "role": user["role"],
        "municipio_id": user["municipio_id"]
    }), 200

@app.route("/api/admin/zones/states", methods=["GET"])
@require_roles("ADMIN", "ALCALDE")
def get_zone_states():
    user = request.current_user
    if user["role"] == "ALCALDE" and user["municipio_id"]:
        # Alcalde can only see their assigned municipality
        if user["municipio_id"] in ZONE_STATES:
            return jsonify({"success": True, "states": {user["municipio_id"]: ZONE_STATES[user["municipio_id"]]}}), 200
        else:
            return jsonify({"success": True, "states": {}}), 200 # No zones for this alcalde
    return jsonify({"success": True, "states": ZONE_STATES}), 200

@app.route("/api/admin/zones/update-state", methods=["POST"])
@require_roles("ADMIN", "ALCALDE")
def update_zone_state():
    data = request.get_json()
    zone_name = data.get("zone_name")
    state = data.get("state")
    if not zone_name or not state:
        return jsonify({"success": False, "message": "Nombre de zona y estado son requeridos"}), 400
    if state not in ["green", "yellow", "red"]:
        return jsonify({"success": False, "message": "Estado debe ser green, yellow o red"}), 400
    user = request.current_user
    if user["role"] == "ALCALDE" and user["municipio_id"] != zone_name:
        return jsonify({"success": False, "message": "Forbidden: Alcalde can only update their assigned municipality"}), 403
    
    if zone_name in ZONE_STATES:
        ZONE_STATES[zone_name]["state"] = state
        ZONE_STATES[zone_name]["updated_at"] = datetime.now().isoformat()
        ZONE_STATES[zone_name]["updated_by"] = user["email"]
        return jsonify({"success": True, "message": "Estado actualizado correctamente", "zone": ZONE_STATES[zone_name]}), 200
    else:
        return jsonify({"success": False, "message": "Zona no encontrada"}), 404

@app.route("/api/admin/zones/bulk-update", methods=["POST"])
@require_roles("ADMIN", "ALCALDE")
def bulk_update_zones():
    data = request.get_json()
    updates = data.get("updates", [])
    if not updates:
        return jsonify({"success": False, "message": "No se proporcionaron actualizaciones"}), 400
    user = request.current_user
    updated_zones = []
    for update in updates:
        zone_name = update.get("zone_name")
        state = update.get("state")
        if user["role"] == "ALCALDE" and user["municipio_id"] != zone_name:
            return jsonify({"success": False, "message": "Forbidden: Alcalde can only bulk update their assigned municipality"}), 403
        if zone_name in ZONE_STATES and state in ["green", "yellow", "red"]:
            ZONE_STATES[zone_name]["state"] = state
            ZONE_STATES[zone_name]["updated_at"] = datetime.now().isoformat()
            ZONE_STATES[zone_name]["updated_by"] = user["email"]
            updated_zones.append(ZONE_STATES[zone_name])
    return jsonify({"success": True, "message": f"Se actualizaron {len(updated_zones)} zonas", "updated_zones": updated_zones}), 200

@app.route("/api/admin/users/alcalde", methods=["POST"])
@require_roles("ADMIN")
def create_alcalde_user():
    data = request.get_json()
    email = data.get("email")
    nombre = data.get("nombre")
    municipio_id = data.get("municipio_id")
    password = data.get("password")
    if not all([email, nombre, municipio_id, password]):
        return jsonify({"message": "Email, nombre, municipio_id and password are required"}), 400
    if email in USERS:
        return jsonify({"message": "User with this email already exists"}), 409
    if municipio_id not in ZONE_STATES:
        return jsonify({"message": "Invalid municipio_id"}), 400
    
    new_id = max(u["id"] for u in USERS.values()) + 1 if USERS else 1
    USERS[email] = {
        "id": new_id,
        "email": email,
        "nombre": nombre,
        "password": password, # In a real app, hash this!
        "role": "ALCALDE",
        "municipio_id": municipio_id,
        "is_active": True
    }
    return jsonify({"message": "Alcalde user created successfully", "user": USERS[email]}), 201

@app.route("/api/admin/users", methods=["GET"])
@require_roles("ADMIN")
def get_all_users():
    return jsonify(list(USERS.values())), 200

@app.route("/api/admin/users/<int:user_id>", methods=["PUT"])
@require_roles("ADMIN")
def update_user(user_id):
    user_to_update = None
    for email, user_data in USERS.items():
        if user_data["id"] == user_id:
            user_to_update = user_data
            break
    
    if not user_to_update:
        return jsonify({"message": "User not found"}), 404

    data = request.get_json()
    user_to_update["email"] = data.get("email", user_to_update["email"])
    user_to_update["nombre"] = data.get("nombre", user_to_update["nombre"])
    user_to_update["role"] = data.get("role", user_to_update["role"])
    user_to_update["municipio_id"] = data.get("municipio_id", user_to_update["municipio_id"])
    user_to_update["is_active"] = data.get("is_active", user_to_update["is_active"])
    
    if user_to_update["role"] == "ALCALDE" and not user_to_update["municipio_id"]:
        return jsonify({"message": "municipio_id is required for ALCALDE role"}), 400
    if "password" in data and data["password"]:
        user_to_update["password"] = data["password"]
    
    return jsonify({"message": "User updated successfully", "user": user_to_update}), 200

@app.route("/api/admin/users/<int:user_id>", methods=["DELETE"])
@require_roles("ADMIN")
def delete_user(user_id):
    user_to_delete_email = None
    for email, user_data in USERS.items():
        if user_data["id"] == user_id:
            user_to_delete_email = email
            break
    
    if not user_to_delete_email:
        return jsonify({"message": "User not found"}), 404
    
    del USERS[user_to_delete_email]
    return jsonify({"message": "User deleted successfully"}), 200

@app.route("/api/health")
def health_check():
    return jsonify({"status": "healthy", "service": "cerro-largo-backend-simplified"}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)


