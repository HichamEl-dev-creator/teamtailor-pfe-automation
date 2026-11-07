# Candidatures PFE Teamtailor — Playwright (version finale)

Ce projet aide à parcourir les offres Teamtailor, remplir les formulaires, joindre le CV et une vidéo et, **uniquement avec `--submit`**, envoyer les candidatures. Par défaut, les commandes de test **n’envoient aucune candidature**.

> Les sélecteurs reposent sur les libellés des captures d'écran fournies, et non sur une validation complète du DOM en production. Vérifier **une seule offre en mode test** avant toute soumission. Les formulaires peuvent varier selon l'offre.

## 1. Fichiers à préparer

Dans le dossier du projet :

- `apply.py` : script principal
- `profil.json` : prénom, nom, école (`FST`), formation, coordonnées et motivation
- `Votre CV.pdf` : CV fourni (Ajouter votre propre CV)
- `presentation_pfe.mp4` : **à ajouter soi-même**, présentation vidéo obligatoire
- `requirements.txt` : bibliothèques Python

Ajouter vos propres informations dans le fichier `profil.json`.

## 2. Ubuntu / Linux (terminal Bash)

Dans le terminal, placez-vous dans le dossier du projet :

```bash
cd ~/Documents/Projet_Teamtailor_PFE_Final
```

Installez le support des environnements virtuels :

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip
```

Créez et activez l'environnement virtuel :

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Installez les dépendances puis Chromium :

```bash
python -m pip install -r requirements.txt
python -m playwright install chromium
```

Si des bibliothèques système Linux sont manquantes :

```bash
python -m playwright install-deps chromium
```

À **chaque nouveau terminal**, réactivez l'environnement :

```bash
source .venv/bin/activate
```

Pour quitter l'environnement : `deactivate`.

**Ubuntu et l’erreur `externally-managed-environment` :** utilisez `.venv` comme ci-dessus, sans `--break-system-packages`.

## 3. Windows (PowerShell)

Installez Python 3.10+ depuis python.org et vérifiez que le lanceur `py` fonctionne. Ouvrez PowerShell dans le dossier du projet (adaptez le chemin) :

```powershell
cd "$HOME\Documents\Projet_Teamtailor_PFE_Final"
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m playwright install chromium
```

Si PowerShell refuse temporairement d'exécuter `Activate.ps1`, vous pouvez utiliser, **pour cette session uniquement** :

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\.venv\Scripts\Activate.ps1
```

À **chaque nouvelle session PowerShell**, activez l'environnement :

```powershell
.\.venv\Scripts\Activate.ps1
```

**Windows (Invite de commandes CMD)**, activation alternative :

```bat
.venv\Scripts\activate.bat
```

Pour quitter l'environnement : `deactivate`.


## 4. Tester sans soumettre (Windows et Linux)

Après avoir activé `.venv` et ajouté `presentation_pfe.mp4` :

```bash
python apply.py --limit 1
```

Tester jusqu'à cinq offres pertinentes :

```bash
python apply.py --limit 5
```

Aucune de ces commandes ne clique sur « Envoyer ma candidature ». Pour voir les résultats :

- `captures/offre_1_previsualisation.png` : formulaire rempli ;
- `captures/offre_1_erreur.png` : capture en cas d'erreur ;
- `candidatures.csv` : journal (`test`, `soumis`, `erreur`, `à vérifier`...) ;
- `offres.json` : offres découvertes.

Si les fichiers ne s'importent pas ou si des champs restent vides, **ne lancez pas** le mode envoi avant correction.

## 6. Envoyer une candidature réelle

**Attention, les commandes suivantes déclenchent un envoi réel.** Après vérification manuelle du premier formulaire :

```bash
python apply.py --submit --limit 1
```

Pour traiter les offres jugées pertinentes selon le filtre du script :

```bash
python apply.py --submit
```

Pour inclure aussi les offres hors profil (déconseillé) :

```bash
python apply.py --submit --all-offers
```

Le script mémorise les candidatures `soumis` dans `candidatures.csv`. Ne supprimez pas ce journal avant d'avoir vérifié les candidatures enregistrées. Le nombre d'offres est découvert automatiquement et peut différer de 81.

## 7. CAPTCHA, erreurs et limites

- Un CAPTCHA doit être résolu **manuellement** ; aucun contournement n'est implémenté.
- Des pauses entre les offres évitent une surcharge du portail, mais ne garantissent pas l'absence de limitation.
- Le script enregistre les erreurs par offre et s'arrête si une soumission a un statut incertain, afin de limiter les doublons.
- Certaines offres peuvent demander des champs supplémentaires non couverts par le script ; vérifier visuellement et respecter les règles du portail.
- Il n'est pas garanti que tous les champs ou uploads soient reconnus sans ajustement sur le formulaire réel.
