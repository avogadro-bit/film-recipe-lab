# Entrée Leica Q3 43 — révision 8

Les DNG LEICA Q3 43 disposent d'une entrée spécifique, sans conversion en RAF.
Les RAF, Apple ProRAW et autres modèles restent sur leurs traitements précédents.
Un Q2 a été trouvé dans l'échantillon ; aucune normalisation Q3 n'est appliquée à
ce modèle sans mesures propres. Cette adaptation n'est pas un moteur Fuji natif.

## Luminosité indépendante du JPEG de chaque photo

Une sélection déterministe de 52 DNG locaux a été examinée par métadonnées.
Le banc retient 30 Q3 43 en mode Standard, répartis avant mesure en 20 images
d'ajustement et 10 images de vérification, par dossiers entiers. Les rendus Leica
stylisés et monochromes sont exclus de l'ajustement.

Le gain retenu est **+1,011500 EV**, ajouté à BaselineExposure. Il correspond à la
médiane des alignements de luma entre le développement PROVIA et les aperçus
Standard Leica du groupe d'ajustement. Les couleurs des aperçus ne servent jamais
de cibles et leurs pixels ne sont jamais incorporés au résultat.

Sur les dix images de vérification, l'écart absolu médian entre le gain fixe et
l'estimation individuelle vaut 0,064 EV ; le P90 vaut 0,142 EV. Il s'agit d'une
normalisation empirique de luminosité, pas d'une exposition physique étalonnée ni
d'une mesure de fidélité Fuji. Elle ne force pas chaque scène au même histogramme.

L'ouverture d'un Q3 43 ne dépend désormais plus du style du JPEG incorporé. La
normalisation est fixe pour le modèle, quel que soit le film sélectionné ; le
curseur d'exposition reste relatif à cette base. L'aperçu et l'export utilisent le
même gain. La base metadata et le décalage du modèle restent distincts dans les
informations de source.

## Couleurs et latitude

LibRaw décode les données capteur avec leurs niveaux noir/blanc et leur balance
des blancs. Sa matrice de conversion couleur est ensuite appliquée en virgule
flottante, avant les LUT Fuji, pour conserver les RGB négatifs hors gamut sRGB et
les valeurs supérieures au blanc. La conversion a été comparée à celle de LibRaw
sur un Q3 43 : écart moyen d'environ 0,5 unité sur 65535 dans les zones non écrêtées,
compatible avec l'arrondi de sa sortie entière. Aucun profil de couleur Fuji n'a
été ajusté à partir de photos Leica de scènes différentes.

Sources techniques :
[structures LibRaw](https://www.libraw.org/node/31),
[traitement des matrices embarquées](https://www.libraw.org/node/2320),
[code LibRaw 0.22.0 de conversion et normalisation](https://github.com/LibRaw/LibRaw/blob/0.22.0/src/postprocessing/postprocessing_utils_dcrdefs.cpp).

Les cellules Bayer contenant au moins deux échantillons à moins de 32 codes du
blanc capteur sont repérées avant dématriçage. Un masque adouci neutralise leur
chroma en conservant leur luma après conversion : cela supprime la dominante rose
observée dans les hautes lumières écrêtées. C'est une approximation conservative,
qui peut désaturer un éclairage coloré réellement saturé. Elle ne reconstruit pas
les détails perdus. Les autres hautes lumières conservent leurs couleurs et leur
latitude flottante. La réserve interne de trois EV et sa limite de précision
16 bits restent celles du décodeur existant.

## Vérifications

- 103 tests réussis, dont détection stricte du modèle, absence de dépendance au
  style de l'aperçu, conservation des RGB signés et du headroom, neutralisation
  des pixels écrêtés sans modification de leur luma.
- Quatre DNG réels : 20260621_0001, L1006259, L1004777, L1003163.
- Dix films : sorties finies ; H−2, DR400, WB R+4/B+4 modifient les pixels.
- Contrôle visuel de la planche, avant et après correction des zones roses.
- Un dématriçage pleine définition comparé à l'aperçu à 600 pixels : écart absolu
  linéaire moyen 0,00260. Les dématriçages de résolutions différentes ne sont pas
  identiques ; la normalisation d'exposition est commune.

Reproduction :
`scripts/calibrate_leica_input.py` puis `scripts/validate_leica_input.py`.
Les originaux sont lus uniquement s'ils sont présents localement.

[Mesure du gain](../outputs/leica-input/calibration.json) ·
[Vérification du moteur intégré](../outputs/leica-input/validation.json) ·
[Planche des réglages](../outputs/leica-input/controls.jpg).

La fidélité colorimétrique entre un Leica et un Fuji photographiant la même scène
n'a pas été mesurée. Les approximations existantes des films, du DR et des recettes
restent présentes. Cette étape est une adaptation d'entrée fonctionnelle, pas la
fin du projet de reproduction Fuji.
