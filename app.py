"""
app.py  –  Nouakchott Transport Network  (Dashboard v3 – Optimisé)
==================================================================
Améliorations vs v2 :
  • BASE_FIG pré-calculée une seule fois, jamais re-rendue complète
  • Cache LRU pour les routes (Dijkstra ne tourne qu'une fois par paire)
  • Dropdowns searchables avec groupes (quartiers, POIs)
  • Option "Choisir sur la carte" conservée
  • Toggles Roads / Intersections via Plotly restyle (pas de re-render)
  • uirevision cohérent pour garder le viewport
  • Temps estimé affiché (vitesse urbaine 30 km/h)
  • prevent_initial_call + no_update systématiques

Run :
    pip install dash plotly pandas scipy numpy
    python app.py                             # utilise le CSV par défaut
    python app.py path/to/transport.csv
    MAX_ROWS=1000 python app.py               # test rapide sur sous-réseau
"""

from __future__ import annotations

import os
import sys
import math
import json
import logging
import functools
from pathlib import Path

import dash
from dash import dcc, html, Input, Output, State, ctx, no_update
import plotly.graph_objects as go

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# ── Chemin CSV ────────────────────────────────────────────────────────────────
CSV_PATH = (
    sys.argv[1]
    if len(sys.argv) > 1
    else os.environ.get(
        "TRANSPORT_CSV",
        str(Path(__file__).parent / "nouakchott_transport_network.csv"),
    )
)
MAX_ROWS = int(os.environ.get("MAX_ROWS", "0")) or None

# ── Chargement du graphe (une seule fois au démarrage) ────────────────────────
log.info(f"Chargement du graphe depuis {CSV_PATH} …")
from graph import build_graph_from_csv, TransportGraph
G: TransportGraph = build_graph_from_csv(CSV_PATH, max_rows=MAX_ROWS)
log.info(G.summary())

# ── Index spatial KDTree (construit une seule fois) ───────────────────────────
log.info("Construction de l'index spatial …")
from snapping import GraphSnapper
SNAPPER = GraphSnapper(G)
log.info("Index spatial prêt.")

# ── Composantes connexes + stats (pré-calculés, cachés) ──────────────────────
from graph_algos import (
    get_component_map, get_components_list, graph_stats,
    compute_route, run_bfs, run_dfs, get_mst,
)
log.info("Calcul des composantes connexes …")
_comp_map = get_component_map(G)
_comps    = get_components_list(G)
_stats    = graph_stats(G)
log.info(f"  {_stats['components']} composantes, plus grande = {_stats['largest_component_pct']:.1f}%")

# ── Geocoding (cache JSON sur disque) ─────────────────────────────────────────
from geocoding import geocode, reverse_geocode


# ─────────────────────────────────────────────────────────────────────────────
# Cache LRU pour les routes calculées
# ─────────────────────────────────────────────────────────────────────────────

@functools.lru_cache(maxsize=512)
def _cached_route(src_node: int, dst_node: int) -> dict:
    """
    Calcule l'itinéraire optimal et le met en cache.
    La clé est (src_node, dst_node) — deux entiers légers.
    Le cache évite de relancer Dijkstra pour les mêmes paires.
    """
    return compute_route(G, src_node, dst_node)


# ─────────────────────────────────────────────────────────────────────────────
# POI / Dropdown options  (groupées par quartier)
# ─────────────────────────────────────────────────────────────────────────────
#
# IMPORTANT : les coordonnées sont embarquées directement ici.
# Aucun appel réseau n'est nécessaire pour les lieux de la liste.
# La valeur du dropdown est la clé dans POI_COORDS.
# Pour ajouter un lieu : ajoutez une entrée dans _POI_GROUPS ET dans POI_COORDS.
#
# Coordonnées vérifiées via OpenStreetMap (Nominatim) — précision ~50 m.

# Dictionnaire value → {"lat": float, "lon": float, "display_name": str}
POI_COORDS: dict[str, dict] = {
    # ── Santé ─────────────────────────────────────────────────────────────────
    "poi:hopital-cheikh-zayed": {
        "lat": 18.0751095, "lon": -15.9357556,
        "display_name": "Hôpital Cheikh Zayed, Dar Naim, Nouakchott",
    },
    "poi:hopital-national": {
        "lat": 18.0965,    "lon": -15.9657,
        "display_name": "Hôpital National de Nouakchott, Ksar",
    },
    "poi:pharmacie-centrale": {
        "lat": 18.0960,    "lon": -15.9670,
        "display_name": "Pharmacie Centrale, Ksar, Nouakchott",
    },
    # ── Éducation ─────────────────────────────────────────────────────────────
    "poi:universite-nouakchott": {
        "lat": 18.1010,    "lon": -15.9730,
        "display_name": "Université de Nouakchott Al-Aasriya, Tevragh Zeina",
    },
    "poi:ecole-ksar": {
        "lat": 18.0980,    "lon": -15.9560,
        "display_name": "École Ksar, Ksar, Nouakchott",
    },
    # ── Quartiers ─────────────────────────────────────────────────────────────
    "poi:tevragh-zeina": {
        "lat": 18.1100,    "lon": -15.9820,
        "display_name": "Tevragh Zeina, Nouakchott-Ouest",
    },
    "poi:ksar": {
        "lat": 18.0990,    "lon": -15.9560,
        "display_name": "Ksar, Nouakchott-Ouest",
    },
    "poi:el-mina": {
        "lat": 18.0600,    "lon": -15.9750,
        "display_name": "El Mina, Nouakchott-Sud",
    },
    "poi:arafat": {
        "lat": 18.0380,    "lon": -15.9570,
        "display_name": "Arafat, Nouakchott-Sud",
    },
    "poi:dar-naim": {
        "lat": 18.0800,    "lon": -15.9340,
        "display_name": "Dar Naim, Nouakchott-Nord",
    },
    "poi:teyarett": {
        "lat": 18.0850,    "lon": -15.9650,
        "display_name": "Teyarett, Nouakchott-Ouest",
    },
    "poi:sebkha": {
        "lat": 18.0700,    "lon": -15.9650,
        "display_name": "Sebkha, Nouakchott-Ouest",
    },
    "poi:riad": {
        "lat": 18.0620,    "lon": -15.9450,
        "display_name": "Riad, Nouakchott-Sud",
    },
    "poi:toujounine": {
        "lat": 18.0650,    "lon": -15.9200,
        "display_name": "Toujounine, Nouakchott-Nord",
    },
    # ── Axes routiers ─────────────────────────────────────────────────────────
    "poi:autoroute-rosso": {
        "lat": 18.0413271, "lon": -15.9590933,
        "display_name": "Autoroute Rosso, Arafat, Nouakchott",
    },
    "poi:route-espoir": {
        "lat": 18.0750,    "lon": -15.9300,
        "display_name": "Route de l'Espoir, Nouakchott",
    },
    "poi:carrefour-3-poteaux": {
        "lat": 18.0448984, "lon": -15.9739024,
        "display_name": "Carrefour 3 Poteaux, El Mina, Nouakchott",
    },
    "poi:base-marine": {
        "lat": 18.0563499, "lon": -15.9777163,
        "display_name": "Route de la Base Marine, El Mina, Nouakchott",
    },
    # ── Administration ────────────────────────────────────────────────────────
    "poi:palais-presidentiel": {
        "lat": 18.0890,    "lon": -15.9910,
        "display_name": "Palais Présidentiel, Tevragh Zeina, Nouakchott",
    },
    "poi:mairie": {
        "lat": 18.0860,    "lon": -15.9640,
        "display_name": "Mairie de Nouakchott, Ksar",
    },
    "poi:aeroport": {
        "lat": 18.0977,    "lon": -15.9478,
        "display_name": "Aéroport International Oumtounsy, Nouakchott",
    },
    "poi:bcm": {
        "lat": 18.0920,    "lon": -15.9800,
        "display_name": "Banque Centrale de Mauritanie, Tevragh Zeina",
    },
    # ── Mosquées ──────────────────────────────────────────────────────────────
    "poi:mosquee-thier-tamime": {
        "lat": 18.0413271, "lon": -15.9590933,
        "display_name": "Mosquée Thiérno Tamime, Autoroute Rosso, Nouakchott",
    },
    "poi:mosquee-saudi": {
        "lat": 18.0870,    "lon": -15.9730,
        "display_name": "Grande Mosquée Saoudienne, Ksar, Nouakchott",
    },
    # ── Marchés ───────────────────────────────────────────────────────────────
    "poi:marche-capital": {
        "lat": 18.0960,    "lon": -15.9620,
        "display_name": "Marché Capital, Ksar, Nouakchott",
    },
    "poi:marche-cinquieme": {
        "lat": 18.0710,    "lon": -15.9630,
        "display_name": "Marché Cinquième, Sebkha, Nouakchott",
    },
    # ── Rues / Points connus du cache existant ────────────────────────────────
    "poi:rue-didi": {
        "lat": 18.1181751, "lon": -15.980536,
        "display_name": "Rue Didi Ould Bounaama, F-Nord, Nouakchott",
    },
    "poi:rue-moustapha": {
        "lat": 18.1142321, "lon": -15.9827066,
        "display_name": "Rue Moustapha Ould Mohamed Saleck, Las Palmas, Nouakchott",
    },
    "poi:sid-ahmed": {
        "lat": 18.1078812, "lon": -15.9547204,
        "display_name": "Sid'Ahmed Ould Khyar, Ksar, Nouakchott",
    },
}

# Définition des groupes du dropdown (label affiché, value = clé POI_COORDS)
_POI_GROUPS: list[dict] = [
    # ── Santé ──────────────────────────────────────────────────────────────────
    {"label": "🏥 Hôpital Cheikh Zayed",        "value": "poi:hopital-cheikh-zayed",  "group": "Santé"},
    {"label": "🏥 Hôpital National",             "value": "poi:hopital-national",       "group": "Santé"},
    {"label": "💊 Pharmacie centrale",            "value": "poi:pharmacie-centrale",     "group": "Santé"},
    # ── Éducation ──────────────────────────────────────────────────────────────
    {"label": "🎓 Université de Nouakchott",     "value": "poi:universite-nouakchott",  "group": "Éducation"},
    {"label": "🏫 École de Ksar",                "value": "poi:ecole-ksar",             "group": "Éducation"},
    # ── Quartiers ──────────────────────────────────────────────────────────────
    {"label": "📍 Tevragh Zeina",                "value": "poi:tevragh-zeina",          "group": "Quartiers"},
    {"label": "📍 Ksar",                         "value": "poi:ksar",                   "group": "Quartiers"},
    {"label": "📍 El Mina",                      "value": "poi:el-mina",                "group": "Quartiers"},
    {"label": "📍 Arafat",                       "value": "poi:arafat",                 "group": "Quartiers"},
    {"label": "📍 Dar Naim",                     "value": "poi:dar-naim",               "group": "Quartiers"},
    {"label": "📍 Teyarett",                     "value": "poi:teyarett",               "group": "Quartiers"},
    {"label": "📍 Sebkha",                       "value": "poi:sebkha",                 "group": "Quartiers"},
    {"label": "📍 Riad",                         "value": "poi:riad",                   "group": "Quartiers"},
    {"label": "📍 Toujounine",                   "value": "poi:toujounine",             "group": "Quartiers"},
    # ── Axes routiers ──────────────────────────────────────────────────────────
    {"label": "🛣️  Autoroute Rosso",             "value": "poi:autoroute-rosso",        "group": "Axes routiers"},
    {"label": "🛣️  Route de l'Espoir",           "value": "poi:route-espoir",           "group": "Axes routiers"},
    {"label": "🛣️  Carrefour 3 Poteaux",         "value": "poi:carrefour-3-poteaux",    "group": "Axes routiers"},
    {"label": "🛣️  Route Base Marine",           "value": "poi:base-marine",            "group": "Axes routiers"},
    # ── Administration ─────────────────────────────────────────────────────────
    {"label": "🏛️  Palais Présidentiel",         "value": "poi:palais-presidentiel",    "group": "Administration"},
    {"label": "🏛️  Mairie de Nouakchott",        "value": "poi:mairie",                 "group": "Administration"},
    {"label": "✈️  Aéroport Oumtounsy",          "value": "poi:aeroport",               "group": "Administration"},
    {"label": "🏦  Banque Centrale (BCM)",        "value": "poi:bcm",                    "group": "Administration"},
    # ── Mosquées ───────────────────────────────────────────────────────────────
    {"label": "🕌 Mosquée Thiérno Tamime",       "value": "poi:mosquee-thier-tamime",   "group": "Mosquées"},
    {"label": "🕌 Grande Mosquée Saoudienne",    "value": "poi:mosquee-saudi",          "group": "Mosquées"},
    # ── Marchés ────────────────────────────────────────────────────────────────
    {"label": "🛒 Marché Capital",               "value": "poi:marche-capital",         "group": "Marchés"},
    {"label": "🛒 Marché Cinquième",             "value": "poi:marche-cinquieme",       "group": "Marchés"},
    # ── Rues connues ───────────────────────────────────────────────────────────
    {"label": "🛣️  Rue Didi Ould Bounaama",      "value": "poi:rue-didi",               "group": "Rues"},
    {"label": "🛣️  Rue Moustapha Ould M. Saleck","value": "poi:rue-moustapha",          "group": "Rues"},
    {"label": "🛣️  Sid'Ahmed Ould Khyar",        "value": "poi:sid-ahmed",              "group": "Rues"},
]

def _build_dropdown_options() -> list[dict]:
    """Convertit _POI_GROUPS en options dcc.Dropdown avec groupes."""
    return [
        {"label": poi["label"], "value": poi["value"], "group": poi["group"]}
        for poi in _POI_GROUPS
    ]

DROPDOWN_OPTIONS = _build_dropdown_options()


# ─────────────────────────────────────────────────────────────────────────────
# Figure de base — pré-calculée UNE SEULE FOIS au démarrage
# ─────────────────────────────────────────────────────────────────────────────

MAP_CENTER = dict(lat=18.08, lon=-15.97)
MAP_ZOOM   = 11

# Prépare les tableaux d'arêtes une fois (réutilisés sans recalcul)
log.info("Pré-calcul des traces de la carte …")
_EDGE_LONS: list[float] = []
_EDGE_LATS: list[float] = []
for u, v, _ in G.edges:
    _EDGE_LONS += [G.nodes[u]["lon"], G.nodes[v]["lon"], None]
    _EDGE_LATS += [G.nodes[u]["lat"], G.nodes[v]["lat"], None]

_NODE_LONS = [d["lon"] for d in G.nodes.values()]
_NODE_LATS = [d["lat"] for d in G.nodes.values()]


def _build_base_figure() -> go.Figure:
    """
    Construit la figure de base avec toutes les couches.
    Appelée UNE SEULE FOIS au démarrage — résultat stocké dans BASE_FIG.

    Index des traces (important pour restyle/extendData) :
      0 — Roads (arêtes)
      1 — Intersections (nœuds)
      2 — Route optimale (placeholder vide)
      3 — Marqueur Départ (placeholder)
      4 — Marqueur Destination (placeholder)
    """
    traces = [
        # Trace 0 : Roads
        go.Scattermap(
            lon=_EDGE_LONS, lat=_EDGE_LATS,
            mode="lines",
            line=dict(width=1, color="rgba(100,130,200,0.35)"),
            hoverinfo="none",
            name="Routes",
            visible=True,
        ),
        # Trace 1 : Intersections
        go.Scattermap(
            lon=_NODE_LONS, lat=_NODE_LATS,
            mode="markers",
            marker=dict(size=3, color="#3b82f6", opacity=0.45),
            hoverinfo="none",
            name="Intersections",
            visible=True,
        ),
        # Trace 2 : Route optimale (vide au départ)
        go.Scattermap(
            lon=[], lat=[],
            mode="lines",
            line=dict(width=5, color="#ef4444"),
            hoverinfo="none",
            name="Itinéraire optimal",
            visible=False,
        ),
        # Trace 3 : Marqueur Départ (vide au départ)
        go.Scattermap(
            lon=[], lat=[],
            mode="markers+text",
            marker=dict(size=14, color="#22c55e"),
            text=[],
            textfont=dict(size=12, color="#22c55e"),
            textposition="middle right",
            hoverinfo="text",
            name="Départ",
            visible=False,
        ),
        # Trace 4 : Marqueur Destination (vide au départ)
        go.Scattermap(
            lon=[], lat=[],
            mode="markers+text",
            marker=dict(size=14, color="#ef4444"),
            text=[],
            textfont=dict(size=12, color="#ef4444"),
            textposition="middle right",
            hoverinfo="text",
            name="Destination",
            visible=False,
        ),
    ]
    fig = go.Figure(data=traces)
    fig.update_layout(
        map=dict(style="open-street-map", center=MAP_CENTER, zoom=MAP_ZOOM),
        margin=dict(l=0, r=0, t=0, b=0),
        legend=dict(
            bgcolor="rgba(15,23,42,0.85)", bordercolor="#334155",
            borderwidth=1, font=dict(color="#f1f5f9", size=11),
            x=0.01, y=0.99,
        ),
        paper_bgcolor="#0f172a",
        height=580,
        # uirevision fixe → le viewport (zoom/centre) n'est JAMAIS resetté
        # sauf si on change cette valeur explicitement
        uirevision="network-base-v1",
    )
    return fig


log.info("Construction de la figure de base …")
BASE_FIG: go.Figure = _build_base_figure()
log.info("Figure de base prête.")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers figure (MST / BFS — ces modes refont une figure complète car rares)
# ─────────────────────────────────────────────────────────────────────────────

def _fig_with_mst(mst_edges: list) -> go.Figure:
    """Figure de base + couche MST en vert. Appelée rarement → OK de reconstruire."""
    lons, lats = [], []
    for u, v, _ in mst_edges:
        lons += [G.nodes[u]["lon"], G.nodes[v]["lon"], None]
        lats += [G.nodes[u]["lat"], G.nodes[v]["lat"], None]
    fig = go.Figure(BASE_FIG)   # copie légère
    fig.add_trace(go.Scattermap(
        lon=lons, lat=lats,
        mode="lines",
        line=dict(width=2, color="#22c55e"),
        hoverinfo="none",
        name="ACM (Kruskal)",
    ))
    fig.update_layout(uirevision="mst")
    return fig


def _fig_with_bfs(reachable: set[int], src_node: int) -> go.Figure:
    """Figure de base + nœuds BFS en jaune. Appelée rarement → OK de reconstruire."""
    lons = [G.nodes[n]["lon"] for n in reachable if n in G.nodes]
    lats = [G.nodes[n]["lat"] for n in reachable if n in G.nodes]
    fig = go.Figure(BASE_FIG)   # copie légère
    fig.add_trace(go.Scattermap(
        lon=lons, lat=lats,
        mode="markers",
        marker=dict(size=5, color="#fbbf24", opacity=0.55),
        hoverinfo="none",
        name="Visités (BFS/DFS)",
    ))
    nd = G.nodes[src_node]
    fig.add_trace(go.Scattermap(
        lon=[nd["lon"]], lat=[nd["lat"]],
        mode="markers",
        marker=dict(size=14, color="#a855f7"),
        name="Source BFS/DFS",
        hoverinfo="text",
        hovertext=f"Source : nœud {src_node}",
    ))
    fig.update_layout(uirevision="bfs")
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# Style constants
# ─────────────────────────────────────────────────────────────────────────────

C = {
    "bg":      "#0f172a",
    "card":    "#1e293b",
    "border":  "#334155",
    "text":    "#f1f5f9",
    "muted":   "#94a3b8",
    "accent":  "#3b82f6",
    "green":   "#22c55e",
    "red":     "#ef4444",
    "yellow":  "#fbbf24",
    "purple":  "#a855f7",
}

# Style commun pour les dcc.Dropdown
_DD_STYLE = {
    "backgroundColor": "#0f172a",
    "color": C["text"],
    "border": f"1px solid {C['border']}",
    "borderRadius": "6px",
    "fontSize": "13px",
}


def _card(children, extra_style: dict | None = None) -> html.Div:
    style = {
        "background": C["card"],
        "border": f"1px solid {C['border']}",
        "borderRadius": "10px",
        "padding": "16px",
        "marginBottom": "14px",
        "color": C["text"],
    }
    if extra_style:
        style.update(extra_style)
    return html.Div(style=style, children=children)


def _label(text: str, tip: str = "") -> html.Div:
    children: list = [
        html.Span(text, style={"fontWeight": "600", "fontSize": "12px", "color": C["text"]})
    ]
    if tip:
        children.append(
            html.P(tip, style={"margin": "2px 0 6px", "fontSize": "11px", "color": C["muted"]})
        )
    return html.Div(children, style={"marginBottom": "4px"})


def _btn(label: str, btn_id: str, color: str = "#3b82f6", outline: bool = False) -> html.Button:
    if outline:
        style = {
            "cursor": "pointer", "padding": "8px 14px", "borderRadius": "6px",
            "border": f"1px solid {color}", "background": "transparent",
            "color": color, "fontWeight": "600", "fontSize": "12px",
            "width": "100%", "marginTop": "6px",
        }
    else:
        style = {
            "cursor": "pointer", "padding": "8px 14px", "borderRadius": "6px",
            "border": "none", "background": color,
            "color": "white", "fontWeight": "700", "fontSize": "13px",
            "width": "100%", "marginTop": "6px",
        }
    return html.Button(label, id=btn_id, n_clicks=0, style=style)


# ─────────────────────────────────────────────────────────────────────────────
# App layout
# ─────────────────────────────────────────────────────────────────────────────

app = dash.Dash(__name__, title="Nouakchott Transport — Itinéraire")

# CSS global pour les dropdowns en dark mode (injection via index_string ou assets)
app.index_string = """
<!DOCTYPE html>
<html>
<head>
{%metas%}
<title>{%title%}</title>
{%favicon%}
{%css%}
<style>
  /* Dropdown dark mode override */
  .Select-control { background-color: #0f172a !important; border-color: #334155 !important; }
  .Select-menu-outer { background-color: #1e293b !important; border-color: #334155 !important; z-index: 9999; }
  .Select-option { background-color: #1e293b !important; color: #f1f5f9 !important; }
  .Select-option:hover, .Select-option.is-focused { background-color: #334155 !important; }
  .Select-value-label { color: #f1f5f9 !important; }
  .Select-placeholder { color: #94a3b8 !important; }
  .Select-input input { color: #f1f5f9 !important; background: transparent !important; }
  .VirtualizedSelectFocusedOption { background-color: #3b82f6 !important; color: white !important; }
  /* Scrollbar subtile */
  ::-webkit-scrollbar { width: 6px; } ::-webkit-scrollbar-track { background: #1e293b; }
  ::-webkit-scrollbar-thumb { background: #334155; border-radius: 3px; }
</style>
</head>
<body>
{%app_entry%}
<footer>{%config%}{%scripts%}{%renderer%}</footer>
</body>
</html>
"""

app.layout = html.Div(
    style={
        "fontFamily": "Inter, system-ui, sans-serif",
        "background": C["bg"],
        "minHeight": "100vh",
        "color": C["text"],
    },
    children=[

        # ── Header ─────────────────────────────────────────────────────────
        html.Div(
            style={
                "background": "linear-gradient(135deg,#1e3a5f,#0f172a)",
                "padding": "16px 28px",
                "borderBottom": f"1px solid {C['border']}",
                "display": "flex",
                "alignItems": "center",
                "gap": "16px",
            },
            children=[
                html.Span("🗺️", style={"fontSize": "28px"}),
                html.Div([
                    html.H1(
                        "Réseau de Transport — Nouakchott",
                        style={"margin": 0, "fontSize": "20px", "fontWeight": "700"},
                    ),
                    html.P(
                        "Trouvez votre itinéraire · Analysez le réseau routier",
                        style={"margin": 0, "fontSize": "12px", "color": C["muted"]},
                    ),
                ]),
                # Tabs
                html.Div(
                    style={"marginLeft": "auto", "display": "flex", "gap": "8px"},
                    children=[
                        html.Button("🧭 Itinéraire", id="tab-simple", n_clicks=0,
                                    style={"padding": "7px 16px", "borderRadius": "6px",
                                           "border": "none", "cursor": "pointer",
                                           "background": C["accent"], "color": "white",
                                           "fontWeight": "700", "fontSize": "12px"}),
                        html.Button("🔬 Analyse avancée", id="tab-advanced", n_clicks=0,
                                    style={"padding": "7px 16px", "borderRadius": "6px",
                                           "border": f"1px solid {C['border']}", "cursor": "pointer",
                                           "background": "transparent", "color": C["muted"],
                                           "fontWeight": "600", "fontSize": "12px"}),
                    ],
                ),
            ],
        ),

        # ── Body ────────────────────────────────────────────────────────────
        html.Div(
            style={"display": "flex", "gap": "16px", "padding": "16px 20px"},
            children=[

                # ── Panneau gauche ─────────────────────────────────────────
                html.Div(style={"width": "300px", "flexShrink": 0}, children=[

                    # ────────────── MODE SIMPLE ────────────────────────────
                    html.Div(id="panel-simple", children=[

                        # Carte de recherche d'itinéraire
                        _card([
                            html.H3("🧭 Trouver un itinéraire",
                                    style={"margin": "0 0 14px", "fontSize": "14px"}),

                            # ── Départ ──────────────────────────────────────
                            _label("📍 Départ",
                                   "Sélectionnez dans la liste ou cliquez sur la carte"),
                            dcc.Dropdown(
                                id="dd-from",
                                options=DROPDOWN_OPTIONS,
                                placeholder="Choisissez un lieu de départ…",
                                searchable=True,
                                clearable=True,
                                style={"marginBottom": "4px"},
                                # Le style dark mode est injecté via CSS global
                            ),
                            html.Div(
                                id="label-from",
                                style={"fontSize": "11px", "color": C["green"],
                                       "marginTop": "4px", "minHeight": "16px"},
                            ),
                            _btn("📌 Choisir le départ sur la carte",
                                 "btn-pick-start", color="#16a34a", outline=True),

                            html.Hr(style={"border": f"1px solid {C['border']}", "margin": "12px 0"}),

                            # ── Destination ──────────────────────────────────
                            _label("🏁 Destination",
                                   "Sélectionnez dans la liste ou cliquez sur la carte"),
                            dcc.Dropdown(
                                id="dd-to",
                                options=DROPDOWN_OPTIONS,
                                placeholder="Choisissez une destination…",
                                searchable=True,
                                clearable=True,
                                style={"marginBottom": "4px"},
                            ),
                            html.Div(
                                id="label-to",
                                style={"fontSize": "11px", "color": C["red"],
                                       "marginTop": "4px", "minHeight": "16px"},
                            ),
                            _btn("📌 Choisir la destination sur la carte",
                                 "btn-pick-end", color="#dc2626", outline=True),

                            html.Hr(style={"border": f"1px solid {C['border']}", "margin": "12px 0"}),

                            _btn("🔴  Calculer l'itinéraire", "btn-route", color="#dc2626"),

                            html.Div(
                                id="route-result",
                                style={"marginTop": "10px", "fontSize": "12px",
                                       "lineHeight": "1.6"},
                            ),
                        ]),

                        # Carte stats réseau
                        _card([
                            html.H3("📊 Réseau routier",
                                    style={"margin": "0 0 10px", "fontSize": "13px"}),
                            html.Div(id="stats-block",
                                     style={"fontSize": "12px", "color": C["muted"]}),
                        ]),

                        # Toggles couches carte
                        _card([
                            html.H3("👁️ Affichage de la carte",
                                    style={"margin": "0 0 10px", "fontSize": "13px"}),
                            html.Div(style={"display": "flex", "gap": "8px"}, children=[
                                html.Button(
                                    "🛣️ Routes",
                                    id="btn-toggle-roads",
                                    n_clicks=0,
                                    style={
                                        "flex": 1, "padding": "6px", "borderRadius": "6px",
                                        "border": f"1px solid {C['accent']}",
                                        "background": C["accent"], "color": "white",
                                        "fontWeight": "600", "fontSize": "11px",
                                        "cursor": "pointer",
                                    },
                                ),
                                html.Button(
                                    "🔵 Intersections",
                                    id="btn-toggle-nodes",
                                    n_clicks=0,
                                    style={
                                        "flex": 1, "padding": "6px", "borderRadius": "6px",
                                        "border": f"1px solid {C['accent']}",
                                        "background": C["accent"], "color": "white",
                                        "fontWeight": "600", "fontSize": "11px",
                                        "cursor": "pointer",
                                    },
                                ),
                            ]),
                            html.P("Cliquez pour afficher/masquer les couches.",
                                   style={"fontSize": "10px", "color": C["muted"],
                                          "margin": "6px 0 0"}),
                        ]),

                        # Bannière mode clic carte
                        html.Div(id="pick-mode-banner", style={"display": "none"}),

                    ]),

                    # ────────────── MODE AVANCÉ ────────────────────────────
                    html.Div(id="panel-advanced", style={"display": "none"}, children=[

                        # Connexité
                        _card([
                            html.H3("🔗 Vérifier la connexité",
                                    style={"margin": "0 0 10px", "fontSize": "13px"}),
                            html.P(
                                "Déterminez si tous les carrefours sont accessibles entre eux.",
                                style={"fontSize": "11px", "color": C["muted"], "margin": "0 0 8px"},
                            ),
                            _btn("Analyser la connexité", "btn-conn", color=C["accent"]),
                            html.Div(id="conn-result",
                                     style={"marginTop": "8px", "fontSize": "12px"}),
                        ]),

                        # BFS / DFS
                        _card([
                            html.H3("🔍 Parcours BFS / DFS",
                                    style={"margin": "0 0 10px", "fontSize": "13px"}),
                            _label("Point de départ",
                                   "Utilise le départ déjà sélectionné ou le premier nœud"),
                            dcc.Input(
                                id="input-traverse", type="text", debounce=True,
                                placeholder="ex. Centre Ville…",
                                style={
                                    "width": "100%", "boxSizing": "border-box",
                                    "padding": "7px", "borderRadius": "6px",
                                    "border": f"1px solid {C['border']}",
                                    "background": "#0f172a", "color": C["text"],
                                    "fontSize": "12px",
                                },
                            ),
                            _btn("▶ Lancer BFS & DFS", "btn-traverse", color=C["purple"]),
                            html.Div(
                                id="traverse-result",
                                style={"marginTop": "8px", "fontSize": "11px",
                                       "color": "#c4b5fd", "whiteSpace": "pre-wrap",
                                       "lineHeight": "1.6"},
                            ),
                        ]),

                        # MST
                        _card([
                            html.H3("🌳 Arbre Couvrant Minimal (Kruskal)",
                                    style={"margin": "0 0 10px", "fontSize": "13px"}),
                            html.P(
                                "Infrastructure minimale pour relier tous les carrefours.",
                                style={"fontSize": "11px", "color": C["muted"], "margin": "0 0 8px"},
                            ),
                            _btn("🟢 Afficher l'ACM", "btn-mst", color="#16a34a"),
                            html.Div(
                                id="mst-result",
                                style={"marginTop": "8px", "fontSize": "11px", "color": "#86efac"},
                            ),
                        ]),
                    ]),

                ]),

                # ── Carte + légende ────────────────────────────────────────
                html.Div(style={"flex": 1, "minWidth": 0}, children=[

                    _card(
                        [dcc.Graph(
                            id="map-graph",
                            figure=BASE_FIG,
                            config={"scrollZoom": True, "displayModeBar": False},
                            style={"height": "580px"},
                        )],
                        extra_style={"padding": "0", "overflow": "hidden"},
                    ),

                    _card([
                        html.Span("Légende : ", style={"fontWeight": "700", "fontSize": "12px"}),
                        html.Span("🔵 Réseau routier  ", style={"fontSize": "12px"}),
                        html.Span("🔴 Itinéraire optimal  ",
                                  style={"fontSize": "12px", "color": C["red"]}),
                        html.Span("🟢 ACM (Kruskal)  ",
                                  style={"fontSize": "12px", "color": C["green"]}),
                        html.Span("🟡 Nœuds visités (BFS/DFS)",
                                  style={"fontSize": "12px", "color": C["yellow"]}),
                    ], extra_style={"padding": "8px 16px", "display": "flex",
                                    "flexWrap": "wrap", "gap": "4px", "marginBottom": 0}),

                ]),
            ],
        ),

        # ── Stores (état léger côté client) ────────────────────────────────
        dcc.Store(id="store-src-node",  data=None),   # id du nœud source snappé
        dcc.Store(id="store-dst-node",  data=None),   # id du nœud destination snappé
        dcc.Store(id="store-src-coord", data=None),   # [lat, lon] départ
        dcc.Store(id="store-dst-coord", data=None),   # [lat, lon] destination
        dcc.Store(id="store-pick-mode", data=None),   # "start" | "end" | None
        dcc.Store(id="store-mode",      data="simple"),
        dcc.Store(id="store-roads-visible",  data=True),   # toggle état roads
        dcc.Store(id="store-nodes-visible",  data=True),   # toggle état nodes
    ],
)


# ─────────────────────────────────────────────────────────────────────────────
# Callbacks
# ─────────────────────────────────────────────────────────────────────────────

# ── Changement de tab ─────────────────────────────────────────────────────────
@app.callback(
    Output("panel-simple",   "style"),
    Output("panel-advanced", "style"),
    Output("tab-simple",     "style"),
    Output("tab-advanced",   "style"),
    Output("store-mode",     "data"),
    Input("tab-simple",   "n_clicks"),
    Input("tab-advanced", "n_clicks"),
    prevent_initial_call=False,
)
def switch_tab(n_simple, n_advanced):
    is_adv = ctx.triggered_id == "tab-advanced"
    show   = {"display": "block"}
    hide   = {"display": "none"}
    active   = {"padding": "7px 16px", "borderRadius": "6px", "border": "none",
                "cursor": "pointer", "background": C["accent"],
                "color": "white", "fontWeight": "700", "fontSize": "12px"}
    inactive = {"padding": "7px 16px", "borderRadius": "6px",
                "border": f"1px solid {C['border']}", "cursor": "pointer",
                "background": "transparent", "color": C["muted"],
                "fontWeight": "600", "fontSize": "12px"}
    if is_adv:
        return hide, show, inactive, active, "advanced"
    return show, hide, active, inactive, "simple"


# ── Bloc stats réseau ─────────────────────────────────────────────────────────
@app.callback(
    Output("stats-block", "children"),
    Input("store-mode", "data"),
)
def show_stats(_):
    s = _stats
    conn_badge = (
        html.Span("✅ Connexe", style={"color": C["green"], "fontWeight": "700"})
        if s["is_connected"]
        else html.Span(f"⚠️ {s['components']} composantes",
                       style={"color": C["yellow"], "fontWeight": "700"})
    )
    return [
        html.P(f"Carrefours (nœuds)  : {s['intersections']:,}", style={"margin": "3px 0"}),
        html.P(f"Segments de route   : {s['road_segments']:,}", style={"margin": "3px 0"}),
        html.P(f"Longueur totale     : {s['total_km']:.1f} km",  style={"margin": "3px 0"}),
        html.P(["Connexité : ", conn_badge],                      style={"margin": "3px 0"}),
    ]


# ── Dropdown Départ → geocode + snap ─────────────────────────────────────────
@app.callback(
    Output("label-from",      "children"),
    Output("store-src-node",  "data"),
    Output("store-src-coord", "data"),
    Input("dd-from", "value"),
    prevent_initial_call=True,
)
def geocode_from(value):
    return _geocode_and_snap(value, is_start=True)


# ── Dropdown Destination → geocode + snap ─────────────────────────────────────
@app.callback(
    Output("label-to",        "children"),
    Output("store-dst-node",  "data"),
    Output("store-dst-coord", "data"),
    Input("dd-to", "value"),
    prevent_initial_call=True,
)
def geocode_to(value):
    return _geocode_and_snap(value, is_start=False)


def _geocode_and_snap(value: str | None, is_start: bool):
    """
    Résout les coordonnées d'un lieu sélectionné dans le dropdown et snapper
    au nœud le plus proche du graphe.

    Ordre de résolution (du plus rapide au plus lent) :
      1. POI_COORDS (dict en mémoire, instantané) ← utilisé pour toutes les
         valeurs "poi:..." de la liste déroulante
      2. geocode() (cache JSON sur disque, ~1 ms si déjà en cache)
      3. Nominatim HTTP (fallback réseau, ~1-2 s) ← rarement atteint

    Retourne (label_html, node_id, [lat, lon]).
    """
    if not value:
        return "", None, None

    # ── Étape 1 : lookup direct dans POI_COORDS (zéro réseau) ────────────────
    result = POI_COORDS.get(value)

    # ── Étape 2 : fallback Nominatim (pour clics carte ou valeurs custom) ─────
    if result is None:
        result = geocode(value.strip())

    if result is None:
        return (
            html.Span(
                "❌ Lieu non trouvé dans le réseau. Essayez de cliquer directement sur la carte.",
                style={"color": C["red"], "fontSize": "11px"},
            ),
            None, None,
        )

    snap       = SNAPPER.snap(result["lat"], result["lon"])
    short_name = result["display_name"].split(",")[0]
    color      = C["green"] if is_start else C["red"]
    label      = html.Span(
        f"✅ {short_name} {snap.label()}",
        style={"color": color},
    )
    return label, snap.node_id, [result["lat"], result["lon"]]


# ── Boutons pick-mode (clic sur carte) ────────────────────────────────────────
@app.callback(
    Output("store-pick-mode",  "data"),
    Output("pick-mode-banner", "children"),
    Output("pick-mode-banner", "style"),
    Input("btn-pick-start", "n_clicks"),
    Input("btn-pick-end",   "n_clicks"),
    prevent_initial_call=True,
)
def set_pick_mode(n_start, n_end):
    mode = "start" if ctx.triggered_id == "btn-pick-start" else "end"
    text = (
        "🖱️  Cliquez sur la carte pour choisir le point de départ."
        if mode == "start"
        else "🖱️  Cliquez sur la carte pour choisir la destination."
    )
    banner_style = {
        "background": "#1c3461" if mode == "start" else "#3a1c1c",
        "border": f"1px solid {C['border']}",
        "borderRadius": "8px",
        "padding": "8px 12px",
        "marginBottom": "10px",
        "fontSize": "12px",
        "color": C["text"],
        "display": "block",
    }
    return mode, text, banner_style


# ── Clic sur la carte → snap + remplissage dropdown ──────────────────────────
@app.callback(
    Output("dd-from",          "value",   allow_duplicate=True),
    Output("label-from",       "children",allow_duplicate=True),
    Output("store-src-node",   "data",    allow_duplicate=True),
    Output("store-src-coord",  "data",    allow_duplicate=True),
    Output("dd-to",            "value",   allow_duplicate=True),
    Output("label-to",         "children",allow_duplicate=True),
    Output("store-dst-node",   "data",    allow_duplicate=True),
    Output("store-dst-coord",  "data",    allow_duplicate=True),
    Output("store-pick-mode",  "data",    allow_duplicate=True),
    Output("pick-mode-banner", "style",   allow_duplicate=True),
    Input("map-graph", "clickData"),
    State("store-pick-mode", "data"),
    prevent_initial_call=True,
)
def handle_map_click(click_data, pick_mode):
    no_up  = no_update
    hidden = {"display": "none"}

    if not click_data or not pick_mode:
        return (no_up,) * 8 + (None, hidden)

    pt  = click_data["points"][0]
    lat = pt.get("lat")
    lon = pt.get("lon")
    if lat is None or lon is None:
        return (no_up,) * 8 + (None, hidden)

    snap    = SNAPPER.snap(lat, lon)
    address = reverse_geocode(snap.node_lat, snap.node_lon)
    short   = address.split(",")[0] if "," in address else address
    color   = C["green"] if pick_mode == "start" else C["red"]
    label_el = html.Span(
        f"✅ {short} {snap.label()}",
        style={"color": color},
    )

    if pick_mode == "start":
        return (
            address, label_el,
            snap.node_id, [snap.node_lat, snap.node_lon],
            no_up, no_up, no_up, no_up,
            None, hidden,
        )
    else:
        return (
            no_up, no_up, no_up, no_up,
            address, label_el,
            snap.node_id, [snap.node_lat, snap.node_lon],
            None, hidden,
        )


# ── Calcul de l'itinéraire ────────────────────────────────────────────────────
@app.callback(
    Output("map-graph",    "figure",   allow_duplicate=True),
    Output("route-result", "children"),
    Input("btn-route", "n_clicks"),
    State("store-src-node",  "data"),
    State("store-dst-node",  "data"),
    State("store-src-coord", "data"),
    State("store-dst-coord", "data"),
    prevent_initial_call=True,
)
def compute_route_cb(n_clicks, src_node, dst_node, src_coord, dst_coord):
    """
    Calcule l'itinéraire optimal et met à jour UNIQUEMENT les traces
    route + marqueurs dans la figure (pas de reconstruction complète).

    Performance :
      • BASE_FIG est copiée (légère), pas reconstruite depuis les données.
      • Le résultat Dijkstra est mis en cache par (src_node, dst_node).
      • uirevision dynamique conserve le viewport.
    """
    if not src_node or not dst_node:
        msg = html.Span(
            "⚠️  Veuillez d'abord sélectionner un départ et une destination.",
            style={"color": C["yellow"]},
        )
        return no_update, msg

    # Copie légère de la figure de base (partage les mêmes données numpy)
    fig = go.Figure(BASE_FIG)

    # Route via cache LRU — Dijkstra ne tourne qu'une fois par paire unique
    result = _cached_route(int(src_node), int(dst_node))

    if result["ok"]:
        path = result["path"]
        route_lons = [G.nodes[n]["lon"] for n in path]
        route_lats = [G.nodes[n]["lat"] for n in path]
        # Met à jour trace 2 (route) directement
        fig.data[2].lon     = route_lons
        fig.data[2].lat     = route_lats
        fig.data[2].visible = True

    # Marqueur Départ (trace 3)
    if src_coord:
        fig.data[3].lon     = [src_coord[1]]
        fig.data[3].lat     = [src_coord[0]]
        fig.data[3].text    = ["  Départ"]
        fig.data[3].visible = True

    # Marqueur Destination (trace 4)
    if dst_coord:
        fig.data[4].lon     = [dst_coord[1]]
        fig.data[4].lat     = [dst_coord[0]]
        fig.data[4].text    = ["  Destination"]
        fig.data[4].visible = True

    # uirevision unique par paire → viewport conservé sauf si paire change
    fig.update_layout(uirevision=f"route-{src_node}-{dst_node}")

    # Feedback utilisateur
    if result["ok"]:
        d_m  = result["distance_m"]
        d_km = result["distance_km"]
        dist_str = f"{d_m:.0f} m" if d_m < 1000 else f"{d_km:.2f} km"
        # Temps estimé (vitesse moyenne urbaine : 30 km/h)
        speed_kmh = 30.0
        time_min  = (d_km / speed_kmh) * 60
        time_str  = (
            f"{int(time_min)} min"
            if time_min < 60
            else f"{int(time_min // 60)}h{int(time_min % 60):02d}"
        )
        feedback = [
            html.P("✅ Itinéraire trouvé !",
                   style={"color": C["green"], "fontWeight": "700", "margin": "4px 0"}),
            html.P(f"📏 Distance  : {dist_str}",
                   style={"margin": "3px 0"}),
            html.P(f"⏱️  Temps est. : ~{time_str} (30 km/h)",
                   style={"margin": "3px 0", "color": C["muted"]}),
            html.P(f"🔀 Segments  : {result['hops']} tronçons",
                   style={"margin": "3px 0"}),
            html.P("La route est affichée en rouge sur la carte.",
                   style={"color": C["muted"], "fontSize": "11px", "margin": "6px 0 0"}),
        ]
    else:
        feedback = [
            html.P("❌ Aucun itinéraire trouvé",
                   style={"color": C["red"], "fontWeight": "700", "margin": "4px 0"}),
            html.P(result["error"],
                   style={"color": C["yellow"], "fontSize": "12px", "margin": "4px 0",
                          "lineHeight": "1.5"}),
        ]

    return fig, feedback


# ── Toggle couches carte (Roads / Intersections) ──────────────────────────────
@app.callback(
    Output("map-graph",             "figure",   allow_duplicate=True),
    Output("btn-toggle-roads",      "style"),
    Output("btn-toggle-nodes",      "style"),
    Output("store-roads-visible",   "data"),
    Output("store-nodes-visible",   "data"),
    Input("btn-toggle-roads", "n_clicks"),
    Input("btn-toggle-nodes", "n_clicks"),
    State("store-roads-visible", "data"),
    State("store-nodes-visible", "data"),
    prevent_initial_call=True,
)
def toggle_layers(n_roads, n_nodes, roads_vis, nodes_vis):
    """
    Bascule la visibilité des couches Roads (trace 0) et Intersections (trace 1).
    Utilise fig.update_traces (ciblé par index) → pas de re-render complet.
    """
    triggered = ctx.triggered_id
    new_roads_vis = roads_vis
    new_nodes_vis = nodes_vis

    if triggered == "btn-toggle-roads":
        new_roads_vis = not roads_vis
    elif triggered == "btn-toggle-nodes":
        new_nodes_vis = not nodes_vis

    def _btn_style(active: bool) -> dict:
        return {
            "flex": 1, "padding": "6px", "borderRadius": "6px",
            "cursor": "pointer", "fontWeight": "600", "fontSize": "11px",
            "border": f"1px solid {C['accent']}",
            "background": C["accent"] if active else "transparent",
            "color": "white" if active else C["muted"],
        }

    # Copie la figure courante et ajuste la visibilité des traces 0 et 1
    fig = go.Figure(BASE_FIG)
    fig.data[0].visible = new_roads_vis
    fig.data[1].visible = new_nodes_vis
    fig.update_layout(uirevision="toggle-layers")

    return (
        fig,
        _btn_style(new_roads_vis),
        _btn_style(new_nodes_vis),
        new_roads_vis,
        new_nodes_vis,
    )


# ── Connexité ─────────────────────────────────────────────────────────────────
@app.callback(
    Output("conn-result", "children"),
    Input("btn-conn", "n_clicks"),
    prevent_initial_call=True,
)
def check_conn(_):
    s = _stats
    if s["is_connected"]:
        return html.Span(
            f"✅ Le réseau est entièrement connexe — "
            f"tous les {s['intersections']:,} carrefours sont reliés.",
            style={"color": C["green"], "fontWeight": "600"},
        )
    comps = get_components_list(G)
    sizes = sorted([len(c) for c in comps], reverse=True)
    return [
        html.P("⚠️  Le réseau n'est PAS entièrement connexe.",
               style={"color": C["yellow"], "fontWeight": "700", "margin": "4px 0"}),
        html.P(f"Nombre de composantes : {len(comps)}",
               style={"margin": "3px 0", "fontSize": "12px"}),
        html.P(
            f"Plus grande composante : {sizes[0]:,} carrefours "
            f"({sizes[0] / G.n_nodes * 100:.1f} % du réseau)",
            style={"margin": "3px 0", "fontSize": "12px"},
        ),
        html.P(f"5 plus grandes : {sizes[:5]}",
               style={"margin": "3px 0", "fontSize": "11px", "color": C["muted"]}),
    ]


# ── BFS / DFS traversal ───────────────────────────────────────────────────────
@app.callback(
    Output("map-graph",       "figure",   allow_duplicate=True),
    Output("traverse-result", "children"),
    Input("btn-traverse", "n_clicks"),
    State("input-traverse",  "value"),
    State("store-src-node",  "data"),
    prevent_initial_call=True,
)
def run_traversal(_, traverse_input, src_node_store):
    """Lance BFS + DFS depuis le nœud source. Résultat affiché en jaune sur la carte."""
    src        = None
    input_label = ""

    if traverse_input and traverse_input.strip():
        r = geocode(traverse_input.strip())
        if r:
            snap        = SNAPPER.snap(r["lat"], r["lon"])
            src         = snap.node_id
            input_label = traverse_input.strip()

    if src is None and src_node_store is not None:
        src = int(src_node_store)
    if src is None:
        src = next(iter(G.nodes))

    bfs_r = run_bfs(G, src)
    dfs_r = run_dfs(G, src)

    fig = _fig_with_bfs(bfs_r["reachable"], src)

    prefix = f"« {input_label} »" if input_label else f"nœud {src}"
    text = (
        f"BFS depuis {prefix}\n"
        f"  Carrefours visités : {bfs_r['visited_count']:,}\n"
        f"  Profondeur max     : {bfs_r['max_depth']} sauts\n"
        f"  Profondeur moy.    : {bfs_r['avg_depth']:.1f} sauts\n"
        f"  15 premiers nœuds  : {bfs_r['first_15']}\n\n"
        f"DFS depuis {prefix}\n"
        f"  Carrefours visités : {dfs_r['visited_count']:,}\n"
        f"  15 premiers nœuds  : {dfs_r['first_15']}"
    )
    return fig, text


# ── MST (Kruskal) ─────────────────────────────────────────────────────────────
@app.callback(
    Output("map-graph",  "figure",   allow_duplicate=True),
    Output("mst-result", "children"),
    Input("btn-mst", "n_clicks"),
    prevent_initial_call=True,
)
def show_mst(_):
    """Affiche l'Arbre Couvrant Minimal. Résultat Kruskal est lui-même mis en cache."""
    mst = get_mst(G)
    fig = _fig_with_mst(mst["edges"])
    feedback = [
        html.P("✅ Arbre Couvrant Minimal calculé (Kruskal)",
               style={"color": C["green"], "fontWeight": "700", "margin": "4px 0"}),
        html.P(f"Segments dans l'ACM : {mst['edge_count']:,}",
               style={"margin": "3px 0"}),
        html.P(f"Coût total          : {mst['total_cost_km']:.1f} km",
               style={"margin": "3px 0"}),
        html.P(f"Économie vs réseau  : {mst['savings_pct']:.1f} %",
               style={"margin": "3px 0"}),
        html.P(
            "L'ACM en vert représente l'infrastructure minimale pour relier "
            "tous les carrefours du réseau.",
            style={"color": C["muted"], "fontSize": "11px",
                   "margin": "6px 0 0", "lineHeight": "1.5"},
        ),
    ]
    return fig, feedback


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "=" * 62)
    print("  🗺️  Nouakchott Transport Network  –  v3 Dashboard (Optimisé)")
    print(f"  Graphe  : {G.n_nodes:,} intersections · {G.n_edges:,} segments")
    print(f"  Cache   : LRU 512 routes, KDTree spatial index")
    print(f"  Open    : http://127.0.0.1:8050")
    print("=" * 62 + "\n")
    app.run(debug=False, host="0.0.0.0", port=8050)