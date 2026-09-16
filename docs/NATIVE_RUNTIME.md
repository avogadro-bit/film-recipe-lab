# Du calendrier natif au message de traitement RAW

Suite de cette étape : [envoi terminé, réception native et nouvelle frontière de configuration](NATIVE_MESSAGES.md). Les premières frontières décrites ici restent reproductibles sans les options de transport et de réception.

Résultats locaux des 11 et 12 septembre 2026. Les fonctions proviennent du firmware X-T4 2.12 épinglé et sont exécutées sans modifier leurs instructions ni remplacer leurs appels. **Aucun calcul de pixels Fuji, rendu RAF ou rendu DNG n’est encore validé.**

## Résultats reproductibles

| Commande | Résultat observé | Portée |
|---|---|---|
| `xt4-runtime-probe` | 272 cas réussis, installateur terminé | Réglages, date, fuseau et verrou du calendrier |
| `xt4-sync-probe` | 24 cas réussis | Construction native, prise sans attente, restitution, compteurs vide/plein |
| `xt4-orchestrator-probe` | Arrêt attendu après 2281 instructions | Installation puis synchronisation ; sélecteur de requêtes absent |
| `xt4-raw-frontier-probe` | Arrêt attendu après 5103 instructions | Initialisations et requêtes natives, jusqu’à la lecture de l’entrée RAW absente |
| `xt4-raf-metadata-probe` | Retour natif réussi après 346 instructions | Géométrie du bloc de métadonnées de `DSCF2344.RAF` |
| `xt4-resource-probe` | Arrêt attendu après 5792 instructions | Préparateur de ressource terminé, message construit, envoi incomplet |

`passed` indique que les invariants du probe sont respectés. Dans les trois probes d’orchestration, cela inclut un arrêt à une dépendance volontairement absente ; **l’orchestrateur ne termine pas**. Les rapports le déclarent explicitement.

## Calendrier et installation complète

Le blocage antérieur à `0x01b8441c` est levé avec un calendrier de test explicite : `2026:09:11 12:34:56`, décalage `+00:00`. Les fonctions natives réalisent la copie, le verrouillage et le formatage EXIF.

| Adresse RAM | Valeur du banc | Usage observé |
|---|---|---|
| `0x01791688` | mot initial 0 | Spinlock, écrit 1 puis 0 |
| `0x017916b0` | six octets année−2000, mois, jour, heure, minute, seconde | Calendrier en cache |
| `0x01b8441c` | octet 0 | Sélection du chemin calendrier |
| `0x01b84ff0`, `…ff2`, `…ff4` | octets 0 | Signe, heures et minutes du décalage |
| `0x01b84ff6` | octet 1 | Branche sans ajout de l’heure saisonnière |

Les autres octets de ces pages sont interdits. Les 272 cas vérifient les six champs de réglage, les chaînes aux offsets contexte `0x3120` et `0x5424`, le verrou libéré, la source calendrier inchangée, la pile et le contrôle des interruptions restaurés. Ce calendrier est un état choisi, pas une capture de boîtier.

## Objets de synchronisation créés par Fuji

`0x0004be9c` initialise en 22 instructions l’objet de 20 octets et son pointeur dans la table. Pour un identifiant `id`, les adresses observées sont :

```text
objet = 0x00063168 + 20 × (id − 1)
entrée de table = 0x0007a944 + 4 × (id − 1)
```

L’entrée choisie comporte trois mots : attribut 0, compteur initial, compteur maximal. Le constructeur natif remplit les cinq mots de l’objet et l’entrée de table. Le banc ne réutilise que ces sorties validées.

`0x000551c8` prend une unité ; `0x00051920` la restitue. Les essais couvrent les identifiants 1, 117, 118 et 250, ainsi que les compteurs vide, plein et intermédiaire. Ils vérifient aussi les retours `0`, `−50` pour la prise sans attente d’un compteur vide et `−43` pour la restitution à un compteur plein. Ce sont les valeurs natives observées, sans déclaration d’équivalence complète avec une API publique.

L’état du cœur 0 est explicite : pointeur courant opaque `0x06600000`, état système 0, mot à `0x0005b56c` nul, verrou à `0x0005b580` libre, propriétaire à `…588` égal à `0xffffffff`, profondeur à `…58c` nulle. Dans les probes de synchronisation et les premières frontières, le pointeur courant n’est pas mappé. Le probe de ressource ajoute seulement l’identité décrite ci-dessous ; aucun ordonnanceur n’est reconstitué. Les fonctions critiques `0x00048eac` et `0x00048f30` exécutent réellement leurs instructions atomiques et barrières.

## Initialisation des requêtes et orchestration

L’initialiseur `0x0219b658` termine après 27637 instructions. Il écrit le mode initial 8 et initialise ses tableaux. `0x02198fc0`, appelé avec le mode 2, termine ensuite après 18915 instructions. Ce choix est un paramètre explicite : les entrées de requête `0x32` et de réponse `0x33` de sa table contiennent chacune une ressource ; les modes voisins examinés n’en contiennent pas.

La table est sélectionnée par l’octet `0x0372d4e0`. Pour les codes supérieurs à `0x1a`, `0x0219965c` calcule :

```text
0x025d03d8 + mode × 0x5f0 + (code − 0x1b) × 20
```

Les pages `0x0372d000…0x03735fff` et `0x02f00000` commencent sans octet lisible. Le nouveau mode `write_initializes` autorise une écriture native à rendre ses seuls octets lisibles. Les instantanés transférés à la fonction suivante conservent ces plages exactes ; les trous redeviennent des témoins `CC` interdits.

L’orchestrateur utilise les objets natifs 117 et 118. Une configuration de journalisation est fournie par un pointeur à `0x017b2764`, vers une table synthétique dont seul le masque de catégorie 12, à l’offset `0x5e8c`, est lisible et vaut zéro. Le test natif du masque reste exécuté. Il s’agit d’un réglage de diagnostic, pas d’un contournement d’une erreur de développement.

Le parcours atteint `0x022365a8`, puis `0x01171388`. La première lecture de ce dernier, à `0x011713a8`, vise le pointeur du premier mot du descripteur RAW. Dans le probe de frontière, ce pointeur vaut `0x06900000` et reste volontairement non mappé. Les compteurs sont rétablis : deux cycles prise/restitution pour l’objet 117 et trois pour l’objet 118. Les verrous et le contrôle des interruptions sont restaurés au point d’arrêt.

## Lecture native du RAF utilisateur

Le format attendu par `0x01171388` correspond au bloc de métadonnées RAF : compteur d’entrées big-endian sur quatre octets, puis identifiant et longueur sur deux octets chacun, suivis de la valeur. La correspondance des tags de dimensions et de recadrage est corroborée par le [lecteur primaire de LibRaw, fonction `parse_fuji`](https://github.com/LibRaw/LibRaw/blob/master/src/metadata/fuji.cpp). LibRaw n’est pas appelé pour produire le résultat du probe natif.

Pour `DSCF2344.RAF` du X100VI : bloc à l’offset fichier 2694924, longueur 22260 octets, 16 entrées. Le lecteur X-T4 retourne 0 et produit les dix mots suivants :

```text
5196, 7872, 21, 12, 5152, 7728, 5152, 7728, 14, 42
```

Ils correspondent aux paires big-endian des tags `0x0100`, `0x0110`, `0x0111`, `0x0113` et `0x0141`. La géométrie RAW est 7872 × 5196 ; les coordonnées de recadrage sont haut 21, gauche 12. Le rôle complet de la paire `(14, 42)` n’est pas déclaré établi par ce test.

Le probe ouvre le RAF en lecture seule, refuse les placeholders iCloud, borne la taille du bloc à 1 Mio, vérifie chaque entrée et conserve les empreintes du header et du bloc. La zone témoin après les 20 octets de sortie reste intacte. **Cette lecture commune de métadonnées ne valide pas le traitement des pixels X100VI par le firmware X-T4.**

## Préparateur de ressource et message natif

`xt4-resource-probe` vérifie d’abord le lecteur de métadonnées isolé, puis relit le bloc et compare sa provenance avant réutilisation. Le bloc réel devient l’entrée en lecture seule à `0x06900000`. Les autres données du banc restent des états de test explicites, notamment :

| Champ | Valeur | Justification et limite |
|---|---|---|
| Contexte `+0x3c`, entier signé 16 bits | 1 | Propriétaire de la requête ; zéro est la sentinelle d’entrée vide de la table native |
| Contexte `+0xb80`, mot 32 bits | 1 | Première entrée réelle de la table CMOS ; ce choix ne représente pas le mode de capture du X100VI |
| TCB `0x06600000 + 0xcc`, mot 32 bits | 1 | Identifiant du thread courant ; seul ce champ du TCB est lisible |
| Table `0x0007a55c`, mot 32 bits | `0x06600000` | Correspondance de l’identifiant 1, vérifiée par la fonction native |

Les fonctions d’allocation et de recherche retrouvent elles-mêmes la ressource : aucun pointeur de travail n’est substitué. Le sélecteur `0x0219d7b4` retrouve le profil CMOS 1 dans la table de 22 entrées à `0x025e6988`, avec un pas de `0x120` octets. Ses deux mots à l’offset `0x118`, `(2, 4)`, sont copiés dans le contexte à `+0x584`.

Le préparateur `0x022365a8` retourne. Les sept mots de la ressource à contexte `+0x48` valent :

```text
0, 0, 0, 15744, 15504, 5196, 2097152
```

Les tailles sont vérifiées contre la sortie native du lecteur RAF : `2 × 7872`, `2 × (7728 + 2 × 12)` et `5196`. Les emplacements de buffers restent nuls ; aucune donnée de pixels n’entre dans le moteur.

`0x02203cc8` construit ensuite sur la pile un en-tête de 12 octets et une charge utile de 68 octets. L’en-tête indique événement `0x1219`, expéditeur 1, destination 9 et pointeur `0x0700ff58`. Les champs suivis de la charge utile sont le wrapper `0x06500000`, l’opération `0x23`, le callback `0x021d28e4` et le type 5. Le remplissage n’est pas déclaré validé.

L’expéditeur `0x0127e784` reçoit bien `R0=9`, `R1=0x0700ff9c`. Après 5792 instructions, sa lecture de configuration à `0x018ead24` provoque l’arrêt attendu, PC `0x0127e7a0`. Cette adresse appartient à la table `0x018ead04 + 4 × (destination − 1)`. **Le message n’est pas envoyé et aucun consommateur de pixels n’est exécuté.**

La suite de code observée consulte aussi un callback global à `0x017314a0` puis un allocateur. Ces observations statiques servent à rechercher les constructeurs d’objets réels ; elles ne justifient pas de remplir arbitrairement la mémoire RTOS avec des zéros.

## Reproduction et rapports

```bash
.venv/bin/python -m fuji_recipe_lab xt4-runtime-probe research/extracted/xt4-2.12 --output research/reports/runtime-replay.json
.venv/bin/python -m fuji_recipe_lab xt4-sync-probe research/extracted/xt4-2.12 --output research/reports/sync-replay.json
.venv/bin/python -m fuji_recipe_lab xt4-raw-frontier-probe research/extracted/xt4-2.12 --output research/reports/raw-frontier-replay.json
.venv/bin/python -m fuji_recipe_lab xt4-raf-metadata-probe research/extracted/xt4-2.12 "/chemin/DSCF2344.RAF" --output research/reports/raf-metadata-replay.json
.venv/bin/python -m fuji_recipe_lab xt4-resource-probe research/extracted/xt4-2.12 "/chemin/DSCF2344.RAF" --output research/reports/resource-replay.json
.venv/bin/python -m unittest discover -s tests -v
```

Rapports locaux validés : `xt4-runtime-probe.json`, `xt4-sync-probe-replay.json`, `xt4-orchestrator-probe-replay.json`, `xt4-raw-frontier-probe.json`, `xt4-raf-metadata-probe.json`, `xt4-resource-probe.json`, dans `research/reports/`. **39 tests d’infrastructure et d’API GUI passent.** Les binaires, les blocs photo et les rapports détaillés restent locaux et exclus du dépôt.

## Suite

Retrouver les initialisations de la destination 9, de ses buffers et de son consommateur, puis suivre le traitement effectif du message `0x1219`. Le descripteur doit aussi recevoir les buffers de pixels réellement attendus. Une validation native complète X100VI nécessitera son propre moteur ARM64 et ses données, ou une preuve précise de compatibilité pour chaque étape réutilisée. Pour les DNG, le CFA, la linéarisation, l’espace d’entrée et la calibration restent à adapter et à valider. Le moteur `render` demeure indisponible.
