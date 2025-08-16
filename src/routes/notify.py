# src/routes/notify.py
import os
import json
import re
from datetime import datetime, timezone
from threading import Lock
from flask import Blueprint, request, jsonify

notify_bp = Blueprint("notify", __name__)

# Archivo donde persistimos suscripciones (stub)
SUBS_STORE_PATH = os.environ.get("SUBS_STORE_PATH", "/tmp/subscribers.json")

# Lock simple para escrituras concurrentes
_store_lock = Lock()

# Regex E.164 (ej: +598...)
E164_RE = re.compile(r"^\+?[1-9]\d{6,14}$")

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

def _read_store() -> list:
    if not os.path.exists(SUBS_STORE_PATH):
        return []
    try:
        with open(SUBS_STORE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []

def _write_store(rows: list) -> None:
    os.makedirs(os.path.dirname(SUBS_STORE_PATH), exist_ok=True)
    tmp = SUBS_STORE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    os.replace(tmp, SUBS_STORE_PATH)

@notify_bp.route("/subscribe", methods=["POST"])
def subscribe():
    """
    Stub seguro para pre-registrar interesados en WhatsApp:
      Body: { phone: string, zones: string[], consent: boolean }
      -> 200 { success: true }
    """
    data = request.get_json(silent=True) or {}
    phone = str(data.get("phone") or "").strip()
    zones = data.get("zones") or []
    consent = bool(data.get("consent"))

    # Validaciones mínimas
    if not phone or not E164_RE.match(phone):
        return jsonify({"success": False, "message": "Teléfono inválido. Formato E.164 (+598...)." }), 400
    if not isinstance(zones, list) or not zones or not all(isinstance(z, str) and z.strip() for z in zones):
        return jsonify({"success": False, "message": "Debe seleccionar al menos una zona."}), 400
    if not consent:
        return jsonify({"success": False, "message": "Debe aceptar el consentimiento."}), 400

    # Normalizar zonas (trim)
    zones = [z.strip() for z in zones if isinstance(z, str) and z.strip()]

    # Persistencia simple en JSON (upsert por phone)
    with _store_lock:
        rows = _read_store()
        idx = next((i for i, r in enumerate(rows) if r.get("phone_e164") == phone), None)
        row = {
            "phone_e164": phone,
            "zones": zones,
            "consent": True,
            "active": True,
            "created_at": _utc_now_iso(),
            "verified_at": None
        }
        if idx is None:
            rows.append(row)
        else:
            # Update manteniendo created_at previo si existe
            prev = rows[idx]
            row["created_at"] = prev.get("created_at") or row["created_at"]
            rows[idx] = row
        _write_store(rows)

    return jsonify({"success": True}), 200
