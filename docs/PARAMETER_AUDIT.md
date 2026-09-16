# Réponse des paramètres — audit et corrections

**Révision 7 — tons quatre voies et aperçu interactif :** les anciens réglages
Fuji Ombres/Hautes lumières sont remplacés par Highlights, Whites, Shadows et
Blacks sur une échelle −100…+100. Highlights/Shadows agissent largement autour
des tons moyens ; Whites/Blacks ciblent davantage les extrémités. Les courbes
sont monotones et calculées sur la luminance scène-linéaire sans écrêter la
réserve du RAW ni modifier les rapports RGB. Dans les directions de récupération
(Highlights/Whites négatifs, Shadows/Blacks positifs), une passe locale guidée
par les contours restaure uniquement la texture encore présente dans le RAW.
Les recettes v1 sont migrées automatiquement. Le modèle vise une précision et
une séparation des zones comparables à un éditeur RAW professionnel, mais ne
reproduit ni le code ni une calibration de Capture One.

Les gestes interactifs utilisent un aperçu linéaire 1 800 px mis en cache ; la
pleine définition reste utilisée après stabilisation à l’ouverture, au zoom
100 % et pour l’export. Le cache pleine définition est partagé entre aperçu et
export. Cette séparation évite de recalculer environ 60 MP à chaque déplacement
de curseur.

**Révision 6 — stabilité des teintes :** pour les dix LUT officielles,
les réglages ombres/hautes lumières/DR utilisent deux rendus. Le rendu RAW
ajusté fournit la luminance ; le rendu au même WB/exposition avec les tons
neutres et DR100 fournit la direction de chroma RVB. La chroma suit le ratio
de luminance et est réduite aux limites du gamut. Cela empêche la LUT de
changer de teinte en réponse aux seuls réglages tonals, tout en conservant
la gradation récupérée avant le film. Les autres effets couleur interviennent
ensuite et peuvent modifier cette chroma. Le zéro reste identique.

C'est une stratégie indépendante, pas une méthode Fuji mesurée. Une couleur
déjà perdue dans le rendu de référence écrêté ne peut pas être restaurée par
cette stratégie ; les zones blanches retrouvent une gradation neutre. Le calcul
nécessite un deuxième passage LUT lorsque les réglages tonals sont actifs.
97 tests passent, dont stabilité de direction de chroma pour les dix LUT et
conservation de la luminance récupérée. Comparatif sur IMG_4768.DNG :
`outputs/magenta-audit/comparison.jpg` ; mesures dans `report.json`.
La forte dominante signalée n'a pas été reproduite avec la même intensité
sur ce fichier, mais une dérive de la LUT a été mesurée et corrigée.


**Version actuelle : [chaîne linéaire v5 et exposition initiale estimée](LINEAR_PIPELINE_V5.md).**
Les révisions décrites ci-dessous sont historiques.


**Révision 4 :** ombres et hautes lumières manuelles utilisent désormais deux
courbes monotones distinctes, raccordées à une luminance affichée de 0,5.
Le zéro conserve le rendu existant. À luminance 0,25, Ombres +4 donne 0,084
et −2 donne 0,345 (anciennement environ 0,191 et 0,280). La réponse des
hautes lumières est symétrique. Le coefficient de force 0,8 est un choix
d’amplitude pour répondre au retour utilisateur, pas une mesure Fuji.
Les couleurs restent dans le gamut par réduction de chroma si nécessaire.
La priorité DR conserve sa courbe automatique séparée et désactive ces curseurs.
92 tests passent : demi-pas, sens, monotonie, zone opposée préservée et zéro.
Comparatif : `outputs/brightness-dr-audit/tone-v4.jpg`.


**Mise à jour : [révision 3 — luminosité initiale, DR et Color Chrome](RESPONSE_V3.md).**
Les mesures ci-dessous documentent la révision précédente.

La révision 2 des effets rapproche plusieurs commandes des références disponibles.
Elle ne garantit pas la réponse identique de tous les réglages de X RAW STUDIO.
Les LUT officielles et leur adaptateur photo restent inchangés.

## Corrections appuyées sur des références

### Décalages de balance des blancs

La formule uniforme `2**(shift/24)` est remplacée par les 36 coefficients Q10
du DAT X-T4 2.12, extraits du préfixe dont le SHA-256 est vérifié.
Le zéro est 1024 ; les valeurs sont non linéaires et asymétriques.
La source, les offsets et l’exécution isolée des 361 combinaisons sont décrits
dans [NATIVE_CONFIGURATION.md](NATIVE_CONFIGURATION.md).

| Décalage | Ancien gain | Gain de la table |
|---|---:|---:|
| Rouge +9 | 1,297 | 1,852 |
| Rouge −9 | 0,771 | 0,541 |
| Bleu +9 | 1,297 | 1,498 |
| Bleu −9 | 0,771 | 0,573 |

Le GUI applique ces facteurs au RGB linéaire avant la LUT. Le firmware compose
ses gains dans un autre contexte de couleur : l’origine des coefficients est
vérifiée, leur application aux pixels n’est pas une reproduction du pipeline
capteur. Ni la compatibilité X100VI ni celle des DNG n’est mesurée. Certains
petits décalages sont plus faibles que l’ancienne formule : aucune amplification
globale arbitraire n’a été ajoutée. Le pas de température dans le GUI est passé
à 10 K, dans la plage 2500–10000 K du manuel X100VI.

### Color Chrome et Color Chrome FX Blue

Les deux modèles STRONG sont ajustés sur les paires OFF/STRONG publiées par
[Fujifilm](https://www.fujifilm-x.com/en-gb/learning-centre/color-chrome-and-film-grain-effects/),
puis évalués sans réajustement sur une autre scène X100V convertie dans
[X RAW STUDIO par Alik Griffin](https://alikgriffin.com/a-look-at-fujifilms-new-jpg-effects-clarity-color-chrome-grain/).
Ce photographe fournit ses propres exemples : il s’agit d’une source primaire.

Le modèle Color Chrome module luminosité et chroma en fonction de la saturation
et des teintes chaudes/vertes. FX Blue diminue la luminosité des zones bleues,
sans assombrir les gris, rouges ou verts. La réponse WEAK reste une interpolation
à mi-chemin vers STRONG, faute de paire indépendante WEAK.

| Erreur RGB moyenne absolue (échelle 0–1) | Avant | Après |
|---|---:|---:|
| Color Chrome, pixels réservés de la scène Fuji | 0,01947 | 0,01097 |
| Color Chrome, scène X100V indépendante | 0,01552 | 0,00432 |
| FX Blue, pixels réservés de la scène Fuji | 0,02096 | 0,00386 |
| FX Blue, scène X100V indépendante | 0,01338 | 0,00662 |

Les JPEG publics sont compressés et leurs recettes complètes ne sont pas
connues. La seconde scène provient de captures écran : recalage entier de
1–2 pixels et léger lissage pour atténuer compression/décalage. L’erreur mesure
la reproduction de ces exemples, pas une précision universelle du moteur.
Reproduction : `python -m scripts.fit_chrome_effects` dans l’environnement du
projet. Sources, empreintes et mesures : `research/reference-effects/`.

## Contrôle de toutes les familles de paramètres

| Paramètres | Résultat de l’audit / limite restante |
|---|---|
| Film | 10 LUT officielles vérifiées ; autres films explicitement artistiques. |
| Exposition | Multiplication linéaire `2**IL` avant LUT ; pas de 1/3 IL GUI. Le point de départ LibRaw n’est pas calibré au boîtier. |
| Grille R/B | Table X-T4 intégrée, synchronisation GUI/recette/export. Application RGB adaptée, pas capteur. |
| WB du fichier | Balance fournie par LibRaw ; peut déjà inclure les décalages de prise de vue. |
| WB auto / priorité blanc / ambiance | Heuristiques de moyenne grise, pas détection Fuji de scène/éclairage. Restent non calibrées. |
| WB Kelvin / préréglages | Ajustements relatifs autour de 5500 K après la balance du fichier. Ne sont pas encore une sélection absolue d’illuminant capteur. Limite majeure persistante. |
| DR100/200/400 | Correction : compression des hautes lumières préservant désormais les tons sous 18 % et les rapports RGB. Ce sont des courbes approximatives ; aucune récupération de données capteur déjà écrêtées. |
| Priorité DR | Correction : DR et courbe manuelle sont pris en charge automatiquement, curseurs désactivés. Courbe automatique approximative ; conditions ISO Fuji non émulées. |
| Highlights / Whites / Shadows / Blacks | Plage −100…+100, zones distinctes, monotonie et conservation des rapports RGB vérifiées. Une restauration locale guidée par les contours agit dans les directions de récupération ; elle ne recrée que le contraste présent dans le RAW. Amplitude exacte non calibrée contre Capture One ou Fuji. |
| Couleur | Réponse croissante de chroma, neutres préservés ; échelle −4…+4 non calibrée. |
| Color Chrome / FX Blue | STRONG rapproché de deux scènes de référence ; WEAK interpolé, interactions entre effets non calibrées. |
| Netteté | Réponse aux contours vérifiée dans les deux sens ; rayon et quantité non calibrés. |
| Clarté | Modèle local approximatif. Essai de fit des exemples ±2/±5 rejeté : rayons/quantités incohérents entre niveaux négatifs, pas de validation sur une autre scène. Rapport conservé `clarity-fit.json`. |
| Réduction du bruit | Lissage croissant vérifié ; pas de modèle de bruit ISO/capteur Fuji. |
| Grain / taille | Texture déterministe et deux tailles actives ; pas de distribution Fuji mesurée, aperçu/export diffèrent selon l’échelle. |
| Filtres ACROS / mono | Préfiltrage couleur avant ACROS, teintes mono actives. Variantes non présentes dans le pack LUT officiel. |
| Lissage peau | Masque de couleur et lissage actifs ; aucune détection de visage Fuji. |
| Taille / ratio / téléconvertisseur | Géométrie active et originaux conservés. Dimensions dérivées de LibRaw, pas exactement les dimensions JPEG du boîtier ; pas de super-résolution. |
| JPEG Fine/Normal | Compression effective à l’export ; niveaux de qualité non équivalents au codec Fuji. L’aperçu conserve sa qualité fixe. |
| TIFF 8/16 bits | Profondeur réelle, précision et ICC testés. |
| sRGB / Adobe RGB | Conversion et profil ICC à l’export ; aperçu géré en sRGB. Gamut initial limité par le décodage sRGB. |
| Optimisation optique / HDR | Indisponibles, commandes désactivées. |
| Nom / modèle / firmware / version | Métadonnées de recette, pas des transformations de pixels ; le modèle cible ne change pas les LUT du GFX. |

Référence des interactions/plages : [manuel Fujifilm X100VI](https://app.fujifilm-dsc.com/en/manual/x100vi/menu_shooting/image_quality_setting/).

## Vérifications

85 tests passent, dont nouveaux contrôles de la table WB, neutralité/sélectivité
des effets Chrome, DR préservant les tons moyens, priorité DR et réponse des
détails. 54 contrôles sur les fichiers Leica DNG et X100VI RAF vérifient que
chaque commande d’image/sortie testée change les pixels, la géométrie ou les
octets exportés : `outputs/parameter-audit/operational-coverage.json`.
Les commandes conditionnelles sont testées dans leur contexte actif (Kelvin,
monochrome, grain). Cela ne prouve pas leur fidélité à Fuji.

Pour réduire les écarts restants : mêmes RAW convertis dans X RAW STUDIO avec
un seul réglage variable, réglages complets consignés, plusieurs scènes et ISO.
Les JPEG incorporés aux RAF donnent un seul point de référence et ne permettent
pas d’isoler la réponse de chaque curseur.
