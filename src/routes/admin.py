
from flask import Blueprint, request, jsonify
import hashlib

admin_bp = Blueprint('admin', __name__)

# Usuario y contraseña (password con hash SHA-256)
ADMIN_CREDENTIALS = {
    'admin': hashlib.sha256('cerrolargo2025'.encode()).hexdigest()
}

@admin_bp.route('/api/admin/login', methods=['POST'])
def admin_login():
    if not request.is_json:
        return jsonify({'success': False, 'message': 'Formato no válido. Esperado: JSON'}), 400

    data = request.get_json(silent=True) or {}
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({'success': False, 'message': 'Usuario y contraseña requeridos'}), 400

    password_hash = hashlib.sha256(password.encode()).hexdigest()
    stored_hash = ADMIN_CREDENTIALS.get(username)

    if stored_hash == password_hash:
        return jsonify({'success': True, 'message': 'Autenticación correcta'}), 200
    else:
        return jsonify({'success': False, 'message': 'Credenciales incorrectas'}), 401
