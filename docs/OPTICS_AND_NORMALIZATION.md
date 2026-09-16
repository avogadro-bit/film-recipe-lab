# Corrections optiques et normalisation — septembre 2026

## Chaîne de couleur réelle

`RAW → dématriçage / balance caméra → RGB linéaire sRGB D65 float32 → normalisation d’exposition → corrections optiques facultatives → réglages de recette en linéaire → F-Gamut / F-Log2 → LUT Fuji → gamma 2,2 vers sRGB → effets de sortie / export`.

La conversion F-Gamut utilise les primaires BT.2020 ; l’encodage est **F-Log2**, pas F-Log2 C, conformément aux dix tables F-Log2 / 65Grid du manifeste. Une vérification numérique place le gris linéaire 18 % autour du code 400 sur 1023. [Documentation Fuji](https://www.fujifilm-x.com/global/support/download/technical-data/).

Cela normalise l’espace et l’encodage attendus par la LUT, pas la réponse spectrale des capteurs. Il n’y a pas de conversion en RAF ni de simulation physique du capteur ETERNA. Les matrices caméra viennent de LibRaw/DNG. Le chemin Leica Q3 43 applique sa matrice en flottant pour conserver les couleurs signées ; le chemin générique conserve de la marge lumineuse mais passe encore par la conversion entière LibRaw, susceptible d’écrêter certaines couleurs négatives.

L’exposition est adaptée séparément :

- DNG : `BaselineExposure`, lorsqu’il est présent.
- Leica Q3 43 : décalage fixe supplémentaire de +0,842182 IL, ajusté sur les références locales ; ce n’est pas une calibration couleur Fuji.
- RAF : compensation du DR de capture, puis estimation à partir de la luminosité du JPEG intégré et de sa recette reconnue.
- Autres appareils : estimation d’un gain global à partir de la luminosité de l’aperçu intégré, lorsqu’il est exploitable. Ce gain reste une estimation et peut dépendre du style JPEG du fabricant.

Aucun pixel du JPEG intégré n’est utilisé dans l’image exportée. La balance des blancs créative reste une adaptation de RGB déjà équilibré, pas un recalcul complet du profil DNG pour chaque illuminant. Une vraie standardisation colorimétrique plus poussée demanderait des profils caméra/éclairage mesurés sur une mire commune.

## Corrections optiques

Les nouveaux réglages `lens_distortion` et `lens_vignetting` valent `off` par défaut ou `auto`. Ils sont enregistrés dans les recettes JSON, appliqués avant le film et avant les recadrages, avec la même géométrie pour aperçu et export. La comparaison sans film conserve les corrections optiques choisies. Le cache RAW n’est pas modifié.

- DNG Leica Q2 et Q3 43 natifs mosaïqués : lecture du WarpRectilinear dans OpcodeList3. La première implémentation applique la géométrie radiale du plan vert à tous les canaux. Elle **ne corrige pas les aberrations chromatiques** et ne traite pas tous les opcodes DNG. Les versions inconnues, termes tangentiels, listes multiples et coefficients non inversibles sont refusés. [Spécification Adobe, chapitre 7](https://helpx.adobe.com/content/dam/help/en/camera-raw/digital-negative/jcr_content/root/content/flex/items/position/position-par/download_section_733958301/download-1/DNG_Spec_1_7_1_0.pdf).
- Autres RAW : une seule correspondance caméra/objectif Lensfun est requise. La correction est interpolée à la focale et, pour le vignettage, à l’ouverture. La distance de mise au point est supposée lointaine (1 000 m), donc le vignettage à courte distance peut rester approximatif. [API Lensfun](https://letmaik.github.io/lensfunpy/api/lensfunpy.Modifier.html).
- Les DNG linéaires/computationnels et les DNG hors périmètre validé sont exclus de l’automatisme pour ne pas ajouter une correction à une géométrie déjà transformée ou inconnue.
- Aucun remplacement par un objectif voisin : l’absence de profil est affichée et laisse les pixels inchangés. L’option « Optimisation optique Fuji » historique reste indisponible et distincte.

Le traitement conserve les valeurs HDR en flottant et rééchantillonne par bandes pour limiter la mémoire. L’orientation portrait est rétablie après traitement dans les axes du capteur. Les bords peuvent être légèrement recadrés par la mise à l’échelle de correction. Les valeurs ne constituent pas une validation du rendu propriétaire Fuji ou Adobe.

## Essais sur les fichiers réels

19 photos, 7 boîtiers, 9 configurations boîtier–objectif ; dix films testés par photo. Toutes les sorties sont finies, dimensions conservées et empreintes SHA-256 des originaux inchangées.

| Boîtier / objectif | Essai optique |
|---|---|
| Leica Q2 / Summilux 28 mm | Distorsion DNG appliquée |
| Leica Q3 43 / APO-Summicron 43 mm, quatre scènes | Distorsion DNG appliquée |
| Canon EOS R6m2 / EF 100–400 mm II, plusieurs focales | Distorsion et vignettage Lensfun appliqués |
| Canon EOS R6m2 / EF 16–35 mm III, 26 et 35 mm | Distorsion et vignettage Lensfun appliqués |
| Canon EOS R6m2 / 100–400 mm + multiplicateur 1,4× III | Profil absent ; aucune correction |
| Fujifilm X100VI / objectif intégré | Profil exact absent dans la base installée ; aucune correction |
| Panasonic S1R / Sigma 85 mm F1.2 Art 026 | Profil absent ; aucune correction |
| Phase One iXG 100MP / Schneider RS 120 mm Macro | Profil absent ; aucune correction |
| iPhone 16 Pro / caméra 6,765 mm ProRAW | DNG linéaire ; aucune correction automatique |

Deux exports JPEG corrigés pleine définition ont été relus : Leica 9 536 × 6 344 et Canon 6 022 × 4 024. Après réduction commune à 600 pixels, l’écart absolu moyen RGB linéaire aperçu/export vaut respectivement 0,00267 et 0,00241. Ce sont des contrôles de cohérence et de fonctionnement, pas des mesures d’erreur de distorsion contre une mire.

Rapports et comparatifs privés : `outputs/camera-optics-validation/`, exclus de Git. Reproduction : `python -m scripts.validate_optics_cameras /chemin/photo1.DNG /chemin/photo2.CR3 --output outputs/nouvel-essai --full-export /chemin/photo1.DNG`.
