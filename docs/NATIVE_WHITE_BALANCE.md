# Balance des blancs native — 13 septembre 2026

**Le calcul isolé des gains fonctionne sur le code X-T4 2.12. Aucun rendu d’image ni calibration réelle n’est validé.** `xt4-wb-probe` exécute les instructions originales, vérifie les deux modules par SHA-256 et garde les octets inconnus illisibles. Les valeurs de calibration fournies sont des entrées synthétiques reconnaissables, réservées au diagnostic.

## Structure et octet inconnu

La trace du destinataire RAW confirme que `0x021ae6fc` écrit les onze premiers octets de la structure de douze octets à `0x0288d1fc`. Son instruction `LDM` à `0x021ae880` copie trois mots et tente aussi de lire l’octet `+11`, resté inconnu. Rapport : `research/reports/xt4-wb-structure-writes.json` (variante explicite `cfg_feb0=0`, validation globale à faux).

| Décalage | Type observé | Utilisation dans le calcul isolé |
|---|---|---|
| +0, +1 | Deux octets signés | Décalages des deux axes WB |
| +2 | Octet | Index d’une paire de coefficients |
| +3 | Octet | Sélecteur d’une autre paire |
| +4, +6, +8 | Trois entiers 16 bits | Gains en entrée |
| +10 | Octet | 0 et 2 activent les corrections ; 1 prend la branche neutre |
| +11 | Inconnu | Non lu dans les appels testés à `0x022a830c`, R2 nul |

Le dernier octet reste **illisible**, même dans les essais réussis. Cela démontre son absence d’utilisation dans ces appels isolés, sans prouver son état au démarrage ni son absence d’utilisation dans toute la chaîne. Aucune page BSS n’a été remplie arbitrairement de zéros. Le parcours RAW complet conserve sa frontière antérieure.

## Dépendances de calibration

`0x022a7cf4` choisit les coefficients des décalages. Zéro renvoie l’unité Q10 (`1024`). Les valeurs hors de −9…+9 suivent aussi cette branche dans cette fonction ; cela ne change pas la validation des recettes de l’application.

| Axe / décalage s | Offset dans cfgdata |
|---|---|
| Premier axe, +1…+9 | `0xf55d + 2 × (s − 1)` |
| Premier axe, −9…−1 | `0xf56d − 2 × s` |
| Second axe, +1…+9 | `0xf581 + 2 × (s − 1)` |
| Second axe, −9…−1 | `0xf591 − 2 × s` |

Il faut **36 coefficients de 16 bits**, lus en little-endian par `0x01263bf4`. Les 36 essais sans ces données s’arrêtent à l’adresse attendue ; les deux cas neutres terminent sans calibration. Les valeurs réelles restent inconnues.

`0x022a8018` lit une paire dont les offsets figurent dans la table native `0x02601b10` : `0xf5a6 + 4 × index` et l’offset suivant de deux octets. Le nombre d’entrées vient de `cfgdata[0x420f82]`, validé par `0x012f20d8` dans l’intervalle 1…31. Le banc fournit explicitement 31 et vérifie les index 0, 15, 30 ainsi que le rabattement de 255 vers 30.

`0x022a8064` ajoute une paire sélectionnée parmi `0xf700…0xf71e`. Les sélecteurs 6…11 utilisent la même paire `0xf714/0xf716`. Ces identifiants restent internes : leur correspondance avec les libellés de l’interface n’est pas établie.

## Calcul et validation

`0x022a824c` multiplie trois facteurs Q10 par axe, utilise un produit intermédiaire sur 64 bits, décale de 20 bits puis stocke le facteur composé sur 16 bits. `0x022a830c` conserve le premier gain et applique aux deux suivants une multiplication, l’ajout de 512 puis un décalage de 10 bits. Le vérificateur respecte les largeurs des entiers ARM.

**251 cas réussissent : 38 dépendances et 213 calculs de gains.** Ils couvrent les branches 0/1/2, les décalages de −9 à +9, des valeurs hors plage et plusieurs index/sélecteurs, avec gains non uniformes. Le banc exige le retour natif, la pile restaurée, les six octets de sortie attendus et aucune autre écriture dans les régions surveillées. La comparaison utilise un calcul entier indépendant, **pas une image de référence produite par un boîtier**.

Rapport : `research/reports/xt4-wb-isolated-first.json`.

```bash
.venv/bin/python -m fuji_recipe_lab xt4-wb-probe research/extracted/xt4-2.12 --output research/reports/wb-replay.json
```

Les rapports existants ne sont pas écrasés. Quatre tests supplémentaires contrôlent les garde-fous : champ défini accessible, remplissage inaccessible, calibration absente inaccessible et firmware incorrect rejeté avant exécution.

## Suite : données Fuji retrouvées

Les coefficients de décalage WB ont depuis été extraits du préfixe de configuration du DAT vérifié. Un banc distinct teste les 361 combinaisons avec ces valeurs. Le chemin BSS explique aussi le remplissage de structure. [Nouvelle analyse, provenance et limites](NATIVE_CONFIGURATION.md). Les essais synthétiques décrits ci-dessus sont conservés comme contrôles arithmétiques.

## Travail restant (état initial de ce banc)

Retrouver la provenance des valeurs de configuration et de calibration, puis poursuivre la chaîne de pixels avec ses buffers et dépendances matérielles. Ce banc n’est pas appelé par le rendu de l’interface. Les gains synthétiques ne sont pas exportés comme profil, recette ou approximation Fuji. Le moteur X100VI et l’adaptation DNG restent à établir séparément.
