# GeoData Sol

**Application de collecte, de gestion et d'analyse des données géotechniques.**

Réalisée par **ESSOLA AVA GUYLENE** — classe 3GCU, matricule 24P101.

GeoData Sol aide les étudiants en génie civil, les techniciens de laboratoire et les ingénieurs
géotechniciens à centraliser des données de sol (teneur en eau, limites d'Atterberg, résistance,
CBR…) venant de plusieurs sources, à **contrôler leur qualité**, à les **analyser** et à produire un
**rapport**, tout en conservant leur **provenance** et leurs **limites d'utilisation**.

> GeoData Sol ne tire **jamais** de conclusion sur la sécurité d'un ouvrage : il présente des données
> et des statistiques, dont l'interprétation relève d'un ingénieur qualifié.

---

## Installation et lancement (Windows)

Prérequis : Python 3.13.

```powershell
# 1. Créer l'environnement Python (une seule fois)
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt

# 2. Lancer l'application
.venv\Scripts\python -m streamlit run app.py
```

L'application s'ouvre dans le navigateur à l'adresse `http://localhost:8501`.
Pour l'arrêter : `Ctrl + C` dans le terminal.

Les projets sont enregistrés dans `data/geodata.db` (base SQLite créée au premier lancement) et sont
retrouvés à chaque réouverture ; le dernier projet utilisé se rouvre automatiquement.

**Pour découvrir l'application en 1 clic** : sur la page d'accueil, bouton **« 🧪 Essayer »**. Il crée un
projet d'exercice avec un jeu de données **fictif** contenant des pièges volontaires.

---

## Parcours utilisateur

| Étape | Page | Ce que fait l'application |
|---|---|---|
| 1-2. Projet | 📁 Projets | Fiche projet (nom, localisation, type d'ouvrage, confidentialité), enregistrée |
| 3. Collecte | 📥 Importer des données · 🌐 Collecte en ligne | Fichiers XLSX, XLS, CSV ; URL directe d'un fichier public ; jeu pédagogique ; **fiche de provenance obligatoire** |
| 4. Vérification | 🔎 Contrôle qualité | Structure, types, unités, manquants, doublons, lignes de synthèse, formats incohérents, valeurs atypiques ; **l'utilisateur tranche et valide** |
| 5. Organisation | 🕳️ Sondages et échantillons | Fiches de sondage et d'échantillon ; rattachement des essais ; localisation inconnue conservée comme telle |
| 6-7. Analyse | 📊 Analyses | Statistiques descriptives, histogramme, boîte à moustaches, nuage de points, comparaison de groupes, corrélations de Pearson et Spearman, profils en profondeur |
| 8. Export | 📄 Rapports et exports | Rapport PDF ; classeur Excel ; tableaux CSV (format français) |
| 9. Reprise | 🏠 Accueil | Projet rouvert automatiquement ; 🕘 Historique de toutes les opérations |

## Règles scientifiques appliquées

1. Des valeurs ambiguës (« 25 % », « 0,25 », « 25 ») ne sont **jamais mélangées automatiquement** : l'utilisateur interprète chaque groupe.
2. Toute **conversion d'unité** est proposée avec son facteur, puis **validée** par l'utilisateur et tracée.
3. Chaque jeu de données a une **fiche de provenance** (source, fichier ou URL, date, auteur, licence, limites d'usage) ; pour une URL, l'empreinte SHA-256 du fichier est conservée.
4. Les **valeurs atypiques** sont signalées (règle de Tukey, méthode affichée), **jamais supprimées** : l'utilisateur les conserve ou les exclut de l'analyse en le justifiant.
5. La **virgule décimale française** est reconnue (« 0,25 ») ; les nombres sont affichés à la française.
6. **Profils de profondeur** : profondeur verticale, de 0 (surface) vers le bas ; une courbe par sondage ; **un site par graphique**.
7. Chaque graphique a un titre, les variables avec leurs unités, une légende si nécessaire et le **nombre d'observations n**.
8. **Corrélations** : Pearson et Spearman, avec n, p-value, sensibilité aux valeurs atypiques et limites (corrélation ≠ causalité).
9. Les résultats distinguent **observations, résultats calculés, estimations statistiques, hypothèses et limites**.
10. Les données de **localisation inconnue** restent marquées comme telles.

Les données brutes importées ne sont jamais modifiées : la version « validée » est une copie
recalculée à partir des décisions enregistrées (journal des décisions de contrôle qualité).

## Sources de données en ligne

La page « Collecte en ligne » commence par des sources utiles au **Cameroun**, dont un jeu réel de
données géotechniques sur les sols latéritiques de Ngaoundal (Université de Dschang, Mendeley Data,
licence CC BY 4.0), téléchargeable en un clic avec sa provenance pré-remplie.

## Organisation du code

```
app.py                  point d'entrée : base de données, menu, projet actif
pages/                  interface (une page Streamlit par fichier, en français)
geodata/
  db.py                 accès à la base SQLite (seul module qui dialogue avec SQLite)
  importation.py        lecture XLSX / XLS / CSV sans interprétation des valeurs
  qualite.py            contrôle qualité : interprétation, unités, doublons, atypiques
  organisation.py       rattachement aux sondages, échantillons et profondeurs
  analyse.py            statistiques, corrélations, graphiques (plotly)
  collecte.py           sources en ligne et téléchargement par URL
  rapport.py            rapport PDF (fpdf2, matplotlib) et exports Excel / CSV
  pedagogique.py        jeu de données pédagogique fictif et guide de l'exercice
  ui.py, ui_import.py   éléments d'interface partagés
exemples/               fichiers d'essai FICTIFS (dont jeu_pedagogique_fictif.xlsx)
docs/                   cahier des charges
```

Technologies : Python 3.13, Streamlit, SQLite, pandas, SciPy, Plotly, matplotlib, fpdf2, openpyxl, xlrd, requests.
