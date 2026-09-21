# Vérification avant partage — 15 septembre 2026

Le dépôt Git local est initialisé. Aucun commit, dépôt distant ou envoi à GitHub n’a été effectué. Le code original est sous licence MIT, selon le choix de l’auteur.

## Problèmes corrigés

- Le paquet ne se construisait pas : setuptools détectait plusieurs dossiers de premier niveau comme packages. La découverte est maintenant limitée à `kora`.
- Des caches photo et téléchargements de recherche échappaient au `.gitignore`. Tout `research/`, les sorties, les photos, les LUT `.cube`, les firmwares et les clés usuelles sont exclus. Un contrôle supplémentaire inspecte aussi les fichiers déjà suivis par Git.
- Les LUT étaient incluses dans le paquet Python. Elles sont désormais exclues du wheel et de l’archive source et installées séparément depuis l’archive originale, avec validation SHA-256 des dix tables avant écriture.
- Les chemins personnels du lanceur, du README et de la provenance WB ont été supprimés. Trois scripts d’essai reçoivent maintenant leurs photos en arguments.
- Le démarrage pouvait parcourir toute la bibliothèque avant le choix de dossier. Les racines sont maintenant des raccourcis ; l’analyse commence à la sélection explicite. Sans `--root`, le dossier personnel est proposé sans analyse récursive préalable.
- L’accès à `st_blocks` est protégé sur les systèmes qui ne fournissent pas ce champ. Les requêtes JSON mal formées du sélecteur de dossier sont refusées ; une déconnexion du navigateur pendant l’envoi d’une image n’imprime plus de traceback BrokenPipe.

## Vérifications effectuées

| Vérification | Résultat |
|---|---|
| Suite locale avec LUT et Lensfun | 124 tests réussis |
| Wheel installé hors du dépôt, environnement Python 3.13 neuf, LUT installées séparément | 122 tests réussis lors du dernier contrôle du paquet |
| Même installation sans LUT | 110 réussis, 12 intégrations LUT explicitement ignorées |
| `pip check` dans l’environnement neuf | Aucun conflit |
| Compilation Python et syntaxe JavaScript | Réussies |
| Contrôle des fichiers suivis/non ignorés | Aucun fichier interdit, secret reconnu ou chemin personnel détecté |
| Contenu du wheel et de l’archive source | Pas de LUT `.cube`, firmware, photo, cache ou chemin personnel détecté |
| Installateur LUT | Archive officielle validée ; archives synthétiques corrompues/manquantes rejetées ; chemins ZIP non extraits |
| GUI | Choix de dossier, zoom, panneaux et état/rendu de correction optique vérifiés dans le navigateur |
| Fichiers réels | 19 photos, 7 boîtiers, 9 configurations d’objectif, dix films par photo ; originaux inchangés |
| Exports corrigés | Leica 60 MP et Canon 24 MP relus ; cohérence aperçu/export mesurée |

Le premier `pip check` dans l’ancien environnement partagé signalait un conflit Gradio/Starlette extérieur à ce projet. Ces bibliothèques ne font pas partie du paquet ; l’installation neuve ne présente pas ce conflit. L’environnement photo existant n’a pas été réorganisé pour le corriger.

L’environnement neuf a résolu notamment rawpy 0.27.1, NumPy 2.5.3, Pillow 12.3.0, SciPy 1.18.1, Pydantic 2.13.5, tifffile 2026.9.15 et lensfunpy 1.18.0. Le fichier historique `requirements-tested.txt` décrit un autre ensemble local ; le paquet installe les plages déclarées dans `pyproject.toml`.

## Limites du résultat

Ces contrôles ne sont pas un audit de sécurité exhaustif ou un avis juridique. Le contrôle de secrets recherche des motifs connus ; relire les fichiers à publier. Les coefficients WB dérivés du firmware sont documentés dans [THIRD_PARTY.md](../THIRD_PARTY.md).

La matrice GitHub Actions proposée couvre macOS, Linux et Windows / Python 3.11 et 3.13. **Elle n’a pas encore été exécutée sur GitHub.** Les essais réels décrits ici ont été exécutés sur macOS. Aucun rendu exact Fuji, étalonnage universel des appareils ou correction optique de tous les objectifs n’est revendiqué. [Couverture optique et chaîne de normalisation](OPTICS_AND_NORMALIZATION.md).

## Reproduire avant un premier commit

```sh
python -m pip install -e '.[emulation,optics]' build
python -m unittest discover -s tests -v
python scripts/check_release.py
python -m build
git status --short
git add --dry-run .
```

Ne pas utiliser `git add -f` sur les données ignorées. Les rapports et comparatifs de photos sont destinés à rester locaux. Publier les sources via Git plutôt qu’une copie brute du dossier de travail, qui contient plusieurs gigaoctets de données privées ignorées.
