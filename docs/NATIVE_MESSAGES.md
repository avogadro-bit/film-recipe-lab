# Transmission et réception natives d’une requête RAW

Résultats locaux du 12 septembre 2026, firmware X-T4 2.12 épinglé. **Aucun rendu de pixels n’est encore produit.** Les étapes suivantes prolongent le [préparateur de ressource](NATIVE_RUNTIME.md) et ne changent pas cette limite.

## Ce qui termine

| Exécution | Instructions | Vérifications |
|---|---:|---|
| Création d’une file Fuji `0x0004af4c` | 194 | Objet de 36 octets, pointeur de table, compteurs vides |
| Création d’un pool Fuji `0x0004b830` | 556 | Marqueur natif, quatre blocs disponibles, liste libre |
| Envoi `0x0127e784` | 607 | En-tête et 68 octets copiés, un pointeur en file, un bloc alloué |
| Réception `0x0127e914` | 510 | En-tête et charge utile identiques, file vidée, bloc restitué |
| Orchestrateur RAW `0x022152a8` avec métadonnées RAF réelles | 6438 | Retour complet, pile restaurée, message natif en file 9, ressource marquée `0x10200000` |

Le transport est testé séparément avec une charge utile synthétique non uniforme. Son aller-retour est vérifié octet par octet. L’orchestrateur utilise ensuite sa propre charge utile, construite par les instructions Fuji à partir du contexte et des métadonnées de `DSCF2344.RAF`.

## Objets réellement construits

La destination possède deux objets distincts : une file de pointeurs et un pool de blocs. Pour l’identifiant `id` :

```text
file       = 0x0007ad2c + 36 × (id − 1)
table file = 0x0005d1c8 +  4 × (id − 1)
pool       = 0x0005d9a0 + 84 × (id − 1)
table pool = 0x0005d5b0 +  4 × (id − 1)
```

Le banc fournit quatre emplacements et des blocs de 80 octets, avec des buffers séparés pour les destinations 9 et 7. Il fournit aussi un état de démarrage à froid de la liste des pools. **Ces capacités sont des entrées de test, pas les capacités récupérées au démarrage du boîtier.** Le constructeur de tâche `0x022047c0` révèle statiquement une configuration différente : 48 emplacements de 104 octets pour cette famille de tâches. Le banc minimal teste le mécanisme sans prétendre reproduire tout le démarrage.

Les constructeurs écrivent les objets et les listes libres. Les octets non écrits des pages restent illisibles. La fusion de deux pages partageant une adresse refuse toute contradiction entre octets connus et conserve les trous inconnus.

La page de données `0x01731000`, initialement incluse dans le premier module vérifié, est séparée de ses segments de code pour permettre l’enregistrement natif du callback à `0x017314a0`. Les instructions restent inchangées. Le callback `0x0128fa38` est installé par `0x0127e40c` ; son masque de journalisation est explicitement nul. Ce n’est pas un remplacement de fonction.

## Tâche destinataire retrouvée

`0x022047c0` associe la boucle `0x0221a290` à sa tâche. Cette boucle reçoit les messages par `0x0127e9d0`, traite certains événements particuliers via `0x02215230`, puis copie le contenu de la requête dans le wrapper avec `0x02204afc`.

Le wrapper est désormais initialisé par `0x02204830`, puis lié au contexte par `0x02204880`. Les valeurs natives `+0x45 = 3`, `+0x46 = 1` permettent d’aller au-delà du champ précédemment inconnu.

Pour la réception, le banc entre directement dans la boucle avec `R0=9` et une identité courante 9 explicite. **Il n’émule pas un changement de contexte par l’ordonnanceur.** Son objet de drapeaux est créé par `0x0004b0c4`, à partir d’attributs et de drapeaux initiaux nuls. Les fonctions de synchronisation et les instructions atomiques continuent de s’exécuter nativement.

Pour l’opération `0x23`, la table à `0x025f1de8` pointe vers la séquence à `0x025f1f80` :

```text
04 13 14 0e 15 1f 30 29 38 2d 27 35 9c 9e
```

Il s’agit d’identifiants internes de cette séquence ; ils ne sont pas assimilés aux codes d’autres enums portant des noms voisins.

## Notification de progression

Le callback `0x021d28e4` produit une notification vers la tâche 7. Cette destination est enregistrée nativement par `0x021ee4f8`. La valeur 7 est corroborée par la chaîne d’appels `0x02120e20 → 0x021cb604 → 0x021d4064 → 0x021ee4f8`.

Le message observé possède l’événement `0x923c`, l’expéditeur 9, la destination 7 et une charge utile de 16 octets. Il contient le wrapper `0x06500000`, le contexte `0x06000000`, le code suivi `8` et l’opération `0x23`. La file 9 est vide, son bloc a été libéré, et la file 7 contient la notification. **Ce message ne prouve pas qu’une image soit calculée ou terminée.**

## Frontière actuelle et variantes exploratoires

Après 6735 instructions dans la tâche, le chemin `0x022073f4 → 0x021ae6fc → 0x022a9520` demande le paramètre `0xfeb0` au lecteur natif `0x01263954`. L’accès au pointeur de configuration fourni par le banc vise `0x0680feb0`, PC `0x0126396c`. Cet octet est volontairement absent du probe de validation.

La documentation primaire de fffw décrit une zone `cfgdata` chargée au démarrage, contenant notamment des paramètres et des données de calibration ; son organisation varie selon les modèles. Cela donne une piste pour la provenance du bloc, **sans établir la signification ni la valeur du paramètre X-T4 `0xfeb0`**. [Notes de l’auteur sur cfgdata](https://github.com/tiredboffin/fffw/wiki/Route-0xff80#settings-cabinet).

L’option de recherche `--cfg-feb0` permet d’explorer explicitement une valeur hypothétique, sans la déclarer récupérée ni autoriser le rendu. Les valeurs 0 et 255 atteignent toutes deux une écriture dans la zone de balance des blancs à `0x0288d1fc`. En autorisant seulement les écritures natives de cette page, la variante 0 atteint ensuite une lecture de quatre octets à `0x0288d204`, PC `0x021ae880`, dont certains octets restent inconnus. Il faut distinguer les champs utilisés, l’initialisation globale et un éventuel remplissage de structure avant de poursuivre.

## Reproduction

```bash
.venv/bin/python -m kora xt4-message-probe research/extracted/xt4-2.12 --output research/reports/message-replay.json
.venv/bin/python -m kora xt4-resource-probe research/extracted/xt4-2.12 '/chemin/DSCF2344.RAF' --with-transport --output research/reports/transport-replay.json
.venv/bin/python -m kora xt4-resource-probe research/extracted/xt4-2.12 '/chemin/DSCF2344.RAF' --with-receiver --output research/reports/receiver-replay.json
```

Les rapports existants sont immuables. `passed` du probe de réception vérifie l’arrêt précis attendu, la réception et les notifications ; **il ne signifie pas que la tâche ou le développement ont terminé**. Les variantes hypothétiques gardent cette validation à faux lorsqu’elles quittent cette frontière connue.

La prochaine étape porte sur l’initialisation de la configuration et de la structure de balance des blancs, puis sur les buffers RAW, les gains et le traitement des pixels. La compatibilité X100VI et l’adaptateur DNG ne sont toujours pas validés.

Le 13 septembre, le suivi des écritures confirme que seul l’octet `+11` de la structure reste inconnu. Le calcul isolé des gains termine sans le lire sur 213 cas avec calibration synthétique explicite ; 38 essais identifient les dépendances des décalages WB. [Analyse et limites](NATIVE_WHITE_BALANCE.md). Le parcours RAW de référence conserve son arrêt à `0xfeb0` (rapport `xt4-receiver-wb-regression.json`).

La suite avec les coefficients du DAT et l’état de remplissage dérivé du BSS atteint 7273 instructions, jusqu’au global `0x0190d784`, avant la configuration étendue `0x420f82`. [Configuration retrouvée et portée du démarrage émulé](NATIVE_CONFIGURATION.md).
