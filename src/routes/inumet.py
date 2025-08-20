# src/routes/inumet.py
# -*- coding: utf-8 -*-
"""
INUMET alerts router (WIS2 / OGC API)
- Lee cap-alerts/items con los campos del schema oficial
- Si viene vacío, consulta 'messages' por metadata_id y genera una alerta sintética
- Filtro textual por Cerro Largo (si la descripción/nombre lo mencionan)
- ?debug=1 devuelve métricas

Requisitos:
  - requests
"""

import os
import time
import json
import unicodedata

import requests
from flask import Blueprint, jsonify, request

# -------------------- Blueprint --------------------
inumet_bp = Blueprint("inumet", __name__)

# -------------------- Endpoints INUMET (WIS2/pygeoapi) --------------------
INUMET_BASE = "https://w2b.inumet.gub.uy/oapi"
INUMET_CAP_ALERTS = (
    f"{INUMET_BASE}/collections/urn%3Awmo%3Amd%3Auy-inumet%3Acap-alerts/items"
)
INUMET_MESSAGES = f"{INUMET_BASE}/collections/messages/items"
WIS2_METADATA_ID = "urn:wmo:md:uy-inumet:cap-alerts"

# -------------------- Queryables (schema oficial) --------------------
COMMON_PROPS = (
    "description,name,phenomenonTime,reportId,reportTime,units,value,wigos_station_identifier"
)

# -------------------- Texto: Cerro Largo --------------------
_DEPT_TOKENS = {
    "cerro largo", "cerrolargo", "c largo", "c.largo", "dpto cerro largo",
}
_LOCALIDADES = {
    "melo", "rio branco", "río branco", "fraile muerto", "aceguá", "isidoro noblía",
    "cerro de las cuentas", "arévalo", "arevalo", "bañado de medina", "tres islas",
    "laguna merín", "centurión", "ramón trigo", "arbolito", "quebracho",
    "plácido rosas", "placido rosas", "tupambaé", "las cañas",
}

def _norm_text(s: str) -> str:
    s = (s or "").lower()
    s = unicodedata.normalize("NFD", s)
    return "".join(ch for ch in s if not unicodedata.combining(ch))

def _mentions_cerro_largo(props: dict) -> bool:
    fields = [
        props.get("name"), props.get("description"),
        props.get("headline"), props.get("event"),
        props.get("areaDesc"), props.get("geographicDomain"),
        props.get("instruction"), props.get("senderName"),
    ]
    n = _norm_text(" ".join([x for x in fields if x]))
    if any(_norm_text(t) in n for t in _DEPT_TOKENS):
        return True
    if any(_norm_text(loc) in n for loc in _LOCALIDADES):
        return True
    return False

# -------------------- WIS2 signal (messages) --------------------
def _wis2_signal(limit=50):
    """
    Si cap-alerts/items viene vacío, consultamos 'messages'
    filtrando por metadata_id=urn:wmo:md:uy-inumet:cap-alerts.
    """
    try:
        params = {
            "f": "json",
            "limit": limit,
            "metadata_id": WIS2_METADATA_ID,
            "sortby": "-datetime",   # si el server lo soporta
        }
        r = requests.get(
            INUMET_MESSAGES,
            params=params,
            headers={"Accept": "application/json"},
            timeout=12,
        )
        if not r.ok:
            return {"ok": False, "status": r.status_code}

        data = r.json()
        feats = data.get("features") or []
        if not feats:
            return {"ok": True, "has_signal": False}

        props = (feats[0].get("properties") or {})
        return {
            "ok": True,
            "has_signal": True,
            "last_datetime": props.get("datetime") or props.get("time") or props.get("pubtime"),
            "last_data_id": props.get("data_id"),
            "last_metadata_id": props.get("metadata_id"),
            "returned": len(feats),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}

# -------------------- Endpoints --------------------
@inumet_bp.get("/")
def inumet_base():
    return jsonify({
        "ok": True,
        "service": "inumet",
        "endpoints": [
            "/api/inumet/alerts/raw",
            "/api/inumet/alerts/cerro-largo",
        ],
    }), 200

@inumet_bp.get("/alerts/raw")
def alerts_raw():
    """Passthrough/diagnóstico del feed INUMET (sólo campos del schema)."""
    try:
        r = requests.get(
            INUMET_CAP_ALERTS,
            params={
                "f": "json",
                "limit": 200,
                "skipGeometry": True,
                "properties": COMMON_PROPS,
            },
            headers={"Accept": "application/json"},
            timeout=15,
        )
        ctype = (r.headers.get("Content-Type") or "").lower()
        if ("json" not in ctype) and ("geo+json" not in ctype):
            return jsonify({
                "ok": False,
                "status": r.status_code,
                "content_type": ctype,
                "note": "INUMET no devolvió JSON",
                "text_preview": r.text[:500],
            }), r.status_code

        payload = r.json()
        resp = {
            "ok": True,
            "status": r.status_code,
            "numberMatched": payload.get("numberMatched"),
            "numberReturned": payload.get("numberReturned"),
            "features_sample": (payload.get("features") or [])[:2],
        }

        if (payload.get("numberReturned") or 0) == 0:
            resp["wis2"] = _wis2_signal()

        return jsonify(resp), 200

    except requests.Timeout:
        return jsonify({"ok": False, "error": "Timeout consultando INUMET"}), 504
    except requests.RequestException as e:
        return jsonify({"ok": False, "error": f"HTTP error: {e}"}), 502
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@inumet_bp.get("/alerts/cerro-largo")
def alerts_cerro_largo():
    """
    Sin geometría: usa sólo texto para detectar Cerro Largo.
    Si no hay items, devuelve alerta sintética cuando hay 'señal' en messages.
    """
    try:
        r = requests.get(
            INUMET_CAP_ALERTS,
            params={
                "f": "json",
                "limit": 200,
                "skipGeometry": True,   # limpiamos dependencias
                "properties": COMMON_PROPS,
            },
            headers={"Accept": "application/json"},
            timeout=15,
        )
        ctype = (r.headers.get("Content-Type") or "").lower()
        if ("json" not in ctype) and ("geo+json" not in ctype):
            return jsonify({
                "ok": False,
                "status": r.status_code,
                "content_type": ctype,
                "note": "INUMET no devolvió JSON",
                "text_preview": r.text[:500],
            }), r.status_code

        payload = r.json()
        feats = payload.get("features") or []

        out = []
        for f in feats:
            props = f.get("properties", {}) or {}
            if _mentions_cerro_largo(props):
                out.append({
                    "reportId": props.get("reportId"),
                    "name": props.get("name") or "Alerta INUMET",
                    "description": props.get("description") or "",
                    "phenomenonTime": props.get("phenomenonTime"),
                    "reportTime": props.get("reportTime"),
                    "units": props.get("units"),
                    "value": props.get("value"),
                    "wigos_station_identifier": props.get("wigos_station_identifier"),
                })

        # Si no hay alertas y el feed devolvió 0, intentamos señal WIS2
        wis2 = None
        if len(out) == 0 and (payload.get("numberReturned") or 0) == 0:
            wis2 = _wis2_signal()
            # Generar alerta sintética si hay señal, para que el widget muestre algo
            if wis2 and wis2.get("ok") and wis2.get("has_signal"):
                out.append({
                    "reportId": wis2.get("last_data_id") or "wis2-signal",
                    "name": "Aviso INUMET (señal WIS2)",
                    "description": (
                        "Se detectó notificación reciente en WIS2 para cap-alerts, "
                        "pero el listado HTTP de alertas está vacío. Puede haber "
                        "desfase de publicación."
                    ),
                    "phenomenonTime": None,
                    "reportTime": wis2.get("last_datetime"),
                    "units": None,
                    "value": None,
                    "wigos_station_identifier": None,
                })

        # Ordenar por más reciente
        out.sort(key=lambda x: (x.get("reportTime") or ""), reverse=True)

        if request.args.get("debug") == "1":
            return jsonify({
                "ok": True,
                "count": len(out),
                "alerts": out,
                "feed_numberMatched": payload.get("numberMatched"),
                "feed_numberReturned": payload.get("numberReturned"),
                "wis2": wis2,
            }), 200

        return jsonify({"ok": True, "count": len(out), "alerts": out, "wis2": wis2}), 200

    except requests.Timeout:
        return jsonify({"ok": False, "error": "Timeout consultando INUMET"}), 504
    except requests.RequestException as e:
        return jsonify({"ok": False, "error": f"HTTP error: {e}"}), 502
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
