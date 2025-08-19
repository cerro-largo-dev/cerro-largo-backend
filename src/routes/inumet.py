# src/routes/inumet.py
import requests
from flask import Blueprint, jsonify

inumet_bp = Blueprint("inumet", __name__)

# Colección oficial INUMET (WIS2/pygeoapi) – CAP alerts (JSON/GeoJSON)
INUMET_CAP_ALERTS = (
    "https://w2b.inumet.gub.uy/oapi/collections/"
    "urn%3Awmo%3Amd%3Auy-inumet%3Acap-alerts/items?f=json"
)

# BBOX aproximado de Cerro Largo [minLon, minLat, maxLon, maxLat]
CERRO_LARGO_BBOX = (-55.10, -33.10, -53.80, -31.70)


def _bbox_from_geometry(geom: dict):
    """
    Devuelve bbox [minx,miny,maxx,maxy] desde geometry GeoJSON (Polygon/MultiPolygon).
    Si ya viene geometry.bbox lo usa; si no, lo calcula.
    """
    if not geom:
        return None

    # Si el servidor incluye bbox ya calculado:
    if "bbox" in geom and isinstance(geom["bbox"], (list, tuple)) and len(geom["bbox"]) >= 4:
        # Algunas implementaciones de GeoJSON pueden incluir [minx,miny,maxx,maxy]
        b = geom["bbox"]
        return [float(b[0]), float(b[1]), float(b[2]), float(b[3])]

    t = geom.get("type")
    if t not in ("Polygon", "MultiPolygon"):
        return None

    coords = []
    if t == "Polygon":
        for ring in geom.get("coordinates", []):
            coords.extend(ring)
    else:  # MultiPolygon
        for poly in geom.get("coordinates", []):
            for ring in poly:
                coords.extend(ring)

    if not coords:
        return None

    xs = [c[0] for c in coords]
    ys = [c[1] for c in coords]
    return [min(xs), min(ys), max(xs), max(ys)]


def _bbox_intersects(a, b):
    """True si bboxes [minx,miny,maxx,maxy] se intersectan."""
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


def _level_from_props(props):
    """
    INUMET CAP en pygeoapi expone el nivel numérico en 'value' (1/2/3)
    y el texto en 'name' (ej: 'Advertencia Amarilla').
    """
    lv = props.get("value")
    if isinstance(lv, (int, float)):
        return int(round(lv))
    # Fallback por texto
    name = (props.get("name") or "").lower()
    if "amarill" in name:
        return 1
    if "naranja" in name:
        return 2
    if "roja" in name or "rojo" in name:
        return 3
    return None


@inumet_bp.route("/alerts/cerro-largo", methods=["GET"])
def alerts_cerro_largo():
    """
    Devuelve alertas de INUMET (CAP) que intersecten el BBOX de Cerro Largo,
    mapeadas a un esquema simple y ordenadas por severidad (3>2>1).
    """
    try:
        r = requests.get(INUMET_CAP_ALERTS, timeout=10)
        r.raise_for_status()
        payload = r.json()
        feats = payload.get("features", []) or []

        out = []
        for f in feats:
            geom = f.get("geometry")
            if not geom:
                continue
            bb = _bbox_from_geometry(geom)
            if not bb:
                continue
            if not _bbox_intersects(bb, CERRO_LARGO_BBOX):
                continue

            props = f.get("properties", {}) or {}
            level = _level_from_props(props)

            out.append({
                "id": props.get("reportId") or props.get("id"),
                "name": props.get("name") or "Alerta INUMET",
                "description": props.get("description") or "",
                "level": level,  # 1=Amarilla, 2=Naranja, 3=Roja
                "phenomenonTime": props.get("phenomenonTime"),
                "reportTime": props.get("reportTime") or props.get("sent"),
            })

        # Ordenar por severidad (desc), luego por hora de emisión (desc) si querés:
        out.sort(key=lambda x: (x["level"] or 0, x["reportTime"] or ""), reverse=True)

        return jsonify({"ok": True, "count": len(out), "alerts": out}), 200

    except requests.RequestException as e:
        return jsonify({"ok": False, "error": f"INUMET request failed: {e}"}), 502
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
