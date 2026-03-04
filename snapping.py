"""
snapping.py
===========
Snap arbitrary (lat, lon) coordinates to the nearest node in the transport graph.

Uses scipy.spatial.KDTree on projected coordinates for fast O(log n) queries.

Public API
----------
  GraphSnapper(G)             – build the index (call once)
  snapper.snap(lat, lon)      – returns SnapResult
  snapper.snap_batch(points)  – vectorised version
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from scipy.spatial import KDTree

if TYPE_CHECKING:
    from graph import TransportGraph


# ── Simple equirectangular projection (good enough for a city) ────────────────

def _project(lat: float, lon: float, lat0: float = 18.08, lon0: float = -15.97) -> tuple[float, float]:
    """
    Convert (lat, lon) to approximate (x, y) in metres relative to (lat0, lon0).
    Accurate within ~0.1 % for distances < 50 km near the equator.
    """
    R = 6_371_000
    x = math.radians(lon - lon0) * R * math.cos(math.radians(lat0))
    y = math.radians(lat - lat0) * R
    return x, y


@dataclass
class SnapResult:
    node_id: int
    node_lat: float
    node_lon: float
    distance_m: float   # straight-line distance from query point to snapped node

    def label(self) -> str:
        d = self.distance_m
        if d < 10:
            return f"(snapped, <10 m)"
        elif d < 1000:
            return f"(snapped {d:.0f} m away)"
        else:
            return f"(snapped {d/1000:.1f} km away)"


class GraphSnapper:
    """
    Builds a KDTree from all graph nodes and provides fast nearest-node lookup.

    Parameters
    ----------
    G : TransportGraph
    """

    def __init__(self, G: "TransportGraph"):
        self._G = G
        self._ids = np.array(sorted(G.nodes.keys()), dtype=np.int64)
        # Build projected coordinate array
        coords_m = np.array(
            [_project(G.nodes[nid]["lat"], G.nodes[nid]["lon"]) for nid in self._ids],
            dtype=np.float64,
        )
        self._tree = KDTree(coords_m)
        self._lat0 = 18.08
        self._lon0 = -15.97

    def snap(self, lat: float, lon: float) -> SnapResult:
        """Return the nearest graph node to (lat, lon)."""
        x, y = _project(lat, lon)
        dist_m, idx = self._tree.query([x, y])
        nid = int(self._ids[idx])
        nd = self._G.nodes[nid]
        return SnapResult(
            node_id=nid,
            node_lat=nd["lat"],
            node_lon=nd["lon"],
            distance_m=float(dist_m),
        )

    def snap_batch(self, points: list[tuple[float, float]]) -> list[SnapResult]:
        """Snap a list of (lat, lon) pairs in one KDTree query."""
        projected = np.array([_project(lat, lon) for lat, lon in points], dtype=np.float64)
        dists, idxs = self._tree.query(projected)
        results = []
        for dist_m, idx in zip(dists, idxs):
            nid = int(self._ids[idx])
            nd = self._G.nodes[nid]
            results.append(SnapResult(
                node_id=nid,
                node_lat=nd["lat"],
                node_lon=nd["lon"],
                distance_m=float(dist_m),
            ))
        return results

    def nearest_in_component(
        self,
        lat: float,
        lon: float,
        component: set[int],
        k: int = 10,
    ) -> SnapResult | None:
        """
        Find the nearest node within a specific connected component.
        Used to suggest the closest reachable alternative when no route exists.
        """
        x, y = _project(lat, lon)
        dists, idxs = self._tree.query([x, y], k=min(k, len(self._ids)))
        for dist_m, idx in zip(dists, idxs):
            nid = int(self._ids[idx])
            if nid in component:
                nd = self._G.nodes[nid]
                return SnapResult(
                    node_id=nid,
                    node_lat=nd["lat"],
                    node_lon=nd["lon"],
                    distance_m=float(dist_m),
                )
        return None
