# Statut, lancement et notification DMA — 14 septembre 2026

**Les fonctions Fuji de lecture de statut et de lancement passent 84 essais isolés. Le callback de notification et les attentes sont également exécutés nativement. Cela ne constitue ni un périphérique DMA émulé, ni un transfert terminé, ni un rendu d’image.**

## Statut et lancement : 84 cas

La commande `xt4-dma-probe --control` fournit des valeurs de registre **synthétiques et statiques** à des fonctions natives. Ces valeurs ne sont pas des mesures sur boîtier. Aucun hook ne fait évoluer le statut, aucune interruption n’est générée et aucun état de ce banc n’est transféré au destinataire RAW. Le banc précédent sans `--control` conserve ses pages de capture en écriture seule.

Le décodeur `0x11adbe4` lit le registre `base + 0x30`, extrait son bit 16, puis copie les registres `base + 0x14` et `base + 0x18` dans la structure fournie. La table ROM `0x1582cf4` traduit les valeurs 0/1 en octets 0/1. Son retour zéro signifie que cette lecture a terminé ; **il n’atteste pas un transfert réussi**.

Les 70 cas de lecture couvrent les canaux 1 et 9, zéro, chacun des 32 bits isolés, `0xffffffff` et `0xa5a5a5a5`. Ils vérifient le résultat, les trois adresses lues, l’absence d’écriture registre et la conservation des octets de padding de la structure.

La fonction de lancement `0x11adb34` attend que le bit 16 du statut soit nul. Elle lit ensuite `base + 0x28` et y écrit la valeur précédente avec le bit 28 positionné. Douze cas sur deux canaux vérifient :

- trois mots de commande distincts et la préservation de leurs autres bits ;
- un statut occupé constant : le code atteint sa limite de 256 instructions en continuant de sonder le statut, sans écrire de commande ;
- l’arrêt sur un statut inconnu ;
- l’arrêt sur une commande inconnue après un statut synthétique disponible.

Deux cas supplémentaires vérifient le rejet natif du canal 16, sans accès aux registres. Les erreurs ou états d’achèvement d’autres circuits ne sont pas déduits de ces fonctions.

## Callback et attentes natives

Le callback `0x21c702c`, installé par le chemin de copie `0x21ca300`, lit l’identifiant de tâche à `0x3735ba9`. S’il vaut zéro, il retourne. Sinon il appelle `0x127e0c8(identifiant, 0x10)` pour signaler un drapeau.

Le banc crée le drapeau 9 via `0x4b0c4`, avec valeur initiale zéro et identifiant de tâche 9 explicitement fourni. Il appelle le callback directement, **sans prétendre qu’une IRQ ou un DMA l’ait déclenché**. Les sondages utilisent `0x127dfd8` avec délai zéro, pour ne pas simuler d’ordonnanceur.

| Étape | Résultat natif |
|---|---|
| Création du drapeau | retour zéro, aucun événement |
| Sondage avant notification | `0xffffffce` (−50), aucun événement |
| Callback avec cible zéro | retourne sans signaler |
| Callback avec cible 9 | signale le masque `0x10` |
| Premier sondage après notification | retour zéro, masque observé `0x10` |
| Deuxième sondage | dépend de l’attribut du drapeau |

Avec l’attribut 0, l’événement reste présent et le deuxième sondage réussit. Avec l’attribut 4, le premier sondage efface l’événement et le second retourne −50. Les deux séquences de six étapes passent. Le code à `0x54e90…0x54e9c` confirme que le bit 2 de l’attribut contrôle cet effacement. Les images ne sont jamais accessibles à ce banc.

## Le choix réel d’attribut reste inconnu

La fonction de création de tâche `0x127d76c` consulte le mot à l’offset `+0x18` du descripteur : s’il vaut `0xa5f0a5f0`, elle choisit l’attribut 0 ; sinon elle choisit 4. Cette branche est atteinte après les vérifications du registre de tâches et une allocation native de pile, désormais exécutées dans le banc décrit ci-dessous.

Le bloc RAW `0x2204800…0x2204828`, avant cet appel, écrit six mots : identifiant, paramètres de tâche, taille de pile `0x1400`, entrée `0x221a290` et argument. **Il ne définit pas le septième mot à `+0x18`.**

Le premier banc exécute ce bloc sur une pile gardée, avec identifiant 9 et autres paramètres explicitement fournis, puis transfère seulement ses 24 octets définis à l’essai de sélection d’attribut. Celui-ci s’arrête à `0x127d7c0` en lisant le mot inconnu. Aucun zéro ni marqueur n’est ajouté pour imposer un résultat.

## Allocation native et appelant RAW

Le nouveau module `task_initialization.py`, inclus dans `xt4-dma-probe --control`, exécute le constructeur de mémoire variable `0x4ba4c`. Il fournit un identifiant de pool 1, une arène synthétique de 64 Kio à `0x6a00000` et des registres d’objets initialement vides. Le contenu de l’arène et de la pile est inconnu : seules les écritures natives rendent leurs octets lisibles. Ces conditions représentent un démarrage à froid de banc, pas une capture mémoire du boîtier.

Le constructeur termine après **520 instructions** et inscrit son objet à `0x7a01c` dans la table `0x79fd8`. Ses données gardées sont transférées à la préparation du coordinateur `0x21cb604`, avec destination 7 explicitement fournie. Ce parcours atteint l’appelant RAW `0x21f08ac`, qui lit la table ROM `0x25eb468` et appelle `0x22047c0` avec `(9, 0x251b754, 6)`. Les paramètres de tâche ne sont donc plus choisis par le banc dans ce parcours.

La création de file/pool `0x127e42c`, puis la création de tâche `0x127d76c`, exécutent trois allocations via `0x4f4d8 → 0x5328c → 0x40d74` :

| Usage | Taille demandée | Adresse produite dans l’arène du banc |
|---|---:|---|
| File de 48 messages | 192 octets | `0x6a00008` |
| 48 blocs de 104 octets, avec en-têtes de 4 octets | 5 184 octets | `0x6a000d0` |
| Pile de la tâche | 5 120 octets | `0x6a01518` |

Les objets de file et de pool, les registres d’allocations et les six mots du descripteur sont vérifiés. Aucun retour d’allocation n’est substitué au code natif.

Le parcours initial depuis `0x21f08ac` atteignait 2 533 instructions. Le parcours étendu depuis `0x21cb604` atteint désormais **3 399 instructions**, puis s’arrête sur la lecture inconnue à `0x700ff8c`, PC `0x127d7c0`. Le déplacement de l’adresse vient des cadres de pile supplémentaires ; il s’agit toujours du septième mot du descripteur. La trace complète des écritures confirme qu’aucun appel précédent de ce parcours n’a écrit ce mot. La tâche n’a pas fini sa création ; aucune RAM de cette exécution interrompue n’est transférée au destinataire RAW.

## Préparation précédente et provenance de pile

Les six initialisations suivantes sont désormais exécutées et leurs écritures vérifiées, sur des pages initialement inconnues :

| Routine native | Effet observé |
|---|---|
| `0x21cf870` | Effacement de 16 octets à `0x2d1d1f8` |
| `0x21f2b48` | Effacement du tableau de 768 octets à `0x31d4070` et du demi-mot à `0x336b31c` |
| `0x21ee4f8` | Enregistrement de la destination 7 à `0x3678e30` |
| `0x21ef6e4` | Initialisation d’un état à `0x367cfdc` avec valeurs 0, 4 et −1 |
| `0x21ef1e8` | Initialisation des champs de requête à `0x3678e34…0x3678e4f` |
| `0x21ee538` | Écriture du pointeur `0x3726ff4` à `0x3726ff0` |

La chaîne directe retrouvée par désassemblage des modules vérifiés est :

`0x1e1de60 → 0x2120c20 → 0x21cb604 → 0x21d4064 → 0x21f096c → 0x21f08ac → 0x22047c0`.

L’appel à `0x2120c20` est à `0x1e1df7c`. Cette routine crée notamment la tâche 25 via `0x223d348`, puis la tâche 7 via `0x127d76c` à `0x2120e14`, avant de passer la destination 7 à `0x21cb604` à `0x2120e24`. Ces créations précédentes **ne sont pas encore exécutées par ce banc** et peuvent modifier la pile réutilisée ensuite. La routine générale `0x1e1de60` est référencée dans l’en-tête du module B à `0x1e0f00c` ; cela ne suffit pas à établir l’adresse ni le contenu initial de sa pile. Cette provenance reste à reconstruire, sans supposer un remplissage zéro ou un attribut 4.

## Première création du démarrage : même dépendance

Un second parcours indépendant, `startup_initialization` dans le rapport, commence maintenant à l’entrée `0x2120c20`. Il utilise un pool mémoire natif neuf et des registres d’objets vides pour le premier identifiant rencontré. Il ne reçoit aucune RAM du parcours RAW interrompu.

L’appelant fournit nativement `(26, 0x25bd09c, 3)` à `0x2246f7c`. Cette routine crée une file de 48 entrées, un pool de 48 blocs de 32 octets, puis demande une pile de `0x1400` octets. Les allocations de 192, 1 728 et 5 120 octets sont effectuées par le même allocateur Fuji. Les objets construits et le descripteur `[26, 0x25bd09c, 3, 0x1400, 0x22491fc, 26]` sont vérifiés.

Après **2 534 instructions**, la première tâche rencontre elle aussi une lecture inconnue à `0x127d7c0` : l’adresse est `0x700ff94`, soit le mot `+0x18` du descripteur. Aucune écriture de ce parcours ne l’a défini. La création de cette première tâche ne termine pas ; les tâches suivantes, dont 25, 7 et RAW, ne sont pas exécutées dans ce parcours.

Cela établit, pour une pile initialement inconnue, que l’obstacle précède la tâche RAW et les tâches 25/7. Leur seul ajout au banc ne résoudra pas la dépendance : il faut une provenance de pile antérieure à `0x2120c20`.

Le désassemblage retrouve aussi l’appel indirect du module B : `0x1291908` recherche le module 6 via `0x1290fb8`, appelle `0x1280c14` pour la région déclarée, puis charge l’entrée à l’offset `+0xc` de l’en-tête et l’appelle à `0x1291950`. La chaîne amont passe par `0x12b1a84`, appelé à `0x12b2bd0` ou `0x12b2c60`. Ces routines de démarrage plus générales ne sont pas exécutées par les deux parcours. Leurs vérifications et leurs dépendances matérielles ne sont pas remplacées par des retours supposés.

L’attribut zéro utilisé dans l’ancien destinataire RAW demeure donc une hypothèse de banc, pas une valeur native récupérée. Le choix 4 n’est pas automatiquement appliqué au destinataire sur la base de sa seule vraisemblance.

## Reproduction et portée

```bash
.venv/bin/python -m fuji_recipe_lab xt4-dma-probe research/extracted/xt4-2.12 --control --output research/reports/dma-control-replay.json
.venv/bin/python -m unittest discover -s tests -v
```

Rapport actuel : `research/reports/xt4-boot-hardware-validated.json` (`passed: true`). Il conserve les 84 cas, les deux séquences de notification, les fragments isolés, le parcours étendu RAW et le parcours indépendant de la première tâche du démarrage. Il ajoute l’entrée isolée de la tâche 86 sur sa pile remplie nativement, ainsi que les initialisations de verrous jusqu’au registre matériel inconnu, décrites dans [Tâche de démarrage](NATIVE_BOOT_TASK.md). Les arrêts attendus sur données inconnues sont des résultats de diagnostic, pas des créations de tâches réussies. **68 tests unitaires passent**, notamment le refus de firmware modifié et de sélecteurs de parcours invalides.

Les prochaines dépendances sont le cycle matériel réel des transferts, les attributs de la tâche, les buffers adaptés aux pixels d’entrée et leur calibration. Le projet reste inachevé : l’interface affiche toujours l’aperçu intégré avec recette non appliquée, et aucun rendu exact RAF/DNG n’est validé.
