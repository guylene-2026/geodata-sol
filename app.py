"""Point d'entrée de GeoData Sol.

Lancement (depuis le dossier du projet, sans activer le venv) :
    .venv\\Scripts\\python -m streamlit run app.py

Ce fichier prépare la base de données et construit le menu de navigation ;
le contenu de chaque page se trouve dans le dossier pages/.

Version en ligne (Hugging Face) : la variable d'environnement GEODATA_DEMO=1 active le
« mode démonstration » — la base démarre avec les projets de demo/geodata_demo.db.
"""

import os
import shutil
from pathlib import Path

import streamlit as st

from geodata import AUTEUR_APPLICATION, NOM_APPLICATION, VERSION, db, ui

st.set_page_config(page_title=NOM_APPLICATION, page_icon="🪨", layout="wide")

ui.appliquer_style()

# Mode démonstration (serveur en ligne) : la base démarre avec les projets de démonstration.
# Activé par la variable GEODATA_DEMO=1 ou par la présence du fichier demo/EN_LIGNE
# (ajouté uniquement dans la copie publiée en ligne).
DOSSIER_DEMO = Path(__file__).resolve().parent / "demo"
MODE_DEMO = os.environ.get("GEODATA_DEMO") == "1" or (DOSSIER_DEMO / "EN_LIGNE").exists()
BASE_DEMO = DOSSIER_DEMO / "geodata_demo.db"
if MODE_DEMO and not db.CHEMIN_BASE.exists() and BASE_DEMO.exists():
    db.CHEMIN_BASE.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(BASE_DEMO, db.CHEMIN_BASE)

# Crée le fichier data/geodata.db et ses tables au premier lancement
db.initialiser_base()

# Menu de navigation, regroupé selon le parcours utilisateur
navigation = st.navigation(
    {
        "": [
            st.Page(ui.PAGE_ACCUEIL, title="Accueil", icon="🏠", default=True),
            st.Page(ui.PAGE_PROJETS, title="Projets", icon="📁"),
        ],
        "Collecte": [
            st.Page(ui.PAGE_IMPORT, title="Importer des données", icon="📥"),
            st.Page(ui.PAGE_SOURCES, title="Collecte en ligne", icon="🌐"),
        ],
        "Préparation": [
            st.Page(ui.PAGE_CONTROLE, title="Contrôle qualité", icon="🔎"),
            st.Page(ui.PAGE_SONDAGES, title="Sondages et échantillons", icon="🕳️"),
        ],
        "Résultats": [
            st.Page(ui.PAGE_ANALYSES, title="Analyses", icon="📊"),
            st.Page(ui.PAGE_RAPPORTS, title="Rapports et exports", icon="📄"),
            st.Page(ui.PAGE_HISTORIQUE, title="Historique", icon="🕘"),
        ],
    }
)

# Au lancement, on rouvre le dernier projet utilisé (pas en ligne : la base y est partagée
# entre tous les visiteurs, chacun choisit son projet)
if not MODE_DEMO:
    ui.restaurer_dernier_projet()

# Rappel du projet actif dans la barre latérale
with st.sidebar:
    projet = ui.projet_actif()
    if projet:
        st.success(f"📁 Projet ouvert :\n\n**{projet['nom']}**")
        st.button("Fermer le projet", width="stretch", on_click=ui.fermer_projet)
    else:
        st.info("Aucun projet ouvert.")
    if MODE_DEMO:
        st.warning("**Version en ligne de démonstration.** Les données sont partagées entre les visiteurs et "
                   "peuvent être réinitialisées lors d'un redémarrage du serveur.", icon="🌐")
    st.caption(f"{NOM_APPLICATION} — version {VERSION}  \nRéalisée par {AUTEUR_APPLICATION}")

navigation.run()
