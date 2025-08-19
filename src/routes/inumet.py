# src/routes/inumet.py
import os
import time
import json
import requests
from flask import Blueprint, jsonify
from shapely.geometry import shape, Point, Polygon, MultiPolygon

inumet_bp = Blueprint("inumet", __name__)

# Colección oficial (pygeoapi WIS2) – INUMET CAP alerts (JSON/GeoJSON)
INUMET_CAP_ALERTS = (
    "https://w2b.inumet.gub.uy/oapi/collections/"
    "urn%3Awmo%3Amd%3Auy-inumet%3Acap-alerts/items?f=json"
)

# Donde leer el polígono de Cerro Largo:
# 1) URL pública (recomendado) -> mover el archivo a /public del frontend
CERRO_GEOJSON_URL = os.environ.get(
    "cerro_largo_municipios_2025.geojson",
    # ejemplo de fallback local (si prefieres copiar el archivo en el backend):
    # "file://./data/series_cerro_largo.geojson"
    ""
)

# Cache básico en memoria para no re-leer el polígono a cada request
_CERRO_POLY = None
_CERRO_LAST = 0
_CERRO_TTL = 600  # 10 minutos


def _load_cerro_polygon():
    """Carga y cachea el polígono (o multipolígono) de Cerro Largo desde URL o archivo local."""
    global _CERRO_POLY, _CERRO_LAST

    now = time.time()
    if _CERRO_POLY is not None and (now - _CERRO_LAST) < _CERRO_TTL:
        return _CERRO_POLY

    src = CERRO_GEOJSON_URL.strip()
    if not src:
        # Si no se configuró URL, intentar leer un archivo local común
        # Ajusta la ruta si lo copias en el backend (ej: ./data/series_cerro_largo.geojson)
        local_path = os.path.join(os.path.dirname(__file__), "..", "static", "series_cerro_largo.geojson")
        local_path = os.path.abspath(local_path)
        if not os.path.exists(local_path):
            raise RuntimeError("Falta CERRO_GEOJSON_URL o archivo local de Cerro Largo")
        with open(local_path, "r", encoding="utf-8") as f:
            gj = json.load(f)
    else:
        if src.startswith("file://"):
            with open(src.replace("file://", ""), "r", encoding="utf-8") as f:
                gj = json.load(f)
        else:
            r = requests.get(src, timeout=10)
            r.raise_for_status()
            gj = r.json()

    # Unir todas las geometrías del GeoJSON en un MultiPolygon único
    geoms = []
    feats = gj.get("features") or []
    for ft in feats:
        g = ft.get("geometry")
        if not g:
            continue
        shp = shape(g)
        # Filtrar por tipos poligonales
        if isinstance(shp, (Polygon, MultiPolygon)):
            geoms.append(shp)

    if not geoms:
        raise RuntimeError("El GeoJSON no contiene polígonos válidos")

    # Unir todo en un multipolígono
    # Nota: shapely.ops.unary_union no está importado; MultiPolygon con suma básica:
    from shapely.ops import unary_union
    cerro_union = unary_union(geoms)

    _CERRO_POLY = cerro_union
    _CERRO_LAST = now
    return _CERRO_POLY


def _level_from_props(props):
    """
    INUMET CAP: nivel numérico en 'value' (1/2/3) y texto en 'name' (ej: 'Advertencia Amarilla').
    """
    lv = props.get("value")
    if isinstance(lv, (int, float)):
        return int(round(lv))
    name = (props.get("name") or "").lower()
    if "amarill" in name:
        return 1
    if "naranja" in name:
        return 2
    if "roja" in name or "rojo" in name:
        return 3
    return None


@inumet_bp.route("/api/inumet/alerts/cerro-largo", methods=["GET"])
def alerts_cerro_largo():
    """Devuelve alertas INUMET que INTERSECTEN el polígono real de Cerro Largo."""
    try:
        poly = _load_cerro_polygon()

        r = requests.get(INUMET_CAP_ALERTS, timeout=10)
        r.raise_for_status()
        payload = r.json()
        feats = payload.get("features", []) or []

        out = []
        for f in feats:
            geom = f.get("geometry")
            if not geom:
                continue
            alert_shape = shape(geom)
            # Intersección poligonal real
            if not poly.intersects(alert_shape):
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

        # Orden: más severa primero, y opcionalmente más reciente
        out.sort(key=lambda x: (x["level"] or 0, x["reportTime"] or ""), reverse=True)

        return jsonify({"ok": True, "count": len(out), "alerts": out}), 200

    except requests.RequestException as e:
        return jsonify({"ok": False, "error": f"INUMET request failed: {e}"}), 502
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
