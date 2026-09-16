# Modes de buffers et listes DMA natives — 13 septembre 2026

Suite : [conditions de lancement, statut et notification native](NATIVE_DMA_CONTROL.md). Le banc de capture décrit ci-dessous reste distinct des nouveaux essais sur valeurs de registre synthétiques.

**Le constructeur Fuji de listes DMA passe 52 essais. Ses écritures registre sont capturées, mais aucune réponse du périphérique n’est fournie et aucun transfert de pixels n’est exécuté. Le mode de buffers 7 fonctionne jusqu’au sémaphore DMA dans le banc RAW ; sa capacité reste insuffisante pour la géométrie X100VI actuelle. Le rendu exact et le projet complet restent à construire.**

## Deux sélecteurs distincts

Le programme RAW 6, à l’offset contexte `0x3b`, détermine les réservations par étape. Le **mode de table des buffers**, à `0x372d4e0`, choisit les descripteurs disponibles. Ces deux valeurs ne sont pas interchangeables.

Le banc historique choisissait le mode de table 2. La fonction `0x2198fc0` accepte désormais explicitement les modes 2, 6 et 7 dans le banc. Son initialiseur natif et ses gardes mémoire restent exécutés ; les autres valeurs sont rejetées avant accès au firmware.

Le fragment `0x2214a64…0x2214a70` sélectionne 6 dans un préparateur natif. Cependant, le mode 6 ne fournit pas les ressources `0x32` et `0x33` utilisées par l’orchestrateur `0x22152a8`. Il s’arrête à `0x2236618`, en lisant un descripteur nul, après 4334 instructions. Son rapport reste `passed: false`, avec destinataire non exécuté : il ne résout pas ce parcours.

La fonction native `0x21ee5c0` produit le mode 7 lorsque l’octet `+8` de son entrée vaut 1, sauf pour les types prioritaires `0x1d` et `0x20`. Le résultat est transmis au changement de mode via `0x21ef008`. Cette condition a été identifiée dans les instructions ; **le paquet d’entrée et le changement de mode complet ne sont pas reconstruits**. Le choix 7 reste donc un cas d’étude explicite, sans prétendre reproduire l’état d’un boîtier.

| Mode de table | Descripteur `0x2f`, slot 1 | Capacité déclarée | Ressources `0x32` / `0x33` |
|---|---|---:|---|
| 2 | `0x25d8cec`, buffer `0x34983c00` | 13 107 200 octets | présentes |
| 6 | `0x25d6ddc`, buffer `0x65a00000` | 55 464 192 octets | absentes |
| 7 | `0x25e3efc`, buffer `0x65a00000` | 55 464 192 octets | présentes |

En mode 7, le destinataire réserve nativement le descripteur, passe la WB, transmet les trois notifications et prépare le transfert. Il atteint le sémaphore non initialisé à `0x7acd0` après **21 874 instructions**. Le descripteur indique un pas de 12 768 octets et 4344 lignes, alors que le transfert issu des métadonnées X100VI utilise encore 15 744 octets par ligne. Son étendue reste **81 868 800 octets** : `fits_static_capacity` reste faux. Aucune mémoire supplémentaire n’a été ajoutée pour dissimuler cette incompatibilité.

## Constructeur DMA isolé

Le chemin de copie observé appelle `0x21ca300`, qui demande le descripteur DMA numéro `0x20` via `0x11ae54c`. L’entrée ROM à `0x1582e80` vaut :

```text
10 2c 03 00 08 00 00 00 01 00 00 00
```

L’acquisition du canal et ses handles ne sont pas encore disponibles. Le banc appelle donc directement le constructeur inférieur **`0x11ae2b0`**, avec des paramètres explicitement synthétiques et les champs pertinents de cette entrée ROM vérifiée. Il ne contourne pas une dépendance du destinataire pour le faire avancer : il s’agit d’une expérience séparée, dont aucun état n’est réutilisé dans le parcours RAW.

Les 48 cas de construction combinent deux canaux (1 et 9), trois nombres de lignes (1, 3 et 31), quatre couples de drapeaux d’incrément et deux remplissages initiaux de la liste (`0x00` et `0xa5`). Les pas source/destination diffèrent volontairement de la largeur. Les adresses source et destination sont **non mappées**, sans photo chargée.

Chaque ligne de liste occupe 32 octets. Les octets produits sont comparés à un calcul indépendant :

| Offset | Champ observé |
|---|---|
| `+0x00` | largeur − 1 |
| `+0x04` | source + numéro de ligne × pas source |
| `+0x08` | destination + numéro de ligne × pas destination |
| `+0x0c` | contrôle source |
| `+0x10` | contrôle destination |
| `+0x14` | adresse du descripteur suivant et bits bas conservés/modifiés |
| `+0x18…+0x1f` | octets inchangés dans ce constructeur |

Pour cette requête, le contrôle vaut `0x30700`, auquel le code ajoute le bit `0x4` lorsque le drapeau correspondant vaut zéro. Le constructeur remplace les 28 bits supérieurs du lien, conserve les autres bits bas et positionne le bit 0. Il efface ensuite ce bit sur le dernier élément. La zone après la liste et les octets laissés intacts sont également vérifiés.

Les quatre cas invalides vérifient le rejet natif, retour `0xffffffe2` (−30), sans écriture de descripteur ni de registre : liste mal alignée, capacité de liste insuffisante, largeur non divisible par huit et canal 16.

## Écritures registre et arrêt obligatoire

Les pages de capture sont **en écriture seule**. Leur contenu n’est jamais une réponse matérielle, même après une écriture native. Un test d’infrastructure vérifie explicitement cette propriété. Le banc n’implémente ni les effets des registres, ni un état de périphérique, ni une interruption.

Pour le canal 1, le constructeur émet successivement :

| Adresse | Valeur / rôle observé |
|---|---|
| `0xfff4a500` | `0x1002c2c`, sélection écrite par `0x11addc4` |
| `0xfffe1014` | adresse source |
| `0xfffe1018` | adresse destination |
| `0xfffe1010` | zéro |
| `0xfffe1028` | `0x1100001` |

Il tente ensuite de lire `0xfffe1030`, au PC `0x5aa40`. Pour le canal 9, les registres de canal se trouvent à `0xfffe9000` et la sélection à `0xfff4a510`. Toutes les constructions s’arrêtent à cette lecture inconnue. Le garde mémoire et la protection Unicorn peuvent chacun signaler le même accès ; les deux observations sont conservées.

Les instructions suivantes attendent que le bit `0x10000` soit nul, puis prévoient notamment de soumettre le pointeur de liste au registre `+0x24`. **Elles ne sont pas exécutées dans ce banc.** L’absence de réponse matérielle ne devient jamais un zéro implicite, un succès forcé ou une copie Python.

## Reproduction

```bash
.venv/bin/python -m fuji_recipe_lab xt4-dma-probe research/extracted/xt4-2.12 --output research/reports/dma-replay.json
.venv/bin/python -m fuji_recipe_lab xt4-resource-probe research/extracted/xt4-2.12 '/chemin/photo.RAF' --with-receiver --firmware-config --boot-wb --extended-config --raw-resource-plan --request-mode 7 --output research/reports/mode7-replay.json
.venv/bin/python -m unittest discover -s tests -v
```

Rapports :

- `research/reports/xt4-dma-descriptors-validated.json` : 52 cas validés ; aucune image produite.
- `research/reports/xt4-receiver-mode7-validated.json` : parcours mode 7 et arrêt attendu validés.
- `research/reports/xt4-receiver-dma-mode2-regression.json` : parcours mode 2 toujours valide.
- `research/reports/xt4-receiver-mode6-incompatible.json` : échec diagnostiqué avant le destinataire, attendu pour ce mode et cette orchestration.

**66 tests unitaires passent.** L’interface continue d’afficher l’aperçu intégré, avec recette non appliquée. Les dépendances suivantes sont la sémantique et la fin des transferts matériels, la bonne géométrie d’entrée, les vrais pixels et leur calibration. La compatibilité DNG et la fidélité finale Fuji ne sont pas validées.
