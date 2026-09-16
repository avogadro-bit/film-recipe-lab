# Ressources tierces et provenance

Le code du projet ne confère aucun droit sur les marques Fujifilm, les LUT, les firmwares ou les dépendances tierces. Ce projet indépendant n’est pas affilié à Fujifilm.

## LUT Fujifilm

Source : [page officielle des LUT](https://www.fujifilm-x.com/global/support/download/lut/), archive GFX ETERNA 55 v1.10. La page décrit leur chargement dans un logiciel de montage ; ce projet ne présume pas d’un droit de redistribution et exclut les `.cube` de Git, du wheel et de l’archive source.

Le manifeste du projet contient uniquement leurs noms et SHA-256. L’utilisateur télécharge l’archive séparément, consulte les conditions du fournisseur puis l’installe localement avec `python -m fuji_recipe_lab.lut_install`. L’installateur conserve les octets originaux.

## Recherche native et balance des blancs

Les firmwares, modules extraits, outils tiers téléchargés et rapports de recherche restent locaux dans `research/`, exclu de Git. Le code du banc décrit des observations et des adresses, mais n’inclut pas les binaires du fabricant.

`fuji_recipe_lab/luts/wb-shifts-xt4.json` contient 38 coefficients numériques de balance des blancs observés dans la configuration du X-T4 2.12. Leur provenance et les limites de l’application RGB sont conservées dans le fichier. Ce sont des données dérivées d’une analyse du firmware, pas une calibration indépendante du X100VI. La licence choisie pour le code original ne s’étend pas automatiquement à des éléments tiers ; cette provenance doit rester visible lors du partage.

## Dépendances

Les dépendances Python sont installées séparément par pip et conservent leurs propres licences et notices. Consulter les métadonnées et fichiers de licence des versions réellement installées, notamment rawpy/LibRaw, NumPy, SciPy, Pillow, Pydantic, tifffile et, pour l’extra `emulation`, Unicorn et Capstone. ExifTool est une dépendance système externe. Le profil Adobe RGB système, les photos, JPEG de référence, documents du fabricant et téléchargements ne sont pas redistribués.

## Code original

L’option `optics` installe lensfunpy et sa base Lensfun séparément. Le projet ne copie pas cette base dans le dépôt. Les coefficients DNG Leica sont lus à la demande dans les photos de l’utilisateur, sans les inclure dans les sources ni les jeux de tests publics. L’implémentation géométrique se réfère à la [spécification DNG Adobe](https://helpx.adobe.com/camera-raw/digital-negative.html) et l’intégration des profils à la [documentation lensfunpy](https://letmaik.github.io/lensfunpy/).

Le code original est distribué sous [licence MIT](LICENSE). Cette licence ne remplace pas celles des ressources tierces. Ce document fournit l’inventaire des ressources ; il ne constitue pas une validation juridique des droits de distribution.
