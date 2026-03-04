"""
graph_algos.py
==============
High-level wrappers around the low-level algorithms in algorithms.py.

Returns user-friendly dicts that the dashboard can render directly,
including component-aware error messages and route summaries.
"""

from __future__ import annotations

import functools
from typing import TYPE_CHECKING

from algorithms import (
    bfs, dfs, dijkstra, reconstruct_path,
    kruskal, connected_components,
)

if TYPE_CHECKING:
    from graph import TransportGraph


# ── Component index (computed once, cached) ───────────────────────────────────

@functools.lru_cache(maxsize=1)
def get_component_map(G: "TransportGraph") -> dict[int, int]:
    """
    Return {node_id: component_index}.
    Cached so it's only computed once per graph instance.
    NOTE: lru_cache requires G to be hashable; TransportGraph is used as-is —
    wrap the call with the same G object every time.
    """
    comps = connected_components(G)
    mapping = {}
    for i, comp in enumerate(comps):
        for nid in comp:
            mapping[nid] = i
    return mapping


def get_components_list(G: "TransportGraph") -> list[set[int]]:
    return connected_components(G)


# ── Route computation ─────────────────────────────────────────────────────────

def compute_route(
    G: "TransportGraph",
    src: int,
    dst: int,
) -> dict:
    """
    Compute shortest path from src to dst.

    Returns
    -------
    {
      "ok"          : bool,
      "path"        : list[int],         # node ids
      "distance_m"  : float,
      "distance_km" : float,
      "hops"        : int,
      "error"       : str | None,        # human-readable error message
      "suggestion"  : int | None,        # nearest reachable node to dst
    }
    """
    comp_map = get_component_map(G)
    src_comp = comp_map.get(src)
    dst_comp = comp_map.get(dst)

    if src == dst:
        nd = G.nodes[src]
        return _ok([], 0.0, 0)

    if src_comp != dst_comp:
        return {
            "ok": False,
            "path": [],
            "distance_m": -1,
            "distance_km": -1,
            "hops": -1,
            "error": (
                "No route found. The start and destination are in different "
                "disconnected parts of the road network — they cannot be reached "
                "from each other with the available road data."
            ),
            "suggestion": None,
        }

    res = dijkstra(G, src, dst)
    dist = res["dist"].get(dst, float("inf"))

    if dist == float("inf"):
        return {
            "ok": False,
            "path": [],
            "distance_m": -1,
            "distance_km": -1,
            "hops": -1,
            "error": "No route found between these two locations.",
            "suggestion": None,
        }

    path = reconstruct_path(res, src, dst)
    return _ok(path, dist, len(path) - 1)


def _ok(path, dist_m, hops):
    return {
        "ok": True,
        "path": path,
        "distance_m": dist_m,
        "distance_km": dist_m / 1000,
        "hops": hops,
        "error": None,
        "suggestion": None,
    }


# ── BFS / DFS ─────────────────────────────────────────────────────────────────

def run_bfs(G: "TransportGraph", source: int) -> dict:
    r = bfs(G, source)
    return {
        "visited_count": len(r["visited_order"]),
        "first_15": r["visited_order"][:15],
        "max_depth": max(r["distance"].values()) if r["distance"] else 0,
        "avg_depth": (sum(r["distance"].values()) / len(r["distance"])) if r["distance"] else 0,
        "reachable": r["reachable"],
    }


def run_dfs(G: "TransportGraph", source: int) -> dict:
    r = dfs(G, source)
    return {
        "visited_count": len(r["visited_order"]),
        "first_15": r["visited_order"][:15],
        "reachable": r["reachable"],
    }


# ── MST ───────────────────────────────────────────────────────────────────────

@functools.lru_cache(maxsize=1)
def get_mst(G: "TransportGraph") -> dict:
    """Compute and cache the MST (expensive for large graphs)."""
    result = kruskal(G)
    total_graph_weight = sum(w for _, _, w in G.edges)
    return {
        "edges": result["mst_edges"],
        "total_cost_m": result["total_cost"],
        "total_cost_km": result["total_cost"] / 1000,
        "is_spanning": result["is_spanning"],
        "savings_pct": (1 - result["total_cost"] / total_graph_weight) * 100
        if total_graph_weight > 0
        else 0,
        "edge_count": len(result["mst_edges"]),
    }


# ── Graph stats ───────────────────────────────────────────────────────────────

def graph_stats(G: "TransportGraph") -> dict:
    comps = get_components_list(G)
    sizes = sorted([len(c) for c in comps], reverse=True)
    return {
        "intersections": G.n_nodes,
        "road_segments": G.n_edges,
        "total_km": sum(w for _, _, w in G.edges) / 1000,
        "components": len(comps),
        "largest_component_pct": sizes[0] / G.n_nodes * 100 if G.n_nodes else 0,
        "is_connected": len(comps) == 1,
        "avg_degree": sum(len(v) for v in G.adj.values()) / G.n_nodes if G.n_nodes else 0,
    }
