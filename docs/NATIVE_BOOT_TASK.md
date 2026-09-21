# Tâche de démarrage du module image — 14 septembre 2026

**La tâche qui appelle le module image est identifiée comme la tâche 86. Son descripteur et le remplissage natif de sa pile sont vérifiés. Son entrée s’exécute dans un banc isolé jusqu’à un verrou global inconnu. Le module image lui-même n’est pas encore atteint depuis cette entrée.**

## Provenance du chemin

Le constructeur `0x12b0c50` prépare la file 86, puis écrit le descripteur de tâche au bloc `0x12b0c80…0x12b0cbc` :

`[86, 0x168ccec, 5, 0x1000, 0x12b2b00, 0]`.

L’entrée `0x12b2b00` initialise ses états et un buffer, puis appelle `0x12b26c0`, qui passe par la table d’actions `0x168cf3c` dans `0x12b25f4`. Pour l’état initial zéro, cette table sélectionne `0x12b2b68`. La sélection et l’entrée dans cette fonction sont observées dynamiquement dans le nouveau banc.

Le désassemblage relie ensuite ce gestionnaire, lorsque ses conditions réussissent, à `0x12b1a84 → 0x1291908`. Cette dernière routine recherche le module 6 et appelle l’entrée contenue à l’offset `+0xc` de son en-tête : `0x1e1de60`. Une autre action de la même table, `0x12b2c08`, peut emprunter le même chemin. Ces branches ultérieures ne sont pas encore exécutées dans ce banc.

## Remplissage natif de pile

Le constructeur général `0x127d76c` lit l’identifiant à `0x127d7f8`. Au bloc `0x127d8ec…0x127d914`, il récupère la taille et le pointeur de pile du registre de tâches, réduit l’identifiant à un octet et appelle `0x1281a40` pour remplir la pile.

Le nouveau `boot_task_probe` exécute :

1. Le bloc du descripteur : **15 instructions**, six mots vérifiés.
2. Le bloc de recherche de pile et son appel de remplissage : **3 101 instructions**. Les 4 096 octets sont tous écrits par le code natif à la valeur `0x56`, l’identifiant 86. Aucune autre valeur n’est ajoutée dans la pile.
3. L’entrée `0x12b2b00` avec argument zéro : **285 instructions**, sur cette pile remplie nativement.

La pile est relocalisée à `0x700f000` ; son pointeur et le SP d’entrée `0x7010000` sont des paramètres explicites du banc. Les routines de création du contexte noyau et l’ordonnanceur ne sont pas exécutés. Ce parcours vérifie donc une entrée de fonction sur une arène de pile justifiée par le remplissage natif ; il ne constitue pas une restauration complète de la tâche réelle.

**Cette pile n’est jamais injectée dans un appel RAW commencé plus tard.** Il reste nécessaire d’exécuter les étapes intermédiaires pour conserver leurs écritures réelles.

## Nouvelle dépendance

Les états à `0x1af36d8`, le buffer de 216 octets à `0x1b6895c`, son pointeur interne et l’événement à `0x1bd5670` sont initialisés par les instructions natives. La table ROM choisit l’action 2, soit `0x12b2b68`.

La lecture du verrou `0x178c5a0`, PC `0x12807f8`, arrête l’entrée isolée. Un banc supplémentaire exécute maintenant son initialiseur `0x11bf390`. Il initialise le verrou via `0x128075c`, efface des données et parcourt plusieurs tables de configuration avant des appels supplémentaires. Ce parcours rencontre d’abord un autre verrou non initialisé, à `0x1949ca0`.

## Initialisations préalables exécutées

Deux fonctions natives règlent cette seconde dépendance dans le banc :

| Fonction | Résultat vérifié | Instructions |
|---|---|---:|
| `0x11a1564` | Efface exactement 300 octets à `0x1949b7c` | 252 |
| `0x11a1584` | Installe 18 mots depuis la table ROM `0x15824a0`, écrit le marqueur `0x22233344` et restitue le verrou à zéro | 613 |
| `0x11bf390` | Initialise le premier verrou et ses tables, puis rencontre un accès matériel inconnu | 45 656 |

Seules les données gardées des deux appels terminés sont transmises au suivant. Les piles de ces appels préparatoires restent distinctes de celle de la tâche 86. Le retour de l’initialiseur complet est encore inconnu : sa RAM interrompue n’est transférée ni à la tâche 86 ni au destinataire RAW.

## Blocage matériel confirmé

L’appel `0x11bfae8 → 0x5aa38` tente une lecture de 32 bits à `0xff70f03c`, avec retour prévu à `0x11bfaec`. La fonction native `0x11bfac4` est un opérateur de lecture/modification/écriture : dans le cas observé, elle veut effacer le masque `0x7` en conservant les autres bits. Sans valeur ni sémantique de périphérique justifiées, le banc arrête cette lecture. Aucun zéro ni état de réussite n’est fourni.

Cette dépendance est distincte du DMA image à `0xfffe0000`, déjà rencontré dans le destinataire RAW. Lever le seul verrou logiciel ne donne donc pas un démarrage complet ni un moteur de pixels.

Les sources consultées le 14 septembre 2026 ne résolvent pas cette dépendance. La [présentation RTOS de FujiHack](https://wiki.fujihack.org/rtos/) porte explicitement sur les recherches X-A2 ; elle ne constitue pas une spécification matérielle du X-T4. La [liste de travaux FujiHack](https://wiki.fujihack.org/todo/), dont le contenu est daté d’avril 2024, décrit la création d’un émulateur avec ses périphériques comme un chantier à réaliser. Cette page ne prouve pas à elle seule qu’aucun autre émulateur n’existe ; les recherches effectuées n’ont pas fourni de modèle validé pour ces registres X-T4.

Pour valider la reproduction exacte, il manque notamment un modèle documenté ou mesuré des périphériques utilisés, le comportement du traitement matériel des pixels, les calibrations pertinentes et des couples entrée/rendu Fuji permettant de comparer le résultat. Les tests d’instructions et de mémoire ne remplacent pas cette validation d’image. La prise en charge des DNG et la différence X-T4/X100VI restent des travaux séparés non résolus.

## Validation

Le rapport `research/reports/xt4-boot-hardware-validated.json` passe les vérifications des initialisations préalables, de l’arrêt matériel attendu, du parcours de la tâche 86, des deux parcours de création précédents et des 84 cas de contrôle DMA. `passed` signifie que les observations attendues du diagnostic sont conformes, pas que le démarrage ou le rendu a réussi. Le refus de firmware modifié couvre aussi les nouveaux bancs. **68 tests unitaires passent.**

```bash
.venv/bin/python -m kora xt4-dma-probe research/extracted/xt4-2.12 --control --output research/reports/boot-task-replay.json
.venv/bin/python -m unittest discover -s tests -v
```

Le projet reste inachevé : aucun transfert matériel complet ni rendu exact RAF/DNG n’est validé ; l’interface conserve l’aperçu intégré avec recette non appliquée.
