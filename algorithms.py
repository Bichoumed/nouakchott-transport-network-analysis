"""
algorithms.py
=============
Graph traversal and optimisation algorithms for the transport network.

Algorithms implemented (from scratch, no external graph libraries used):
  1. BFS  – Breadth-First Search
  2. DFS  – Depth-First Search
  3. Dijkstra – Single-source shortest path (min-heap)
  4. Kruskal  – Minimum Spanning Tree (Union-Find)

All functions accept a TransportGraph or a plain adjacency-list dict so they
can also be unit-tested independently.
"""

import heapq
from collections import deque
from typing import Optional
from graph import TransportGraph


# ---------------------------------------------------------------------------
# 1. BFS – Breadth-First Search
# ---------------------------------------------------------------------------

def bfs(
    G: TransportGraph,
    source: int,
) -> dict:
    """
    Breadth-First Search from `source`.

    Returns
    -------
    {
      'visited_order' : list[int]   – nodes in visit order,
      'parent'        : dict        – parent[v] = u (BFS tree),
      'distance'      : dict        – hop-count distance from source,
      'reachable'     : set[int]    – all reachable nodes,
    }
    """
    visited = {source}
    parent = {source: None}
    distance = {source: 0}
    visited_order = [source]
    queue = deque([source])

    while queue:
        u = queue.popleft()
        for v, _ in G.adj.get(u, []):
            if v not in visited:
                visited.add(v)
                parent[v] = u
                distance[v] = distance[u] + 1
                visited_order.append(v)
                queue.append(v)

    return {
        "visited_order": visited_order,
        "parent": parent,
        "distance": distance,
        "reachable": visited,
    }


def is_connected(G: TransportGraph) -> bool:
    """Return True if all nodes are reachable from node 0."""
    if G.n_nodes == 0:
        return True
    source = next(iter(G.nodes))
    result = bfs(G, source)
    return len(result["reachable"]) == G.n_nodes


def connected_components(G: TransportGraph) -> list[set[int]]:
    """Return list of connected components (sets of node ids)."""
    unvisited = set(G.nodes.keys())
    components = []
    while unvisited:
        seed = next(iter(unvisited))
        result = bfs(G, seed)
        comp = result["reachable"]
        components.append(comp)
        unvisited -= comp
    return components


# ---------------------------------------------------------------------------
# 2. DFS – Depth-First Search
# ---------------------------------------------------------------------------

def dfs(
    G: TransportGraph,
    source: int,
) -> dict:
    """
    Iterative Depth-First Search from `source`.

    Returns
    -------
    {
      'visited_order' : list[int],
      'parent'        : dict,
      'reachable'     : set[int],
    }
    """
    visited = set()
    parent = {source: None}
    visited_order = []
    stack = [source]

    while stack:
        u = stack.pop()
        if u in visited:
            continue
        visited.add(u)
        visited_order.append(u)
        for v, _ in G.adj.get(u, []):
            if v not in visited:
                if v not in parent:
                    parent[v] = u
                stack.append(v)

    return {
        "visited_order": visited_order,
        "parent": parent,
        "reachable": visited,
    }


# ---------------------------------------------------------------------------
# 3. Dijkstra – Single-source shortest path
# ---------------------------------------------------------------------------

def dijkstra(
    G: TransportGraph,
    source: int,
    target: Optional[int] = None,
) -> dict:
    """
    Dijkstra's algorithm using a binary min-heap (heapq).

    Parameters
    ----------
    source : start node id.
    target : if provided, stop early when target is settled.

    Returns
    -------
    {
      'dist'   : dict[int → float]  – shortest distances from source,
      'parent' : dict[int → int]    – shortest-path tree,
    }
    Reconstruct path: call reconstruct_path(result, source, target).
    """
    INF = float("inf")
    dist = {nid: INF for nid in G.nodes}
    dist[source] = 0.0
    parent = {source: None}
    heap = [(0.0, source)]  # (dist, node)
    settled = set()

    while heap:
        d_u, u = heapq.heappop(heap)
        if u in settled:
            continue
        settled.add(u)
        if target is not None and u == target:
            break
        for v, w in G.adj.get(u, []):
            if v in settled:
                continue
            alt = d_u + w
            if alt < dist[v]:
                dist[v] = alt
                parent[v] = u
                heapq.heappush(heap, (alt, v))

    return {"dist": dist, "parent": parent}


def reconstruct_path(dijkstra_result: dict, source: int, target: int) -> list[int]:
    """
    Rebuild the shortest path from dijkstra result.

    Returns list of node ids from source → target, or [] if unreachable.
    """
    parent = dijkstra_result["parent"]
    if dijkstra_result["dist"].get(target, float("inf")) == float("inf"):
        return []  # unreachable
    path = []
    cur = target
    while cur is not None:
        path.append(cur)
        cur = parent.get(cur)
    path.reverse()
    if path[0] != source:
        return []
    return path


def shortest_path(G: TransportGraph, source: int, target: int) -> dict:
    """
    Convenience wrapper: compute shortest path and return friendly result.

    Returns
    -------
    {
      'path'     : list[int]  – node ids, empty if unreachable,
      'distance' : float      – total distance in metres (-1 if unreachable),
      'hops'     : int,
    }
    """
    res = dijkstra(G, source, target)
    path = reconstruct_path(res, source, target)
    dist = res["dist"].get(target, -1)
    return {
        "path": path,
        "distance": dist if dist != float("inf") else -1,
        "hops": len(path) - 1 if path else -1,
    }


# ---------------------------------------------------------------------------
# 4. Kruskal – Minimum Spanning Tree
# ---------------------------------------------------------------------------

class UnionFind:
    """Disjoint-set (union-find) with path compression and union by rank."""

    def __init__(self, nodes: list[int]):
        self.parent = {n: n for n in nodes}
        self.rank = {n: 0 for n in nodes}

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]  # path halving
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> bool:
        """Union a and b. Returns True if they were in different components."""
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return False
        if self.rank[ra] < self.rank[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        if self.rank[ra] == self.rank[rb]:
            self.rank[ra] += 1
        return True


def kruskal(G: TransportGraph) -> dict:
    """
    Kruskal's Minimum Spanning Tree algorithm.

    Returns
    -------
    {
      'mst_edges'   : list[(u, v, weight)],
      'total_cost'  : float   (metres),
      'is_spanning' : bool    (True if MST covers all nodes),
    }
    """
    uf = UnionFind(list(G.nodes.keys()))
    sorted_edges = sorted(G.edges, key=lambda e: e[2])
    mst_edges = []
    total_cost = 0.0

    for u, v, w in sorted_edges:
        if uf.union(u, v):
            mst_edges.append((u, v, w))
            total_cost += w
            if len(mst_edges) == G.n_nodes - 1:
                break  # MST complete

    return {
        "mst_edges": mst_edges,
        "total_cost": total_cost,
        "is_spanning": len(mst_edges) == G.n_nodes - 1,
    }


# ---------------------------------------------------------------------------
# Experimentation helpers
# ---------------------------------------------------------------------------

def compare_bfs_dfs(G: TransportGraph, source: int) -> dict:
    """
    Run BFS and DFS from the same source and compare their traversal orders.

    Returns summary statistics.
    """
    b = bfs(G, source)
    d = dfs(G, source)

    bfs_order = b["visited_order"]
    dfs_order = d["visited_order"]

    # How many nodes appear in the same position in both traversals?
    common_pos = sum(1 for i, (x, y) in enumerate(zip(bfs_order, dfs_order)) if x == y)

    return {
        "bfs_order": bfs_order[:20],   # first 20 for display
        "dfs_order": dfs_order[:20],
        "bfs_reachable": len(b["reachable"]),
        "dfs_reachable": len(d["reachable"]),
        "both_reachable_match": len(b["reachable"]) == len(d["reachable"]),
        "common_positions": common_pos,
    }


# ---------------------------------------------------------------------------
# CLI smoke-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    from graph import build_graph_from_csv

    csv = sys.argv[1] if len(sys.argv) > 1 else "nouakchott_transport_network.csv"
    print("Building graph …")
    G = build_graph_from_csv(csv, max_rows=500)
    print(G.summary())

    src = next(iter(G.nodes))

    print("\n--- BFS ---")
    b = bfs(G, src)
    print(f"  Visited {len(b['visited_order'])} nodes")
    print(f"  First 10: {b['visited_order'][:10]}")

    print("\n--- DFS ---")
    d = dfs(G, src)
    print(f"  Visited {len(d['visited_order'])} nodes")
    print(f"  First 10: {d['visited_order'][:10]}")

    print("\n--- Connectivity ---")
    comps = connected_components(G)
    print(f"  Connected: {len(comps) == 1}")
    print(f"  Components: {len(comps)}")

    nodes_list = list(G.nodes.keys())
    if len(nodes_list) >= 2:
        s, t = nodes_list[0], nodes_list[min(50, len(nodes_list)-1)]
        print(f"\n--- Shortest path: {s} → {t} ---")
        sp = shortest_path(G, s, t)
        print(f"  Distance: {sp['distance']:.1f} m, Hops: {sp['hops']}")
        print(f"  Path: {sp['path']}")

    print("\n--- Kruskal MST ---")
    mst = kruskal(G)
    print(f"  MST edges   : {len(mst['mst_edges'])}")
    print(f"  Total cost  : {mst['total_cost']/1000:.2f} km")
    print(f"  Is spanning : {mst['is_spanning']}")
