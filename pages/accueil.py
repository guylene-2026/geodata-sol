"""Page d'accueil : présentation, accès rapides et indicateurs."""

import streamlit as st

from geodata import AUTEUR_APPLICATION, DESCRIPTION_APPLICATION, NOM_APPLICATION, db, pedagogique, ui

st.title(f"🪨 {NOM_APPLICATION}")
st.markdown(f"#### {DESCRIPTION_APPLICATION}")
st.caption(
    "Pour les étudiants en génie civil, les techniciens de laboratoire "
    "et les ingénieurs géotechniciens."
)
st.caption(f"Application réalisée par **{AUTEUR_APPLICATION}**.")

# --- Indicateurs -----------------------------------------------------------
ind = db.indicateurs()
c1, c2, c3, c4 = st.columns(4)
c1.metric("Projets enregistrés", ind["projets"], border=True)
c2.metric("Jeux de données importés", ind["jeux_donnees"], border=True)
c3.metric("Sondages enregistrés", ind["sondages"], border=True)
c4.metric(
    "Dernière analyse",
    ui.date_fr(ind["derniere_analyse"], avec_heure=False)
    if ind["derniere_analyse"]
    else "Aucune",
    border=True,
)

st.divider()

# --- Accès rapides ---------------------------------------------------------
st.subheader("Que voulez-vous faire ?")

col_a, col_b, col_c = st.columns(3)
with col_a:
    if st.button("➕ Nouveau projet", type="primary", width="stretch"):
        st.session_state["projets_mode"] = "nouveau"
        st.switch_page(ui.PAGE_PROJETS)
    if st.button("📥 Importer des données", width="stretch"):
        st.switch_page(ui.PAGE_IMPORT)
with col_b:
    if st.button("📂 Ouvrir un projet", width="stretch"):
        st.session_state["projets_mode"] = "ouvrir"
        st.switch_page(ui.PAGE_PROJETS)
    if st.button("🌐 Collecte de données en ligne", width="stretch"):
        st.switch_page(ui.PAGE_SOURCES)
with col_c:
    if st.button("📊 Analyses", width="stretch"):
        st.switch_page(ui.PAGE_ANALYSES)
    if st.button("📄 Rapports", width="stretch"):
        st.switch_page(ui.PAGE_RAPPORTS)

with st.container(border=True, key="carte_exercice"):
    c1, c2 = st.columns([3, 1], vertical_alignment="center")
    c1.markdown("**🧪 Découvrir l'application avec des données d'exercice**  \n"
                "Crée un projet d'exercice avec un jeu de données **fictif** contenant des pièges "
                "(unités mélangées, valeurs manquantes, valeur aberrante…), puis ouvre le contrôle qualité.")
    if c2.button("🧪 Essayer", width="stretch"):
        projet_id, jeu_id = pedagogique.projet_exercice()
        ui.ouvrir_projet(projet_id)
        st.session_state["_qc_jeu_suivant"] = jeu_id
        st.session_state["_qc_message"] = ("Projet d'exercice ouvert avec le jeu pédagogique FICTIF. Guide de "
                                           "l'exercice : page « Importer des données », encadré 🧪.")
        st.switch_page(ui.PAGE_CONTROLE)

st.divider()

# --- Parcours conseillé ----------------------------------------------------
st.subheader("Le parcours en 6 étapes")
etapes = [
    ("1. Projet", "Créez votre projet : nom, localisation, type d'ouvrage."),
    ("2. Collecte", "Importez un fichier Excel/CSV ou récupérez un fichier public en ligne."),
    ("3. Vérification", "Contrôlez unités, valeurs manquantes, doublons et valeurs atypiques."),
    ("4. Organisation", "Rattachez les résultats aux sondages, échantillons et profondeurs."),
    ("5. Analyse", "Statistiques, graphiques, corrélations et profils en profondeur."),
    ("6. Rapport", "Générez un rapport PDF et exportez vos tableaux."),
]
colonnes = st.columns(3)
for i, (titre, texte) in enumerate(etapes):
    with colonnes[i % 3]:
        with st.container(border=True, key=f"carte_etape_{i}"):
            st.markdown(f"**{titre}**")
            st.caption(texte)

st.warning(
    "**Important :** GeoData Sol aide à organiser et analyser des données. "
    "Il ne tire **jamais** de conclusion sur la sécurité d'un ouvrage : "
    "l'interprétation reste la responsabilité d'un ingénieur qualifié.",
    icon="⚠️",
)
