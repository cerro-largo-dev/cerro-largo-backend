# src/routes/inumet.py
import os, json
from pathlib import Path
import requests
from flask import Blueprint, jsonify
from shapely.geometry import shape

inumet_bp = Blueprint("inumet", __name__)

# Endpoint oficial (pygeoapi / WIS2 INUMET - CAP alerts)
INUMET_CAP_ALERTS = (
    "https://w2b.inumet.gub.uy/oapi/collections/"
    "urn%3Awmo%3Amd%3Auy-inumet%3Acap-alerts/items?f=json"
)

# ---------- Carga del polígono de Cerro Largo (desde tu GeoJSON) ----------
_CERRO_LARGO_GEOM = None  # cache en memoria

def _load_cerro_largo_geom():
    """
    Carga y une todos los features del GeoJSON de Cerro Largo en un MultiPolygon.
    Usa la ruta de env CERRO_LARGO_GEOJSON o un fallback dentro del repo.
    """
    global _CERRO_LARGO_GEOM
    if _CERRO_LARGO_GEOM is not None:
        return _CERRO_LARGO_GEOM

    # Base del proyecto (2 niveles arriba de este archivo)
    base_dir = Path(__file__).resolve().parents[2]

    # 1) Ruta por ENV (útil si me dijiste "los tengo en esta ruta!!")
    env_path = os.environ.get("CERRO_LARGO_GEOJSON")
    if env_path:
        candidates = [Path(env_path)]
    else:
        # 2) Fallbacks típicos (ajústalos si tu ruta es distinta)
        candidates = [
            base_dir / "static" / "assets" / "cerro_largo_municipios_2025.geojson",
            base_dir / "static" / "assets" / "series_cerro_largo.geojson",
        ]

    for p in candidates:
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                gj = json.load(f)

            # Unir todos los features en una sola geometría
            geoms = []
            feats = gj.get("features") or []
            if not feats and gj.get("type") == "Feature":
                feats = [gj]  # por si es un único Feature

            for feat in feats:
                g = feat.get("geometry")
                if g:
                    geoms.append(shape(g))

            if not geoms:
                raise RuntimeError(f"GeoJSON sin geometrías: {p}")

            # Union (sin unary_union para evitar dependencia pesada)
            from shapely.ops import unary_union
            _CERRO_LARGO_GEOM = unary_union(geoms)
            return _CERRO_LARGO_GEOM

    raise FileNotFoundError(
        "No encontré el GeoJSON de Cerro Largo. "
        "Define CERRO_LARGO_GEOJSON=/ruta/tu_archivo.geojson o coloca el archivo en static/assets/"
    )

# ---------- Utilidades ----------
def _level_from_props(props: dict):
    """
    INUMET CAP (pygeoapi) expone:
      - 'value' numérico (1/2/3) => nivel (amarilla/naranja/roja)
      - 'name' texto (ej: 'Advertencia Amarilla')
    """
    lv = props.get("value")
    if isinstance(lv, (int, float)):
        return int(round(lv))
    n = (props.get("name") or "").lower()
    if "amarill" in n: return 1
    if "naranja" in n: return 2
    if "roja" in n or "rojo" in n: return 3
    return None

# ---------- Endpoint ----------
@inumet_bp.route("/alerts/cerro-largo", methods=["GET"])
def alerts_cerro_largo():
    """
    Devuelve alertas CAP de INUMET cuya geometría intersecta Cerro Largo (polígono real).
    """
    try:
        # 1) Cargar polígono de Cerro Largo
        cerro = _load_cerro_largo_geom()

        # 2) Traer alertas de INUMET
        r = requests.get(INUMET_CAP_ALERTS, timeout=10)
        r.raise_for_status()
        payload = r.json()
        feats = payload.get("features") or []

        out = []
        for f in feats:
            geom = f.get("geometry")
            if not geom:
                continue
            try:
                alert_geom = shape(geom)
            except Exception:
                continue

            # 3) Filtrar por intersección
            if not alert_geom.intersects(cerro):
                continue

            props = f.get("properties") or {}
            out.append({
                "id": props.get("reportId") or props.get("id"),
                "name": props.get("name") or "Alerta INUMET",
                "description": props.get("description") or "",
                "level": _level_from_props(props),  # 1/2/3
                "phenomenonTime": props.get("phenomenonTime"),
                "reportTime": props.get("reportTime") or props.get("sent"),
            })

        # 4) Orden: mayor severidad primero
        out.sort(key=lambda x: (x["level"] or 0, x["reportTime"] or ""), reverse=True)

        return jsonify({"ok": True, "count": len(out), "alerts": out}), 200

    except requests.RequestException as e:
        return jsonify({"ok": False, "error": f"INUMET request failed: {e}"}), 502
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
