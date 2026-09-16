# Révision 7 : exposition initiale des RAF

Le calcul d'exposition initial utilisait le film et le DR du fichier, mais omettait
ses ombres, hautes lumières et effets de couleur lors de la comparaison avec le
JPEG incorporé. Il comparait donc deux recettes différentes. La référence utilise
désormais les réglages de prise de vue importables par `shooting_settings`.
La balance des blancs déjà appliquée au RAW n'est pas réappliquée.

Cette référence reste indépendante de la recette choisie dans le GUI : déplacer
un curseur ne recalcule pas l'exposition initiale. L'export et l'aperçu partagent
toujours le même gain. Le traitement des DNG reste inchangé.

## Évaluation

Expérience : `.venv/bin/python -m scripts.evaluate_recipe_exposure`.
L'ajustement n'utilise que l'aperçu incorporé du RAF et sa recette source. Les JPEG
externes sont réservés à la mesure. Les résultats ci-dessous portent sur les jours
d'évaluation déjà utilisés précédemment, pas sur un nouvel ensemble aveugle.

| Film | Images évaluées | ΔE00 médian avant | Après | RMS luma avant → après |
|---|---:|---:|---:|---:|
| Classic Negative | 5 | 4,62 | 4,15 | 0,0618 → 0,0550 |
| Classic Chrome | 1 | 9,42 | 6,99 | 0,1145 → 0,0868 |
| ACROS | 5 | 4,19 | 3,24 | 0,0730 → 0,0618 |

Ce sont des médianes des mesures par image. L'évaluation réduit les images à
384 pixels et ajuste l'exposition à partir de leur cache ; le code de production
travaille sur l'aperçu de 1600 pixels avant réduction. Deux contrôles directs du
code intégré donnent des écarts d'estimation de 0,012 et 0,028 EV par rapport au
banc réduit (DSCF2182 et DSCF2200).

L'amélioration n'est pas universelle : le P90 ΔE00 médian de Classic Negative passe
de 7,05 à 7,35. Aucun film ne satisfait encore tous les critères de fidélité. La
correction est intégrée parce qu'elle rétablit une comparaison cohérente de la
recette source et améliore globalement l'exposition, pas comme calibration native.
La planche montre aussi des différences restantes de couleur et de grain.

[Mesures](../outputs/recipe-exposure-candidate/report.json) ·
[Comparaison JPEG / avant / après](../outputs/recipe-exposure-candidate/comparison.jpg).

## Courbe RAW expérimentale écartée

Le script `scripts/evaluate_raw_tone_candidate.py` transpose la réponse publique
mesurée dans une courbe d'exposition avant LUT, avec pivot et amplitudes déterminés
sur l'axe neutre de chaque film/DR. Il conserve des valeurs flottantes au-delà du
blanc ; il ne développe pas à partir du JPEG.

À exposition identique, l'erreur médiane Classic Negative augmente de 4,62 à 5,35,
Classic Chrome de 9,42 à 9,77 et ACROS de 4,19 à 4,52. Cette courbe n'est pas
intégrée. Le moteur conserve la courbe v6 et sa protection contre les dérives de
teinte. [Rapport de l'expérience](../outputs/raw-tone-candidate/report.json).

Validation logicielle : 101 tests réussis, dont une régression vérifiant que
l'ancrage RAF reprend la recette source sans doubler les décalages de WB.
Ces tests ne constituent pas une preuve de fidélité photographique.
