# Validation du socle de recherche — 13 septembre 2026

## Tests exécutés

Commande : `.venv/bin/python -m unittest discover -s tests -v`.

**68 tests réussis.** Sur cet environnement Codex/macOS, le JIT d’Unicorn a nécessité l’exécution autorisée hors bac à sable ; dans le bac à sable, le processus quittait avec SIGILL (code 132).

| Vérification | Résultat |
|---|---|
| ARM, Thumb, ARM64 : addition et retour synthétiques | 3 architectures validées |
| Accès à une adresse non déclarée | Erreur enregistrée, aucune mémoire fictive ajoutée |
| Boucle infinie | Arrêt au budget d’instructions |
| Moteur exact indisponible | Erreur explicite, aucun fichier image de substitution |
| Recettes invalides / nombres non finis | Rejet |
| TIFF 16 bits avec un seul écart de +1 | Écart détecté sans réduction en 8 bits |
| Tailles d’image différentes | Comparaison refusée, aucun redimensionnement |
| Inspection d’un DAT synthétique | Indices retrouvés, fichier source inchangé |
| Décodeur LZ : littéraux, recouvrements, distances, limites | Concordance avec une copie octet par octet sur un flux synthétique reproductible |
| Conteneur : encodages mixtes, corruption de chacun des sept segments, bornes | Rejets attendus |
| Mauvais firmware / mauvais module natif | Refus avant extraction ou exécution |
| Lectures, écritures et instructions dans le remplissage d’alignement | Arrêt explicite |
| Plages mémoire partielles et adjacentes | Plages connues accessibles, trous interdits |
| Traces bornées avec plages qui se chevauchent | Aucun doublon, troncature signalée |
| Métadonnées RAF modifiées entre validation et réutilisation | Refus avant orchestration |
| API GUI : session, origine et hôte incorrects | Accès refusé |
| API GUI : recette JSON, champ inconnu, export image | Aller-retour validé, champ rejeté, rendu refusé |
| Import GUI : nom contenant des traversées et taille excessive | Copie confinée au répertoire temporaire, excès rejeté |

Le fichier `research/reports/emulator-selftest.json` contient les registres, les traces et les empreintes des programmes synthétiques. **Aucun code de traitement d’image Fuji n’a été exécuté par ces tests.**

## Essais sur le firmware réel

Les commandes `xt4-film-probe` et `xt4-parameter-probe` ont été exécutées séparément de la suite unitaire, avec les modules dont les empreintes sont vérifiées. Elles exécutent du code Fuji réel ; leurs entrées sont des états synthétiques contrôlés.

- Fonction de noms internes : 26 cas réussis.
- Constructeur complet de paramètres RAW et utilitaires natifs : 136 entrées admissibles, retours et sorties conformes aux branches analysées et aux invariants mémoire.
- Dix entrées invalides : arrêt attendu sur une dépendance non cartographiée à `0x00057b74`, aucune substitution de code.
- Extraction réelle : sept sommes de contrôle concordantes, quatre objets décompressés aux tailles déclarées.

Il s’agit d’une validation de cohérence statique/native, sans oracle issu d’un boîtier. **Aucun de ces essais ne calcule une image.** [Provenance, plages testées et limites](NATIVE_XT4.md).

La suite historique ajoute **272 essais de circulation des six champs suivis** et **20 essais ThreadX**. Le nouveau banc calendrier termine ensuite l’installateur pour les 272 cas ; 24 cas supplémentaires valident la synchronisation native. Les initialisations de requêtes permettent d’atteindre le lecteur RAW, testé séparément sur les métadonnées de `DSCF2344.RAF`. Le RTOS complet et le calcul des pixels restent absents. [Détail des nouveaux essais](NATIVE_RUNTIME.md).

Le probe `xt4-resource-probe` réutilise ce bloc réel : le préparateur de ressource retourne, puis un message natif de 68 octets est construit. Après 5792 instructions, le parcours s’arrête sur une lecture de configuration de la destination 9 (`0x018ead24`, PC `0x0127e7a0`). L’envoi n’est pas terminé ; aucun buffer de pixels n’est fourni.

Avec `--with-transport`, les objets de messagerie sont construits nativement et l’orchestrateur termine après 6438 instructions. `xt4-message-probe` valide séparément l’envoi (607 instructions), la réception (510), l’égalité des octets et la restitution du bloc. Avec `--with-receiver`, la tâche 9 consomme la requête et envoie une notification vers la tâche 7 ; elle atteint la configuration inconnue `0xfeb0` après 6735 instructions. [Détail, hypothèses et limites](NATIVE_MESSAGES.md).

Le banc isolé de balance des blancs passe 251 cas : 38 dépendances de calibration et 213 calculs de gains avec coefficients synthétiques explicites. Le remplissage inconnu reste inaccessible. Le destinataire RAW de référence conserve sa frontière validée. [Détail et limites](NATIVE_WHITE_BALANCE.md).

Le nouveau banc de configuration passe 367 cas avec les valeurs du DAT, plus la recherche native du descripteur BSS et le remplissage borné de la page WB. Le parcours RAW étendu atteint 7273 instructions ; les variantes précédentes restent reproductibles. [Provenance et portée exacte](NATIVE_CONFIGURATION.md).

Le bloc DEFAULT de 8192 octets est retrouvé et copié nativement ; son lecteur renvoie 1 dans les trois modes d’accès testés. Le gestionnaire WB retourne dans le destinataire RAW, qui atteint ensuite la réservation manquante de type `0x2f` après 21 473 instructions. Les observations de registres sont bornées et testées. [Détail](NATIVE_DEFAULT.md).

Avec `--raw-resource-plan`, le fragment natif d’affectation du programme 6 est exécuté. Le destinataire crée la réservation `0x2f` et atteint le sémaphore DMA absent après 21 907 instructions. Un banc séparé exécute l’initialiseur DMA : il construit le sémaphore 228 avec huit unités et s’arrête sur le registre matériel `0xfffe0000` après 783 instructions. Sa RAM n’est pas réutilisée. Le calcul d’étendue révèle aussi une incompatibilité entre les dimensions du banc et la capacité déclarée du buffer sélectionné. Le parcours DEFAULT précédent passe toujours. [Détail et reproduction](NATIVE_RESOURCE_PLAN.md).

Le nouveau `xt4-dma-probe` passe 52 cas : 48 constructions de listes avec capture des écritures registre, puis quatre rejets natifs d’entrées invalides. Les pages de capture interdisent toute lecture, y compris la relecture d’une valeur précédemment écrite. Le mode de buffers 7 réserve un descripteur de 55 464 192 octets et atteint le même sémaphore après 21 874 instructions ; les dimensions X100VI du banc ne tiennent toujours pas dans ce buffer. Le mode 6 est documenté comme incompatible avec cette orchestration, car les ressources `0x32`/`0x33` y sont absentes. [Détail et reproduction](NATIVE_DMA.md).

Avec `--control`, 84 cas vérifient séparément le décodeur de statut et les conditions de lancement sur des registres synthétiques statiques. Deux séquences de six étapes exécutent le constructeur de drapeau, le callback natif et les attentes avant/après notification, pour les attributs 0 et 4. Deux fragments natifs supplémentaires confirment que le choix réel d’attribut nécessite un mot de pile non défini par le bloc de construction étudié. Aucun de ces états n’est transmis au destinataire RAW. [Détail](NATIVE_DMA_CONTROL.md).

Le même banc exécute désormais le constructeur de mémoire variable (520 instructions), puis la préparation du coordinateur et l’appelant RAW avec paramètres lus dans la ROM (3 399 instructions jusqu’au champ inconnu). Six initialisations précédentes, trois allocations natives et les objets file/pool sont vérifiés dans une arène synthétique gardée. L’état antérieur de la pile n’est pas fourni ; la garde interrompt la sélection d’attribut et cette RAM n’est pas réutilisée. Rapport : `research/reports/xt4-native-predecessors-validated.json`.

Le rapport `research/reports/xt4-startup-first.json` ajoute un parcours indépendant depuis `0x2120c20`. La tâche 26, première de cette séquence, effectue ses trois allocations et rencontre le même champ inconnu après 2 534 instructions. Les paramètres proviennent des instructions natives ; aucun attribut n’est injecté et aucune RAM du parcours interrompu n’est réutilisée. Le rapport global passe les vérifications des deux parcours et des 84 cas DMA précédents.

Le rapport `research/reports/xt4-boot-task-validated.json` ajoute le descripteur de la tâche 86 (15 instructions), son remplissage de pile natif (3 101 instructions) et son entrée isolée (285 instructions). La table native sélectionne le gestionnaire de démarrage ; le verrou `0x178c5a0` reste indisponible. La pile est une arène relocalisée, sans restauration de contexte noyau ; aucune donnée n’est injectée dans un appel RAW ultérieur. [Provenance et limites](NATIVE_BOOT_TASK.md).

Le rapport actuel `research/reports/xt4-boot-hardware-validated.json` ajoute deux initialisations natives terminées (252 et 613 instructions), suivies de l’initialiseur de configuration qui atteint le registre matériel inconnu `0xff70f03c` après 45 656 instructions. Les 18 valeurs d’initialisation sont comparées à la ROM vérifiée. Seuls les appels terminés transmettent leur RAM au suivant ; la RAM interrompue n’est pas réutilisée.

## Interface graphique

La bibliothèque du service contient 2 598 fichiers. L’API a ouvert les trois photos du tableau ci-dessous et livré leurs aperçus intégrés ; les SHA-256 avant/après restent identiques. Une recette ACROS, hautes lumières `1.5`, décalage rouge `2`, a été validée et restituée sans perte de ces champs. `render_available` reste faux. Rapport : `research/reports/gui-integration.json`.

L’interface a été inspectée visuellement dans Safari, avec ouverture de `DSCF2344.RAF`. **Enregistrer la recette** a téléchargé `Downloads/Classic-Negative.json` (464 octets). **Charger JSON**, suivi de la sélection de ce même fichier, a réaffiché les champs attendus et le message « Recette chargée ». Les tests HTTP valident séparément une recette comportant des valeurs différentes des valeurs par défaut.

## Fichiers utilisateur vérifiés

| Source | Structure observée | Jeu d’essai produit |
|---|---|---|
| `20260621_0001.DNG` — Leica Q3 43 | Bayer 2×2, 9536×6344 | `outputs/leica-q3-dng/` |
| `IMG_4768.DNG` — iPhone 16 Pro | Image multicanal, pas de CFA exposé | `outputs/apple-proraw-dng/` |
| `DSCF2344.RAF` — X100VI | X-Trans 6×6, RAW 7872×5196 | `outputs/fuji-x100vi-raf/` |

Chaque dossier contient un manifeste SHA-256, les métadonnées, un tableau float32 linéaire sRGB, un aperçu neutre et la référence JPEG embarquée quand disponible. Tous les tableaux sont finis. Les empreintes des trois originaux sont identiques avant et après la préparation.

Le JPEG intégré au DNG Leica choisi est en noir et blanc selon ses métadonnées ; le RAW conserve des données couleur. Le RAF testé indique notamment Classic Negative, DR de développement 400, Color Chrome et FX Blue forts. L’existence de cette référence ne valide qu’un rendu préexistant, pas l’application de nouvelles recettes.

## Inventaire

L’inventaire récursif trouve 1 774 DNG dans le dossier Photo, et 810 RAF plus 14 DNG dans le dossier X100VI. Le nombre de fichiers résidents iCloud change pendant la synchronisation : utiliser `local_counts` dans un nouvel inventaire pour connaître la disponibilité au moment d’un test. Le premier décompte de 53 RAF annoncé pendant l’exploration reposait sur une estimation conservatrice de l’allocation disque ; ce n’est pas le nombre total de RAF.

## Rapports disponibles

- `research/reports/raw-inventory.json` : chemins locaux et fichiers annexes.
- `research/reports/xt4-2.12-inspection.json` : inspection statique du firmware officiel.
- `research/reports/xraw-studio-static.json` : empreinte de XRFC.dylib et symboles sélectionnés.
- `research/reports/emulator-selftest.json` : banc d’émulation synthétique.
- `research/extracted/xt4-2.12/manifest.json` : sept segments, quatre objets et leurs empreintes.
- `research/reports/xt4-module-map-cli.json` : bases candidates, références de chaînes et appels au constructeur.
- `research/reports/xt4-film-probe.json` : 26 exécutions natives de la fonction de noms.
- `research/reports/xt4-parameter-probe.json` : 146 essais du constructeur, dont 136 entrées admissibles.
- `research/reports/xt4-chain-probe-guarded.json` : 272 essais de circulation, avec les gardes mémoire et les empreintes vérifiées à chaque chargement.
- `research/reports/xt4-threadx-probe.json` : 20 essais ciblés sur le cœur 0.
- `outputs/*/manifest.json` : provenance et limites de chaque jeu d’essai.

Ces rapports restent locaux et ne sont pas inclus dans un éventuel dépôt public. Les fichiers sous `research/vendor/` sont des références consultées, pas des dépendances exécutées par le projet.

## Non validé

Équivalence de la décompression avec un dump RAM indépendant, autres firmwares X6/X8, cartographie système complète, conventions d’appel hors fonctions documentées, calcul natif des pixels, mémoire de calibration, DSP/ISP, conversion exacte d’un RAF, adaptation DNG vers le moteur Fuji, qualité ou vitesse de rendu d’une application finale.
