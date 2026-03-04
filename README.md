# 🗺️ Réseau de Transport — Nouakchott

> Analyse et calcul d'itinéraires dans le réseau routier de Nouakchott  
> Sujet 1 · Cours Analyse de Graphes · Université de Nouakchott Al-Aasriya 2024-2025

---

## Aperçu

Application interactive qui charge le réseau routier de Nouakchott depuis des données **OpenStreetMap** (Geofabrik), le modélise sous forme de **graphe pondéré**, et permet de :

- Calculer l'itinéraire optimal entre deux points (algorithme de **Dijkstra**)
- Analyser la connectivité du réseau (**BFS / DFS**)
- Afficher l'**Arbre Couvrant Minimal** (algorithme de **Kruskal**)
- Explorer le réseau via une carte interactive **Dash / Plotly**

---

## Démonstration rapide

```
python app.py
# → ouvre http://127.0.0.1:8050
```

---

## Structure du projet

```
projet/
│
├── app.py                          # Application Dash principale
├── graph.py                        # Classe TransportGraph + parsing CSV
├── algorithms.py                   # BFS, DFS, Dijkstra, Kruskal (from scratch)
├── graph_algos.py                  # Wrappers haut niveau pour le dashboard
├── snapping.py                     # Index spatial KDTree (snap coordonnées → nœud)
├── geocoding.py                    # Géocodage Nominatim avec cache JSON
├── experiments.py                  # Script d'expérimentations et benchmarks
│
├── nouakchott_transport_network.csv  # Dataset (23 360 entrées, 4 613 km de routes)
├── geocode_cache.json              # Cache des géocodages (évite les requêtes réseau)
│
└── README.md
```

---

## Dataset

| Propriété | Valeur |
|-----------|--------|
| Source | OpenStreetMap via [Geofabrik](https://download.geofabrik.de/africa/mauritania.html) |
| Fichier original | `mauritania-latest-free.shp.zip` |
| Fichier utilisé | `nouakchott_transport_network.csv` |
| Entrées totales | 23 360 |
| Dont routes | 23 256 (16 types : residential, trunk, primary…) |
| Dont arrêts/stations | 104 (bus_stop, bus_station, taxi) |
| Longueur totale | ~4 613 km |
| Zone couverte | Bounding box Nouakchott : lon [-16.05, -15.75] / lat [17.90, 18.25] |

**Colonnes du CSV :**

| Colonne | Description |
|---------|-------------|
| `category` | `road`, `stop`, `station` |
| `subtype` | Type OSM (`residential`, `primary`, `trunk`…) |
| `name` | Nom de la voie (renseigné pour ~5% des routes) |
| `lon` / `lat` | Coordonnées GPS du centre du segment |
| `length_m` | Longueur du segment en mètres (poids de l'arête) |
| `osm_id` | Identifiant unique OpenStreetMap |
| `geometry_wkt` | Géométrie `LINESTRING` avec tous les points du segment |

---

## Modélisation

Le réseau est représenté comme un **graphe non orienté pondéré** :

- **Nœuds** : intersections routières (coordonnées GPS arrondies à 5 décimales ≈ 1 m)
- **Arêtes** : segments de route reliant deux intersections
- **Poids** : longueur du segment en mètres (calculée par la formule haversine)
- **Représentation** : liste d'adjacence `{ node_id: [(voisin, poids), ...] }`

---

## Algorithmes implémentés

Tous les algorithmes sont implémentés **from scratch** dans `algorithms.py`, sans bibliothèque de graphes externe.

### BFS — Parcours en Largeur
```
Complexité : O(V + E)
Usage      : vérification de la connexité, composantes connexes
File FIFO  : explore niveau par niveau
```

### DFS — Parcours en Profondeur
```
Complexité : O(V + E)
Usage      : comparaison avec BFS, détection d'impasses
Pile LIFO  : explore aussi loin que possible avant de revenir
```

### Dijkstra — Plus Court Chemin
```
Complexité : O((V + E) log V)  avec tas binaire (heapq)
Usage      : calcul d'itinéraire optimal entre deux nœuds
Condition  : poids strictement positifs (vérifiée ici)
Optimisation : arrêt anticipé dès que la destination est atteinte
```

### Kruskal — Arbre Couvrant Minimal
```
Complexité : O(E log E)  dominée par le tri des arêtes
Usage      : infrastructure minimale pour connecter tous les carrefours
Structure  : Union-Find avec compression de chemin et union par rang
```

---

## Installation

### Prérequis

- Python 3.10+
- pip

### Dépendances

```bash
pip install dash plotly pandas scipy numpy tldextract
```

| Package | Rôle |
|---------|------|
| `dash` | Framework application web |
| `plotly` | Rendu cartographique interactif |
| `pandas` | Chargement et manipulation du CSV |
| `scipy` | `KDTree` pour le snapping spatial en O(log N) |
| `numpy` | Calculs vectoriels sur les coordonnées |
| `tldextract` | Parsing des noms de domaine (géocodage) |

### Lancer l'application

```bash
# Lancement standard
python app.py

# Avec un CSV spécifique
python app.py chemin/vers/transport.csv

# Limiter les lignes (test rapide)
MAX_ROWS=1000 python app.py

# Variable d'environnement pour le CSV
TRANSPORT_CSV=/data/nouakchott.csv python app.py
```

Ouvrir ensuite : **http://127.0.0.1:8050**

---

## Fonctionnalités

### 🧭 Mode Itinéraire

- Sélectionner le **départ** et la **destination** via les menus déroulants (29 lieux groupés par catégorie : Santé, Éducation, Quartiers, Axes routiers, Mosquées, Marchés…)
- Ou cliquer directement sur la carte pour choisir n'importe quel point du réseau
- Cliquer **Calculer l'itinéraire** → le chemin optimal s'affiche en rouge
- Distance totale, temps estimé (~30 km/h) et nombre de segments sont affichés

### 🔬 Mode Analyse avancée

- **Connexité** : lance un BFS sur tout le réseau et affiche le nombre de composantes connexes et leurs tailles
- **BFS / DFS** : visualise en jaune les nœuds visités depuis un point source
- **ACM (Kruskal)** : affiche en vert l'Arbre Couvrant Minimal avec son coût total

### 👁️ Affichage

- Basculer l'affichage des routes et des intersections indépendamment
- Zoom et navigation conservés entre les calculs (`uirevision`)

---

## Optimisations de performance

| Optimisation | Détail |
|---|---|
| `BASE_FIG` pré-calculée | La figure de base (routes + nœuds) est construite une seule fois au démarrage |
| Cache LRU routes | `functools.lru_cache(maxsize=512)` sur les paires `(src, dst)` déjà calculées |
| Index KDTree | Snapping en O(log N) via `scipy.spatial.KDTree` au lieu de O(N) |
| `uirevision` dynamique | Le viewport (zoom/centre) n'est jamais réinitialisé inutilement |
| `prevent_initial_call` | Les callbacks ne se déclenchent pas au chargement |
| POI en mémoire | Les 29 lieux du dropdown ont leurs coordonnées embarquées — zéro appel réseau |

---

## Lancer les expérimentations

```bash
python experiments.py nouakchott_transport_network.csv
```

Ce script exécute et affiche :
1. Construction du graphe et statistiques
2. Analyse de la connexité (composantes, taille de la plus grande)
3. Comparaison BFS vs DFS (ordre de visite, profondeur, temps)
4. Dijkstra sur plusieurs paires de nœuds (distance, sauts, temps d'exécution)
5. Kruskal MST (nombre d'arêtes, coût total, économie vs réseau complet)
6. Scalabilité : benchmarks BFS/DFS/Kruskal sur graphes aléatoires (n=50, 200, 500)

---

## Architecture des callbacks Dash

```
Départ sélectionné (dropdown)
    └─► geocode_from()  →  store-src-node, store-src-coord

Destination sélectionnée (dropdown)
    └─► geocode_to()    →  store-dst-node, store-dst-coord

Clic sur carte  +  mode pick
    └─► handle_map_click()  →  met à jour le dropdown + stores

Bouton "Calculer"
    └─► compute_route_cb()
            ├─ _cached_route(src, dst)  ←  LRU cache Dijkstra
            ├─ Met à jour trace 2 (route rouge)
            ├─ Met à jour traces 3-4 (marqueurs)
            └─► map-graph.figure  +  route-result

Toggles Roads / Intersections
    └─► toggle_layers()  →  visible=True/False sur traces 0-1
```

---

## Notes sur les données OSM

- Le réseau n'est **pas entièrement connexe** : certains segments OSM ne sont pas reliés physiquement, créant de petites composantes isolées. La plus grande composante couvre >95% des nœuds.
- Seules ~5% des routes ont un nom renseigné dans OSM pour Nouakchott.
- Le graphe est **non orienté** : les sens uniques ne sont pas modélisés (données OSM `oneway` non exploitées dans cette version).

---

## Pistes d'amélioration

- [ ] Graphe orienté avec les données `oneway` d'OSM
- [ ] Algorithme A* avec heuristique euclidienne pour des calculs plus rapides
- [ ] Pondération par type de voie (vitesse différente sur `trunk` vs `residential`)
- [ ] Intégration des lignes de bus pour l'analyse multimodale
- [ ] Données de trafic en temps réel pour des poids dynamiques

---

## Références

- OpenStreetMap Contributors — https://www.openstreetmap.org
- Geofabrik, extrait Mauritanie — https://download.geofabrik.de/africa/mauritania.html
- Dijkstra, E. W. (1959). *A note on two problems in connexion with graphs.* Numerische Mathematik.
- Cormen et al. (2022). *Introduction to Algorithms* (4e éd.). MIT Press.
- Plotly Dash — https://dash.plotly.com

---

*Projet réalisé dans le cadre du cours Analyse de Graphes — Université de Nouakchott Al-Aasriya, 2024-2025*
