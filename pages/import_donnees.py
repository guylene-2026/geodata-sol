"""Page Importer des données : fichiers XLSX, XLS, CSV + fiche de provenance."""

from pathlib import Path

import pandas as pd
import streamlit as st

from geodata import db, importation, pedagogique, ui, ui_import

LIGNES_APERCU = 50

projet = ui.exiger_projet()
st.title("📥 Importer des données")
st.caption(f"Projet : **{projet['nom']}**")

if message := st.session_state.pop("_import_message", None):
    st.success(message, icon="✅")

jeux = db.lister_jeux(projet["id"])
onglet_import, onglet_jeux = st.tabs(["➕ Nouvel import", f"📚 Jeux de données du projet ({len(jeux)})"])

# ===========================================================================
# Jeux de données du projet
# ===========================================================================
# (Cet onglet est construit en premier : ainsi un fichier illisible dans l'onglet
# « Nouvel import », qui arrête la page, n'empêche pas d'afficher la liste.)
with onglet_jeux:
    if not jeux:
        st.info("Aucun jeu de données importé dans ce projet pour l'instant.")
    for jeu in jeux:
        titre = (
            f"{'🧪 ' if jeu['est_fictif'] else '📄 '}**{jeu['nom']}** — "
            f"{jeu['nb_lignes']} lignes × {jeu['nb_colonnes']} colonnes — "
            f"importé le {ui.date_fr(jeu['date_import'])}"
        )
        with st.expander(titre):
            st.caption(
                f"Type : {db.TYPES_SOURCE.get(jeu['type_source'], jeu['type_source'])}"
                + (f" · feuille « {jeu['feuille']} »" if jeu["feuille"] else "")
                + f" · contrôle qualité : **{jeu['statut_qc']}**"
            )
            prov = db.obtenir_provenance(jeu["id"]) or {}
            if st.button("🔎 Contrôler ce jeu de données", key=f"qc_{jeu['id']}"):
                st.session_state["_qc_jeu_suivant"] = jeu["id"]
                st.switch_page(ui.PAGE_CONTROLE)

            vue = st.segmented_control(
                "Afficher", ["Provenance", "Aperçu", "Modifier la provenance", "Supprimer"],
                default="Provenance", key=f"vue_{jeu['id']}", label_visibility="collapsed",
            )
            if vue == "Provenance":
                ui.afficher_provenance(prov, bool(jeu["est_fictif"]))

            elif vue == "Aperçu":
                complet = db.obtenir_jeu(jeu["id"])
                tableau = importation.json_vers_tableau(complet["contenu_brut"])
                st.dataframe(tableau.head(LIGNES_APERCU), width="stretch")
                st.caption(f"Données brutes telles qu'importées ({len(tableau)} lignes).")

            elif vue == "Modifier la provenance":
                st.caption(
                    f"Le fichier d'origine (« {prov.get('fichier_ou_url')} ») et la date d'import "
                    "ne sont pas modifiables."
                )
                with st.form(f"form_prov_{jeu['id']}"):
                    saisie = ui.champs_provenance(prov)
                    if st.form_submit_button("Enregistrer la fiche", type="primary"):
                        try:
                            db.modifier_provenance(jeu["id"], saisie)
                        except ValueError as erreur:
                            st.error(str(erreur), icon="❌")
                        else:
                            st.session_state["_import_message"] = "Fiche de provenance mise à jour."
                            st.rerun()

            elif vue == "Supprimer":
                st.warning("Le jeu de données et sa fiche de provenance seront définitivement effacés. "
                           "La suppression restera notée dans l'historique.")
                confirmer = st.checkbox("Je confirme la suppression", key=f"conf_{jeu['id']}")
                if st.button("Supprimer définitivement", key=f"suppr_{jeu['id']}", disabled=not confirmer):
                    db.supprimer_jeu(jeu["id"])
                    st.session_state["_import_message"] = f"Jeu de données « {jeu['nom']} » supprimé."
                    st.rerun()

# ===========================================================================
# Nouvel import
# ===========================================================================
with onglet_import:
    st.markdown(
        "Formats acceptés : **Excel (.xlsx, .xls)** et **CSV (.csv)**. "
        "Les valeurs sont conservées **exactement comme dans le fichier** : "
        "elles seront interprétées (nombres, unités, virgules) à l'étape *Contrôle qualité*."
    )
    # Le compteur permet de vider la zone de dépôt après un import réussi
    compteur = st.session_state.setdefault("_import_compteur", 0)
    fichier = st.file_uploader(
        "Choisissez ou glissez un fichier", type=list(importation.EXTENSIONS_ACCEPTEES),
        key=f"depot_{compteur}",
        help="Cliquez sur le bouton « Upload » (téléverser) pour choisir un fichier sur votre "
             "ordinateur, ou faites glisser le fichier dans la zone.",
    )
    st.caption("👆 Cliquez sur **Upload** (bouton en anglais, imposé par Streamlit) pour choisir "
               "votre fichier, ou faites-le glisser dans la zone ci-dessus.")

    with st.expander("🧪 Pas de données ? Utiliser le jeu pédagogique FICTIF"):
        st.markdown(
            "Un jeu de **19 lignes inventées** (4 sondages sur 2 sites d'exercice) qui contient "
            "**volontairement des pièges** pour s'exercer à tout le parcours. Il est marqué « fictif » partout "
            "(fiche de provenance, analyses, rapport)."
        )
        c1, c2 = st.columns(2)
        if c1.button("📥 Charger le jeu pédagogique dans ce projet", type="primary"):
            jeu_id = pedagogique.charger(projet["id"], projet.get("auteur"))
            st.session_state["_qc_jeu_suivant"] = jeu_id
            st.session_state["_import_message"] = (
                f"Jeu « {pedagogique.NOM_JEU} » chargé, avec 4 fiches de sondage fictives. Étape suivante : "
                "ouvrez l'onglet « Jeux de données du projet » puis « 🔎 Contrôler ce jeu de données ».")
            st.rerun()
        c2.download_button("⬇️ Télécharger le fichier Excel du jeu", pedagogique.fichier_excel(),
                           file_name=pedagogique.NOM_FICHIER,
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        st.markdown("**Guide de l'exercice — les pièges à trouver :**")
        st.dataframe(pd.DataFrame(pedagogique.PIEGES, columns=["Piège", "Où l'application le signale",
                                                               "Conduite attendue"]),
                     hide_index=True, width="stretch")

    if fichier is not None:
        message = ui_import.assistant_import(
            projet, fichier.getvalue(), fichier.name, cle=f"import_{compteur}", type_source="fichier",
            fichier_ou_url=fichier.name, nom_propose=Path(fichier.name).stem,
        )
        if message:
            st.session_state["_import_compteur"] = compteur + 1
            st.session_state["_import_message"] = message
            st.rerun()
