# Force des commandes Leica DNG / RAF

**Précision ultérieure de l'utilisateur :** le problème recherché est le caractère
du résultat (une apparence numérique qui persiste sur Leica), relativement à son
rendu de base. Ce n'est pas simplement l'amplitude d'un curseur ou l'écart entre
deux simulations. Les mesures ci-dessous ne réfutent pas cette observation.

Un second passage (`--films`) compare les neuf autres films à PROVIA, toujours
sur les mêmes quatre DNG et cinq RAF. La variation moyenne médiane de Classic
Negative vaut 10,68/255 sur DNG contre 13,23/255 sur RAF ; à cellules RGB communes
elle vaut 12,33 contre 12,50. Ces mesures vérifient l'application des films,
mais ne mesurent ni la qualité esthétique ni la fidélité de l'apparence Fuji.
[Planche des films](../outputs/format-response/films-comparison.jpg) ·
[Données](../outputs/format-response/films-report.json).

La normalisation Q3 43 v8 calibre seulement une luminosité d'entrée empirique.
Elle utilise la conversion couleur Leica/LibRaw, sans profil de correspondance
Leica-vers-Fuji mesuré sur des scènes identiques. Elle ne démontre donc pas que
les relations entre couleurs et les transitions de tons équivalent à celles du
Fuji avant LUT. Les rendus actuels reposent sur des LUT vidéo GFX ETERNA 55 et une
adaptation photo ; ce n'est pas une reproduction du pipeline photo X100VI.
Le prochain diagnostic doit comparer le rendu de base effectivement utilisé par
l'utilisateur avec le résultat souhaité. Augmenter toutes les amplitudes ou
ajouter du grain ne constitue pas une correction démontrée de ce problème.

L'utilisateur précise que sa référence est l'image à l'ouverture dans le GUI.
Or le GUI affiche momentanément l'aperçu incorporé, puis la recette sauvegardée
ou Classic Negative par défaut. Cette image n'est donc pas nécessairement une
base sans film. Un défaut a aussi été corrigé : les vignettes des rendus de recette
et les aperçus incorporés partageaient un cache, si bien qu'une réouverture pouvait
étiqueter un ancien rendu comme aperçu incorporé. Les caches sont séparés.
Le bouton « Voir sans film » affiche explicitement le développement neutre existant,
sans simulation ni réglages de recette, et permet de revenir à la recette.
La syntaxe JavaScript a été contrôlée avec `node --check`.

[Base RAW du GUI / Classic Negative / Classic Chrome / Eterna](../outputs/format-response/raw-base-versus-films.jpg)
sur quatre Leica et deux Fuji. La base RAW est le même rendu simple sRGB que celui
du bouton de comparaison, avec écrêtage au blanc d'affichage. Ce n'est pas un
développement Leica de référence. Ces clarifications ne résolvent pas à elles
seules la différence esthétique ressentie ; aucun coefficient du moteur n'a été
modifié dans cette étape.

La révision 8 a été contrôlée sur quatre DNG Leica Q3 43 et cinq RAF X100VI.
Toutes les images utilisent la même recette initiale : Classic Negative, DR100,
WB caméra sans décalage, exposition zéro et effets neutres. Chaque commande est
modifiée isolément. Les brouillons propres aux fichiers dans le GUI ne sont pas
utilisés. Aucun coefficient de rendu n'a été changé pendant cet audit.

Sur les images entières, les réponses moyennes diffèrent : H−2 produit une
variation RGB médiane de 5,57 niveaux sur 255 pour les DNG, contre 8,87 pour les
RAF. Color Chrome fort donne 1,17 contre 2,37. À l'inverse, FX Blue, couleur +4 et
WB R+4/B+4 ont davantage d'effet moyen sur les DNG de cet échantillon. L'impression
d'un effet plus faible peut donc se vérifier sur certaines photos et commandes,
sans être une réduction générale liée au format.

## Comparaison à couleur et luminosité proches

Les pixels du rendu initial sont regroupés dans une grille RGB de 12 × 12 × 12.
Seules les cellules ayant au moins 100 pixels de chaque format sont retenues.
Chaque cellule commune reçoit le même poids : les grandes zones de ciel ou
d'ombre d'une scène ne dominent plus la comparaison. 141 cellules sont partagées.

| Commande | Variation RGB DNG, sur 255 | Variation RGB RAF, sur 255 |
|---|---:|---:|
| H−2 | 6,51 | 6,65 |
| H+4 | 18,70 | 19,34 |
| S−2 | 2,619 | 2,621 |
| S+4 | 8,01 | 7,85 |
| DR400 depuis DR100 | 3,287 | 3,314 |
| WB R+4/B+4 | 4,84 | 4,81 |
| Color Chrome fort | 3,16 | 3,30 |
| FX Blue fort | 2,61 | 2,44 |
| Couleur +4 | 4,45 | 4,42 |

Ces chiffres mesurent un changement, pas une erreur de fidélité Fuji. Les cellules
restent grossières et les scènes sont différentes : ils ne démontrent pas une
identité entre capteurs. Ils n'appuient toutefois pas l'ajout d'un multiplicateur
général réservé aux DNG. La fonction `render` reçoit des pixels linéaires et une
recette, sans connaître le format du fichier ; sa force n'est pas réduite pour
les DNG.

Le GUI mémorise des brouillons distincts par fichier. Pour comparer manuellement,
réinitialiser la recette sur chaque photo, sélectionner le même film et partir du
même DR. La priorité de plage dynamique doit être désactivée pour tester les
commandes manuelles d'ombres et de hautes lumières.

Reproduction : `.venv/bin/python -m scripts.compare_format_response`.
[Données et fichiers testés](../outputs/format-response/report.json).
Les caches sont des aperçus RAW normalisés de la révision 8 ; il faut les régénérer
si la normalisation ou le décodeur change.
