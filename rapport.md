# Atlas du tissu productif agricole du Togo — rapport méthodologique

## 1. Contexte

L'objectif est de rendre lisible la géographie du tissu productif agricole togolais à partir des
données publiques ouvertes : où sont les exploitations, les ZAAP, les coopératives et les services
(marchés, magasins d'intrants, pépinières), et quels territoires cumulent production et
sous-équipement. Le tableau de bord sert à repérer des priorités, pas à établir des causalités.

## 2. Sources

| Source | Contenu | Date | Usage |
|---|---|---|---|
| Portail de données ouvertes agricoles du Togo (exports CSV) | 8 jeux géolocalisés | export du 1er octobre 2026 | toutes les analyses |
| OCHA COD-AB Togo v02, via HDX (CC BY-IGO) | limites et superficies des régions et préfectures | valides au 7 janvier 2021 | choroplèthes, densités |
| Banque mondiale, via HDX | 36 indicateurs nationaux, 1960–2023 | — | contexte uniquement, non cartographié |

| Jeu | Lignes brutes | Retenues | Géométrie | Champs propres |
|---|---:|---:|---|---|
| Grandes exploitations | 220 | 220 | point | nom, année de création |
| Petites exploitations | 13 119 | 13 116 | polygone | coopérative de rattachement (type, nom) |
| Plantations | 2 911 | 2 911 | point | nom, année, statut foncier |
| ZAAP / ZAPB (champs individuels) | 1 883 | 1 863 | polygone | coopérative |
| Coopératives agricoles | 6 859 | 6 859 | point | nom, statut, type |
| Marchés | 1 078 | 1 078 | polygone | jours, organisme |
| Pépinières agricoles | 728 | 728 | point | année de création, foncier |
| Magasins d'intrants | 463 | 463 | point | organisme, jours d'ouverture |

Tous portent région, préfecture, commune et canton déclarés.

## 3. Préparation des données

Le traitement est entièrement reproductible : `python -m src.data_loader`.

1. **Textes** : espaces normalisés ; encodage réparé (1 605 cellules du type « coopÃ©rative ») ;
   « Nsp », « Néant », « Ne sait pas » et vides traités comme manquants ; listes `{a,b}` normalisées.
2. **Années** : conservées si comprises entre 1900 et 2026 ; les autres (199, 20014…) deviennent manquantes.
3. **Géométries** : 937 polygones invalides réparés (`make_valid`) ; chaque entité reçoit un point
   représentatif ; les surfaces sont calculées en UTM 31N. Aucun enregistrement sans coordonnées.
4. **Doublons** : 23 doublons exacts (attributs et géométrie identiques) exclus et listés dans
   `data/processed/exclusions.csv`. Aucune autre exclusion.
5. **Niveaux administratifs** : les noms déclarés sont déjà cohérents (5 régions, 39 préfectures,
   394 cantons, aucune variante orthographique). Le canton « Loko » existant dans deux préfectures,
   la clé de canton est « préfecture|canton ».
6. **Jointure géographique** : les agrégats suivent la préfecture **déclarée**, jointe aux polygones
   OCHA par nom normalisé. Trois ajustements : « Plaine du Mô » → Mô, « Naki-Ouest » → Kpendjal-Ouest,
   « Lomé Commune » fusionnée dans Golfe (les données ne la distinguent pas). Contrôle : 95,2 % des
   points tombent dans le polygone de leur préfecture déclarée ; les écarts, proches des limites,
   sont conservés et signalés par l'indicateur `dans_prefecture_declaree`.
7. **Cantons** : les polygones de cantons OCHA (373) ne concordent pas avec les 394 cantons déclarés
   (64 % d'accord spatial). Ils ne sont donc pas utilisés : chaque canton est représenté par un point,
   position médiane de ses enregistrements.

Le dictionnaire de données est dans `data/processed/dictionnaire_donnees.csv` ; chaque variable y est
marquée **observée** ou **calculée**. Les valeurs manquantes ne sont jamais estimées.

## 4. Indicateurs

| Indicateur | Définition | Nature |
|---|---|---|
| Exploitations | nombre d'enregistrements (grandes, petites, plantations) | observé |
| Densité d'exploitations | exploitations pour 100 km² (superficie OCHA) ; région et préfecture seulement | calculé |
| Superficie ZAAP | somme des surfaces des champs individuels levés | calculé |
| Coopératives, marchés, intrants, pépinières | nombre et densité pour 100 km² | observé / calculé |
| Niveau d'équipement d'un canton | nombre de types de service présents parmi marchés, intrants, pépinières : aucun, un, plusieurs | calculé |
| Cantons équipés | cantons ayant au moins un service / cantons du périmètre | calculé |
| Quadrants | densités d'exploitations et de coopératives comparées aux médianes nationales des 39 préfectures | calculé |
| Corrélation | ρ de Spearman entre les deux densités, préfectures du périmètre (minimum 5) | calculé |
| Accès aux intrants | magasins pour 1 000 exploitations | calculé |

Les cartes choroplèthes saturent au 90e centile pour que quelques préfectures très denses n'écrasent
pas les autres ; la légende l'indique par « ≥ ».

## 5. Analyses (Togo entier)

**Exploitations.** 16 247 exploitations recensées, soit 28,4 pour 100 km² : 13 116 petites (81 %),
2 911 plantations (18 %), 220 grandes (1 %).

| Région | Exploitations | Pour 100 km² | Coopératives | ZAAP (ha) | Marchés | Intrants | Pépinières |
|---|---:|---:|---:|---:|---:|---:|---:|
| Maritime | 5 700 | 89,3 | 1 186 | 0 | 205 | 50 | 100 |
| Savanes | 4 739 | 55,4 | 1 337 | 1 070 | 212 | 28 | 232 |
| Kara | 1 956 | 16,6 | 791 | 0 | 254 | 84 | 118 |
| Plateaux | 2 617 | 15,0 | 2 243 | 254 | 220 | 229 | 218 |
| Centrale | 1 235 | 9,4 | 1 302 | 1 | 187 | 72 | 60 |

Les densités les plus fortes sont au sud-est (Bas-Mono 273, Lacs 243) et à l'extrême nord (Tône 153,
Cinkassé 120). Les plantations dominent dans Agou, Tchaoudjo, Blitta et Kloto.

**ZAAP.** 1 325 ha de champs levés dans 16 préfectures, dont 81 % en région Savanes (Oti 364 ha,
Tône 236 ha, Tandjoaré 230 ha). Les 23 autres préfectures n'ont aucun champ dans le jeu.

**Équipements.** 374 cantons sur 394 (95 %) ont au moins un service : 88 % ont un marché, 51 % un
magasin d'intrants, 38 % une pépinière. 20 cantons n'en ont aucun, dont Tambigou (Kpendjal,
60 exploitations), Warkambou (Tône, 49) et Edzi (Avé, 46). Quatre préfectures des Savanes n'ont
aucun magasin d'intrants recensé : Cinkassé, Kpendjal, Kpendjal-Ouest, Oti-Sud.

**Coopératives et exploitations.** Sur les 39 préfectures, la densité de coopératives et la densité
d'exploitations sont positivement associées (ρ = 0,65 ; p < 0,001). Cette association vient presque
entièrement des petites exploitations (ρ = 0,65) ; elle est faible et non significative pour les
plantations (ρ = 0,25 ; p = 0,13) et nulle pour les grandes exploitations (ρ = 0,08 ; p = 0,61).
Six préfectures ont une densité d'exploitations supérieure à la médiane et une densité de
coopératives inférieure : Avé, Vo, Kozah, Agou, Assoli et Tchaoudjo.

**Croisements.** Parmi les préfectures denses en exploitations, celles qui comptent le moins de
magasins d'intrants pour 1 000 exploitations sont Cinkassé et Kpendjal-Ouest (0), Bas-Mono (2,2),
Avé (3,4) et Lacs (4,0). Côté ZAAP, le canton de Tampialime (Tandjoaré, 70 ha) n'a aucun service ;
Imlè-Adiva (Amou), Tamongue et Nano (Tandjoaré) n'en ont qu'un.

## 6. Limites

- **Couverture de la collecte inconnue.** Les jeux recensent des unités géolocalisées ; rien n'indique
  qu'ils soient exhaustifs. Un zéro peut signifier « non collecté ». Les petites exploitations sont
  absentes de Mô et Tchamba et très inégalement réparties (41 % en Maritime, 3 % en Centrale).
- **Corrélation non indépendante.** 97,6 % des petites exploitations portent le nom d'une coopérative :
  elles semblent recensées à travers les réseaux coopératifs. La corrélation observée peut donc
  refléter le mode de collecte autant qu'une réalité de terrain, et ne dit rien d'un effet des
  coopératives sur la production, ni l'inverse.
- **Compter n'est pas mesurer la production.** Une « exploitation » est un enregistrement, sans surface
  cultivée ni volume produit comparables entre types. « Forte production » signifie ici « forte densité
  d'exploitations recensées ».
- **ZAAP.** Champs individuels, pas périmètres officiels : la superficie est sous-estimée et ne décrit
  que 16 préfectures.
- **Niveaux géographiques.** Densités disponibles par région et préfecture seulement ; aucune superficie
  fiable par canton. Les limites datent de 2021 ; 4,8 % des points sortent du polygone de leur
  préfecture déclarée.
- **Cantons.** Le total de 394 est celui des cantons présents dans les données, pas une liste officielle ;
  un canton absent de tous les jeux n'apparaît pas, ce qui surestime le taux d'équipement.
- **Temps.** L'année n'existe que pour grandes exploitations, plantations et pépinières, et désigne la
  création d'unités encore actives : aucune évolution temporelle fiable ne peut en être tirée.
- **Équipement.** La présence d'un service dans un canton ne dit rien de sa capacité ni de son accessibilité.

## 7. Recommandations

1. **Vérifier sur le terrain les 20 cantons sans aucun service**, en commençant par ceux qui comptent le
   plus d'exploitations (Tambigou, Warkambou, Edzi, Tampialime, Sangou).
2. **Examiner l'accès aux intrants dans les Savanes** : quatre préfectures sans magasin recensé alors que
   la région concentre 81 % des ZAAP levées et 29 % des exploitations.
3. **Regarder de près les six préfectures « exploitations fortes, coopératives faibles »** (Avé, Vo,
   Kozah, Agou, Assoli, Tchaoudjo) avant toute action : l'écart peut tenir à la collecte.
4. **Améliorer les données** : publier le périmètre et la date de collecte de chaque jeu, une liste
   officielle des cantons avec leurs limites, les surfaces cultivées par exploitation et les
   périmètres officiels des ZAAP. Ces quatre éléments lèveraient l'essentiel des limites ci-dessus.

## 8. Vérification

`python tests/smoke_test.py` exécute tous les callbacks : démarrage, cinq vues, filtres croisés (clic
carte, désélection, réinitialisation, lien partageable), sept combinaisons de filtres dont une
sélection vide, et les deux exports CSV. Les captures des vues sont dans `outputs/`.
