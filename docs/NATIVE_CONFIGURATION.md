# Configuration du DAT et initialisation WB — 13 septembre 2026

**Les 36 coefficients de décalage WB du firmware X-T4 2.12 sont retrouvés et utilisés par le code natif. La chaîne RAW dépasse les anciens arrêts de configuration et de remplissage WB. Aucun pixel n’est encore rendu.** Ces données viennent du DAT Fuji ; elles ne constituent pas un dump de calibration d’un exemplaire de boîtier ni une calibration X100VI.

## Provenance du bloc de configuration

`0x01263f40` installe le pointeur cfgdata à `0x045e8000`. Le chemin de secours demande à `0x01264db8` les premiers `0x72000` octets de configuration. Cette routine calcule le bloc de départ `6`, avec des blocs de `0x20000` octets, soit l’offset flash `0xc0000`. Le lecteur `0x01264250` convertit les blocs en octets et `0x0126420c → 0x011a6dc8` ajoute la base flash `0xf0000000`.

Le banc vérifie deux frontières natives **avant les appels de stockage** : bloc 6, trois blocs entiers et destination choisie ; puis adresse flash `0xf00c0000` et taille `0x60000`. Il n’exécute pas le transfert matériel, ni le reliquat de `0x12000` octets. L’étendue complète de `0x72000` est l’argument du chargeur identifié.

À cet offset de `main.bin`, le DAT contient le marqueur `55 aa` attendu à `+0x202`, les tables de gains et les paramètres employés par le parcours WB. Le chargement exige le SHA-256 complet du segment principal et celui de la tranche :

```text
main.bin : ac1c4a4f40d7eac89ca58662dbbabd1256402fb2d89df436872be61c36273442
tranche  : 4b9d1113af1fc914fa2055df1087ffc665585aecf27116c50debd47eee56e643
offset   : 0xc0000
taille   : 0x72000
```

Le lecteur Fuji confirme le marqueur `0xaa55`, le paramètre `0xfeb0 = 15`, le paramètre `0xa8 = 0` et le masque de diagnostic `0x5e8c = 0`. Les pages importées sont en lecture seule, avec leur propre hash. L’intervalle de configuration `0x72000…0x4bffff` demeure inconnu : il n’est pas rempli de zéros.

La petite table à `0x0167793c`, appliquée par `0x01263b2c` lorsque les autres sources sont invalides, contient 143 entrées aux offsets `0x100…0x3a1`. Elle ne fournit pas les coefficients WB ; ce n’est pas la source utilisée ici.

Les notes de fffw décrivent cfgdata comme une zone chargée au démarrage et dont l’organisation varie selon le modèle. Les adresses et valeurs X-T4 ci-dessus proviennent de l’analyse locale du firmware, et non d’une transposition des exemples de ce wiki. [Source primaire de contexte](https://github.com/tiredboffin/fffw/wiki/Route-0xff80#settings-cabinet).

## Coefficients réellement utilisés

`xt4-cfg-probe` exécute `0x022a7cf4` pour **les 361 couples rouge/bleu de −9 à +9**. Chaque coefficient non neutre est lu directement dans la tranche vérifiée ; le décalage zéro conserve l’unité Q10 produite par le code Fuji. Le banc vérifie aussi les adresses de chaque lecture, le retour, la restauration de pile et les six octets de sortie.

Les 361 cas passent. Ils complètent les 251 essais antérieurs sur données synthétiques, utiles pour vérifier séparément les multiplications et arrondis avec des valeurs non uniformes. Ils ne remplacent pas une comparaison d’images avec un boîtier.

Rapport : `research/reports/xt4-firmware-configuration-validated.json` : 367 cas (361 combinaisons, quatre lectures de paramètres, deux frontières d’adressage), plus les vérifications BSS suivantes.

## Remplissage WB expliqué par le démarrage

Le segment principal contient une table à l’offset fichier `0x140000`, dont les pointeurs sont relatifs à l’adresse mémoire `0x00e20000`. Le code `0x01290fb8` référence directement cette adresse et retrouve l’enregistrement du module 6 à `0x00e2013c` :

| Champ | Valeur |
|---|---|
| Adresse du module | `0x01e0f000` |
| Taille chargée | `0x900000` |
| Début BSS | `0x0270f000` |
| Taille BSS | `0x126a000` |
| Offset flash du module | `0x5c0000` |

Le chargeur `0x012648ac` tente une remise à zéro par DMA. Son chemin logiciel de secours à `0x01264a90` charge le début et la taille BSS depuis cet enregistrement puis appelle `0x01281a40` avec la valeur zéro. Le banc exécute la recherche d’enregistrement et la préparation de ces arguments natifs.

Pour limiter l’émulation, il exécute ensuite **la même fonction native de remplissage sur la seule page `0x0288d000`**, comprise dans cette plage. Les 4096 octets sont écrits à zéro, en 3091 instructions, avec pile restaurée. Il transfère seulement l’octet `0x0288d207` au parcours RAW ; les onze champs utiles restent initialisés par leurs écritures natives habituelles.

**C’est une dérivation de l’état à froid depuis le chemin BSS, avec exécution d’une sous-plage. Le démarrage complet, le choix effectif du repli DMA et la totalité de la plage de `0x126a000` octets ne sont pas émulés.** Le rapport conserve explicitement cette portée.

## Nouveau parcours RAW

Les variantes restent distinctes et reproductibles :

| Variante | Instructions du destinataire | Arrêt validé |
|---|---:|---|
| Référence sans configuration | 6735 | Lecture absente de `cfgdata[0xfeb0]` |
| Page de configuration du DAT | 7027 | Octet final WB inconnu lors du `LDM` |
| Configuration et remplissage BSS dérivé | 7273 | Lecture de l’état global `0x0190d784`, PC `0x01294d80` |

La dernière variante effectue la copie des douze octets vers `0x0288cec8`, lit le paramètre de diagnostic `0xa8` depuis le DAT, puis entre dans `0x022a830c`. Elle bloque dans la chaîne `0x022a8018 → 0x012f20d8 → 0x012638d0 → 0x01294d70`, avant la lecture du nombre d’entrées à l’offset `0x420f82`. Ce dernier offset dépasse le préfixe retrouvé. Aucune valeur hypothétique n’est fournie pour franchir ces deux dépendances.

Les gains du contexte RAW sont encore des entrées de banc, et aucun buffer de pixels n’est alimenté. `passed` valide l’arrêt attendu, les copies, le transport et les états suivis ; il ne signifie pas qu’un développement a terminé.

Rapports : `xt4-receiver-firmware-config.json`, `xt4-receiver-native-wb-boot-validated.json` et `xt4-receiver-configuration-regression.json` dans `research/reports/`.

## Reproduction

```bash
.venv/bin/python -m fuji_recipe_lab xt4-cfg-probe research/extracted/xt4-2.12 --output research/reports/config-replay.json
.venv/bin/python -m fuji_recipe_lab xt4-resource-probe research/extracted/xt4-2.12 '/chemin/photo.RAF' --with-receiver --firmware-config --boot-wb --output research/reports/wb-boot-replay.json
```

`--firmware-config` exclut `--cfg-feb0`, et `--boot-wb` exige `--firmware-config`. Les rapports existants sont immuables. Aucun fichier photo, réglage du boîtier ou comportement de rendu de l’interface n’est modifié.

La suite consiste à retrouver l’initialisation du global `0x0190d784` et de la configuration étendue, puis les buffers RAW et le traitement effectif des pixels. La compatibilité X100VI et l’entrée DNG restent à valider.

## Suite : bloc DEFAULT retrouvé

Le bloc demandé à `0x420000` a depuis été identifié dans le DAT et copié par la primitive native. Le lecteur de nombre d’entrées retourne, puis le gestionnaire WB termine. La prochaine frontière est une réservation RAW manquante, de type `0x2f`. [Provenance, modes d’accès et nouveaux contrôles](NATIVE_DEFAULT.md).
