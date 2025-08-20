# src/routes/inumet.py
import os
import time
import json
import zipfile
import unicodedata
import xml.etree.ElementTree as ET

import requests
from flask import Blueprint, jsonify, request
from shapely.geometry import shape, Polygon, MultiPolygon
from shapely.ops import unary_union, transform as shp_transform

# Blueprint
inumet_bp = Blueprint("inumet", __name__)

# -------------------- Config --------------------
# Feed oficial CAP de INUMET (pygeoapi)
INUMET_CAP_ALERTS = (
    "https://w2b.inumet.gub.uy/oapi/collections/"
    "urn%3Awmo%3Amd%3Auy-inumet%3Acap-alerts/items"
)

# Fuente del polígono del dpto (preferir archivo local, ej: ./data/cerro_largo.geojson)
CERRO_SHAPE_FILE = os.getenv("CERRO_SHAPE_FILE", "").strip()

# Alternativa remota si no hay archivo local
CERRO_GEOJSON_URL = os.getenv(
    "CERRO_GEOJSON_URL",
    "https://cerro-largo-frontend.onrender.com/cerro_largo_municipios_2025.geojson",
).strip()

# Cache de polígono (para no recalcular en cada request)
_CERRO_POLY = None
_CERRO_LAST = 0.0
_CERRO_TTL = 600  # 10 min
_CERRO_SWAPPED = False  # si se detectó y corrigió lat/lon en la forma

# -------------------- Helpers geom --------------------
def _uy_bounds_ok(bounds) -> bool:
    """Rango razonable para Uruguay si las coords están en (lon, lat)."""
    minx, miny, maxx, maxy = bounds
    return (-59 <= minx <= -50) and (-36 <= miny <= -29) and \
           (-59 <= maxx <= -50) and (-36 <= maxy <= -29)

def _normalize_lonlat(geom):
    """
    Asegura (lon,lat). Si parece (lat,lon), intercambia ejes.
    Devuelve (geom_normalizado, swapped_bool).
    """
    swapped = shp_transform(lambda x, y, z=None: (y, x), geom)
    if not _uy_bounds_ok(geom.bounds) and _uy_bounds_ok(swapped.bounds):
        return swapped, True
    return geom, False

def _polygons_from_kml_bytes(kml_bytes: bytes):
    """Extrae polígonos de un KML (bytes)."""
    ns = {'k': 'http://www.opengis.net/kml/2.2'}
    root = ET.fromstring(kml_bytes)
    polys = []
    for pm in root.findall('.//k:Placemark', ns):
        for poly in pm.findall('.//k:Polygon', ns):
            coords_el = poly.find('.//k:outerBoundaryIs/k:LinearRing/k:coordinates', ns)
            if coords_el is None:
                coords_el = poly.find('.//k:coordinates', ns)
            if not coords_el or not (coords_el.text or '').strip():
                continue
            coords = []
            for tok in coords_el.text.strip().split():
                parts = tok.split(',')
                if len(parts) >= 2:
                    try:
                        lon = float(parts[0]); lat = float(parts[1])
                        coords.append((lon, lat))
                    except Exception:
                        pass
            if len(coords) >= 3:
                try:
                    polys.append(Polygon(coords))
                except Exception:
                    pass
    return polys

def _load_polygon_from_file(path: str):
    """Carga polígono/multipolígono desde archivo local .kmz/.kml/.geojson."""
    path = os.path.abspath(path)
    if not os.path.exists(path):
        raise RuntimeError(f"Archivo de forma no encontrado: {path}")

    ext = os.path.splitext(path)[1].lower()
    if ext == ".kmz":
        with zipfile.ZipFile(path, 'r') as z:
            kml_name = "doc.kml" if "doc.kml" in z.namelist() else None
            if not kml_name:
                for n in z.namelist():
                    if n.lower().endswith(".kml"):
                        kml_name = n
                        break
            if not kml_name:
                raise RuntimeError("KMZ sin KML interno")
            polys = _polygons_from_kml_bytes(z.read(kml_name))
    elif ext == ".kml":
        with open(path, "rb") as f:
            polys = _polygons_from_kml_bytes(f.read())
    elif ext in (".geojson", ".json"):
        with open(path, "r", encoding="utf-8") as f:
            gj = json.load(f)
        polys = []
        for ft in (gj.get("features") or []):
            g = ft.get("geometry")
            if not g:
                continue
            shp = shape(g)
            if isinstance(shp, (Polygon, MultiPolygon)):
                polys.append(shp)
    else:
        raise RuntimeError("Formato no soportado (usa .kmz/.kml/.geojson)")

    if not polys:
        raise RuntimeError("No se encontraron polígonos en el archivo de forma")
    return unary_union(polys)

def _load_polygon_from_url(url: str):
    """Carga polígono/multipolígono desde un GeoJSON remoto."""
    r = requests.get(url, timeout=12)
    r.raise_for_status()
    gj = r.json()
    polys = []
    for ft in (gj.get("features") or []):
        g = ft.get("geometry")
        if not g:
            continue
        shp = shape(g)
        if isinstance(shp, (Polygon, MultiPolygon)):
            polys.append(shp)
    if not polys:
        raise RuntimeError("GeoJSON remoto sin polígonos válidos")
    return unary_union(polys)

def _load_cerro_polygon():
    """Carga la forma (local o remota), normaliza lon/lat y la cachea."""
    global _CERRO_POLY, _CERRO_LAST, _CERRO_SWAPPED
    now = time.time()
    if _CERRO_POLY is not None and (now - _CERRO_LAST) < _CERRO_TTL:
        return _CERRO_POLY

    if CERRO_SHAPE_FILE:
        union = _load_polygon_from_file(CERRO_SHAPE_FILE)
    else:
        union = _load_polygon_from_url(CERRO_GEOJSON_URL)

    union_norm, swapped = _normalize_lonlat(union)
    _CERRO_POLY = union_norm
    _CERRO_LAST = now
    _CERRO_SWAPPED = swapped
    return _CERRO_POLY

# -------------------- Helpers texto --------------------
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

def _level_from_props(p: dict):
    name = (p.get("name") or "").lower()
    val = p.get("value")
    if isinstance(val, (int, float)):
        return int(round(val))
    if "amarill" in name:
        return 1
    if "naranja" in name:
        return 2
    if "roj" in name:
        return 3
    return None

# -------------------- Endpoints --------------------
@inumet_bp.get("/")
def inumet_base():
    src = CERRO_SHAPE_FILE or CERRO_GEOJSON_URL
    return jsonify({
        "ok": True,
        "service": "inumet",
        "shape_source": src,
        "endpoints": [
            "/api/inumet/alerts/raw",
            "/api/inumet/alerts/cerro-largo",
        ],
    }), 200

@inumet_bp.get("/alerts/raw")
def alerts_raw():
    """Passthrough del feed INUMET (diagnóstico)."""
    try:
        r = requests.get(
            INUMET_CAP_ALERTS,
            params={"f": "json", "limit": 200},  # traer más ítems por seguridad
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
                "text_preview": r.text[:500],
            }), r.status_code

        payload = r.json()
        return jsonify({
            "ok": True,
            "status": r.status_code,
            "numberMatched": payload.get("numberMatched"),
            "numberReturned": payload.get("numberReturned"),
            "features_sample": (payload.get("features") or [])[:2],
        }), 200

    except requests.Timeout:
        return jsonify({"ok": False, "error": "Timeout consultando INUMET"}), 504
    except requests.RequestException as e:
        return jsonify({"ok": False, "error": f"HTTP error: {e}"}), 502
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@inumet_bp.get("/alerts/cerro-largo")
def alerts_cerro_largo():
    """
    1) Incluye alertas con geometría que intersecten la forma del dpto.
    2) Fallback textual: si no intersecta / no hay geometría,
       se incluye si el texto menciona 'Cerro Largo' o localidades.
    Agrega ?debug=1 para métricas.
    """
    try:
        poly = _load_cerro_polygon()

        r = requests.get(
            INUMET_CAP_ALERTS,
            params={"f": "json", "limit": 200},
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
                "text_preview": r.text[:500],
            }), r.status_code

        payload = r.json()
        feats = payload.get("features") or []

        total = len(feats)
        with_geom = 0
        intersect_count = 0
        text_fallback = 0
        out = []

        for f in feats:
            props = f.get("properties", {}) or {}
            geom = f.get("geometry")
            added = False

            if geom:
                with_geom += 1
                shp = shape(geom)
                shp, _ = _normalize_lonlat(shp)
                if poly.intersects(shp):
                    intersect_count += 1
                    added = True

            if not added and _mentions_cerro_largo(props):
                text_fallback += 1
                added = True

            if added:
                out.append({
                    "id": props.get("reportId") or props.get("id"),
                    "name": props.get("name") or "Alerta INUMET",
                    "description": props.get("description") or "",
                    "level": _level_from_props(props),  # 1=Amarilla, 2=Naranja, 3=Roja
                    "phenomenonTime": props.get("phenomenonTime"),
                    "reportTime": props.get("reportTime") or props.get("sent"),
                })

        out.sort(key=lambda x: (x.get("level") or 0, x.get("reportTime") or ""), reverse=True)

        if request.args.get("debug") == "1":
            return jsonify({
                "ok": True,
                "count": len(out),
                "alerts": out,
                "feed_numberMatched": payload.get("numberMatched"),
                "feed_numberReturned": payload.get("numberReturned"),
                "feed_features_total": total,
                "feed_with_geometry": with_geom,
                "poly_bounds": _load_cerro_polygon().bounds,
                "poly_swapped": _CERRO_SWAPPED,
                "intersect_count": intersect_count,
                "text_fallback_count": text_fallback,
                "polygon_source": CERRO_SHAPE_FILE or CERRO_GEOJSON_URL,
                "polygon_ttl": _CERRO_TTL,
            }), 200

        return jsonify({"ok": True, "count": len(out), "alerts": out}), 200

    except requests.Timeout:
        return jsonify({"ok": False, "error": "Timeout consultando INUMET"}), 504
    except requests.RequestException as e:
        return jsonify({"ok": False, "error": f"HTTP error: {e}"}), 502
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
