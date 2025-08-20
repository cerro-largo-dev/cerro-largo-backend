# src/routes/inumet.py
import os, time, json, requests
from flask import Blueprint, jsonify, request
from shapely.geometry import shape, Polygon, MultiPolygon
from shapely.ops import unary_union

inumet_bp = Blueprint("inumet", __name__)

# Feed oficial CAP de INUMET (pygeoapi)
INUMET_CAP_ALERTS = (
    "https://w2b.inumet.gub.uy/oapi/collections/"
    "urn%3Awmo%3Amd%3Auy-inumet%3Acap-alerts/items"
)

# GeoJSON de Cerro Largo (ajusta si corresponde)
CERRO_GEOJSON_URL = os.getenv(
    "CERRO_GEOJSON_URL",
    "https://cerro-largo-frontend.onrender.com/cerro_largo_municipios_2025.geojson"
)

# Cache simple del polígono
_CERRO_POLY = None
_CERRO_LAST = 0
_CERRO_TTL = 600  # 10 min


def _load_cerro_polygon():
    global _CERRO_POLY, _CERRO_LAST
    now = time.time()
    if _CERRO_POLY is not None and (now - _CERRO_LAST) < _CERRO_TTL:
        return _CERRO_POLY

    src = CERRO_GEOJSON_URL.strip()
    if src.startswith("file://"):
        with open(src.replace("file://", ""), "r", encoding="utf-8") as f:
            gj = json.load(f)
    else:
        r = requests.get(src, timeout=12)
        r.raise_for_status()
        gj = r.json()

    geoms = []
    for ft in (gj.get("features") or []):
        g = ft.get("geometry")
        if not g:
            continue
        shp = shape(g)
        if isinstance(shp, (Polygon, MultiPolygon)):
            geoms.append(shp)
    if not geoms:
        raise RuntimeError("GeoJSON sin polígonos válidos para Cerro Largo")

    _CERRO_POLY = unary_union(geoms)
    _CERRO_LAST = now
    return _CERRO_POLY


def _level_from_props(props):
    name = (props.get("name") or "").lower()
    val = props.get("value")
    if isinstance(val, (int, float)): return int(round(val))
    if "amarill" in name: return 1
    if "naranja" in name: return 2
    if "roj" in name:     return 3
    return None


@inumet_bp.get("/")
def inumet_base():
    return jsonify({
        "ok": True,
        "service": "inumet",
        "endpoints": [
            "/api/inumet/alerts/raw",
            "/api/inumet/alerts/cerro-largo"
        ]
    }), 200


@inumet_bp.get("/alerts/raw")
def alerts_raw():
    """Passthrough del feed (para diagnóstico)."""
    try:
        r = requests.get(
            INUMET_CAP_ALERTS,
            params={"f": "json"},
            headers={"Accept": "application/json"},
            timeout=15,
        )
        ctype = r.headers.get("Content-Type", "")
        if "application/json" not in ctype:
            return jsonify({
                "ok": False,
                "status": r.status_code,
                "content_type": ctype,
                "note": "INUMET no devolvió JSON",
                "text_preview": r.text[:500]
            }), r.status_code

        payload = r.json()
        # devuelvo metadatos y una muestra
        return jsonify({
            "ok": True,
            "status": r.status_code,
            "numberMatched": payload.get("numberMatched"),
            "numberReturned": payload.get("numberReturned"),
            "features_sample": (payload.get("features") or [])[:1],
        }), 200

    except requests.Timeout:
        return jsonify({"ok": False, "error": "Timeout consultando INUMET"}), 504
    except requests.RequestException as e:
        return jsonify({"ok": False, "error": f"HTTP error: {e}"}), 502
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@inumet_bp.get("/alerts/cerro-largo")
def alerts_cerro_largo():
    """Alertas CAP que intersecten Cerro Largo. Agrega ?debug=1 para métricas."""
    try:
        poly = _load_cerro_polygon()

        r = requests.get(
            INUMET_CAP_ALERTS,
            params={"f": "json"},
            headers={"Accept": "application/json"},
            timeout=15,
        )
        ctype = r.headers.get("Content-Type", "")
        if "application/json" not in ctype:
            return jsonify({
                "ok": False,
                "status": r.status_code,
                "content_type": ctype,
                "note": "INUMET no devolvió JSON",
                "text_preview": r.text[:500]
            }), r.status_code

        payload = r.json()
        feats = payload.get("features") or []

        out = []
        for f in feats:
            geom = f.get("geometry")
            if not geom:
                continue
            if not poly.intersects(shape(geom)):
                continue
            props = f.get("properties", {}) or {}
            out.append({
                "id": props.get("reportId") or props.get("id"),
                "name": props.get("name") or "Alerta INUMET",
                "description": props.get("description") or "",
                "level": _level_from_props(props),  # 1=Amarilla, 2=Naranja, 3=Roja
                "phenomenonTime": props.get("phenomenonTime"),
                "reportTime": props.get("reportTime") or props.get("sent"),
            })

        out.sort(key=lambda x: (x["level"] or 0, x["reportTime"] or ""), reverse=True)

        if request.args.get("debug") == "1":
            return jsonify({
                "ok": True,
                "count": len(out),
                "alerts": out,
                "feed_numberMatched": payload.get("numberMatched"),
                "feed_numberReturned": payload.get("numberReturned"),
                "feed_features_total": len(feats),
                "polygon_ttl": _CERRO_TTL
            }), 200

        return jsonify({"ok": True, "count": len(out), "alerts": out}), 200

    except requests.Timeout:
        return jsonify({"ok": False, "error": "Timeout consultando INUMET"}), 504
    except requests.RequestException as e:
        return jsonify({"ok": False, "error": f"HTTP error: {e}"}), 502
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
