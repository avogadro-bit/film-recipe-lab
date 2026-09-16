# Programme RAW, réservation et transfert DMA — 13 septembre 2026

Suite : [comparaison des modes de buffers et 52 essais de construction native des listes DMA](NATIVE_DMA.md). Les résultats ci-dessous décrivent le mode de buffers 2 historique.

**La ressource `0x2f` est désormais réservée par les instructions Fuji. Le code prépare ensuite un transfert qui dépend du DMA matériel. Aucun pixel n’a été lu ou produit, et la géométrie de ce banc ne tient pas dans la capacité déclarée du buffer choisi. Le projet reste inachevé.**

## Pourquoi la réservation manquait

Le contexte synthétique précédent conservait zéro à l’offset `0x3b`. Cet octet sélectionne un programme dans la table `0x25f3acc`, indépendamment du mode 2 des descripteurs de ressources. Pour le programme zéro, la réservation de `0x2f` appartient à l’étape `0x0c`, absente de la séquence RAW étudiée. L’étape `0x14` arrivait donc sans cette réservation.

Le coordinateur comporte l’affectation native suivante :

```text
0x21ed068  MOV  R3, #6
0x21ed06c  STRB R3, [R0, #0x3b]
```

L’option `--raw-resource-plan` exécute exactement ce fragment, avec le pointeur du contexte fourni par le banc. Seul l’octet écrit est transféré avant l’orchestration. Les modules sont vérifiés par leurs SHA-256 épinglés. **Cela ne signifie pas que le coordinateur complet ait tourné : l’acquisition du contexte et la lecture du fichier qui entourent ce fragment restent hors de cette préparation.** Le programme 6 est un chemin de recherche explicite, pas un état vivant récupéré sur boîtier.

La table du programme 6 est à `0x25f3dbc`. Elle contient les entrées `13 00 2f 00` et `14 00 2f 00`, avec prédicat nul. Pour l’étape observée `0x14`, le répartiteur `0x22054a0` appelle l’allocateur `0x22053c0(wrapper, 0x2f, 0)` puis `0x219afcc`. Aucun descripteur ni ordinal de réservation n’est injecté.

## Résultat de la réservation

Le banc vérifie le nouvel enregistrement à `0x3731220` : propriétaire 1, type `0x2f`, index zéro, ordinal 1. Les 28 octets de son descripteur correspondent à la table ROM ; les deux octets de padding de l’enregistrement ne sont pas validés.

```text
descripteur : 0x25d8cec
sept mots  : 0, 0x34983c00, 0xc80000, 0x1400, 0x1400, 0xa00, 2
```

La recherche `0x2199240` renvoie 1, puis le wrapper renvoie `0x25d8cec`. Le destinataire passe la copie de descripteur qui échouait auparavant. Il entre dans `0x219eb88`, puis `0x21ca300` et dans l’acquisition DMA `0x11ac6b8`.

Le destinataire s’arrête après **21 907 instructions**, sur la lecture du slot de sémaphore `0x7acd0`, au PC `0x5500c`. Les notifications restent `8, 9, 0x28`, statut zéro, et le gestionnaire WB a terminé.

## Initialisation DMA étudiée séparément

L’entrée native `0x11ac684` efface les `0x2c4` octets à `0x1788fe8`, obtient huit via `0x11ae578`, puis appelle `0x127e1e4(228, 8)`. Ce wrapper construit le sémaphore avec compteur initial et maximum égaux à huit.

Le banc déclare explicitement son slot `0x7acd0` libre à l’entrée, comme hypothèse de démarrage. Il vérifie ensuite la structure native à `0x64324` (`0, 8, 8, 8, 0`) et le pointeur inscrit dans le slot. Les autres octets RAM restent inconnus jusqu’à écriture native.

L’initialiseur appelle ensuite `0x11adacc`, qui lit les registres espacés de `0x1000` à partir de `0xfffe0000` et prévoit d’y positionner le bit `0x10000000`. Le premier accès s’arrête après **783 instructions**, au PC `0x5aa40`, faute de périphérique émulé. La valeur initiale du registre et ses effets matériels ne sont pas inventés.

**Aucune RAM de cette exécution interrompue n’est transférée au destinataire.** Le résultat démontre l’origine et les paramètres du sémaphore, ainsi que la première dépendance matérielle ; il ne constitue pas une initialisation DMA terminée.

## Géométrie incompatible dans le banc actuel

Les six mots préparés à l’entrée de `0x219eb88` donnent :

| Paramètre | Valeur |
|---|---:|
| Adresse source calculée | `0x13380` |
| Pas source | 15 744 octets |
| Adresse destination calculée | `0x349a2800` |
| Pas destination | 15 744 octets |
| Largeur copiée | 15 744 octets |
| Lignes | 5 192 |

L’adresse source dérive encore d’un pointeur RAW nul, auquel le code ajoute un décalage de lignes. Elle ne désigne pas les pixels du RAF. Le buffer destination reste non mappé.

L’étendue finale relativement à la base du descripteur vaut :

```text
(destination − base) + (lignes − 1) × pas + largeur = 81 868 800 octets
capacité déclarée du descripteur                         = 13 107 200 octets
```

Cette différence est signalée dans le rapport (`fits_static_capacity: false`). Elle concerne le mélange actuel de métadonnées X100VI et de contexte/mode CMOS de banc X-T4 ; elle n’établit pas une propriété générale de tous les chemins du firmware. Il faut retrouver la bonne configuration d’entrée et la disposition des buffers avant toute copie réelle. Agrandir artificiellement la mémoire masquerait cette dépendance.

## Validation et suite

```bash
.venv/bin/python -m fuji_recipe_lab xt4-resource-probe research/extracted/xt4-2.12 '/chemin/photo.RAF' --with-receiver --firmware-config --boot-wb --extended-config --raw-resource-plan --output research/reports/resource-plan-replay.json
.venv/bin/python -m unittest discover -s tests -v
```

Rapport validé : `research/reports/xt4-receiver-resource-plan-validated.json`. Régression du parcours précédent : `research/reports/xt4-receiver-plan-default-regression.json`. **64 tests passent**, dont les rejets de firmware modifié et de préparation incomplète, ainsi que les lectures bornées des observations de pile. `passed` qualifie les observations et arrêts attendus, jamais un rendu d’image.

Prochain travail : reconstruire les canaux et registres DMA à partir de leurs usages natifs, puis déterminer un descripteur RAW et une géométrie compatibles. Le chargement des vrais pixels, l’adaptation DNG, la calibration et la validation du rendu Fuji restent nécessaires. L’interface conserve son aperçu intégré avec recette non appliquée.
