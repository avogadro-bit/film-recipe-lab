# Classic Negative sur Leica Q3 43 — audit et correction v9

La LUT officielle suffit à appliquer le look vidéo publié par Fuji **si son entrée
et son affichage sont corrects**. Elle ne contient pas le développement RAW du Leica,
ni l'ensemble du moteur JPEG photo Fuji. Cette révision corrige un point documenté
et recalcule l'exposition Leica qui en dépend. Elle ne prétend pas résoudre à elle
seule le caractère « trop numérique » signalé par l'utilisateur.

## Correction intégrée

Le [livre blanc GFX ETERNA 55 v1.01, page 13](https://dl.fujifilm-x.com/support/lut/GFX_ETERNA_WhitePaper_260206_v101.pdf)
recommande Rec.709, D65 et **gamma 2,2** pour regarder les LUT. L'adaptateur utilisait
une hypothèse gamma 2,4. Il convertit désormais les codes de sortie de la LUT depuis
gamma 2,2 vers sRGB, utilisé par le navigateur et les exports ICC. Il ne faut pas
confondre ce gamma d'affichage avec la formule F-Log2 en entrée.

La recommandation concerne le pack entier : correction commune aux dix LUT, avec
validation ciblée Classic Negative. Les fichiers .cube et leurs empreintes restent
inchangés. Ni filtre abpy, ni renforcement artistique supplémentaire n'est ajouté.

La compensation fixe du Q3 43 passe de **+1,011500 à +0,842182 EV**, en plus du
BaselineExposure DNG. Elle a été recalculée avec le décodage flottant actuel :
20 DNG dont l'aperçu Leica est Standard servent à l'estimation ; 10 DNG de dossiers
réservés à l'évaluation servent au contrôle. Sur ces derniers, l'écart absolu médian
à leur exposition estimée individuellement est **0,060 EV**, P90 **0,132 EV**.
Les aperçus stylisés et monochromes ne servent pas à cet ajustement. Aucun pixel
JPEG n'entre dans le rendu. Cela règle la luminosité initiale, pas la colorimétrie
physique du capteur. Les autres modèles Leica n'ont pas ce profil Q3 43.

## Contrôle sur tes fichiers Fuji

Les mêmes recettes et le même principe d'ancrage d'exposition à l'aperçu embarqué
sont utilisés avant/après. Les JPEG séparés servent uniquement à l'évaluation.
Sur les cinq couples Classic Negative de contrôle, la médiane des mesures par image :

| Mesure | v8 / gamma 2,4 | v9 / gamma 2,2 |
|---|---:|---:|
| ΔE00 médian | 4,153 | 3,851 |
| ΔE00 P90 | 7,347 | 6,991 |
| Erreur RMS luma | 0,0550 | 0,0516 |

Les cinq images s'améliorent : DSCF2182, DSCF2200, DSCF2401 copie, DSCF2402 copie et
DSCF2546. Les seuils de fidélité du projet restent non atteints. Ces images ont déjà
été examinées lors des essais précédents : ce n'est pas un nouvel essai aveugle.
Leurs recettes comprennent DR, tons et Chrome ; les chiffres évaluent donc toute
la chaîne, pas la LUT isolée. DSCF2544 reste exclu pour mauvaise correspondance géométrique.

## Pistes évaluées, non intégrées

- **F-Gamut / F-Log2 :** la matrice sRGB linéaire → BT.2020 correspond aux primaires
  officielles à 1,9×10⁻⁸ près ; les valeurs de référence 0 %, 18 % et 90 % sont
  correctement encodées. Aucun motif de modifier cette transformation.
- **LUT F-Log2 C Classic Negative :** test avec ses propres primaires F-Gamut C,
  la même courbe Log et gamma 2,2. Sur les images Fuji d'apprentissage, ΔE médian
  3,716 → 3,681 ; sur le contrôle, 3,851 → 4,010. Pas de bénéfice généralisé démontré :
  la version F-Log2 actuelle est conservée. Les deux chemins ne sont pas interchangeables
  en réutilisant la même matrice de gamut.
- **Matrices DNG sous deux illuminants :** prototype d'interpolation A/D65 selon
  AsShotNeutral, température corrélée et adaptation Bradford. Sur 30 Leica Standard,
  comparaison à luminance ajustée par image : ΔE médian d'apprentissage 3,325 → 3,502,
  contrôle 3,414 → 3,689. Ce JPEG Leica n'est pas une cible colorimétrique ; ces valeurs
  ne réfutent pas le principe DNG, mais ne justifient pas de remplacer notre conversion.
  Le prototype utilise une table CCT limitée à l'intervalle A/D65, ignore les profils
  avancés et teste des caches antérieurs avec écrêtage des valeurs négatives : recherche
  uniquement, pas un lecteur DNG universel ou une preuve d'équivalence au SDK Adobe.
- **Exemples du livre blanc :** image Log et Classic Negative extraites en JPEG 8 bits,
  même scène visuellement. Les essais de niveaux vidéo/complets et gamma ne retrouvent
  pas précisément le rendu publié (meilleur ΔE médian ~5,17 avec la LUT F-Log2 C).
  La chaîne de fabrication du PDF n'est pas documentée : pas d'ajustement de couleurs
  appris sur ces illustrations. Leur correspondance géométrique n'a pas été mesurée.
- **Profil abpy / variante hybride précédente :** rejetés par l'utilisateur, non intégrés.

## Résultat Leica et portée

[Comparatif de quatre scènes](../outputs/classic-negative-adapter/comparatif-leica.jpg) :
base RAW sans film, ancienne version, version corrigée. Les JPEG séparés 1600 px sont
dans le même dossier. La différence avant/après reste **modeste** : ΔE médian entre
0,61 et 1,11 selon la scène. Ce chiffre mesure le changement, pas la ressemblance à Fuji.
Il serait trompeur de présenter cette correction comme une métamorphose du look.

Les hautes lumières, ombres, DR400 et WB R4/B4 ont été appliqués aux quatre scènes :
valeurs finies et modification effective des pixels. Les 104 tests du projet passent,
y compris le contrôle numérique gamma 2,2 et les garde-fous RAW/exports.
Le serveur du GUI a été redémarré en révision 9 : deux appels HTTP sur L1004777
produisent des JPEG 1600 × 1064 lisibles (défaut et hautes lumières −2), avec
un écart moyen de 4,27 niveaux RGB / 255. Le rendu H−2 a été inspecté visuellement.

Pour identifier une correction couleur spécifiquement Leica → Fuji, il manque encore
une cible commune : même scène ou même mire sous un éclairage connu, avec profil de
référence défini. Les scènes non appariées permettent de tester le pipeline, mais pas
de déduire une matrice capteur exacte. Des modifications de saturation arbitraires
pourraient donner davantage de caractère sans établir une meilleure fidélité.

## Reproduction et provenance

- `scripts/audit_official_classic_negative.py` : illustrations, niveaux, matrices, empreintes.
- `scripts/leica_color_candidate.py` : prototype DNG non intégré.
- `scripts/calibrate_leica_gamma22.py` : recalcul sur les 30 décodages flottants locaux.
- `scripts/compare_classic_negative_gamuts.py` : chemins officiels F-Log2 / F-Log2 C.
- `scripts/export_leica_adapter_comparison.py` : quatre comparatifs et contrôle des réglages.
- `outputs/classic-negative-adapter/raf-gamma22/report.json` : contrôle des paires Fuji.
- `outputs/classic-negative-adapter/leica-gamma22-calibration.json` : exposition Leica.

Le rapport RAF a été produit avec `scripts.evaluate_recipe_exposure.main()` en fixant
son `OUT` à `Path('outputs/classic-negative-adapter/raf-gamma22')` ; sa rubrique
`baseline` désigne l'historique v6. La comparaison v8 ci-dessus provient de la rubrique
`candidate` de `outputs/recipe-exposure-candidate/report.json`, sans mélanger les versions.

Sources : [pack Fuji v1.10](https://dl.fujifilm-x.com/support/lut/gfx-eterna-55-3d-lut-v110.zip),
[formule F-Log2 v1.1](https://dl.fujifilm-x.com/technical-data/F-Log2_DataSheet_E_Ver.1.1.pdf),
[documentation DNG Adobe](https://helpx.adobe.com/camera-raw/desktop/dng-and-file-formats/digital-negative.html).
Les originaux photo restent inchangés ; seuls les fichiers présents localement sont lus.
