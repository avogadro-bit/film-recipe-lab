# Essai Classic Negative photographique

Le problème exprimé est le caractère trop numérique du résultat Leica, pas
uniquement la force des commandes. Cet essai compare une autre transformation
des couleurs. Il n'ajoute ni grain, ni flou, ni amplification générale des films.

## Source

Profil Classic Negative sRGB d'[Aaron Buchler / abpy](https://github.com/abpy/FujifilmCameraProfiles),
fondé sur les correspondances photo Adobe pour Fuji X-Trans 4. Ce n'est pas une
LUT officielle Fuji ni une calibration Leica-vers-Fuji. Licence du profil :
CC BY-NC-SA 4.0, attribution Aaron Buchler / abpy ; conservé dans le corpus local
de recherche. Le fichier d'origine n'est pas modifié.

Le [guide de l'auteur](https://abpy.github.io/2023/05/20/linear-profiles.html)
prévoit une entrée sans courbe de contraste préalable. L'essai utilise une entrée
RGB linéaire encodée sRGB, pas F-Log2. Notre conversion LibRaw n'est pas l'intégralité
du pipeline de profil Adobe ; cette différence limite la comparaison.

## Trois colonnes

1. Rendu actuel : LUT GFX ETERNA 55 et adaptation photo existante.
2. Profil photo appliqué directement. Il borne son entrée au domaine de la LUT ;
   cette variante ne convient donc pas à une intégration conservant toute la
   latitude RAW actuelle.
3. Couleurs du profil photo et luma issue du traitement actuel. La branche RAW
   continue à déterminer les tonalités, dont les hautes lumières. Les couleurs
   du profil sont adaptées à cette luma avec une limitation au gamut. Il s'agit
   d'une combinaison expérimentale, pas d'une opération native Fuji.

Un décalage d'entrée de −1,053867 EV est calculé pour faire coïncider les gris
neutres à 18 % entre les deux transformations. Il n'est pas ajusté aux photos de
l'utilisateur et ne remplace pas la normalisation Leica. Il est propre à l'entrée
du profil photo de l'expérience.

[Comparatif Leica, quatre scènes](../outputs/photo-profile-candidate/leica-comparison.jpg).
Il a été inspecté visuellement : différences surtout dans les verts, bleus et
teintes de peau ; la texture ne change pas. L'appréciation de l'aspect « film »
a été recueillie : l’utilisateur a rejeté les trois résultats. Les variantes
expérimentales ne sont pas intégrées.

## Contrôle sur les JPEG Fuji

La variante 3 est aussi évaluée sur les paires RAF/JPEG Classic Negative, avec
la même exposition de source et les mêmes recettes que le moteur actuel.
Ce contrôle réutilise cinq images des jours d'évaluation déjà consultés ; ce n'est
pas un nouvel ensemble aveugle. Aucun paramètre n'est ajusté à ces cinq images.

| Médiane des mesures par image | Actuel | Variante 3 |
|---|---:|---:|
| ΔE00 médian | 4,15 | 3,82 |
| ΔE00 P90 | 7,35 | 6,98 |
| RMS luma | 0,0550 | 0,0526 |

L'amélioration est modeste et ne satisfait pas encore les seuils de fidélité du
projet. Il n'existe pas de paire Leica/Fuji de la même scène dans cet essai.
Le moteur du GUI demeure inchangé en attendant l'évaluation de ce résultat.

Script : `.venv/bin/python -m scripts.compare_photo_profile`.
[Rapport, empreinte SHA-256 et résultats par image](../outputs/photo-profile-candidate/report.json).
