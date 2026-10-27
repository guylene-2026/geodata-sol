"""Page Rapports et exports : rapport PDF et tableaux Excel / CSV (phase 9).

Chaque export est lié au projet et à la provenance des données, et noté dans l'historique.
"""

import re
from datetime import datetime

import streamlit as st

from geodata import analyse as an, db, rapport, ui

projet = ui.exiger_projet()
st.title("📄 Rapports et exports")
st.caption(f"Projet : **{projet['nom']}**")

valides = [j for j in db.lister_jeux(projet["id"]) if j["statut_qc"] == "validé"]
non_valides = [j for j in db.lister_jeux(projet["id"]) if j["statut_qc"] != "validé"]
if non_valides:
    st.caption("Jeux non validés (exclus des résultats, mais listés dans la provenance) : "
               + ", ".join(f"« {j['nom']} » ({j['statut_qc']})" for j in non_valides))


def nom_fichier(extension: str, suffixe: str = "") -> str:
    """Nom de fichier lisible : GeoDataSol_<projet>_<suffixe>_<date>.<ext>."""
    base = re.sub(r"[^A-Za-z0-9_-]+", "_", projet["nom"]).strip("_")[:40] or "projet"
    return f"GeoDataSol_{base}{'_' + suffixe if suffixe else ''}_{datetime.now():%Y-%m-%d}.{extension}"


def noter_export(operation: str, details: str) -> None:
    db.ajouter_historique(operation, details, projet_id=projet["id"], auteur=projet.get("auteur"))


onglet_pdf, onglet_tableaux = st.tabs(["📄 Rapport PDF", "📊 Exports Excel / CSV"])

# ===========================================================================
# Rapport PDF
# ===========================================================================
with onglet_pdf:
    if not valides:
        st.info("Le rapport présente des résultats d'analyse : il faut au moins un jeu de données **validé** "
                "au contrôle qualité.")
        if st.button("🔎 Aller au contrôle qualité"):
            st.switch_page(ui.PAGE_CONTROLE)
    else:
        st.markdown(
            "Le rapport contient : la fiche du projet, la **provenance** de chaque jeu, les **décisions du "
            "contrôle qualité**, les sondages, les **statistiques** et graphiques des variables choisies, les "
            "**corrélations** choisies, les **profils en profondeur** par site, les **hypothèses et limites**, "
            "et l'historique des opérations."
        )
        par_id = {j["id"]: j for j in valides}
        choisis = st.multiselect("Jeux de données à inclure", list(par_id), default=list(par_id),
                                 format_func=lambda i: par_id[i]["nom"])
        variables, correlations = {}, {}
        donnees = rapport.collecter(projet["id"], choisis)
        for j in donnees["jeux"]:
            with st.container(border=True, key=f"carte_rapport_{j['id']}"):
                st.markdown(f"**{j['nom']}**")
                numeriques = an.variables_numeriques(j["description"])
                mesures = [v for v in numeriques if j["description"][v].get("role") == "mesure"]
                variables[j["id"]] = st.multiselect(
                    "Variables à détailler (statistiques + graphiques)", numeriques, default=mesures[:4],
                    format_func=lambda v, d=j["description"]: an.libelle(v, d), key=f"vars_{j['id']}")
                paires = rapport.paires_possibles(j["description"])
                correlations[j["id"]] = st.multiselect(
                    "Corrélations à inclure", paires, default=[],
                    format_func=lambda p, d=j["description"]: f"{an.libelle(p[0], d)} ↔ {an.libelle(p[1], d)}",
                    key=f"corr_{j['id']}")
        avec_profils = st.checkbox("Inclure les profils en fonction de la profondeur (un graphique par site)",
                                   value=True)
        n_graph = sum(len(v) for v in variables.values())
        if n_graph > 12:
            st.caption(f"⏳ {n_graph} variables détaillées : la génération peut prendre quelques secondes de plus.")

        if st.button("🛠️ Générer le rapport PDF", type="primary", disabled=not choisis):
            with st.spinner("Création du rapport…"):
                try:
                    pdf = rapport.rapport_pdf(donnees, variables, correlations, avec_profils)
                except Exception as erreur:  # on montre l'erreur plutôt que de planter la page
                    st.error(f"La création du rapport a échoué : {erreur}", icon="❌")
                else:
                    st.session_state["_rapport_pdf"] = (pdf, nom_fichier("pdf", "rapport"), projet["id"])
                    noter_export("Rapport PDF", f"{len(donnees['jeux'])} jeu(x) : "
                                 + ", ".join(j["nom"] for j in donnees["jeux"])
                                 + f" ; {n_graph} variable(s) ; "
                                 + f"{sum(len(c) for c in correlations.values())} corrélation(s).")
        if st.session_state.get("_rapport_pdf", (None, None, None))[2] == projet["id"]:
            pdf, nom, _ = st.session_state["_rapport_pdf"]
            st.success(f"Rapport prêt ({len(pdf) // 1024} ko).", icon="✅")
            st.download_button("⬇️ Télécharger le rapport PDF", pdf, file_name=nom, mime="application/pdf",
                               type="primary")
            st.caption("Le fichier est enregistré dans le dossier **Téléchargements** de votre ordinateur.")

# ===========================================================================
# Exports Excel / CSV
# ===========================================================================
with onglet_tableaux:
    donnees_tout = rapport.collecter(projet["id"])
    tables = rapport.tables_export(donnees_tout)
    st.markdown("**Classeur Excel complet** : une feuille par tableau (projet, provenance, données validées, "
                "statistiques, sondages, échantillons, essais, décisions du contrôle qualité, historique).")
    if st.button("🛠️ Préparer le classeur Excel"):
        st.session_state["_export_xlsx"] = (rapport.export_excel(donnees_tout), projet["id"])
        noter_export("Export Excel", f"Classeur complet : {len(tables)} feuille(s).")
    if st.session_state.get("_export_xlsx", (None, None))[1] == projet["id"]:
        st.download_button(
            "⬇️ Télécharger le classeur Excel (.xlsx)", st.session_state["_export_xlsx"][0],
            file_name=nom_fichier("xlsx", "export"), type="primary",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    st.divider()
    st.markdown("**Un tableau au format CSV** (séparateur « ; » et virgule décimale : s'ouvre directement "
                "dans Excel en français).")
    choix = st.selectbox("Tableau", list(tables), key="table_csv")
    table = tables[choix]
    st.caption(f"{len(table)} ligne(s) × {table.shape[1]} colonne(s).")
    st.dataframe(table.head(20), hide_index=True, width="stretch")
    suffixe = re.sub(r"[^A-Za-z0-9]+", "_", choix.encode("ascii", "ignore").decode()).strip("_")[:30]
    if st.download_button("⬇️ Télécharger ce tableau (.csv)", rapport.export_csv(table),
                          file_name=nom_fichier("csv", suffixe), mime="text/csv"):
        noter_export("Export CSV", f"Tableau « {choix} » ({len(table)} ligne(s)).")
    st.caption("Chaque export est noté dans l'historique du projet, avec la date et le contenu exporté.")
