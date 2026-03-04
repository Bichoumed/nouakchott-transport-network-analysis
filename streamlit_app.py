from __future__ import annotations

import os
import time
import functools
from pathlib import Path

import streamlit as st
import plotly.graph_objects as go

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG STREAMLIT
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Réseau de Transport — Nouakchott",
    layout="wide",
)

# ─────────────────────────────────────────────────────────────────────────────
# PATH CSV
# ─────────────────────────────────────────────────────────────────────────────
DEFAULT_CSV = str(Path(__file__).parent / "nouakchott_transport_network.csv")
CSV_PATH = os.environ.get("TRANSPORT_CSV", DEFAULT_CSV)
MAX_ROWS = int(os.environ.get("MAX_ROWS", "0")) or None

# ─────────────────────────────────────────────────────────────────────────────
# IMPORTS PROJET (doivent exister dans ton repo)
# ─────────────────────────────────────────────────────────────────────────────
from graph import build_graph_from_csv, TransportGraph
from snapping import GraphSnapper
from graph_algos import (
    get_component_map, get_components_list, graph_stats,
    compute_route, run_bfs, run_dfs, get_mst,
)
from geocoding import geocode, reverse_geocode

# ─────────────────────────────────────────────────────────────────────────────
# POIs (reprend ta logique "value -> coord")
# ─────────────────────────────────────────────────────────────────────────────
POI_COORDS = {
    "Hôpital Cheikh Zayed": (18.0751095, -15.9357556),
    "Hôpital National": (18.0965, -15.9657),
    "Pharmacie Centrale": (18.0960, -15.9670),
    "Université de Nouakchott": (18.1010, -15.9730),
    "Tevragh Zeina": (18.1100, -15.9820),
    "Ksar": (18.0990, -15.9560),
    "El Mina": (18.0600, -15.9750),
    "Arafat": (18.0380, -15.9570),
    "Dar Naim": (18.0800, -15.9340),
    "Teyarett": (18.0850, -15.9650),
    "Sebkha": (18.0700, -15.9650),
    "Riad": (18.0620, -15.9450),
    "Toujounine": (18.0650, -15.9200),
    "Aéroport Oumtounsy": (18.0977, -15.9478),
    "Palais Présidentiel": (18.0890, -15.9910),
    "Banque Centrale (BCM)": (18.0920, -15.9800),
    "Grande Mosquée Saoudienne": (18.0870, -15.9730),
    "Marché Capital": (18.0960, -15.9620),
    "Marché Cinquième": (18.0710, -15.9630),
}

# ─────────────────────────────────────────────────────────────────────────────
# CACHE: charger graphe + snapper 1 seule fois
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_resource(show_spinner=True)
def load_resources(csv_path: str, max_rows: int | None):
    t0 = time.time()
    G: TransportGraph = build_graph_from_csv(csv_path, max_rows=max_rows)
    snapper = GraphSnapper(G)
    stats = graph_stats(G)
    comp_map = get_component_map(G)
    comps = get_components_list(G)
    dt = time.time() - t0
    return G, snapper, stats, comp_map, comps, dt

G, SNAPPER, STATS, COMP_MAP, COMPS, LOAD_SECONDS = load_resources(CSV_PATH, MAX_ROWS)

# ─────────────────────────────────────────────────────────────────────────────
# ROUTE CACHE (éviter recalcul)
# ─────────────────────────────────────────────────────────────────────────────
@functools.lru_cache(maxsize=512)
def cached_route(src: int, dst: int) -> dict:
    return compute_route(G, src, dst)

# ─────────────────────────────────────────────────────────────────────────────
# FIGURE BASE (pré-calcul)
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_resource(show_spinner=False)
def build_base_figure():
    edge_lons, edge_lats = [], []
    for u, v, _ in G.edges:
        edge_lons += [G.nodes[u]["lon"], G.nodes[v]["lon"], None]
        edge_lats += [G.nodes[u]["lat"], G.nodes[v]["lat"], None]
    node_lons = [d["lon"] for d in G.nodes.values()]
    node_lats = [d["lat"] for d in G.nodes.values()]

    fig = go.Figure(
        data=[
            go.Scattermap(
                lon=edge_lons, lat=edge_lats,
                mode="lines",
                line=dict(width=1, color="rgba(100,130,200,0.35)"),
                hoverinfo="none",
                name="Routes",
                visible=True,
            ),
            go.Scattermap(
                lon=node_lons, lat=node_lats,
                mode="markers",
                marker=dict(size=3, opacity=0.45),
                hoverinfo="none",
                name="Intersections",
                visible=True,
            ),
            go.Scattermap(
                lon=[], lat=[],
                mode="lines",
                line=dict(width=5, color="#ef4444"),
                hoverinfo="none",
                name="Itinéraire optimal",
                visible=False,
            ),
            go.Scattermap(
                lon=[], lat=[],
                mode="markers+text",
                marker=dict(size=14, color="#22c55e"),
                text=[],
                textposition="middle right",
                hoverinfo="text",
                name="Départ",
                visible=False,
            ),
            go.Scattermap(
                lon=[], lat=[],
                mode="markers+text",
                marker=dict(size=14, color="#ef4444"),
                text=[],
                textposition="middle right",
                hoverinfo="text",
                name="Destination",
                visible=False,
            ),
        ]
    )
    fig.update_layout(
        map=dict(style="open-street-map", center=dict(lat=18.08, lon=-15.97), zoom=11),
        margin=dict(l=0, r=0, t=0, b=0),
        height=600,
        uirevision="base",
    )
    return fig

BASE_FIG = build_base_figure()

# ─────────────────────────────────────────────────────────────────────────────
# SESSION STATE INIT
# ─────────────────────────────────────────────────────────────────────────────
if "src_node" not in st.session_state:
    st.session_state.src_node = None
if "dst_node" not in st.session_state:
    st.session_state.dst_node = None
if "src_coord" not in st.session_state:
    st.session_state.src_coord = None  # (lat, lon)
if "dst_coord" not in st.session_state:
    st.session_state.dst_coord = None
if "route_result" not in st.session_state:
    st.session_state.route_result = None

# ─────────────────────────────────────────────────────────────────────────────
# UI
# ─────────────────────────────────────────────────────────────────────────────
st.title("Réseau de Transport — Nouakchott")
st.caption("Trouver un itinéraire · Analyser le réseau routier (version Streamlit)")

with st.expander("📌 Infos chargement", expanded=False):
    st.write(f"CSV: `{CSV_PATH}`")
    st.write(f"Chargement: {LOAD_SECONDS:.2f}s")
    st.write(f"Nœuds: {STATS['intersections']:,} — Arêtes: {STATS['road_segments']:,} — Longueur: {STATS['total_km']:.1f} km")
    st.write(f"Connexité: {'Connexe' if STATS['is_connected'] else f\"{STATS['components']} composantes\"}")

left, right = st.columns([0.28, 0.72], gap="large")

# ─────────────────────────────────────────────────────────────────────────────
# LEFT PANEL
# ─────────────────────────────────────────────────────────────────────────────
with left:
    st.subheader("🧭 Itinéraire")

    # toggles
    show_roads = st.toggle("🛣️ Afficher Routes", value=True)
    show_nodes = st.toggle("🔵 Afficher Intersections", value=True)

    st.divider()

    # Dropdowns (searchable)
    poi_list = sorted(list(POI_COORDS.keys()))

    src_choice = st.selectbox("📍 Départ", [""] + poi_list, index=0)
    dst_choice = st.selectbox("🏁 Destination", [""] + poi_list, index=0)

    def resolve_choice(choice: str):
        if not choice:
            return None
        lat, lon = POI_COORDS[choice]
        snap = SNAPPER.snap(lat, lon)
        return snap.node_id, (lat, lon), snap

    if src_choice:
        src_node, src_coord, snap = resolve_choice(src_choice)
        st.session_state.src_node = src_node
        st.session_state.src_coord = src_coord
        st.success(f"Départ: {src_choice} — {snap.label()}")

    if dst_choice:
        dst_node, dst_coord, snap = resolve_choice(dst_choice)
        st.session_state.dst_node = dst_node
        st.session_state.dst_coord = dst_coord
        st.error(f"Destination: {dst_choice} — {snap.label()}")

    st.divider()

    if st.button("🔴 Calculer l'itinéraire", use_container_width=True):
        if st.session_state.src_node is None or st.session_state.dst_node is None:
            st.warning("Veuillez choisir un départ et une destination.")
        else:
            res = cached_route(int(st.session_state.src_node), int(st.session_state.dst_node))
            st.session_state.route_result = res

    if st.session_state.route_result:
        r = st.session_state.route_result
        if r["ok"]:
            d_km = r["distance_km"]
            time_min = (d_km / 30.0) * 60
            st.success("✅ Itinéraire trouvé")
            st.write(f"📏 Distance: **{d_km:.2f} km**")
            st.write(f"⏱️ Temps estimé: **{int(time_min)} min** (30 km/h)")
            st.write(f"🔀 Segments: **{r['hops']}**")
        else:
            st.error("❌ Aucun itinéraire trouvé")
            st.write(r.get("error", "Erreur inconnue"))

# ─────────────────────────────────────────────────────────────────────────────
# RIGHT: MAP
# ─────────────────────────────────────────────────────────────────────────────
with right:
    fig = go.Figure(BASE_FIG)

    # apply layer toggles
    fig.data[0].visible = show_roads
    fig.data[1].visible = show_nodes

    # draw route if exists
    r = st.session_state.route_result
    if r and r.get("ok"):
        path = r["path"]
        fig.data[2].lon = [G.nodes[n]["lon"] for n in path]
        fig.data[2].lat = [G.nodes[n]["lat"] for n in path]
        fig.data[2].visible = True

    # markers
    if st.session_state.src_coord:
        lat, lon = st.session_state.src_coord
        fig.data[3].lon = [lon]
        fig.data[3].lat = [lat]
        fig.data[3].text = ["  Départ"]
        fig.data[3].visible = True

    if st.session_state.dst_coord:
        lat, lon = st.session_state.dst_coord
        fig.data[4].lon = [lon]
        fig.data[4].lat = [lat]
        fig.data[4].text = ["  Destination"]
        fig.data[4].visible = True

    fig.update_layout(uirevision="keep-view")
    st.plotly_chart(fig, use_container_width=True)