# Bloc DEFAULT et retour du traitement WB — 13 septembre 2026

Suite de cette étape : [réservation native avec le programme RAW 6 et frontière DMA](NATIVE_RESOURCE_PLAN.md). Le parcours décrit ci-dessous reste reproductible sans l’option `--raw-resource-plan`.

**Le bloc DEFAULT du DAT est retrouvé, chargé par une primitive native et lu par le calcul Fuji. Le gestionnaire de balance des blancs termine désormais dans le parcours RAW. L’exécution s’arrête ensuite sur une ressource intermédiaire non réservée ; aucun pixel n’est rendu.**

## Origine du bloc étendu

Le chemin de chargement à `0x011ece8c` demande `0x2000` octets à `0x01265520`, avec le mode 1 et une destination obtenue pour l’offset cfgdata `0x420000`.

`0x01265520` retrouve le descripteur 8 via `0x01290fb8`. L’enregistrement situé à l’offset fichier `0x140184` fournit le début flash `0x1820000`. Le mode 1 ajoute `0x17300`, soit **l’offset fichier `0x1837300`** et l’adresse flash `0xf1837300`.

La tranche de 8192 octets commence par `FLSNW001` et contient le nom `DEFAULT`. Son octet `+0xf82` vaut **1**. Son SHA-256 est :

```text
6d960689ca466293128590e92b9dd2ad407e7b051f88c5adaf44749d200f3a29
```

Le chargeur du banc exige aussi le SHA-256 complet de `main.bin` déjà épinglé, puis la forme exacte du descripteur. La présence du nom ou de la signature ne suffit pas à autoriser des données.

## Ce qui est exécuté

1. `0x01265520` calcule les arguments jusqu’à l’entrée du lecteur matériel `0x011a6c7c`. Les adresses et la taille sont vérifiées ; le lecteur matériel n’est pas exécuté.
2. La primitive native `0x01281848` copie les octets vérifiés, exposés en lecture seule à l’adresse flash calculée, vers deux pages RAM gardées à `0x06c20000`. Les 8192 octets de destination correspondent au DAT. La copie termine après 4127 instructions.
3. Le setter natif `0x01294d90` initialise séparément l’état d’accès. Les modes 0, 1 et 2, présents dans les appels du firmware, sont testés. Le lecteur natif `0x012f20d8` renvoie 1 dans les trois cas après lecture de l’octet attendu à `0x06c20f82`.

**Le parcours RAW utilise explicitement le mode 0. Ce choix est une entrée de banc initialisée par le setter natif, pas un mode récupéré dans un dump de boîtier.** Le traducteur `0x012638d0` lit cet état mais conserve l’offset demandé sur le chemin étudié. Aucun résultat matériel n’est remplacé par un stub.

Seuls le bloc `0x420000…0x421fff` et le préfixe inférieur déjà retrouvé sont chargés. Les autres parties de la configuration étendue restent inconnues. Le préfixe inférieur de `0x72000` octets est importé entièrement pour permettre les lectures suivantes, notamment à l’offset `0x4944`. Toute contradiction avec une ancienne valeur explicite provoque un rejet ; les pages restent en lecture seule.

## Retour natif observé

Le banc enregistre les registres avant certaines instructions, sans modifier le processeur. Les points sont bornés à 64 adresses et les observations à 1024 entrées au maximum. La troncature est signalée et n’arrête pas le programme.

| Observation dans le destinataire RAW | Instruction comptée |
|---|---:|
| Entrée du gestionnaire WB `0x021ae6fc` | 6648 |
| Retour du calcul des gains, PC `0x021aee14` | 7488 |
| Retour du gestionnaire WB, PC `0x02207464` | 9525 |
| Entrée de l’opération suivante `0x02218a80` | 21000 |
| Arrêt sur la ressource absente | 21473 |

Les trois valeurs de paramètres écrites à `0x03374016`, `0x03374018` et `0x0337401a` sont `380, 527, 302` dans ce banc. Les codes de progression transmis sont `8, 9, 0x28`, avec statut zéro. La file de notification contient trois messages. Ces nombres décrivent ce cas de test ; ils ne constituent pas une validation colorimétrique.

Le contexte de gains et les autres entrées de travail restent ceux du banc. Seules les métadonnées géométriques proviennent du RAF utilisateur. Le retour WB ne signifie donc pas qu’une photographie soit développée.

## Nouvelle dépendance précisément identifiée

`0x02218a80` appelle `0x02205944`, puis `0x021996fc`. La recherche interne à `0x02199240` reçoit :

```text
R0 = 0x0600003c  contexte propriétaire, identifiant 1
R1 = 0x2f        type de ressource
R2 = 0           index
```

La recherche d’une réservation propriétaire/type/index renvoie zéro. Le wrapper renvoie donc un pointeur nul. L’instruction `LDM` à `0x02218b04` tente ensuite de copier son descripteur depuis l’adresse zéro et le banc s’arrête.

La table de ressources du mode 2 possède pourtant trois descripteurs pour ce type : le premier est à `0x025d8cec`, avec une adresse de buffer `0x34983c00` et une capacité `0xc80000`. **Un descripteur statique disponible n’est pas une réservation active.** Aucun pointeur n’a été injecté pour masquer l’absence de cette réservation, et ces buffers ne sont ni mappés ni remplis de pixels.

La prochaine étape consiste à retrouver le chemin natif qui réserve cette ressource, ses conditions et son lien avec le RAW d’entrée. Les géométries X-T4 et X100VI restent à distinguer ; la compatibilité DNG n’est pas validée.

## Reproduction et contrôles

```bash
.venv/bin/python -m kora xt4-cfg-probe research/extracted/xt4-2.12 --output research/reports/default-replay.json
.venv/bin/python -m kora xt4-resource-probe research/extracted/xt4-2.12 '/chemin/photo.RAF' --with-receiver --firmware-config --boot-wb --extended-config --output research/reports/receiver-default-replay.json
```

Rapports : `research/reports/xt4-configuration-extended-validated.json` et `research/reports/xt4-receiver-default-validated.json`. `passed` valide le retour WB, les notifications et l’arrêt attendu sur la ressource manquante, **pas le rendu**.

**60 tests unitaires passent**, notamment le rejet d’un firmware différent, le refus des conflits de configuration, les préconditions des options et la fidélité des observations de registres. L’interface conserve son aperçu intégré et refuse toujours de présenter un rendu approximatif comme un résultat Fuji.
