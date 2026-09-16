# Audit sur les JPEG X100VI de l’utilisateur

## Décision

**La correspondance n’est pas assez bonne pour transférer ces ajustements aux
DNG.** Les deux modèles expérimentaux ne sont pas intégrés au moteur. Seules
les corrections certaines de lecture des réglages sont appliquées : priorité
aux MakerNotes Fuji et reconnaissance ACROS/filtres depuis Saturation.

Rapport visuel autonome : [ouvrir les comparatifs](../outputs/paired-fuji-validation/rapport.html).

## Données et méthode

Le dossier X100VI contient 810 RAF et 168 JPEG ; 791 RAF et 152 JPEG étaient
présents localement au moment de l’inventaire. 108 couples locaux partageant
leur nom de base ont été trouvés. Aucun placeholder iCloud n’a été lu, aucun
original modifié. Les JPEG des couples portent la signature X100VI 1.21/1.31 ;
date de prise de vue, ISO et temps de pose correspondent aux RAF.

Certains JPEG ont des réglages de développement différents du RAF. Les paires
où le mode, la température ou le décalage WB diffèrent sont exclues du lot de
comparaison directe. Les gains MakerNotes WBRed/WBGreen/WBBlue des couples
retenus ont aussi été vérifiés : pas d’écart supérieur à 1 %.

La sélection avant mesure limite à deux couples par journée/recette et enlève
les copies d’une même capture à recette identique. Elle donne 27 couples :
15 pour l’ajustement, 12 sur d’autres journées pour la vérification. Aucun
pixel de vérification n’entre dans l’optimisation. Deux variantes sont ensuite
évaluées sur ce lot : il s’agit d’une validation exploratoire, pas d’un nouveau
test final aveugle après choix du modèle.

Un cas, DSCF2544, utilise le téléconvertisseur numérique. Le recadrage n’est
pas correctement aligné par le recalage affine limité ; il est affiché dans
le rapport mais exclu de la synthèse couleur. Cela laisse 11 vérifications
pour les mesures couleur : 5 Classic Negative, 5 ACROS et 1 Classic Chrome.
Le dernier groupe est trop petit pour conclure à une généralisation.

Les orientations JPEG sont appliquées ; les paires sont réduites à 384 pixels
et recalées par transformation affine. Les couleurs/tons sont évalués après
un léger lissage, en excluant la bordure et les zones de luminance JPEG sous
0,03 ou au-dessus de 0,97. C’est essentiel pour que les grandes zones noires
des photos de nuit ne rendent pas artificiellement bonne la médiane.
Les défauts locaux de correction optique, de grain et de netteté ne sont pas
validés par ce protocole réduit.

## Résultats

Critères fixés pour cette étape : médiane des erreurs ΔE00 par photo ≤3,
médiane des percentiles 90 ≤6 et erreur lumineuse RMS médiane ≤0,03.
Ce sont des objectifs de travail, pas des seuils officiels Fuji.

| Film, photos de vérification | Moteur actuel ΔE00 | Essai partagé ΔE00 | Essai par film ΔE00 | P90 par film | RMS lumière par film |
|---|---:|---:|---:|---:|---:|
| Classic Negative, 5 | 4,62 | 4,01 | 3,93 | 6,43 | 0,060 |
| Classic Chrome, 1 | 9,42 | 17,37 | 8,82 | 12,18 | 0,110 |
| ACROS, 5 | 4,19 | 4,21 | 2,16 | 7,56 | 0,058 |

**Aucun film ne satisfait tous les critères.** ACROS améliore sa médiane mais
conserve des écarts visibles dans les zones moins bien reproduites.

Le moteur actuel utilise l’aperçu incorporé pour estimer l’exposition de chaque
photo. Les essais utilisent uniquement la compensation de métadonnées et une
correction apprise sur les photos d’ajustement. Le score du moteur actuel ne
doit donc pas être présenté comme celui d’un moteur sans référence par fichier.

## Ce que les essais apprennent

Six coefficients ajustent l’exposition supplémentaire, la réponse des hautes
lumières, des ombres, de la couleur, de Color Chrome et de FX Blue. Le premier
essai partage les coefficients entre films ; le second les ajuste par film.
Les paramètres poussent la réponse des ombres presque à zéro et, pour les
films couleur, Color Chrome également. Cela montre que ce modèle ne peut pas
être interprété comme une calibration fidèle de ces commandes : intégrer ces
valeurs risquerait de rendre les réglages inopérants.

Les copies JPEG retrouvées pour une même capture ont les mêmes recettes.
Le jeu ne contient donc pas les séries contrôlées nécessaires pour isoler
la réponse de chaque curseur, ni des exemples pour les sept autres LUT.
Les LUT vidéo et leur adaptateur photo conservent des écarts dépendant du film,
du niveau d’exposition et des couleurs. Un gain ou une force d’effet ne les
corrige pas de façon fiable.

Les corrections de métadonnées sont appuyées sur les balises définies par
[ExifTool FujiFilm.pm](https://github.com/exiftool/exiftool/blob/master/lib/Image/ExifTool/FujiFilm.pm) :
les valeurs EXIF standard « Hard/Soft » perdent le niveau précis de netteté,
et ACROS/son filtre sont encodés dans Saturation. L’import ne réapplique pas
la WB de prise de vue, déjà utilisée par LibRaw.

## Reproduction et suite

- `research/paired-validation/inventory.json`, `metadata*.json`, `selection.json` : provenance, réglages, inclusions/exclusions et séparation des lots.
- `.venv/bin/python -m scripts.paired_fuji_validation` : préparation/cache des couples.
- `.venv/bin/python -m scripts.fit_paired_response` : essai partagé.
- `.venv/bin/python -m scripts.fit_paired_response --per-film` : essai par film.
- `.venv/bin/python -m scripts.report_paired_validation` : rapport autonome.
- `outputs/paired-fuji-validation/candidate-fit*.json` : coefficients, mesures et limites, non utilisés par le GUI.

Pour identifier le fonctionnement des commandes, la prochaine acquisition
utile est plusieurs rendus Fuji d’un **même RAF**, avec un seul paramètre
variable : H/S à zéro puis extrêmes et intermédiaires, DR, Color/Chrome,
WB neutre puis décalages. Plusieurs scènes doivent rester à part pour valider.
Le projet n’a pas encore les bons matches demandés ; le transfert des essais
aux DNG est volontairement différé selon l’ordre demandé par l’utilisateur.

Validation logicielle : 100 tests passent, dont trois nouveaux tests sur les
MakerNotes, ACROS/filtres et l’absence de double application des décalages WB.
