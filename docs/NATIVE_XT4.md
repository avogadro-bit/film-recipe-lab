# X-T4 2.12 : extraction et premières exécutions natives

Recherche locale du 11 septembre 2026. **Le calcul des pixels Fuji n’est pas encore exécuté.** Les résultats ci-dessous concernent le conteneur, deux modules ARM et la construction de paramètres de développement. Aucun boîtier n’a été utilisé.

## Résultats reproductibles

- Les sept segments du DAT couvrent exactement le fichier et leurs sept sommes de contrôle correspondent.
- Les quatre objets compressés repérés sont décodés entièrement : 33 543 940 octets produits, sans dépassement ni octet manquant par rapport aux en-têtes.
- Deux bases mémoire sont corroborées par leurs en-têtes, des références vers les chaînes et l’exécution native.
- La fonction de noms internes de films passe 26 cas.
- Le constructeur complet de paramètres de développement passe 136 cas avec entrées admissibles. Ses fonctions utilitaires sont exécutées avec leurs vrais octets ; aucun appel n’est remplacé.
- Dix entrées hors des plages retenues conduisent à un accès non cartographié dans la journalisation. Le banc s’arrête et conserve l’erreur. Cela ne valide pas la gestion complète des erreurs.

Les sorties sont comparées aux branches désassemblées et à des invariants mémoire. **Il n’existe pas encore de comparaison avec des sorties de caméra pour ces essais.** La concordance des tailles, la lisibilité du code et ses comportements ciblés ne constituent pas une preuve d’équivalence de tous les octets décompressés avec la RAM physique.

## Conteneur DAT

Source : [firmware officiel X-T4](https://www.fujifilm-x.com/global/support/download/firmware/cameras/x-t4/), version 2.12. Fichier local `research/firmware/XT4-2.12.DAT`, 51 278 280 octets, SHA-256 :

```text
853d273b5603d3a2b93493f0ebd6a762b0b4b6bdc70317777775ae5f8ed93bc5
```

Les offsets ci-dessous sont relatifs au début du payload, situé à `0x274` dans le DAT. Le décodeur reste volontairement limité à cette empreinte ; les autres versions nécessitent une validation distincte.

| Segment | Offset payload | Taille | Décodage | Somme attendue |
|---|---:|---:|---|---:|
| main | `0` | `0x2fc0020` | XOR FF | `56831a6c` |
| region_1 | `0x2fc0020` | `0xc000` | XOR FF | `ff6db51f` |
| region_2 | `0x2fcc020` | `0xd2cfc` | XOR FF | `f657a35a` |
| table_0 | `0x309ed1c` | `0x170` | octets stockés | `ffffb7d8` |
| table_1 | `0x309ee8c` | `0xc8` | octets stockés | `ffffe5fd` |
| region_3 | `0x309ef54` | `0x30000` | XOR FF | `fd2ff4df` |
| region_4 | `0x30cef54` | `0x18000` | XOR FF | `feae74ff` |

Somme calculée : complément binaire sur 32 bits de la somme des octets **décodés**. Ce contrôle porte sur le contenu des segments, comprenant les objets encore compressés. Il ne fournit pas une somme indépendante des sorties de décompression. La finalité des segments anonymes reste inconnue.

## Compression reconstituée

Le composant public `ffun/internal/fflz` étant absent de l’arbre consulté, le décodeur a été reconstitué localement à partir du flux. Le récit de fffw identifie, sur le X-E2 étudié par son auteur, une décompression matérielle par pages DMA de 16 Kio et un format de la famille LZ77 ; il rapporte sa propre validation avec un dump X-A2. Cette validation externe ne valide pas automatiquement notre implémentation X-T4. [Source : Route 0xff80](https://github.com/tiredboffin/fffw/wiki/Route-0xff80).

En-tête de 20 octets, cinq entiers little-endian : taille décompressée, taille compressée **en-tête inclus**, nombre de pages, taille de page `16384`, identifiant `4`. Le nombre de pages vaut `ceil(taille_compressée / 16384)`.

- Premier octet entre 1 et 127 : copier autant d’octets littéraux.
- Premier octet `a >= 128`, suivi de `b` : distance `((a & 127) << 4) | (b >> 4)`, longueur `b & 15`.
- Copier depuis la sortie déjà produite ; les recouvrements sont autorisés.
- Les tokens nuls, distances nulles/hors sortie, longueurs nulles, en-têtes incohérents et dépassements sont refusés. Aucune variante non observée n’est supposée.

| Offset dans main | Taille compressée | Taille produite | Fichier |
|---|---:|---:|---|
| `0x260000` | 3 449 330 | 7 420 408 | `unpacked_00260000.bin` |
| `0x5c0000` | 5 254 523 | 9 437 184 | `unpacked_005c0000.bin` |
| `0xae0000` | 4 632 713 | 10 240 000 | `unpacked_00ae0000.bin` |
| `0x1a00000` | 3 309 617 | 6 446 348 | `unpacked_01a00000.bin` |

Ce format est celui des objets du firmware, **pas celui de la compression des photos RAF**.

## Bases mémoire et provenance

Les deux premiers objets commencent par un en-tête avec une base à l’offset `+4`, une taille réservée à `+8` et une valeur candidate de point d’entrée à `+12`. Seules les deux bases ci-dessous sont employées par les essais.

| Module | Base | Taille réservée | Références ARM vers débuts de chaînes ASCII |
|---|---:|---:|---:|
| `00260000` | `0x01021000` | `0x714000` | 24 551 |
| `005c0000` | `0x01e0f000` | `0x900000` | 2 400 |

Les références sont reconstruites depuis des paires MOVW/MOVT portant sur le même registre et la même condition. Décaler chaque base de ±32 octets réduit nettement le nombre de correspondances, sans le ramener à zéro car les chaînes sont regroupées. Les références identifiées vers les noms de fonctions et les essais natifs apportent des éléments supplémentaires. Aucun offset DAT n’est directement pris comme adresse CPU.

Les troisième et quatrième objets ne reçoivent pas de base d’exécution : leur cartographie n’est pas suffisamment établie. Le manifeste conserve leurs empreintes sans leur attribuer un rôle de moteur couleur ou de LUT.

## Fonctions exécutées

### Identifiants internes

Entrée `0x0102df5c`, argument entier dans R0, retour pointeur de chaîne dans R0. Test des valeurs 0 à 22, 255, `0x80000000`, `0xffffffff` ; retour et pile vérifiés. Le code utilise le module en lecture/exécution, une pile synthétique et une adresse d’arrêt du banc.

Les identifiants obtenus concordent avec [mode_fsim.h versionné](https://github.com/tiredboffin/fffw/blob/bedc091e0b54a1a34aaf6929dd08e1db36d13b08/ffun/ports/xt4/0212/mode_fsim.h). `NUM` est une sentinelle, pas une simulation supplémentaire. Cette fonction fournit des noms de diagnostic, pas des transformations d’image.

### Construction de paramètres RAW

Entrée `0x02237770`, R0 : structure source synthétique de 16 Kio ; R1 : structure auxiliaire de 8 Kio mise à zéro ; R2 : destination writable. La fonction sauvegarde ces pointeurs dans R5, R6 et R4. La destination est remplie initialement avec `A5` ; les octets après `0x270` doivent rester intacts.

Les trois appels retrouvés à `0x021ed0ec`, `0x021edeb0` et `0x021ee14c` passent une adresse auxiliaire réelle `0x1f6b1000`, puis copient la sortie sur `0x270` octets. Le banc utilise une structure auxiliaire synthétique : cela permet de tester le constructeur, sans prétendre reproduire cet état réel.

| Réglage identifié par les chaînes de diagnostic | Offset source | Offset destination | Comportement testé |
|---|---:|---:|---|
| Film interne | `0x5c4` | `0x21d` | 18 codes admissibles, transformation vers un autre enum |
| Dynamique | `0xb14` | `0x215` | codes 1–4 vers 100, 200, 400, 800 |
| Hautes lumières | `0x611` | `0x23d` | codes 4–16 vers `(code − 8) × 5` |
| Ombres | `0x612` | `0x241` | même transformation |
| Décalage WB, axe 0 | `0x5c0` | `0x231` | entier signé −9 à +9 conservé |
| Décalage WB, axe 1 | `0x5c1` | `0x235` | entier signé −9 à +9 conservé |

Ces codes sont internes : leur disponibilité dans les menus et leur correspondance exhaustive aux réglages d’une recette publique restent à établir. Les noms `wb_red`/`wb_blue` des cas du banc sont provisoires ; l’attribution physique des deux axes n’est pas démontrée par le seul constructeur. Le code dynamique 4 accepté ici ne prouve pas l’existence d’un choix DR800 ordinaire dans l’interface X-T4.

Exemples de changement d’enum : ETERNA `0x12 → 0x10`, SUPERIA `0x13 → 0x11`, BLEACH_BYPASS `0x14 → 0x12`. Il serait donc incorrect d’envoyer partout le même entier comme identifiant de film.

Le banc teste 72 combinaisons film/dynamique, 26 variations de tonalité et 38 variations WB. Les 136 retours réussissent en 1 778 à 1 781 instructions. Il vérifie chaque champ attendu, toute la destination par rapport au cas de base avec les seules variations autorisées, la garde mémoire, les empreintes des modules chargés et la restauration de SP.

Les dix entrées invalides passent dans la routine de diagnostic `0x02223924`, puis dans un appel vers `0x00057b74` absent de la cartographie actuelle. Le banc conserve cette faute ; il ne remplace pas la journalisation par un retour fictif. Cette adresse désigne ici une dépendance de code inconnue, pas un registre matériel identifié.

## Rejouer

Depuis le dossier du projet, dans un terminal macOS ordinaire :

```bash
# Destination nouvelle : ne remplace pas une extraction précédente
.venv/bin/python -m kora firmware-extract research/firmware/XT4-2.12.DAT research/extracted/xt4-replay
.venv/bin/python -m kora xt4-map research/extracted/xt4-replay
.venv/bin/python -m kora xt4-film-probe research/extracted/xt4-replay/unpacked_00260000.bin
.venv/bin/python -m kora xt4-parameter-probe research/extracted/xt4-replay
```

Les deux probes demandent Unicorn ; son JIT ne fonctionne pas dans le bac à sable Codex de cet environnement. `--output nouveau-rapport.json` conserve les résultats. Les binaires et rapports détaillés restent locaux et exclus d’un éventuel dépôt.

## Suite technique

Le suivi ultérieur a identifié `0x022388b8` comme convertisseur vers des paramètres compacts, puis `0x022357ac` comme installateur dans le contexte RAW. Les 272 essais et les dépendances ThreadX sont décrits dans [la suite de la recherche](NATIVE_PIPELINE.md). Il reste à atteindre le premier consommateur qui calcule effectivement des pixels, identifier ses tables/calibrations et ses accès au matériel, puis définir un oracle de comparaison Fuji.

La chaîne RAF→pixels, la génération X100VI et l’adaptation DNG restent à construire. Les entrées DNG existantes permettent de préparer les essais, mais elles ne sont pas encore transmises à un moteur d’image Fuji.
