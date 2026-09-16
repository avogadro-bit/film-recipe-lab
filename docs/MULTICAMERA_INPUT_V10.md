# Entrée RAW multimarque — révision 10

## Objectif et résultat

Les simulations Fuji reçoivent une représentation commune, sans conversion des
DNG ou des autres RAW en RAF : **RGB sRGB linéaire, blanc D65, float32**, puis
adaptation F-Gamut / F-Log2. La standardisation de l'espace de travail est possible ;
une identité colorimétrique entre tous les appareils n'en découle pas automatiquement.

Cette révision structure le traitement existant sous un contrat d'entrée explicite,
centralise les profils de normalisation par modèle et ouvre le GUI aux autres RAW.
Elle ne remplace pas LibRaw par un nouveau moteur colorimétrique et ne prétend pas
avoir étalonné tous les appareils. Les LUT officielles et la couleur v9 sont conservées.

## Chaîne commune

1. LibRaw décode le format réel et le capteur, avec ses niveaux noir/blanc.
2. Balance des blancs du fichier et conversion caméra vers le même espace linéaire.
3. Normalisation de luminosité, indépendante de la recette choisie.
4. Contrôle de la forme RGB, du float32 et de l'absence de valeurs non finies ;
   les valeurs supérieures à 1 restent disponibles pour les réglages RAW.
5. Réglages et films communs, puis conversion d'affichage et export ICC.

`input_profiles.py` centralise les profils et décrit la provenance des entrées.
Le seul ajustement fixe actuellement mesuré est celui du **Leica Q3 43** : +0,842182 EV
avec conversion caméra flottante. Il ne s'applique ni au Q2, ni à un autre Leica,
ni à une autre marque. Les RAF conservent leur ancrage par recette source.

Pour les autres modèles, LibRaw fournit la conversion caméra générique. L'exposition
est estimée à partir de la luminance de l'aperçu embarqué lorsqu'il est disponible,
en plus des métadonnées applicables. Aucun pixel de cet aperçu n'est copié dans
l'image. Cette estimation n'est pas une calibration de réflectance et peut dépendre
du style de l'aperçu. Sans aperçu exploitable, seules les métadonnées servent.

Le GUI indique « Entrée générique · non étalonnée » ou le profil spécifique utilisé.
Les détails API distinguent le profil, la méthode d'exposition et l'espace de travail.
La conversion générique conserve les limites du traitement entier de LibRaw : les
valeurs négatives peuvent être perdues lors de la conversion couleur, même si la
réserve de hautes lumières est préservée. Le chemin signé Q3 43 reste spécifique.

## Formats et compatibilité

Découverte/import : RAF, DNG, CR2, CR3, CRW, NEF, NRW, ARW, SR2, SRF, RW2,
ORF, ORI, PEF, PTX, SRW, 3FR, FFF, IIQ, RWL, MOS, MRW, KDC, DCR, ERF, MEF, RAW.
Le sélecteur du navigateur reçoit cette liste du serveur : même contrat à l'import
et à la découverte. Filtre « Autres RAW » ajouté à la bibliothèque.

Une extension acceptée ne garantit pas que tous ses modèles/compressions sont
lisibles. Voir la [liste LibRaw 0.22](https://www.libraw.org/supported-cameras), dont
la disponibilité dépend aussi de la compilation. Les JPEG ne sont pas acceptés comme
source RAW ; leur rendu déjà appliqué nécessite un autre traitement. Limite d'import
HTTP actuelle : 200 Mio ; les fichiers déjà dans les dossiers configurés ne passent
pas par cet import. Les fichiers iCloud non locaux restent refusés.

Dans les dossiers de l'utilisateur : 1881 DNG, 810 RAF, **41 CR3, 1 RW2 et 1 IIQ**.
Les 43 derniers fichiers étaient auparavant ignorés.

## Vérifications effectuées

11 fichiers, sept modèles : Canon EOS R6 Mark II (2), Leica Q2 (1), Leica Q3 43 (4),
iPhone 16 Pro (1), X100VI (1), Panasonic DC-S1R (1), Phase One iXG 100MP (1).
Tous sont décodés ; les dix LUT officielles donnent des résultats finis. Cela vérifie
la compatibilité du traitement, pas une correspondance couleur entre appareils.

Les quatre entrées Leica Q3 43 sont comparées aux caches v9 : erreur maximale <10⁻⁶.
Le changement de structure ne modifie donc pas le rendu Leica approuvé.

108 tests automatisés passent. L'interface a été vérifiée dans le navigateur avec
un CR3 Canon, son rendu Classic Negative, le statut d'entrée générique et le filtre
supplémentaire. Un JPEG Canon pleine définition a été exporté et relu avec profil ICC.

[Comparatif des neuf premiers fichiers](../outputs/multicamera-input/comparatif.jpg),
[rapport principal](../outputs/multicamera-input/validation.json),
[contrôle RW2/IIQ](../outputs/multicamera-input/additional-validation.json),
[export Canon](../outputs/multicamera-input/full-export.json).

## Suite de la calibration

Pour rapprocher les appareils entre eux, chaque nouveau profil doit être appris et
contrôlé sur des mires ou scènes communes, idéalement sous plusieurs illuminants.
La conversion commune permet de conserver les mêmes LUT et recettes pour tous les
modèles et de faire évoluer uniquement leur profil d'entrée. Importer l'intégralité
d'un profil DCP/ICC avec ses courbes de rendu ne serait pas une entrée neutre : il
faudrait distinguer la caractérisation du capteur de son rendu photographique.

## Recherche Classic Negative menée pendant cette révision

Le transfert PROVIA → Classic Negative a été vérifié sur deux exemples publics :
[comparatif X RAW Studio / X-E4](https://dc.watch.impress.co.jp/docs/review/minirepo/1407441.html)
et illustrations du livre blanc Fuji. Après inversion numérique de la LUT PROVIA,
l'application de la LUT Classic Negative donne un ΔE00 médian ~1,23 et ~1,25 sur
les pixels dont l'inversion est exploitable. C'est une entrée équivalente de LUT,
pas un RAW retrouvé ; les JPEG publiés peuvent avoir des traitements supplémentaires.
Les résultats soutiennent la conservation des LUT officielles.

Un correctif chromatique appris sur sept couples RAF/JPEG améliore la médiane des
cinq images de contrôle (3,85 → 3,42), mais dégrade les deux exemples publics
(1,18 → 1,59 et 1,12 → 1,42, métrique lissée image entière). **Il est écarté** : il
pourrait compenser les recettes/conditions d'apprentissage plutôt que le film.
Aucune modification de couleur de cet essai ne passe dans le GUI.

La scène commune DPReview Q3 43 / X100VI a été repérée, mais le DNG n'a pas été
récupéré ; elle n'a donc servi à aucune calibration. Les 51 DNG Q3 43 du corpus
échantillonné contiennent les mêmes ColorMatrix1/2 malgré leurs versions de firmware
4.0.0, 4.1.0 et 4.1.1 ; aucune substitution de matrice n'a été faite.

Scripts : `audit_classic_negative_transfer.py`, `fit_classic_negative_chroma.py`,
`validate_multicamera_input.py`. Les deux fichiers RW2/IIQ supplémentaires ont été
contrôlés avec le même chemin decode/render et consignés séparément.
