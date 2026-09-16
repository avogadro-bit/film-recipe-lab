# Investigation du code fffw — 14 septembre 2026

Analyse du commit `bedc091e0b54a1a34aaf6929dd08e1db36d13b08`, téléchargé et examiné sans exécuter ses commandes USB. Les sources retenues et leur licence sont conservées dans `research/vendor/fffw-service/`. Leurs empreintes, liens versionnés et le désassemblage local sont dans `research/reports/fffw-service-static-audit.json`.

## Ce que cette piste apporte réellement

Le README principal est incomplet sur l'état de publication : des sources `ffun` existent. Cette observation était déjà documentée dans `RESEARCH.md`. Le composant `internal/fflz` importé par le wrapper de compression reste absent de l'arbre examiné, comme `ffem`. Les définitions X-T4 2.12 sont exploitables pour nommer tâches, actions et paramètres, mais ne constituent pas les calculs du moteur. [Sources ffun](https://github.com/tiredboffin/fffw/tree/bedc091e0b54a1a34aaf6929dd08e1db36d13b08/ffun).

## Protocole de diagnostic vérifié dans le code

La couche transport sépare commande et données, avec ouverture de session et transferts USB. La bibliothèque décrit notamment ces requêtes :

| Opération | Code principal | Sous-code |
|---|---|---|
| Taille de configuration | `0x1a0002` | 1 |
| Lecture de configuration | `0x1a0002` | 2 |
| Lecture de journal | `0x200001` | 1 |
| Lecture mémoire | `0x200001` | 2 |

La requête mémoire place l'adresse et la longueur dans les deux derniers mots de ses 16 octets de paramètres. Elle attend les paramètres retournés avant les données. Cela fournit une signature pour retrouver le gestionnaire dans le firmware, pas une preuve d'accès aux registres matériels X-T4. [ffjlib.py](https://github.com/tiredboffin/fffw/blob/bedc091e0b54a1a34aaf6929dd08e1db36d13b08/ff80/ffjlib.py).

Le wrapper `ram read` peut écrire temporairement le réglage de diagnostic `cfgdata[0xf7]`, puis le restaurer. Il ne faut donc pas qualifier cette commande de strictement passive. Aucun appel n'a été effectué sur un boîtier. [cmd.py](https://github.com/tiredboffin/fffw/blob/bedc091e0b54a1a34aaf6929dd08e1db36d13b08/ff80/ff80_cmd/cmd.py).

## Résultat nouveau dans notre firmware local

L'analyse du module A X-T4 2.12, contrôlé par SHA-256 et par son adresse d'en-tête, identifie :

- Table ROM `0x1587714` : 16 adresses consécutives, `0xff70f000` à `0xff70f03c`.
- Table de masques autorisés `0x15877cc` : le masque de l'index 15 est `0x7ff`.
- Accesseur de modification `0x11bfb70` : contrôle l'index, charge adresse et masque, appelle `0x11bfac4`.
- Accesseur de lecture `0x11bfbb0` : contrôle l'index et le pointeur de sortie, appelle `0x5aa38`.
- Modification `0x11bfac4` : valide le masque demandé, lit le registre, applique OR si l'action vaut 1, sinon BIC, puis appelle `0x5a9f0`.

Ces faits complètent le blocage natif déjà observé : effacement demandé du masque `0x7` à `0xff70f03c`. Ils ne donnent ni valeur de réinitialisation, ni effets des bits, ni règle d'accès matériel. Le nom du périphérique reste inconnu. Aucun registre fictif n'a été ajouté à l'émulateur.

La recherche de constantes du protocole dans les segments décompressés n'a pas suffi à identifier le gestionnaire de service. Plusieurs occurrences sont des données sans rapport apparent ; une simple correspondance numérique ne prouve pas une fonction.

## Suite précise

1. Retrouver les appelants des deux accesseurs ci-dessus pour déterminer les usages de chaque index et les séquences d'initialisation.
2. Identifier le gestionnaire USB de service par sa structure de dispatch, puis vérifier si ses lectures couvrent RAM seulement ou aussi MMIO.
3. Rechercher des captures publiques correspondant exactement au modèle, firmware et état d'exécution. Une photographie JPEG ou un dump pris après démarrage ne fournit pas automatiquement la valeur du registre au démarrage.

L'exécution des pixels, l'intégration des recettes dans l'aperçu et l'adaptation DNG restent inachevées. Cette investigation fournit des repères vérifiables, sans démontrer encore un moteur portable.

## Décision après suivi des appelants

Le relevé statique des instructions ARM `b`/`bl` dans les modules A et B, contrôlés par SHA-256, trouve 33 sites visant les deux accesseurs ou leur primitive commune. Le rapport `research/reports/xt4-register-callers-static.json` conserve les instructions précédant chaque site. Ce relevé ne couvre pas les appels indirects, les autres segments ou d'autres modes d'instructions.

Les appelants observés choisissent des index et masques constants ou les chargent depuis des tables. Par exemple, `0x11bb664` vise l'index 13 avec le masque `0x400`; `0x121d2e4` et `0x121d2f4` visent l'index 3 avec les masques `2` et `0x80`. Aucune valeur de réinitialisation ni description des effets du périphérique n'est établie par cette analyse.

Décision : arrêter cette piste comme moyen autonome d'aboutir au moteur exact. Ce n'est pas une preuve d'impossibilité de l'émulation ; c'est un constat d'insuffisance des éléments disponibles. Continuer à franchir les arrêts en inventant les réponses matérielles ne répondrait pas à l'objectif.

Alternative recommandée : recherche instrumentée avec un boîtier du modèle et firmware étudiés, ou collaboration avec un chercheur disposant déjà des captures correspondantes. Demander d'abord si existent une cartographie MMIO, des traces horodatées de la séquence d'initialisation et des paires entrée/sortie intermédiaires du traitement RAW. Un simple dump RAM après démarrage ne remplace pas ces informations. Aucun contact externe n'a été effectué.

Un boîtier de recherche serait nécessaire pendant le développement seulement si les données ne sont pas déjà disponibles. L'autonomie du logiciel final demeure un objectif non démontré. Les RAF X100VI nécessitent ensuite leur propre validation ; le DNG exige une définition de l'entrée adaptée et ne peut pas avoir une référence « JPEG natif Fuji de la même capture » pour un capteur tiers.
