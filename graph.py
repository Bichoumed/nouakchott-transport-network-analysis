"""
graph.py
========
Graph modeling for the Nouakchott transport network.

The network is represented as a weighted undirected graph:
  - Nodes   : unique geographic coordinates (rounded lat/lon pairs),
               representing road intersections or segment endpoints.
  - Edges   : road segments linking two nodes.
  - Weights : Euclidean distance in metres (field `length_m` from the CSV).

Two data-structures are provided:
  1. Adjacency list  – dict[node_id → list[(neighbor_id, weight)]]
  2. Adjacency matrix – only built on demand (memory-intensive for large graphs).
"""

import re
import math
import pandas as pd
from collections import defaultdict
from pathlib import Path


# ---------------------------------------------------------------------------
# Coordinate helpers
# ---------------------------------------------------------------------------

def _parse_linestring(wkt: str) -> list[tuple[float, float]]:
    """Return list of (lon, lat) from a WKT LINESTRING."""
    nums = re.findall(r"[-\d.]+", wkt.replace("LINESTRING", ""))
    coords = []
    it = iter(nums)
    for lon, lat in zip(it, it):
        coords.append((float(lon), float(lat)))
    return coords


def _round_coord(lon: float, lat: float, decimals: int = 5) -> tuple[float, float]:
    """Round coordinates to `decimals` places to snap near-duplicate nodes."""
    return (round(lon, decimals), round(lat, decimals))


def haversine_m(lon1, lat1, lon2, lat2) -> float:
    """Great-circle distance in metres."""
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


# ---------------------------------------------------------------------------
# TransportGraph class
# ---------------------------------------------------------------------------

class TransportGraph:
    """
    Weighted undirected graph for the Nouakchott transport network.

    Attributes
    ----------
    adj      : dict  – adjacency list  { node_id: [(nbr_id, weight), ...] }
    nodes    : dict  – { node_id: {'lon': float, 'lat': float, 'name': str} }
    edges    : list  – [(u, v, weight)]
    n_nodes  : int
    n_edges  : int
    """

    def __init__(self):
        self.adj: dict[int, list[tuple[int, float]]] = defaultdict(list)
        self.nodes: dict[int, dict] = {}
        self.edges: list[tuple[int, int, float]] = []
        self._coord_to_id: dict[tuple, int] = {}
        self._next_id = 0

    # ------------------------------------------------------------------
    # Node / edge registration
    # ------------------------------------------------------------------

    def _get_or_create_node(self, lon: float, lat: float, name: str = "") -> int:
        key = _round_coord(lon, lat)
        if key not in self._coord_to_id:
            nid = self._next_id
            self._coord_to_id[key] = nid
            self.nodes[nid] = {"lon": key[0], "lat": key[1], "name": name or ""}
            self._next_id += 1
        return self._coord_to_id[key]

    def add_edge(self, u: int, v: int, weight: float) -> None:
        if u == v:
            return  # skip self-loops
        self.adj[u].append((v, weight))
        self.adj[v].append((u, weight))
        self.edges.append((u, v, weight))

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def n_nodes(self) -> int:
        return len(self.nodes)

    @property
    def n_edges(self) -> int:
        return len(self.edges)

    # ------------------------------------------------------------------
    # Adjacency matrix (on demand)
    # ------------------------------------------------------------------

    def adjacency_matrix(self) -> tuple[list[int], list[list[float]]]:
        """
        Return (node_ids, matrix) where matrix[i][j] = weight if edge exists,
        0 otherwise. WARNING: O(n²) memory – only use on small subgraphs.
        """
        ids = sorted(self.nodes.keys())
        idx = {nid: i for i, nid in enumerate(ids)}
        n = len(ids)
        mat = [[0.0] * n for _ in range(n)]
        for u, v, w in self.edges:
            i, j = idx[u], idx[v]
            mat[i][j] = w
            mat[j][i] = w
        return ids, mat

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def summary(self) -> str:
        total_w = sum(w for _, _, w in self.edges)
        degree_seq = [len(nbrs) for nbrs in self.adj.values()]
        avg_deg = sum(degree_seq) / len(degree_seq) if degree_seq else 0
        return (
            f"TransportGraph\n"
            f"  Nodes  : {self.n_nodes:,}\n"
            f"  Edges  : {self.n_edges:,}\n"
            f"  Total length : {total_w/1000:.2f} km\n"
            f"  Avg degree   : {avg_deg:.2f}"
        )


# ---------------------------------------------------------------------------
# Factory – build graph from CSV
# ---------------------------------------------------------------------------

def build_graph_from_csv(
    csv_path: str | Path,
    road_types: list[str] | None = None,
    max_rows: int | None = None,
) -> TransportGraph:
    """
    Parse the Nouakchott CSV and return a TransportGraph.

    Parameters
    ----------
    csv_path   : path to the CSV file.
    road_types : list of `subtype` values to include (None = all road rows).
    max_rows   : limit rows for quick testing (None = all).
    """
    df = pd.read_csv(csv_path)

    # Keep only road rows (exclude bus_stop metadata rows if present)
    df = df[df["category"] == "road"].copy()

    if road_types:
        df = df[df["subtype"].isin(road_types)]

    if max_rows:
        df = df.head(max_rows)

    G = TransportGraph()

    for _, row in df.iterrows():
        wkt = row.get("geometry_wkt", "")
        if not isinstance(wkt, str) or "LINESTRING" not in wkt:
            continue

        coords = _parse_linestring(wkt)
        if len(coords) < 2:
            continue

        weight = float(row["length_m"]) if pd.notna(row.get("length_m")) else 0.0
        name = str(row.get("name", "")) if pd.notna(row.get("name")) else ""

        # Register ALL intermediate nodes so adjacent segments share endpoints,
        # producing a well-connected graph (essential for correct BFS/DFS/Dijkstra)
        n_segs = max(len(coords) - 1, 1)
        w_per_seg = weight / n_segs
        prev_nid = None
        for lon_c, lat_c in coords:
            cur_nid = G._get_or_create_node(lon_c, lat_c, name)
            if prev_nid is not None and prev_nid != cur_nid:
                G.add_edge(prev_nid, cur_nid, w_per_seg)
            prev_nid = cur_nid

    return G


# ---------------------------------------------------------------------------
# Convenience: get a smaller representative subgraph for UI speed
# ---------------------------------------------------------------------------

def build_subgraph(G: TransportGraph, seed_node: int, max_nodes: int = 300) -> "TransportGraph":
    """BFS-based subgraph around seed_node for fast rendering."""
    from collections import deque
    visited = {}
    queue = deque([seed_node])
    visited[seed_node] = True
    while queue and len(visited) < max_nodes:
        cur = queue.popleft()
        for nbr, _ in G.adj.get(cur, []):
            if nbr not in visited:
                visited[nbr] = True
                queue.append(nbr)

    sub = TransportGraph()
    for nid in visited:
        nd = G.nodes[nid]
        sub._get_or_create_node(nd["lon"], nd["lat"], nd.get("name", ""))

    for u, v, w in G.edges:
        if u in visited and v in visited:
            uid = sub._get_or_create_node(G.nodes[u]["lon"], G.nodes[u]["lat"])
            vid = sub._get_or_create_node(G.nodes[v]["lon"], G.nodes[v]["lat"])
            if not any(nbr == vid for nbr, _ in sub.adj.get(uid, [])):
                sub.add_edge(uid, vid, w)

    return sub


if __name__ == "__main__":
    import sys
    csv = sys.argv[1] if len(sys.argv) > 1 else "nouakchott_transport_network.csv"
    G = build_graph_from_csv(csv)
    print(G.summary())
