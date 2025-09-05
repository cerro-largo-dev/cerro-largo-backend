# src/map_renderer.py
"""
Renderizador de mapa estático (PNG) a partir de un GeoJSON.
- Colorea polígonos según estado (green/yellow/red/unknown).
- Mapea series de Melo a nombres finales (GEB->Mangrullo, GCB->La Micaela).
- Opcionalmente dibuja etiquetas centradas por polígono.
- Puedes insertar el PNG resultante en tu PDF con ReportLab.

Requisitos:
    shapely
    matplotlib

Uso básico:
    from map_renderer import render_map_png
    render_map_png(
        geojson_path=".../combined_polygons.geojson",
        states_map={"ACEGUÁ":"green","Mangrullo":"yellow","La Micaela":"red"},
        out_png_path="/tmp/mapa.png"
    )
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Tuple, Optional

import matplotlib.pyplot as plt
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

# Paleta por estado
STATE_COLORS = {
    "green":  "#22c55e",
    "yellow": "#eab308",
    "red":    "#ef4444",
    "unknown":"#d1d5db",
}

def _strip_accents_lower(s: str) -> str:
    import unicodedata, re
    if not s:
        return ""
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = s.lower()
    s = re.sub(r"[\s\-_().,/]+", "", s)
    return s

def map_serie_to_name(serie: Optional[str]) -> str:
    """
    Traduce códigos de serie de Melo a nombre final.
    """
    if not serie:
        return ""
    if serie == "GEB":
        return "Mangrullo"
    if serie == "GCB":
        return "La Micaela"
    return f"Melo ({serie})"

def feature_zone_name(props: dict) -> str:
    """
    Obtiene el nombre de zona desde las properties del feature.
    Prioriza 'municipio'; si no, usa 'serie' (mapeada).
    """
    if props.get("municipio"):
        return str(props["municipio"])
    if props.get("serie"):
        return map_serie_to_name(str(props["serie"]))
    # fallback a otras keys comunes
    for k in ("nombre", "name", "label", "title"):
        if props.get(k):
            return str(props[k])
    return ""

def _iter_polygons(geom: BaseGeometry):
    """
    Itera sobre todos los polígonos (soporta Polygon/MultiPolygon).
    """
    gt = geom.geom_type
    if gt == "Polygon":
        yield geom
    elif gt == "MultiPolygon":
        for g in geom.geoms:
            if not g.is_empty:
                yield g

def _bbox_update(bbox: Tuple[float, float, float, float], poly: BaseGeometry):
    minx, miny, maxx, maxy = bbox
    x, y = poly.exterior.xy
    return (min(minx, min(x)), min(miny, min(y)),
            max(maxx, max(x)), max(maxy, max(y)))

def _draw_legend(ax, anchor=(0.02, 0.02), box_alpha=0.85, fontsize=7):
    """
    Dibuja una leyenda simple (esquinas inferiores izquierda por defecto).
    """
    import matplotlib.patches as mpatches
    patches = [
        mpatches.Patch(color=STATE_COLORS["green"],  label="Habilitado"),
        mpatches.Patch(color=STATE_COLORS["yellow"], label="Precaución"),
        mpatches.Patch(color=STATE_COLORS["red"],    label="Cerrado"),
    ]
    leg = ax.legend(
        handles=patches,
        loc="lower left",
        bbox_to_anchor=anchor,
        frameon=True,
        fontsize=fontsize,
    )
    leg.get_frame().set_alpha(box_alpha)

def render_map_png(
    geojson_path: str,
    states_map: Dict[str, str],
    out_png_path: str,
    *,
    figsize: Tuple[float, float] = (8.27, 5.8),  # ~A5 apaisado
    dpi: int = 200,
    draw_labels: bool = True,
    draw_legend: bool = True,
    label_fontsize: int = 6,
    edge_width: float = 0.8,
    face_alpha: float = 0.65,
) -> str:
    """
    Renderiza un PNG del mapa coloreando zonas por estado.

    Params:
        geojson_path  : Ruta al GeoJSON (municipios + series o combinados)
        states_map    : dict {'ACEGUÁ': 'green', 'Mangrullo': 'yellow', ...}
        out_png_path  : salida PNG
        figsize       : tamaño de la figura en pulgadas
        dpi           : resolución
        draw_labels   : dibujar etiquetas de zona en el centro representativo
        draw_legend   : dibujar leyenda de colores
        label_fontsize: tamaño de fuente de etiquetas
        edge_width    : grosor del trazo del polígono
        face_alpha    : opacidad del relleno

    Return:
        Ruta al PNG generado.
    """
    # Normalizar estados a claves sin acentos/espacios
    normalized = {_strip_accents_lower(k): str(v).lower() for k, v in (states_map or {}).items()}

    data = json.loads(Path(geojson_path).read_text(encoding="utf-8"))
    features = data.get("features", [])

    fig = plt.figure(figsize=figsize, dpi=dpi)
    ax = plt.gca()
    ax.set_aspect("equal", adjustable="box")
    ax.axis("off")

    # bbox global
    bbox = (float("inf"), float("inf"), float("-inf"), float("-inf"))

    for feat in features:
        geom = feat.get("geometry")
        if not geom:
            continue
        shp = shape(geom)
        if shp.is_empty:
            continue

        props = feat.get("properties") or {}
        zname = feature_zone_name(props)
        key = _strip_accents_lower(zname)
        state = normalized.get(key, "unknown")
        color = STATE_COLORS.get(state, STATE_COLORS["unknown"])

        for poly in _iter_polygons(shp):
            x, y = poly.exterior.xy
            ax.fill(x, y, facecolor=color, edgecolor=color, linewidth=edge_width, alpha=face_alpha)
            bbox = _bbox_update(bbox, poly)

            if draw_labels and zname:
                try:
                    rp = poly.representative_point()
                    ax.text(
                        rp.x, rp.y,
                        zname.upper(),
                        ha="center", va="center",
                        fontsize=label_fontsize, weight="bold"
                    )
                except Exception:
                    # evitar que una zona rompa el render completo
                    pass

    # Ajustar vista al bbox
    minx, miny, maxx, maxy = bbox
    if minx < maxx and miny < maxy:
        padx = (maxx - minx) * 0.05
        pady = (maxy - miny) * 0.05
        ax.set_xlim(minx - padx, maxx + padx)
        ax.set_ylim(miny - pady, maxy + pady)

    if draw_legend:
        _draw_legend(ax)

    fig.tight_layout(pad=0)
    Path(out_png_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png_path, bbox_inches="tight", pad_inches=0, transparent=False)
    plt.close(fig)
    return out_png_path


# Ejemplo rápido de CLI opcional:
if __name__ == "__main__":
    import argparse, os, sys
    parser = argparse.ArgumentParser(description="Render estático de mapa a PNG.")
    parser.add_argument("--geojson", required=True, help="Ruta al GeoJSON")
    parser.add_argument("--out", required=True, help="PNG de salida")
    parser.add_argument("--states", help="JSON con estados {'ACEGUÁ':'green',...}")
    args = parser.parse_args()

    states = {}
    if args.states:
        try:
            states = json.loads(args.states)
        except Exception as e:
            print("ERROR leyendo --states JSON:", e, file=sys.stderr)
            sys.exit(1)

    render_map_png(args.geojson, states, args.out)
    print(f"OK -> {args.out}")
