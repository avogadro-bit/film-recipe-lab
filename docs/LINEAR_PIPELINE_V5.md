# Révision 5 — latitude des réglages et luminosité initiale

Les versions précédentes ajustaient ombres/hautes lumières après la LUT. Des
valeurs différentes déjà écrêtées par le film ne pouvaient plus être distinguées.
Le décodage LibRaw standard pouvait également écrêter des canaux après balance
des blancs, avant même l’application de l’exposition.

## Chaîne actuelle

1. Décodage avec réserve de trois IL : `user_sat = black + 8*(white-black)`,
   `adjust_maximum_thr=0`, balance du fichier et sortie linéaire sRGB 16 bits.
   L’échelle ×8 est restaurée en flottant ; les valeurs >1 restent présentes.
2. Compensation de métadonnées, puis estimation d’un gain d’exposition global
   depuis l’aperçu incorporé. Le gain est indépendant de la recette sélectionnée.
3. Balance des blancs de recette et exposition.
4. Ombres/hautes lumières dans le domaine d’exposition logarithmique, autour
   du gris linéaire à 18 %. Les courbes sont monotones, raccordées à pente 1,
   et préservent les rapports RGB. Pour les valeurs négatives, une passe locale
   guidée par les contours restaure ensuite le contraste que la compression a
   retiré aux zones lumineuses ou sombres, sans inventer de texture.
5. Compression DR, puis LUT officielle, puis effets couleur et détails.
6. Encodage JPEG/TIFF. La priorité DR pilote les courbes linéaires automatiquement.

La réserve est créée avant la normalisation WB et la conversion RGB, décrites
par [le code LibRaw](https://github.com/LibRaw/LibRaw/blob/master/src/postprocessing/postprocessing_utils_dcrdefs.cpp).
Sur le Leica Q3 43 testé, le décodage avec réserve retrouve des valeurs jusqu’à
2,66 avant exposition. Sur les canaux non écrêtés, le rapport médian entre les
anciens et nouveaux niveaux est de 0,995 : la réserve ne doit pas constituer
une correction d’exposition cachée.

**Limites :** le traitement interne LibRaw reste entier 16 bits. Réserver trois
IL réduit la précision de quantification des très faibles valeurs. Les noirs
et les valeurs négatives hors gamut sRGB ne sont pas conservés ; les détails
saturés dans le capteur ne sont pas reconstruits. Cette évolution augmente la
latitude disponible mais ne constitue pas un moteur flottant natif Fuji, ni
une prise en charge complète des gain maps Apple ProRAW.

## Exposition initiale estimée

La valeur BaselineExposure DNG ne suffisait pas : elle vaut zéro dans le Leica
qui apparaissait sombre. On estime désormais un décalage global supplémentaire
entre −3 et +3 IL, en comparant les quantiles de luminance d’un rendu réduit et
de l’aperçu incorporé. Les extrêmes noirs/blancs sont exclus. Il ne s’agit pas
d’une normalisation de toutes les scènes vers un gris moyen : un aperçu
volontairement sombre reste une référence sombre.

Le film de référence est celui identifié dans les métadonnées RAF, sinon PROVIA.
Pour les DNG, PROVIA sert de référence approximative. Les différences de courbes,
profils couleur et traitement local du JPEG influencent l’estimation : ce gain
n’est ni une mesure photométrique ni une calibration du boîtier. Les pixels de
l’aperçu ne sont jamais utilisés pour fabriquer les pixels exportés.

Le GUI affiche « Base estimée +… IL ». La valeur inclut les métadonnées et le
gain estimé. L’exposition de recette reste relative à cette base. En l’absence
d’aperçu exploitable, seules les métadonnées sont utilisées. La même estimation
issue du décodage réduit est utilisée pour le développement pleine résolution ;
cache indexé par chemin, date de modification et taille, deux fichiers maximum.

| Fichier contrôlé | Métadonnées | Ajustement estimé supplémentaire |
|---|---:|---:|
| Leica 20260621_0001.DNG | 0 IL | +1,128 IL |
| Fuji DSCF2344.RAF | +2 IL | +1,185 IL |
| iPhone IMG_4768.DNG | +4,255 IL | −0,005 IL |

Ces résultats sont propres aux fichiers testés. Ils ne prouvent pas une
correspondance générale avec leurs JPEG. Les recettes enregistrées auparavant
conservent leurs valeurs, mais leur rendu change avec cette nouvelle chaîne.

## Validation

95 tests passent : compensation unique aperçu/export, estimation d’exposition
sur cas synthétiques clairs/sombres, absence de référence exploitable, monotonie,
rapports RGB et récupération d’une gradation avant une LUT écrêtante simulée.
Les valeurs zero et les dix LUT originales restent vérifiées séparément.

Les contrôles sur photos sont dans `outputs/linear-v5/report.json`,
`comparison.jpg` et `additional-dng-checks.json`. Il s’agit d’un audit du
fonctionnement et des rendus, pas d’une validation de fidélité Fuji.

Contrôle élargi : trois autres Leica DNG (L1006259, L1004777, L1003163)
reçoivent respectivement +1,443, +0,956 et +1,015 IL supplémentaires estimés.
Sur IMG_4768.DNG, comparaison du décodage aperçu et pleine résolution après
réduction à 600 pixels : mêmes dimensions, différence absolue linéaire moyenne
0,000153. Cinq DNG et un RAF ont été contrôlés au total.
Le GUI a été vérifié sur le Leica : base estimée +1,13 IL et rendu effectif.
