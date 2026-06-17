# Quiz rapide (Kahoot-like)

Minimal app pour créer une partie depuis un Excel, partager un QR code, et permettre aux étudiants de rejoindre et répondre.

Requirements:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Lancer:

```bash
python app.py
```

Ouvrir http://localhost:5000 puis uploader un fichier Excel (colonnes: question, opt1, opt2, opt3, opt4, correct). La page hôte affichera un QR pour que les étudiants rejoignent.
