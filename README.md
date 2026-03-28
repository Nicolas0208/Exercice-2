# Exercice-2
# Méthodologie — Analyse bibliométrique de l'adoption de l'IA dans la recherche scientifique (2015–2025)

> **Corpus cible :** ~1 650 000 articles scientifiques issus d'OpenAlex
> **Période :** 2015–2025 (11 ans)
> **Pipeline :** 4 scripts Python séquentiels + fichiers de sortie traçables

---

## Table des matières

1. [Vue d'ensemble du pipeline](#1-vue-densemble-du-pipeline)
2. [Script 01 — Extraction OpenAlex](#2-script-01--extraction-openalex)
3. [Script 02 — Nettoyage, enrichissement et détection IA](#3-script-02--nettoyage-enrichissement-et-détection-ia)
4. [Script 03 — Analyse descriptive](#4-script-03--analyse-descriptive)
5. [Script 04 — Analyse sémantique par embeddings](#5-script-04--analyse-sémantique-par-embeddings)
6. [Choix des échelles et paramètres graphiques](#6-choix-des-échelles-et-paramètres-graphiques)
7. [Limites et biais connus](#7-limites-et-biais-connus)

---

## 1. Vue d'ensemble du pipeline

```
01_extract_openalex.py
        │
        ▼
outputs/etape1_extraction/openalex_<année>.csv + .xlsx
        │
        ▼
02_clean_and_prepare.py
        │
        ▼
data/openalex_clean.parquet
        │
        ├──▶ 03_descriptive_analysis.py  ──▶ outputs/etape3_analyse_descriptive.xlsx
        │                                    outputs/figures/fig01 à fig13
        │
        └──▶ 04_semantic_analysis.py     ──▶ outputs/etape4_semantique.xlsx
                                             outputs/figures/fig10_semantic_diversity.png
                                             outputs/figures/fig12_intra_centroid.png
                                             outputs/figures/fig13_inter_shift.png
```

Chaque script est autonome et reproductible. Les livrables intermédiaires (Parquet, CSV) permettent de relancer n'importe quelle étape sans ré-extraire les données.

---

## 2. Script 01 — Extraction OpenAlex

### 2.1 Source de données

**OpenAlex** est une base bibliographique ouverte (héritière de Microsoft Academic Graph) qui indexe plus de 250 millions de travaux scientifiques. Elle est choisie pour :
- Son accès API gratuit (avec clé, rate-limit généreux)
- Sa couverture disciplinaire très large (toutes sciences)
- Ses métadonnées structurées : concepts hiérarchiques, topics, affiliations institutionnelles
- La disponibilité des abstracts en index inversé (format propriétaire reconstruit en texte)

### 2.2 Stratégie d'échantillonnage

#### Paramètres de volume

| Paramètre | Valeur | Justification |
|-----------|--------|---------------|
| Années | 2015–2025 | Couvre la période pré-IA générative jusqu'à l'ère post-ChatGPT |
| Articles/an cible | ~150 000 | Assez grand pour des analyses de sous-groupes fiables |
| Seeds par année | 15 | Diversification de l'échantillon aléatoire |
| Pages par seed | 50 | 50 × 200 = 10 000 articles par seed |
| Articles par page | 200 | Maximum autorisé par l'API OpenAlex |
| **Total estimé** | **~1 650 000** | 15 × 10 000 × 11 ans |

#### Mécanisme `sample= + seed=`

L'API OpenAlex expose un paramètre `sample=N` qui tire aléatoirement N articles parmi ceux correspondant au filtre. Le paramètre `seed=` fixe la graine aléatoire pour la reproductibilité.

**Pourquoi 15 seeds différents ?**
Chaque seed génère un échantillon de 10 000 articles. En variant la graine, on maximise la couverture en évitant de rééchantillonner les mêmes articles. Un mécanisme de déduplication par `openalex_id` dans le `seen_ids` set garantit que les doublons inter-seeds sont comptés mais non réintégrés.

**Pourquoi pagination par `page=` et non par `cursor=` ?**
L'API OpenAlex ne renvoie pas de `next_cursor` quand `sample=` est actif. La pagination par numéro de page (`page=1, 2, ..., 50`) est donc la seule option fonctionnelle dans ce mode.

#### Filtres API appliqués à la requête

```
filter=publication_year:<année>,type:article,has_abstract:true
```

- **`type:article`** : exclut les preprints, livres, chapitres, revues — on veut uniquement des articles à comité de lecture
- **`has_abstract:true`** : condition nécessaire pour l'analyse de contenu (détection IA, embeddings)

### 2.3 Champs extraits

| Champ API | Colonne produite | Usage |
|-----------|-----------------|-------|
| `id` | `openalex_id` | Déduplication, clé primaire |
| `title` | `title` | Analyse textuelle |
| `abstract_inverted_index` | `abstract` | Détection IA, embeddings |
| `publication_date` | `publication_date`, `year` | Temporalité, granularité trimestrielle |
| `type` | — | Filtre (article uniquement) |
| `cited_by_count` | `cited_by_count` | Mesure d'impact, percentile citations |
| `concepts` (niveaux 0–2) | `primary_discipline`, `concepts_json` | Classification disciplinaire |
| `topics` | `topics_json`, `n_topics` | Diversité thématique |
| `authorships` | `n_authors`, `countries` | Taille équipe, géographie |
| `primary_location.source` | `source_journal` | Prestige des revues |

#### Reconstruction de l'abstract

OpenAlex stocke les abstracts sous forme d'**index inversé** (mapping `mot → [positions]`) pour des raisons de droit d'auteur. La fonction `reconstruct_abstract()` reconstruit le texte en ordre positionnel :

```python
positions = [(pos, word) for word, pos_list in inverted_index.items() for pos in pos_list]
positions.sort()
return " ".join(w for _, w in positions)
```

Cette reconstruction est fidèle à l'ordre des mots mais peut manquer de ponctuation dans certains cas.

#### Extraction des concepts

Les concepts OpenAlex sont hiérarchisés en niveaux (0 = domaine large, 1 = champ, 2 = sous-champ). Seuls les **niveaux 0 à 2** sont conservés (`max_level=2`) pour limiter le bruit des concepts très spécifiques. La `primary_discipline` est le concept de niveau 0 le plus saillant.

### 2.4 Robustesse et gestion des erreurs

- **Retry automatique** (3 tentatives, délai exponentiel : 5s, 10s, 15s) sur chaque page
- **Backup CSV systématique** avant la sauvegarde Excel (protection contre les erreurs openpyxl sur certains caractères Unicode)
- **Nettoyage des caractères illégaux Excel** : suppression des caractères de contrôle XML 1.0 (`\x00–\x08`, `\x0b`, `\x0c`, `\x0e–\x1f`) et des surrogates Unicode
- **Rate-limiting** : 0,1 seconde entre chaque requête (respecte les limites API)
- **Libération mémoire** : `del records` et `del df` après sauvegarde de chaque année

### 2.5 Livrables

- `outputs/etape1_extraction/openalex_<année>.xlsx` — un fichier par année
- `outputs/etape1_extraction/openalex_<année>.csv` — backup CSV (encodage UTF-8 BOM)
- `outputs/etape1_extraction/etape1_log.xlsx` — trace globale : seeds, articles, doublons, requêtes, durée, coût estimé

---

## 3. Script 02 — Nettoyage, enrichissement et détection IA

### 3.1 Consolidation des CSV annuels

Les CSV annuels sont concaténés en un unique **Parquet brut** (`data/openalex_raw.parquet`). Le format Parquet est choisi pour :
- Compression columnar efficace (~5× moins de place que CSV)
- Lecture sélective par colonnes (les scripts 03 et 04 ne chargent que ce dont ils ont besoin)
- Préservation des types (évite les ré-inférences coûteuses)

### 3.2 Pipeline de nettoyage

Les étapes sont tracées dans un `cleaning_log` exporté dans l'onglet Excel de traçabilité.

| Étape | Règle | Justification |
|-------|-------|---------------|
| 1. Déduplication | `drop_duplicates(subset=["openalex_id"])` | Les seeds qui se chevauchent peuvent générer des doublons ; l'ID OpenAlex est l'identifiant canonique |
| 2. Filtre abstract | `len(abstract) > 50` | Les abstracts trop courts (< 50 caractères) sont souvent des métadonnées mal parsées ou des articles sans abstract réel ; ils fausseraient la détection IA et les embeddings |
| 3. Filtre discipline | `primary_discipline != "Unknown"` | Un article sans concept de niveau 0 n'est pas classifiable disciplinairement |
| 4. Filtre date | `pd.to_datetime(..., errors="coerce")` + `dropna` | Les dates invalides empêchent les analyses temporelles |

### 3.3 Enrichissements temporels

```python
df["quarter"]    = df["publication_date"].dt.to_period("Q").astype(str)  # ex: "2023Q1"
df["semester"]   = df["year"].astype(str) + "-S" + ((month-1)//6 + 1)   # ex: "2023-S1"
df["post_genai"] = (df["year"] >= 2023).astype(int)                       # dummy binaire
```

**Pourquoi 2023 comme seuil post-GenAI ?**
ChatGPT (GPT-3.5) a été lancé en novembre 2022. Les articles de 2023 sont les premiers pouvant avoir été produits avec des outils de GenAI, et les premier à mentionner massivement ces outils. Le dummy `post_genai` est utilisé comme variable de rupture dans les régressions et tests statistiques.

### 3.4 Classification géographique

#### Définition des zones

| Zone | Définition |
|------|-----------|
| `Global North` | Tous les pays d'affiliation sont dans l'ensemble OCDE 2024 + hauts revenus hors-OCDE |
| `Global South` | Aucun pays dans l'ensemble Global North |
| `International` | Collaboration Nord-Sud (au moins un pays de chaque zone) |
| `Unknown` | Aucune donnée de pays disponible |

**Choix de la liste Global North :** Membres OCDE 2024 (38 pays) + pays à hauts revenus hors-OCDE classiquement associés au Global North en bibliométrie (AE, BH, BN, CY, HK, KW, MT, OM, QA, SA, SG, TW). La Turquie (TR) et le Mexique (MX) sont conservés dans le Global North en tant que membres OCDE malgré leur statut de pays à revenus intermédiaires — conformément à la convention OCDE.

**Logique de classification par article :**
Un article est classé selon l'ensemble des codes pays de toutes ses affiliations d'auteurs. Cette approche article-centrique (vs auteur-centrique) est standard en bibliométrie internationale.

### 3.5 Détection des mentions IA

#### Architecture du dictionnaire

Le dictionnaire `AI_KEYWORDS_DETAILED` est organisé en 4 catégories avec 41 patterns regex au total :

| Catégorie | Exemples | Rationnel |
|-----------|---------|-----------|
| Modèles et architectures | `machine learning`, `deep learning`, `transformer`, `GPT`, `BERT`, `LLM`, `GAN`, `diffusion model` | Termes techniques canoniques, peu ambigus dans un contexte scientifique |
| Techniques et méthodes | `fine-tuning`, `few-shot`, `NLP`, `computer vision`, `transfer learning`, `prompt engineering` | Méthodes spécifiques à l'IA, distinguent l'IA appliquée |
| Outils et produits | `ChatGPT`, `GPT-4`, `Claude`, `Gemini`, `LLaMA`, `TensorFlow`, `PyTorch`, `Hugging Face` | Noms propres non ambigus, signalent l'utilisation concrète d'outils |
| Concepts généraux | `artificial intelligence`, `generative AI`, `AI-assisted`, `AI-driven`, `AI-powered` | Formulations génériques mais indicatives |

**Pourquoi des regex et non un modèle NLP ?**
Sur ~1,65 million d'articles, un modèle de classification nécessiterait soit un fine-tuning coûteux, soit une inférence longue. Les regex sont :
- Instantanées (traitement de l'ensemble du corpus en secondes)
- Totalement transparentes et auditables
- Suffisamment précises pour une première détection sur des termes techniques peu ambigus

#### Niveaux d'intensité IA

| Niveau | Seuil | Interprétation |
|--------|-------|---------------|
| `none` | 0 match | Aucune mention d'IA |
| `peripheral` | 1–2 matches | IA évoquée en passant (ex: revue de littérature) |
| `methodological` | 3–5 matches | IA utilisée comme outil méthodologique |
| `core` | 6+ matches | IA au cœur de l'article |

Ces seuils sont des **proxies ordinaux** : ils ne prétendent pas mesurer l'« importance » de l'IA mais permettent de distinguer les articles qui mentionnent l'IA superficiellement de ceux qui en font leur sujet central.

### 3.6 Livrables

- `data/openalex_clean.parquet` — corpus nettoyé et enrichi
- `outputs/etape2_nettoyage.xlsx` — 7 onglets :
  1. Pipeline de nettoyage (log étape par étape)
  2. Dictionnaire de mots-clés IA
  3. Taux de mention IA par année
  4. Taux de mention IA par discipline
  5. Distribution des intensités IA
  6. Échantillon de 50 articles avec mention IA
  7. Biais géographique (Global North/South/International par année)

---

## 4. Script 03 — Analyse descriptive

### 4.1 Métriques de diversité thématique

La diversité est mesurée sur la distribution des **topics OpenAlex** par groupe (année, trimestre, discipline). Plusieurs métriques complémentaires sont calculées pour éviter les artefacts d'une seule mesure :

#### Shannon Entropy

$$H = -\sum_{i} p_i \log_2 p_i \quad \text{(bits)}$$

- Mesure l'incertitude/variété de la distribution des topics
- **Sensible aux topics rares** : chaque topic contribue selon son log-probabilité
- Interprétation : H élevé = corpus thématiquement diversifié

#### Nombre effectif de topics (Effective N)

$$N_{eff} = 2^H$$

- Transforme l'entropie en un nombre de topics « équivalents » si la distribution était uniforme
- Plus intuitif que les bits : « le corpus se comporte comme s'il y avait N topics également représentés »

#### Coefficient de Gini

$$G = \frac{2\sum_{i} i \cdot c_i - (n+1)\sum c_i}{n \sum c_i}$$

- Mesure la **concentration** : 0 = distribution uniforme, 1 = un seul topic domine tout
- Complémentaire à Shannon : capte les déséquilibres même pour les grands corpus

#### Indice de Herfindahl-Hirschman (HHI)

$$HHI = \sum_i \left(\frac{c_i}{\sum c_j}\right)^2$$

- Emprunté à l'économie de la concurrence, mesure la concentration de marché
- Sensible aux très gros acteurs (topics dominants)

#### Part des top-5 / top-10 topics

$$\text{Top-5 share} = \frac{\sum_{i=1}^{5} c_{(i)}}{\sum_j c_j}$$

- Indicateur simple et immédiatement interprétable
- Permet de répondre à : « Les 5 topics les plus fréquents représentent-ils X% du corpus ? »

#### Simpson Diversity

$$D = 1 - \frac{\sum c_i(c_i-1)}{N(N-1)}$$

- Probabilité que deux articles tirés aléatoirement aient des topics différents
- Robuste aux grands corpus

**Pourquoi autant de métriques ?**
Shannon et Gini capturent des dimensions différentes de la diversité. Un corpus peut avoir une Shannon élevée (beaucoup de topics différents) mais un Gini élevé (quelques topics très dominants). L'utilisation conjointe des 6 métriques permet de caractériser la structure complète de la distribution.

### 4.2 Figures produites

#### Fig. 01 — Volume et composition

- **Panel (a)** : histogramme du volume annuel d'articles (barres) + taux de mention IA (axe Y secondaire, ligne rouge)
  - Double axe : l'axe gauche est absolu (nombre d'articles), l'axe droit est relatif (%) pour éviter la confusion d'échelle entre les deux séries
- **Panel (b)** : top 10 disciplines (barres horizontales)
  - Horizontal pour lisibilité des noms longs de disciplines

#### Fig. 02 — Séries temporelles de diversité (trimestrielle)

Grille 2×2 : Shannon, Effective N, Gini, Top-5 share par trimestre.

**Pourquoi la granularité trimestrielle ?**
La granularité annuelle masque les transitions rapides (ex: adoption de ChatGPT post-novembre 2022). Le trimestre est le compromis entre résolution temporelle et stabilité statistique des estimateurs de diversité.

La **courbe de tendance polynomiale de degré 2** (ligne pointillée rouge) est ajoutée sur le Shannon pour visualiser la tendance de fond sans sur-interpréter les oscillations trimestrielles.

Une **ligne verticale grise en pointillé** à 2023-Q1 marque la rupture post-ChatGPT sur toutes les figures temporelles.

#### Fig. 03 — Heatmap topics × années

- Matrix : top 25 topics (en proportion relative par année, pas en valeur absolue)
- **Pourquoi la proportion et non le compte absolu ?** Le volume d'articles varie d'une année à l'autre. Une normalisation par année permet de comparer la structure relative indépendamment du volume.
- Colormap `YlOrRd` : progression du jaune (faible) au rouge foncé (dominant)
- Ligne bleue verticale en 2023 pour marquer la rupture

#### Fig. 04 — Courbes de Lorenz

Construites pour les années 2016, 2019, 2022, 2025 (représentatives des quatre phases : pré-IA, montée ML, pré-GenAI, post-GenAI).

- Axe X : proportion cumulée des topics (de moins fréquent à plus fréquent)
- Axe Y : proportion cumulée des occurrences
- Plus la courbe s'éloigne de la diagonale, plus la distribution est concentrée

Le Gini dans la légende permet une lecture quantitative immédiate de la courbure.

#### Fig. 05 — Exposition IA : disciplines forte vs faible

- **Classification haute/basse exposition** : médiane du taux de mention IA par discipline comme seuil
- Trois panels (Shannon, Gini, Effective N) pour éviter qu'un seul indicateur soit mal interprété

**Choix de la médiane comme seuil :**
La médiane est robuste aux valeurs extrêmes (une discipline avec 80% de mention IA ne tire pas le seuil vers le haut). Elle partage également le corpus en deux groupes de taille comparable.

#### Fig. 06 — Test avant/après GenAI

Boxplots par métrique de diversité, comparant 2015–2022 vs 2023–2026.

**Tests statistiques utilisés :**
- **Test de Welch (t-test inégalité des variances)** : robuste quand les deux groupes ont des variances différentes (plus vraisemblable ici car l'écart-type de la diversité peut changer après GenAI)
- **Test de Mann-Whitney U** : test non-paramétrique, robuste à la non-normalité des distributions de métriques de diversité
- **Cohen's d** : taille d'effet standardisée

La notation de significativité (`***` p<0,01, `**` p<0,05, `*` p<0,1, `ns`) est affichée directement sur les boxplots.

#### Fig. 07 — Intensité IA

- **Panel (a)** : histogramme empilé 100% par année (none / peripheral / methodological / core)
  - Permet de voir la montée en intensité de la mention IA sans que le volume absolu ne domine la lecture
- **Panel (b)** : Shannon par intensité IA dans le temps
  - Répond à : les articles les plus centrés sur l'IA sont-ils thématiquement plus homogènes ?

#### Fig. 08 — Prestige des revues

**Construction des tiers de prestige :**

```python
p90 = journal_stats["median_citations"].quantile(0.90)  # seuil Top 10%
p75 = journal_stats["median_citations"].quantile(0.75)  # seuil Top 25%
```

- Basé sur la **médiane des citations par journal** (robuste aux articles très cités qui faussent la moyenne)
- Seuil d'éligibilité : journaux avec au moins 5 articles dans le corpus (évite les journaux anecdotiques)
- **Pourquoi les percentiles 90 et 75 ?** Reflète la convention de la littérature bibliométrique (Q1/Q2/Q3) tout en étant adaptée à la distribution fortement asymétrique des citations

Trois panels : volume par tier, Shannon par tier, Gini par tier.

#### Fig. 09 — Biais géographique

- Taux d'adoption IA (%) et Shannon par zone géographique
- Permet de tester si l'adoption de l'IA est plus rapide dans le Global North

#### Fig. 10 — Shannon pondérée par citations (script 03)

**Shannon volumique vs Shannon impact :**

La Shannon standard pondère chaque article de façon égale. La **Shannon pondérée par le percentile de citations** reflète le « centre de gravité intellectuel » du champ :

```python
# Percentile de citations normalisé par année (élimine le biais temporel)
df["cit_percentile"] = rank_within_year(group["cited_by_count"], pct=True)
```

**Pourquoi normaliser par année ?** Un article de 2015 accumulé 9 ans de citations ne doit pas écraser un article de 2024. Le percentile intra-année corrige ce biais de maturité.

Le **delta (impact - volumique)** mesure si les articles les plus cités se concentrent sur les mêmes topics que la masse des publications ou s'en distinguent.

#### Fig. 11 — Forest plot OLS (Mega-Publisher)

**Régression OLS sur la diversité intra-article :**

$$\log(n\_{topics} + 1) = \alpha + \beta_1 \cdot year_{centered} + \beta_2 \cdot post\_genai + \beta_3 \cdot ai\_mention + \beta_4 \cdot is\_mega\_publisher + \sum_k \gamma_k \cdot disc_k + \varepsilon$$

- **Variable dépendante** : `log(n_topics + 1)` — diversité thématique d'un article individuel (approximation de la largeur disciplinaire)
- **`is_mega_publisher`** : flag pour les journaux dans le top 5% en volume (Mega-Publishers comme Elsevier, Springer, MDPI) — teste si la standardisation thématique est pilotée par les éditeurs ou par l'IA
- **Erreurs HC3-robustes** : correction d'hétéroscédasticité (distribution de n_topics très asymétrique)
- **Effets fixes disciplines** : dummies pour les 15 disciplines les plus fréquentes (référence = discipline la plus représentée)

**Pourquoi ce modèle ?** Il isole l'effet causal partiel de l'IA sur la diversité thématique en contrôlant simultanément la tendance temporelle, l'effet post-GenAI, et la structure éditoriale.

#### Fig. 12 — Réseau de collaboration internationale

Heatmap de co-occurrence des pays sur les 20 pays les plus présents.

- Échelle **log1p** : `np.log1p(cooc_matrix)` — compresse les très grandes valeurs pour rendre visible la structure des collaborations mineures
  - Sans log, les paires US-CN, US-GB domineraient visuellement l'ensemble de la matrice
- Masque les cellules à 0 (pas de collaboration) pour améliorer la lisibilité

#### Fig. 13 — Dynamique des équipes (script 03)

- Panel (a) : taille moyenne et médiane des équipes par année
- Panel (b) : impact médian (percentile citations) par type de collaboration (national/international) par année
- Panel (c) : prime à la collaboration — impact médian par taille d'équipe × type de collaboration

### 4.3 Analyses complémentaires dans le fichier Excel

**10 onglets dans `etape3_analyse_descriptive.xlsx` :**
1. Stats descriptives globales (2015–2022 / 2023–2026 / Total)
2. Volume par année
3. Diversité trimestrielle (toutes métriques)
4. Tests avant/après GenAI
5. Prestige des revues
6. Biais géographique
7. Shannon pondérée
8. OLS Mega-Publisher
9. Réseau pays
10. Co-occurrence des concepts

---

## 5. Script 04 — Analyse sémantique par embeddings

### 5.1 Modèle d'embedding

**Modèle :** `all-MiniLM-L6-v2` (sentence-transformers)

| Propriété | Valeur |
|-----------|--------|
| Dimensions | 384 |
| Paramètres | ~22 millions |
| Taille modèle | ~80 Mo |
| Entraînement | Contrastive learning sur 1 milliard de paires texte |
| Benchmark SBERT | 78,9 sur STSB (état de l'art en équilibre vitesse/qualité) |

**Pourquoi ce modèle ?**
- Suffisamment compact pour encoder 1,65 million d'abstracts sur CPU sans GPU dédié
- Représentation sémantique dense de haute qualité : capture le sens au-delà des mots-clés
- Normalisation L2 intégrée : les vecteurs produits sont directement utilisables pour le cosinus

### 5.2 Optimisations CPU

Le script est conçu pour un **Ryzen 7 5700U (8 cœurs / 16 threads, AVX2)** mais s'adapte à tout matériel :

#### Hiérarchie des backends (ordre de performance décroissant)

| Priorité | Backend | Gain | Conditions |
|----------|---------|------|-----------|
| 1 | fastembed ONNX INT8 | 3–5× | `pip install fastembed`, Windows Developer Mode pour symlinks |
| 2 | sentence-transformers + quantisation dynamique INT8 | ~2× | `torch.ao.quantization.quantize_dynamic` (PyTorch ≥ 1.13) |
| 3 | sentence-transformers float32 | baseline | Fallback universel |

**Quantisation INT8 :** Réduit la précision des poids `Linear` de 32 bits à 8 bits entiers. Sur CPU avec instructions AVX2, cela exploite des chemins d'exécution optimisés (VNNI sur Zen 3). Perte de précision négligeable pour des mesures de similarité sémantique.

#### Parallélisme BLAS/OMP

```python
os.environ["OMP_NUM_THREADS"]      = str(n_cpu)
os.environ["MKL_NUM_THREADS"]      = str(n_cpu)
os.environ["OPENBLAS_NUM_THREADS"] = str(n_cpu)
torch.set_num_threads(n_cpu)
```

Ces variables **doivent être définies avant toute importation** (PyTorch, NumPy) car les bibliothèques BLAS/OMP initialisent leur pool de threads au premier import.

#### Détection automatique du matériel

```python
if torch.cuda.is_available():   device = "cuda"
elif torch.backends.mps.is_available():  device = "mps"   # Apple Silicon
else:                           device = "cpu"
```

#### Tri par longueur (`sort_by_length=True`)

Réduit le **padding** dans les batches PyTorch. Quand les abstracts d'un batch ont des longueurs très disparates, les abstracts courts sont paddés jusqu'à la longueur du plus long. Trier par longueur regroupe les abstracts similaires et réduit le rembourrage inutile → +20–30% de vitesse d'encodage.

### 5.3 Système de checkpoints

```python
SAVE_INTERVAL = 100_000  # sauvegarde tous les 100 000 abstracts
```

- Les embeddings sont sauvegardés dans `outputs/embeddings_checkpoint.npy` toutes les 100 000 abstracts
- À la relance, le script reprend automatiquement depuis le dernier checkpoint
- Protège contre les interruptions sur un calcul de plusieurs heures

**Format NPY :** Tableau NumPy float32 de shape `(N, 384)`. Pour 1,65 million d'articles, cela représente ~2,4 Go en RAM.

### 5.4 Diversité sémantique — Métrique centroide

#### Pourquoi le centroïde et non la matrice de distances par paires ?

| Approche | Complexité mémoire | Complexité calcul |
|----------|-------------------|------------------|
| Matrice N×N | O(N² × 4 bytes) = ~10 To pour 1,65M | O(N²) |
| Distance au centroïde | O(N × D) = ~2,4 Go | O(N × D) |

La matrice de distances par paires est **physiquement impossible** en RAM pour 1,65 million d'articles. L'approche centroïde est exactement équivalente pour mesurer la **dispersion globale** du corpus.

#### Formule

$$\bar{E}_t = \frac{1}{|A_t|} \sum_{i \in A_t} \mathbf{e}_i \quad \text{(centroïde annuel)}$$

$$d_{cos}(i, t) = 1 - \frac{\mathbf{e}_i \cdot \hat{E}_t}{\|\mathbf{e}_i\|} \quad \text{(distance cosinus, } \mathbf{e}_i \text{ L2-normalisé)}$$

$$\text{Diversité}(t) = \frac{1}{|A_t|} \sum_{i \in A_t} d_{cos}(i, t)$$

Où $\hat{E}_t = \bar{E}_t / \|\bar{E}_t\|$ est le centroïde unitaire.

#### Norme du centroïde

$$\|\bar{E}_t\| \in [0, 1] \quad \text{(pour des vecteurs L2-normalisés)}$$

- **Proche de 0** : les embeddings s'annulent (corpus thématiquement diffus, directions opposées)
- **Proche de 1** : tous les embeddings pointent dans la même direction (corpus dominé par un seul thème)

Cette métrique est **complémentaire** à la distance cosinus moyenne : un corpus peut avoir une diversité élevée (articles très dispersés) mais une norme de centroïde faible (pas de thème dominant unifié).

### 5.5 Analyse intra/inter-discipline

#### Variance intra-discipline (`mean_intra_dist`)

Pour chaque paire (discipline d, année t) avec au moins `MIN_ARTICLES_PER_DISC_YEAR = 5` articles :

$$\text{intra}(d, t) = \frac{1}{|A_{d,t}|} \sum_{i \in A_{d,t}} d_{cos}(i, C_{d,t})$$

Mesure la dispersion sémantique **interne** à une discipline donnée une année donnée.

#### Saut paradigmatique inter-centroïde (`inter_shift`)

$$\text{shift}(d, t) = d_{cos}(C_{d,t-1}, C_{d,t})$$

Mesure le déplacement du **centre sémantique** d'une discipline d'une année à l'autre.

- **Faible** : la discipline évolue peu sémantiquement (thèmes stables)
- **Élevé** : la discipline a subi un changement de paradigme (nouveaux thèmes dominants)

Un pic de `inter_shift` après 2022 pour une discipline signalerait une réorientation thématique rapide, potentiellement liée à l'IA générative.

### 5.6 Granularité de l'analyse (top-12 disciplines)

```python
MAX_DISCIPLINES = 12  # top-N disciplines les plus fréquentes
```

Limité à 12 pour la **lisibilité des figures** multi-lignes. Au-delà, la palette de couleurs `tab20` devient difficile à discriminer et les légendes illisibles.

### 5.7 Normalisation L2

```python
norms = np.linalg.norm(all_embeddings, axis=1, keepdims=True)
norms = np.where(norms == 0, 1.0, norms)
E_all = (all_embeddings / norms).astype(np.float32)
```

`normalize_embeddings=True` dans `model.encode()` garantit déjà la normalisation L2, mais une **renormalisation explicite** est effectuée au cas où le checkpoint proviendrait d'une version antérieure sans cette option. La gestion du cas `norm=0` (vecteur nul théoriquement impossible) protège contre les divisions par zéro.

### 5.8 Livrables

- `outputs/embeddings_checkpoint.npy` — matrice d'embeddings (N × 384, float32)
- `outputs/etape4_semantique.xlsx` — 3 onglets :
  1. Diversité sémantique par année (all / IA / non-IA)
  2. Centroides par discipline et année (intra/inter métriques)
  3. Notes méthodologiques
- `outputs/etape4_discipline_centroids.csv` — données brutes des centroides
- `outputs/figures/fig10_semantic_diversity.png` — diversité + norme centroïde
- `outputs/figures/fig12_intra_centroid.png` — variance intra-discipline
- `outputs/figures/fig13_inter_shift.png` — saut paradigmatique inter-annuel

---

## 6. Choix des échelles et paramètres graphiques

### 6.1 Paramètres globaux matplotlib

```python
plt.rcParams.update({
    "figure.dpi": 150,           # résolution suffisante pour publication
    "font.size": 11,             # lisible sans être encombrant
    "font.family": "sans-serif", # police neutre, compatible multi-OS
    "axes.spines.top": False,    # suppression des bordures parasites (haut/droite)
    "axes.spines.right": False,  # améliore le ratio signal/bruit visuel
    "axes.grid": True,           # grille légère pour la lecture des valeurs
    "grid.alpha": 0.3,           # grille discrète (ne pas écraser les données)
})
```

**Suppression des spines top/right :** Principe de Tufte — réduire les éléments non informatifs améliore la lisibilité des données.

### 6.2 Palette de couleurs

```python
COLORS = {
    "primary":   "#2563EB",  # bleu — données principales
    "secondary": "#DC2626",  # rouge — indicateurs IA / alertes
    "accent":    "#059669",  # vert — catégories secondaires
    "gray":      "#6B7280",  # gris — lignes de référence / baselines
    "purple":    "#7C3AED",  # violet — métriques spécialisées (centroïde)
}
```

Ces couleurs sont issues du système **Tailwind CSS** (palette cohérente, contraste WCAG AA). Le rouge est réservé aux indicateurs IA pour une cohérence visuelle entre figures.

### 6.3 Ligne verticale ChatGPT

Présente sur **toutes** les figures temporelles à `x=2022.5` (entre 2022 et 2023) :

```python
ax.axvline(2022.5, color=COLORS["gray"], ls="--", alpha=0.5, label="ChatGPT")
```

- `2022.5` et non `2023.0` : ChatGPT est sorti en novembre 2022 ; la rupture dans les données débute donc à la frontière entre les deux années
- Opacité 0,5 : référence visible mais non dominante

### 6.4 Double axe Y (Fig. 01)

Le volume d'articles (axe gauche, absolu) et le taux de mention IA (axe droit, %) évoluent à des échelles très différentes. Le double axe permet de les superposer sans perdre la lecture de l'une ou l'autre série. Les axes droits sont colorés en rouge pour rappeler qu'ils correspondent aux courbes IA.

### 6.5 Échelle log dans la heatmap réseau pays (Fig. 12)

```python
log_matrix = np.log1p(cooc_matrix.astype(float))
```

La distribution des co-publications est **très asymétrique** (loi de puissance) : les paires USA-Chine, USA-Royaume-Uni ont des milliers de co-publications quand la majorité des paires en ont moins de 10. Sans log, la colormap serait saturée sur 3–4 paires et invisible pour le reste. `log1p` (log(1+x)) gère correctement les zéros.

### 6.6 `bbox_inches="tight"` systématique

```python
plt.savefig(path, bbox_inches="tight")
```

Évite que les labels rotatifs (dates trimestrielles) ou les titres débordent hors de la figure sauvegardée. Paramètre systématique pour toutes les figures.

---

## 7. Limites et biais connus

### 7.1 Biais de sélection de l'échantillonnage

La stratégie `sample=` d'OpenAlex est un **échantillonnage aléatoire stratifié par année** et non exhaustif. Pour certaines disciplines peu représentées, le volume peut être insuffisant pour des analyses de sous-groupes fines. Les **doublons inter-seeds** sont correctement filtrés mais peuvent introduire une légère sous-représentation des articles très récents (potentiellement indexés dans plusieurs seeds).

### 7.2 Biais de détection IA par regex

- **Faux positifs :** `"Claude"` peut désigner un prénom, `"Gemini"` un signe astrologique, `"transformer"` un composant électronique. Dans un corpus académique, la fréquence de ces cas ambigus est faible mais non nulle.
- **Faux négatifs :** Des articles utilisant l'IA sans mentionner de terme explicite (ex: méthodes décrites par leur acronyme interne à une communauté) ne seraient pas détectés.
- Les résultats de détection IA doivent être interprétés comme des **tendances** et non des comptages exacts.

### 7.3 Biais de couverture géographique d'OpenAlex

OpenAlex hérite de Crossref et PubMed pour une grande part de son indexation. La littérature publiée dans des revues non-indexées (courantes dans certains pays du Global South) est sous-représentée, ce qui peut artificiellement gonfler la proportion de publications Global North.

### 7.4 Reconstruction de l'abstract

Les abstracts reconstruits depuis l'index inversé manquent parfois de ponctuation et peuvent contenir des artefacts de tokenisation. Cela n'affecte pas la détection de mots-clés mais peut légèrement dégrader la qualité des embeddings pour les abstracts très courts.

### 7.5 Proxy de diversité thématique via n_topics

La variable dépendante de la régression OLS (`log(n_topics+1)`) est un proxy de la diversité **intra-article**, pas de la diversité du corpus. Un article avec beaucoup de topics OpenAlex n'est pas nécessairement plus interdisciplinaire qu'un article spécialisé dans un sous-domaine dont les topics sont nombreux dans la taxonomie OpenAlex.

### 7.6 Diversité sémantique centroïde vs diversité réelle

La distance cosinus au centroïde mesure la dispersion moyenne par rapport au **thème moyen** du corpus annuel. Elle ne capte pas la structure multimodale (ex: deux clusters thématiques distincts) qui serait visible avec une analyse de clustering (t-SNE, UMAP). Une faible distance au centroïde peut signifier soit un corpus uniforme, soit deux groupes symétriques qui se compensent.

---

*Document généré automatiquement à partir de l'analyse des scripts du pipeline — Mars 2026.*
