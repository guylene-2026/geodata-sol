"""Page Projets : créer, ouvrir et modifier un projet d'étude géotechnique."""

import streamlit as st

from geodata import db, ui

TYPES_OUVRAGE = [
    "Bâtiment",
    "Route / voirie",
    "Pont / ouvrage d'art",
    "Barrage / digue",
    "Mur de soutènement",
    "Remblai / terrassement",
    "Ouvrage industriel",
    "Travail pédagogique (TP)",
]
NIVEAUX_CONFIDENTIALITE = ["Public", "Interne", "Confidentiel"]

MODES = {
    "ouvrir": "📂 Mes projets",
    "nouveau": "➕ Nouveau projet",
    "fiche": "✏️ Fiche du projet ouvert",
}


def formulaire_projet(cle: str, valeurs: dict, libelle_bouton: str) -> dict | None:
    """Affiche la fiche projet à remplir. Renvoie les valeurs saisies quand
    l'utilisateur clique sur le bouton, sinon None."""
    with st.form(cle):
        nom = st.text_input("Nom du projet *", value=valeurs.get("nom") or "",
                            placeholder="ex. Extension du lycée Jean Moulin")
        col1, col2 = st.columns(2)
        localisation = col1.text_input(
            "Localisation", value=valeurs.get("localisation") or "",
            placeholder="ville, quartier, adresse…",
        )
        type_actuel = valeurs.get("type_ouvrage")
        options = TYPES_OUVRAGE + ([type_actuel] if type_actuel and type_actuel not in TYPES_OUVRAGE else [])
        type_ouvrage = col2.selectbox(
            "Type d'ouvrage", options,
            index=options.index(type_actuel) if type_actuel else None,
            placeholder="Choisir dans la liste ou écrire un autre type",
            accept_new_options=True,
        )
        description = st.text_area(
            "Description et informations disponibles",
            value=valeurs.get("description") or "",
            placeholder="Objectif de l'étude, essais prévus ou réalisés, documents disponibles…",
        )
        col3, col4 = st.columns(2)
        auteur = col3.text_input("Auteur / responsable", value=valeurs.get("auteur") or "")
        conf_actuelle = valeurs.get("confidentialite") or "Public"
        confidentialite = col4.radio(
            "Confidentialité des données", NIVEAUX_CONFIDENTIALITE,
            index=NIVEAUX_CONFIDENTIALITE.index(conf_actuelle) if conf_actuelle in NIVEAUX_CONFIDENTIALITE else 0,
            horizontal=True,
        )
        acces_autorise = st.text_input(
            "Personnes autorisées à consulter (si données internes ou confidentielles)",
            value=valeurs.get("acces_autorise") or "",
        )
        st.caption("* champ obligatoire")
        if st.form_submit_button(libelle_bouton, type="primary"):
            return {
                "nom": nom, "localisation": localisation, "type_ouvrage": type_ouvrage,
                "description": description, "auteur": auteur,
                "confidentialite": confidentialite, "acces_autorise": acces_autorise,
            }
    return None


def changer_mode(mode: str) -> None:
    """Demande l'affichage d'un autre onglet au prochain rechargement de la page."""
    st.session_state["_projets_mode_suivant"] = mode


# ---------------------------------------------------------------------------
st.title("📁 Projets")

# Message laissé par l'action précédente (création, modification…)
if message := st.session_state.pop("_projets_message", None):
    st.success(message, icon="✅")

# Choix de l'onglet (peut être imposé par la page d'accueil ou une action)
if mode_suivant := st.session_state.pop("_projets_mode_suivant", None):
    st.session_state["projets_mode"] = mode_suivant
if st.session_state.get("projets_mode") not in MODES:
    st.session_state["projets_mode"] = "ouvrir"

mode = st.radio(
    "Que voulez-vous faire ?", list(MODES), format_func=MODES.get,
    key="projets_mode", horizontal=True, label_visibility="collapsed",
)
st.divider()

# --- Liste des projets -----------------------------------------------------
if mode == "ouvrir":
    projets = db.lister_projets()
    if not projets:
        st.info("Aucun projet enregistré pour l'instant. Commencez par en créer un.")
        if st.button("➕ Créer mon premier projet", type="primary"):
            changer_mode("nouveau")
            st.rerun()
    else:
        st.caption(f"{len(projets)} projet(s) enregistré(s), du plus récent au plus ancien.")
        actif_id = st.session_state.get("projet_id")
        for p in projets:
            with st.container(border=True, key=f"carte_projet_{p['id']}"):
                col_info, col_bouton = st.columns([4, 1], vertical_alignment="center")
                with col_info:
                    titre = f"**{p['nom']}**" + ("  🟢 *ouvert*" if p["id"] == actif_id else "")
                    st.markdown(titre)
                    details = [
                        f"📍 {p['localisation'] or 'localisation non renseignée'}",
                        f"🏗️ {p['type_ouvrage'] or 'type non renseigné'}",
                        f"🔒 {p['confidentialite'] or '—'}",
                    ]
                    st.caption(" · ".join(details))
                    st.caption(
                        f"{p['nb_jeux']} jeu(x) de données · {p['nb_sondages']} sondage(s) · "
                        f"créé le {ui.date_fr(p['date_creation'], False)} · "
                        f"modifié le {ui.date_fr(p['date_modification'])}"
                    )
                with col_bouton:
                    if st.button("Ouvrir", key=f"ouvrir_{p['id']}", width="stretch",
                                 type="primary" if p["id"] != actif_id else "secondary"):
                        ui.ouvrir_projet(p["id"])
                        st.session_state["_projets_message"] = f"Projet « {p['nom']} » ouvert."
                        changer_mode("fiche")
                        st.rerun()

# --- Nouveau projet --------------------------------------------------------
elif mode == "nouveau":
    st.subheader("Fiche du nouveau projet")
    saisie = formulaire_projet("form_nouveau", {}, "Enregistrer le projet")
    if saisie is not None:
        try:
            nouvel_id = db.creer_projet(saisie)
        except ValueError as erreur:
            st.error(str(erreur), icon="❌")
        else:
            ui.ouvrir_projet(nouvel_id)
            st.session_state["_projets_message"] = (
                f"Projet « {saisie['nom'].strip()} » enregistré et ouvert."
            )
            changer_mode("fiche")
            st.rerun()

# --- Fiche du projet ouvert ------------------------------------------------
else:
    projet = ui.projet_actif()
    if projet is None:
        st.info("Aucun projet n'est ouvert. Choisissez-en un dans « Mes projets » ou créez-en un.")
    else:
        st.subheader(f"Fiche du projet « {projet['nom']} »")
        st.caption(
            f"Créé le {ui.date_fr(projet['date_creation'])} · "
            f"dernière modification le {ui.date_fr(projet['date_modification'])}"
        )

        # Suite du parcours
        st.markdown("**Étape suivante :**")
        c1, c2, c3 = st.columns(3)
        if c1.button("📥 Importer des données", width="stretch"):
            st.switch_page(ui.PAGE_IMPORT)
        if c2.button("🌐 Collecte en ligne", width="stretch"):
            st.switch_page(ui.PAGE_SOURCES)
        if c3.button("🕳️ Sondages et échantillons", width="stretch"):
            st.switch_page(ui.PAGE_SONDAGES)

        st.markdown("**Modifier la fiche :**")
        saisie = formulaire_projet(f"form_fiche_{projet['id']}", projet, "Enregistrer les modifications")
        if saisie is not None:
            try:
                db.modifier_projet(projet["id"], saisie)
            except ValueError as erreur:
                st.error(str(erreur), icon="❌")
            else:
                ui.ouvrir_projet(projet["id"])  # met à jour le nom affiché à gauche
                st.session_state["_projets_message"] = "Modifications enregistrées."
                st.rerun()

        # Dernières opérations du projet
        with st.expander("🕘 Dernières opérations sur ce projet"):
            operations = db.lister_historique(projet["id"], limite=10)
            for op in operations:
                st.markdown(f"- {ui.date_fr(op['date_operation'])} — **{op['operation']}** : {op['details'] or ''}")
            if not operations:
                st.caption("Aucune opération enregistrée.")

        # Suppression, protégée par une confirmation
        with st.expander("🗑️ Supprimer ce projet"):
            st.warning(
                "La suppression efface définitivement le projet **et toutes ses données** "
                "(jeux de données, sondages, échantillons, essais, historique).",
            )
            confirmation = st.text_input(f"Pour confirmer, tapez le nom exact du projet : {projet['nom']}")
            if st.button("Supprimer définitivement", disabled=confirmation.strip() != projet["nom"]):
                db.supprimer_projet(projet["id"])
                ui.fermer_projet()
                st.session_state["_projets_message"] = f"Projet « {projet['nom']} » supprimé."
                changer_mode("ouvrir")
                st.rerun()
