"""
experiments.py
==============
Experimentation module: run BFS vs DFS comparison, test Dijkstra on multiple
pairs, and analyse MST cost vs full graph cost.

Usage:
    python experiments.py nouakchott_transport_network.csv
"""

import sys
import time
from graph import build_graph_from_csv
from algorithms import (
    bfs, dfs, shortest_path, kruskal, connected_components, compare_bfs_dfs
)


def separator(title=""):
    print("\n" + "=" * 60)
    if title:
        print(f"  {title}")
        print("=" * 60)


def run_experiments(csv_path: str):

    # ------------------------------------------------------------------ #
    # 1. Build graph                                                       #
    # ------------------------------------------------------------------ #
    separator("1. GRAPH CONSTRUCTION")
    t0 = time.perf_counter()
    G = build_graph_from_csv(csv_path)
    t1 = time.perf_counter()
    print(G.summary())
    print(f"  Build time: {t1-t0:.3f} s")

    nodes_list = sorted(G.nodes.keys())
    src = nodes_list[0]

    # ------------------------------------------------------------------ #
    # 2. Connectivity analysis                                             #
    # ------------------------------------------------------------------ #
    separator("2. CONNECTIVITY ANALYSIS")
    t0 = time.perf_counter()
    comps = connected_components(G)
    t1 = time.perf_counter()
    print(f"  Number of connected components : {len(comps)}")
    sizes = sorted([len(c) for c in comps], reverse=True)
    print(f"  Component sizes (top 5)        : {sizes[:5]}")
    print(f"  Largest component covers       : {sizes[0]/G.n_nodes*100:.1f}% of nodes")
    print(f"  Is fully connected?            : {len(comps) == 1}")
    print(f"  Computation time               : {(t1-t0)*1000:.2f} ms")

    # ------------------------------------------------------------------ #
    # 3. BFS vs DFS                                                        #
    # ------------------------------------------------------------------ #
    separator("3. BFS vs DFS COMPARISON")
    for trial_src in [nodes_list[0], nodes_list[len(nodes_list)//4]]:
        print(f"\n  Source node: {trial_src}")
        t0 = time.perf_counter()
        b = bfs(G, trial_src)
        t_bfs = time.perf_counter() - t0

        t0 = time.perf_counter()
        d = dfs(G, trial_src)
        t_dfs = time.perf_counter() - t0

        print(f"  BFS → {len(b['visited_order'])} nodes visited  ({t_bfs*1000:.2f} ms)")
        print(f"  DFS → {len(d['visited_order'])} nodes visited  ({t_dfs*1000:.2f} ms)")
        print(f"  BFS first-10 : {b['visited_order'][:10]}")
        print(f"  DFS first-10 : {d['visited_order'][:10]}")
        print(f"  BFS explores level-by-level (neighbours first).")
        print(f"  DFS explores depth-first (goes as far as possible before backtracking).")
        # Compare hop-distances from BFS to understand graph diameter
        hop_dists = sorted(b["distance"].values())
        if hop_dists:
            print(f"  BFS max hop-depth (eccentricity): {hop_dists[-1]}")
            print(f"  Avg BFS hop-depth               : {sum(hop_dists)/len(hop_dists):.2f}")

    # ------------------------------------------------------------------ #
    # 4. Dijkstra – multiple pairs                                         #
    # ------------------------------------------------------------------ #
    separator("4. DIJKSTRA SHORTEST PATH")
    pairs = [
        (nodes_list[0],   nodes_list[min(100, len(nodes_list)-1)]),
        (nodes_list[0],   nodes_list[min(500, len(nodes_list)-1)]),
        (nodes_list[10],  nodes_list[min(300, len(nodes_list)-1)]),
    ]
    print(f"  {'Pair (src→dst)':<28}  {'Dist (m)':>10}  {'Hops':>6}  {'Time (ms)':>10}")
    print("  " + "-" * 60)
    for s, t in pairs:
        t0 = time.perf_counter()
        sp = shortest_path(G, s, t)
        elapsed = (time.perf_counter() - t0) * 1000
        dist_str = f"{sp['distance']:.1f}" if sp['distance'] >= 0 else "unreachable"
        hops_str = str(sp['hops']) if sp['hops'] >= 0 else "—"
        print(f"  {s} → {t:<18}  {dist_str:>10}  {hops_str:>6}  {elapsed:>10.2f}")

    # ------------------------------------------------------------------ #
    # 5. Kruskal MST                                                       #
    # ------------------------------------------------------------------ #
    separator("5. MINIMUM SPANNING TREE (KRUSKAL)")
    t0 = time.perf_counter()
    mst = kruskal(G)
    t1 = time.perf_counter()
    total_graph_weight = sum(w for _, _, w in G.edges)
    print(f"  MST edges    : {len(mst['mst_edges'])}")
    print(f"  MST cost     : {mst['total_cost']:.1f} m  ({mst['total_cost']/1000:.2f} km)")
    print(f"  All edges cost: {total_graph_weight:.1f} m  ({total_graph_weight/1000:.2f} km)")
    savings = (1 - mst['total_cost'] / total_graph_weight) * 100 if total_graph_weight > 0 else 0
    print(f"  Cost savings vs full graph: {savings:.1f}%")
    print(f"  Is spanning  : {mst['is_spanning']}")
    print(f"  Compute time : {(t1-t0)*1000:.2f} ms")
    print(f"\n  Interpretation: the MST represents the minimum-cost infrastructure")
    print(f"  to connect all intersections — useful for urban planning and cable laying.")

    # ------------------------------------------------------------------ #
    # 6. Random graph test (scalability)                                   #
    # ------------------------------------------------------------------ #
    separator("6. SCALABILITY – RANDOM GRAPH SIZES")
    import random, math
    from graph import TransportGraph

    random.seed(42)
    for n in [50, 200, 500]:
        Gtest = TransportGraph()
        for i in range(n):
            Gtest._get_or_create_node(random.uniform(-16, -15.8), random.uniform(18, 18.2))
        ids = list(Gtest.nodes.keys())
        for i in range(n):
            for _ in range(3):
                j = random.randint(0, n-1)
                w = random.uniform(50, 2000)
                Gtest.add_edge(ids[i], ids[j], w)

        t0 = time.perf_counter()
        bfs(Gtest, ids[0])
        t_bfs = time.perf_counter() - t0
        t0 = time.perf_counter()
        dfs(Gtest, ids[0])
        t_dfs = time.perf_counter() - t0
        t0 = time.perf_counter()
        kruskal(Gtest)
        t_kruskal = time.perf_counter() - t0

        print(f"  n={n:<5}  BFS={t_bfs*1000:.2f}ms  DFS={t_dfs*1000:.2f}ms  Kruskal={t_kruskal*1000:.2f}ms")

    separator("DONE")
    print("  All experiments completed successfully.\n")


if __name__ == "__main__":
    csv = sys.argv[1] if len(sys.argv) > 1 else "nouakchott_transport_network.csv"
    run_experiments(csv)
