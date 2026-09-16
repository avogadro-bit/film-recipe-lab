# LUT officielles du GFX ETERNA 55

**Version actuelle : [audit et correction gamma / Leica v9](CLASSIC_NEGATIVE_LEICA_V9.md).**
Les révisions décrites ci-dessous sont historiques.


Mise à jour : [compensation de luminosité au chargement et réponse DR/Chrome v3](RESPONSE_V3.md).

Le GUI utilise maintenant dix LUT 65³ originales et inchangées du pack Fujifilm
GFX ETERNA 55 v1.10 : PROVIA, Velvia, ASTIA, Classic Chrome, Classic Negative,
PRO Neg. Std, ETERNA, ETERNA Bleach Bypass, REALA ACE et ACROS.
Les anciens filtres artistiques de ces dix films sont remplacés, y compris
pour les recettes déjà mémorisées. Le menu les marque « Fuji LUT ».
PRO Neg. Hi, Nostalgic Negative, Monochrome et Sépia restent des interprétations
explicitement identifiées, car absentes de ce pack. WDR-709 et FLog2-709 sont
des conversions techniques, pas des simulations de film ; elles ne sont pas
ajoutées au menu des films.

## Pipeline photo

1. LibRaw dématrice le RAF/DNG en RGB sRGB linéaire, balance du fichier appliquée.
2. Exposition, balance relative et adaptation de dynamique de la recette.
3. Matrice sRGB linéaire vers F-Gamut (primaires BT.2020, blanc D65).
4. Encodage F-Log2 selon les constantes du document Fujifilm v1.1. Aucune
   compression vidéo supplémentaire des niveaux numériques n’est appliquée.
5. Interpolation trilinéaire dans la LUT officielle 65³, rouge variant le plus
   rapidement dans le fichier .cube. Traitement par bandes pour limiter la RAM.
6. Depuis v9 : sortie Rec.709 / D65, gamma **2,2** selon le livre blanc GFX
   ETERNA 55 v1.01 page 13, réencodée en sRGB pour le navigateur et les exports ICC.
   L’hypothèse gamma 2,4 des versions précédentes est abandonnée.
7. Réglages photographiques indépendants : tons, couleur, grain, détails,
   recadrage. Aucun ancien contraste ou virage couleur du film n’est superposé.

Les filtres couleur ACROS sont des préfiltrages artistiques avant la LUT ; le
pack ne contient pas les variantes ACROS R/Ye/G. À réglages par défaut, le rendu
est exactement celui de notre adaptateur + LUT, sans correction artistique.

## Provenance et limites

Les fichiers sont dans `fuji_recipe_lab/luts/`, accompagnés d’un manifeste avec
les noms originaux et SHA-256. Le chargement vérifie leur intégrité ; une LUT
manquante ou modifiée provoque une erreur, sans substitution silencieuse.
Ils restent attribués à FUJIFILM ; leur téléchargement public n’est pas présenté
comme une licence de redistribution du pack.

- Pack officiel : https://dl.fujifilm-x.com/support/lut/gfx-eterna-55-3d-lut-v110.zip
- Catalogue : https://www.fujifilm-x.com/global/support/download/lut/
- Formule et primaires : https://dl.fujifilm-x.com/technical-data/F-Log2_DataSheet_E_Ver.1.1.pdf
- Notice fournie dans l’archive : `F-Log2_LUT_overview_Ver.2.1E.pdf`.

Ce moteur utilise bien des tables Fuji officielles, mais ce n’est pas le moteur
JPEG photo du X100VI. L’exposition relative issue de LibRaw n’est pas calibrée
en réflectance de scène, la conversion initiale sRGB peut perdre des couleurs
hors gamut, et les DNG ont leur propre réponse capteur. Les effets de recette,
les réglages DR et les traitements locaux Fuji ne sont pas reproduits exactement.
La fidélité aux JPEG Fuji n’a pas encore été mesurée.

## Validation

80 tests réussis : points de référence F-Log2 0 %, 18 %, 90 %, matrice conservant
le blanc, ordre des axes et interpolation, intégrité des dix tables, absence de
superposition artistique aux réglages par défaut, exposition avant écrêtage,
réponse des filtres ACROS, ainsi que les tests existants de rendu/export/GUI.

30 aperçus produits sur un Leica DNG, un Apple DNG et un RAF X100VI.
Planches et mesures : `outputs/official-lut-studio/`.
Export réel RAF en TIFF 16 bits pleine définition, profil ICC vérifié :
`RAF-classic-negative-official.tif`. Ces tests valident le fonctionnement de
l’intégration ; ils ne mesurent pas une équivalence au JPEG du boîtier.
