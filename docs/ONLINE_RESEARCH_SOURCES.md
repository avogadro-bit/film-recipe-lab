# Sources trouvées en ligne — 14 septembre 2026

La recherche apporte des outils et des références utiles, sans résoudre encore la spécification des registres X-T4 ni fournir un moteur image exact portable.

| Source primaire | Apport vérifié | Limite |
|---|---|---|
| [tiredboffin/fffw](https://github.com/tiredboffin/fffw) | Outil `ff80` pour mémoire, diagnostics et données d’ajustement. Le README décrit aussi `ffem`, un émulateur de recherche ARM/ARM64. | `ffem` est indiqué non publié, en développement, pour certaines fonctions. Aucun rendu Fuji exact complet démontré. |
| [Route 0xff80](https://github.com/tiredboffin/fffw/wiki/Route-0xff80) | Notes sur la lecture RAM et `cfgdata`. L’auteur décrit des sorties intermédiaires du traitement image sur X-E2. | Ces résultats X-E2 ne prouvent pas la disponibilité ni les mêmes offsets sur X-T4. Un état de boîtier reste à mesurer. |
| [Photographies X-T4 — Photography Blog](https://www.photographyblog.com/reviews/fujifilm_x_t4_review) | JPEG pleine taille annoncés non modifiés et fichiers RAF téléchargeables. | Il faut vérifier les correspondances de prises de vue et les réglages ; ce n’est pas un jeu systématique de recettes. Aucun fichier téléchargé dans cette recherche. |
| [ExifTool — FujiFilm](https://exiftool.org/TagNames/FujiFilm.html) | Documentation des MakerNotes : simulation, balance des blancs, tons, grain et Color Chrome. | Décrit les métadonnées, pas les algorithmes de rendu. |
| [FujiHack — travaux](https://wiki.fujihack.org/todo/) | Décrit les périphériques à couvrir pour un émulateur. | Contenu daté d’avril 2024 ; ne démontre pas l’état de tous les projets en 2026. |

Les recherches exactes sur `0xff70f03c` et des variantes de l’adresse n’ont pas donné de spécification matérielle applicable. L’absence de résultat n’établit pas l’impossibilité du projet.

Le code public a depuis été examiné : [investigation détaillée du service et de la table de registres X-T4](FFFW_SERVICE_INVESTIGATION.md). L'examen confirme une publication partielle de `ffun` et précise les limites des commandes mémoire. Aucun contact avec un auteur ni aucune opération sur boîtier n’a été effectué.
