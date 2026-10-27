"""Page Historique : journal de toutes les opérations (traçabilité, 8.1)."""

import pandas as pd
import streamlit as st

from geodata import db, ui

st.title("🕘 Historique des opérations")

projet = ui.projet_actif()
if projet:
    tous = st.toggle("Afficher tous les projets", value=False)
else:
    st.caption("Aucun projet ouvert : l'historique de tous les projets est affiché.")
    tous = True

operations = db.lister_historique(None if tous else projet["id"])
if not tous:
    st.caption(f"Projet : **{projet['nom']}**")

if not operations:
    st.info("Aucune opération enregistrée pour l'instant.")
    st.stop()

tableau = pd.DataFrame(
    {
        "Date": [ui.date_fr(o["date_operation"]) for o in operations],
        "Opération": [o["operation"] for o in operations],
        "Projet": [o["projet_nom"] or "—" for o in operations],
        "Jeu de données": [o["jeu_nom"] or "—" for o in operations],
        "Détails": [o["details"] or "" for o in operations],
        "Auteur": [o["auteur"] or "—" for o in operations],
    }
)
if not tous:
    tableau = tableau.drop(columns="Projet")

types = sorted(tableau["Opération"].unique())
choix = st.multiselect("Filtrer par type d'opération", types, placeholder="Toutes les opérations")
if choix:
    tableau = tableau[tableau["Opération"].isin(choix)]

st.caption(f"{len(tableau)} opération(s), de la plus récente à la plus ancienne.")
st.dataframe(
    tableau, width="stretch", hide_index=True,
    column_config={"Détails": st.column_config.TextColumn(width="large")},
)
