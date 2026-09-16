# Révision 3 — luminosité initiale, DR et Color Chrome

## Luminosité au chargement

Le décodage linéaire `no_auto_bright=True` était utilisé sans compensation
liée au fichier. La même correction est désormais appliquée en flottant à
l’aperçu et à l’export, avant les réglages et la LUT :

- DNG : `2**BaselineExposure`, lorsqu’indiqué. Aucun cumul avec les MakerNotes
  Fuji d’un DNG converti. `BaselineExposureOffset` n’est pas appliqué car il
  appartient au profil DNG, que ce moteur n’utilise pas.
- RAF : compensation +1 IL pour une prise de vue DR200, +2 IL pour DR400,
  d’après `DevelopmentDynamicRange`. Aucun gain supplémentaire sans information.
- Le curseur d’exposition reste indépendant, à zéro par défaut. Le GUI indique
  `Base +… IL` près du modèle et des dimensions. Les anciens brouillons restent
  conservés : réinitialiser la recette pour tester les valeurs par défaut.

[Fujifilm décrit la sous-exposition de capture et la remontée au développement](https://www.fujifilm-x.com/en-gb/learning-centre/boost-dynamic-range-in-your-images/).
La définition de BaselineExposure figure dans la spécification DNG publiée par
[Adobe](https://helpx.adobe.com/ca/camera-raw/desktop/dng-and-file-formats/digital-negative.html).
Le chemin de traitement [LibRaw dcraw_process](https://github.com/LibRaw/LibRaw/blob/master/src/postprocessing/dcraw_process.cpp)
ne fait pas cette normalisation d’exposition de base.

Fichiers locaux contrôlés, en lecture seule :

| Fichier | Compensation |
|---|---:|
| Leica Q3 43, 20260621_0001.DNG | 0 IL (BaselineExposure=0) |
| X100VI, DSCF2344.RAF | +2 IL (DR400) |
| iPhone 16 Pro, IMG_4768.DNG | +4,2547 IL (BaselineExposure) |

Le portrait RAF reste plus sombre que son JPEG incorporé après cette correction.
Le point gris par caméra/ISO, les courbes natives et l’adaptation des LUT vidéo
aux photos ne sont pas calibrés. `RawExposureBias=-2.7` n’est pas inversé puis
ajouté aveuglément au DR : cela risquerait de compter la même compensation deux
fois. Le DNG Leica n’est pas éclairci arbitrairement ; son aperçu monochrome
contrasté ne fournit pas une référence isolant l’exposition. Les gain maps et
le traitement local Apple ProRAW restent absents.

Comparatif visuel : `outputs/brightness-dr-audit/baseline-comparison.jpg`.
Il oppose JPEG incorporé, ancien rendu et compensation de métadonnées, avec
Classic Negative par défaut. Les recettes du JPEG et du développement peuvent
être différentes : ce n’est pas une mesure de fidélité.

## DR100 / 200 / 400

La courbe précédente assombrissait trop les hautes lumières : un gris linéaire
à 4 descendait à 0,622 en DR400, avant même la LUT. La nouvelle courbe préserve
les valeurs jusqu’à 18 %, reste continue avec une pente de 1 au raccord, puis
ramène un blanc à 2 (DR200) ou 4 (DR400) à 1. Cela représente respectivement
une et deux valeurs d’exposition supplémentaires à comprimer.

Cette courbe est une approximation mathématique, pas une courbe mesurée dans
X RAW STUDIO. Elle ne recrée pas les détails perdus à la capture ou écrêtés
par le décodage sRGB. La compensation du DR de prise de vue reste fixe : changer
le menu DR de développement ne l’applique pas une seconde fois.

## Color Chrome

La révision 2 ajoutait de la chroma jusqu’à écrêter des canaux dans les couleurs
très saturées. La révision 3 fait décroître cet ajout à proximité de la limite
de saturation et limite la chroma pour rester dans le gamut sans écrêtage
indépendant des canaux. Les paramètres sont réajustés sur la même scène Fuji ;
la seconde scène X100V reste réservée à l’évaluation. FX Blue reste inchangé.

| Erreur RGB moyenne absolue (0–1) | v2 | v3 |
|---|---:|---:|
| Scène Fuji, pixels réservés | 0,010971 | 0,011036 |
| Scène X100V indépendante | 0,004321 | 0,004150 |

L’erreur globale est presque inchangée ; le bénéfice porte sur l’extrapolation
aux couleurs très saturées, pas une prétendue amélioration universelle.
La borne du paramètre de chroma est atteinte lors du fit ; deux scènes JPEG
compressées ne suffisent pas à établir une calibration. WEAK reste à mi-chemin
entre OFF et STRONG.

Reproduire : `.venv/bin/python -m scripts.audit_response_v3`.
Rapport, paramètres et échantillons : `outputs/brightness-dr-audit/response-v3.json`.

## Validation

90 tests passent, avec contrôles supplémentaires sur la compensation appliquée
une seule fois à l’aperçu/export, l’absence d’écrêtage avant LUT, les blancs DR,
la monotonie des courbes et les couleurs saturées. Syntaxe JavaScript vérifiée.
Ces tests ne démontrent pas l’identité avec le moteur Fuji.
