# Références en ligne — 15 septembre 2026

La recherche apporte 23 images téléchargées et 12 comparaisons mesurées. Aucun
coefficient de cette expérience n'est intégré au GUI. Le projet n'est pas terminé.

## Corpus obtenu

- [FAQ Fujifilm : qualité d'image](https://digitalcamera-support-en.fujifilm.com/digitalcameraengpcdetail?aid=000008353) : six illustrations, deux séries séparées à −2, 0 et +4 pour les hautes lumières et les ombres. Les images mesurent environ 878 × 284 pixels et comportent des annotations. Les mesures utilisent uniquement une partie du détail agrandi, hors flèches et cadres. Le modèle des exemples de tonalité n'est pas identifié séparément dans la page.
- [Tomohiro Fujii, Digital Camera Watch : essai X RAW STUDIO sur X-E4](https://dc.watch.impress.co.jp/docs/review/minirepo/1407441.html) : quinze JPEG de 6240 × 4160 pixels, donnant huit comparaisons : exposition, PROVIA vers Classic Negative, FX Blue, WB ombre, WB R+4/B+4, tonalités négatives, couleur +3 et tonalités positives. L'auteur décrit des développements Fuji ; les fichiers portent aussi une trace d'export Lightroom. Les RAF correspondants ne sont pas fournis. Ces images constituent donc des références secondaires, pas des sorties natives garanties intactes.
- [John Peltier : Highlight / Shadow Tone](https://www.jmpeltier.com/fujifilm-highlight-shadow-tones/) : deux captures X RAW STUDIO, X-T2, conservées pour lecture visuelle ; elles ne participent pas au calcul.

URLs exactes, dimensions et empreintes SHA-256 :
[manifest.json](../research/reference-tones/manifest.json).
Métadonnées des JPEG X-E4 : [metadata.json](../research/reference-tones/metadata.json).
Les images restent dans le corpus local de recherche ; leur téléchargement ne
constitue pas une licence de redistribution avec le logiciel.

## Mesures

Script : `.venv/bin/python -m scripts.audit_online_references`.
Il réduit les JPEG à 720 pixels, aligne chaque paire par une transformation affine
bornée, exclut les bords et les transitions fortes, puis mesure les différences par
tranches de luminosité. Les douze alignements passent les garde-fous. Les valeurs
ci-dessous sont en luma des RGB encodés, sur une échelle 0–255 : ce ne sont pas des EV.

Dans les illustrations officielles, Highlight −2 modifie très peu les zones sous
la moitié de l'échelle. La diminution médiane atteint environ 20 niveaux dans la
tranche 0,8–0,9. Shadow −2 relève d'environ 23 niveaux la tranche 0,1–0,2 et laisse
presque inchangées les parties claires. Cela donne des cibles d'amplitude ; on ne
peut pas déduire le traitement RAW interne d'une image déjà développée.

### Contrôle indépendant du FX Blue actuel

Sur les 60 392 pixels bleus sélectionnés dans la scène X-E4 :

| Mesure | Valeur |
|---|---:|
| Erreur absolue RGB moyenne sans effet | 25,57 / 255 |
| Erreur absolue RGB moyenne avec l'effet actuel | 1,72 / 255 |
| Variation médiane de luma dans la référence | −30,86 / 255 |
| Variation médiane produite par l'effet actuel | −30,87 / 255 |

Aucun ajustement n'a été fait sur cette scène. C'est un résultat favorable pour
l'effet appliqué à cette image, pas une validation complète RAW → JPEG, ni une
validation du Color Chrome classique ou de tous les boîtiers.

### Expérience sur les courbes de tonalité

Script : `.venv/bin/python -m scripts.fit_online_tones`.
Quatre amplitudes de la famille de courbes rationnelles sont ajustées sur les
exemples officiels uniquement. Les deux scènes X-E4 sont réservées à l'évaluation.
Le pivot reste fixé à 0,5 ; ombres et hautes lumières sont séparées, ainsi que les
réglages négatifs et positifs. Il s'agit d'une expérience sur la réponse affichée,
pas d'un retour à un moteur qui traite le JPEG à la place du RAW.

| Scène X-E4 | Sans modification : RMS luma | Courbe candidate : RMS luma |
|---|---:|---:|
| H −1 / S −1,5 | 6,40 / 255 | 2,69 / 255 |
| H +2,5 / S +1 | 10,44 / 255 | 5,12 / 255 |

La seconde scène conserve un écart notable ; l'ancienne courbe d'affichage v4 y
obtient même un RMS légèrement inférieur, 4,84. La candidate n'est donc pas une
amélioration universelle. Ces résultats ne comparent pas directement la chaîne
RAW v6 actuelle, car les RAW des exemples publics manquent.

Résultats reproductibles :
[mesures](../outputs/online-reference-audit/measurements.json),
[ajustement](../outputs/online-reference-audit/tone-fit.json).
Les planches avant/après sont dans `outputs/online-reference-audit/`.

## Autres pistes vérifiées

- [pyrocat101/Fujifilm-LUTs](https://github.com/pyrocat101/Fujifilm-LUTs) utilise aussi les LUT vidéo officielles. Son décalage d'exposition et son hypothèse gamma concernent sa propre adaptation ; ils ne prouvent pas une correction pour notre moteur. Le projet n'apporte pas une série native calibrée des commandes Fuji.
- [abpy/FujifilmCameraProfiles](https://github.com/abpy/FujifilmCameraProfiles) propose des profils fondés sur les correspondances Adobe, notamment Classic Negative en LUT. C'est une autre approximation à comparer éventuellement, pas le moteur Fuji. Licence des profils : CC BY-NC-SA 4.0.
- [Demande Reddit de conversion d'une scène DPReview](https://www.reddit.com/r/fujifilm/comments/1uffd19/a_request_to_those_with_an_xtrans_v_camera_and_x/) : la réponse visible renvoie à un échange privé ; aucun fichier public exploitable trouvé dans les commentaires accessibles.

## Suite technique

Utiliser les courbes mesurées comme contraintes de la transformation RAW avant
écrêtage, en tenant compte de la courbe du film et du DR, puis comparer les résultats
aux paires RAF/JPEG locales. Il faut conserver la récupération des valeurs au-delà
du blanc et la stabilité des teintes. Une correction d'affichage seule ne répond
pas au problème de latitude soulevé par l'utilisateur.

La luminosité d'entrée des DNG et le DR ne sont pas validés par cette expérience.
Le transfert aux DNG attend toujours une validation satisfaisante sur les fichiers
Fuji, conformément à l'ordre demandé.
