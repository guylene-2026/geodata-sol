"""Page Collecte en ligne : sources de données publiques et import d'un fichier par URL (phase 8)."""

from pathlib import PurePosixPath

import streamlit as st

from geodata import collecte, ui, ui_import

st.title("🌐 Collecte de données en ligne")

if message := st.session_state.pop("_collecte_message", None):
    st.success(message, icon="✅")

onglet_sources, onglet_url = st.tabs(["📚 Sources de données", "⬇️ Importer depuis une adresse (URL)"])

# ===========================================================================
# Sources de données publiques
# ===========================================================================
with onglet_sources:
    st.markdown(
        "Ressources publiques utiles pour trouver des données géotechniques, **en commençant par le Cameroun**. "
        "La plupart ouvrent des **portails** : "
        "repérez-y un fichier **CSV ou Excel**, copiez l'adresse de son lien de téléchargement "
        "(clic droit → « Copier l'adresse du lien »), puis collez-la dans l'onglet "
        "« Importer depuis une adresse »."
    )
    for i, s in enumerate(collecte.SOURCES):
        with st.container(border=True, key=f"carte_source_{i}"):
            st.markdown(f"**{s['nom']}**")
            st.caption(f"🌍 {s['pays']} — {s['organisme']}")
            if s["url"]:
                st.markdown(f"🔗 [{s['url']}]({s['url']})")
            st.markdown(f"**Contenu :** {s['contenu']}")
            st.markdown(f"**Formats :** {s['formats']}")
            st.caption(f"⚠️ {s['remarques']}")
            for j, (libelle, adresse) in enumerate(s.get("fichiers", {}).items()):
                c1, c2 = st.columns([3, 1], vertical_alignment="center")
                c1.markdown(f"📄 **{libelle}**")
                c1.code(adresse, language=None)
                if c2.button("📥 Utiliser ce fichier", key=f"utiliser_{i}_{j}"):
                    if ui.projet_actif() is None:
                        st.warning("Ouvrez d'abord un projet (page Projets).", icon="📁")
                    else:
                        try:
                            with st.spinner("Téléchargement en cours…"):
                                st.session_state["_telechargement"] = collecte.telecharger(adresse)
                            compteur = st.session_state.setdefault("_collecte_compteur", 0)
                            st.session_state[f"url_{compteur}"] = adresse
                            st.success("Fichier téléchargé. Ouvrez l'onglet **« ⬇️ Importer depuis une adresse "
                                       "(URL) »** pour vérifier l'aperçu et enregistrer.", icon="✅")
                        except ValueError as erreur:
                            st.error(str(erreur), icon="❌")
    st.info("Avant d'utiliser des données publiques : lisez leur **licence**, notez leur **producteur** et leur "
            "**date**, et vérifiez qu'elles concernent bien votre site. Des données d'un autre site ne "
            "remplacent pas une campagne d'investigation.", icon="ℹ️")

# ===========================================================================
# Import par URL directe
# ===========================================================================
with onglet_url:
    projet = ui.projet_actif()
    if projet is None:
        st.warning("Ouvrez d'abord un projet : le fichier téléchargé y sera rattaché.", icon="📁")
        if st.button("Aller à la page Projets"):
            st.switch_page(ui.PAGE_PROJETS)
    else:
        st.caption(f"Projet : **{projet['nom']}**")
        st.markdown(
            "Collez l'adresse **directe** d'un fichier **CSV, XLSX ou XLS** accessible publiquement "
            f"(taille maximale {collecte.TAILLE_MAX_MO} Mo). L'adresse, la date du téléchargement et une "
            "empreinte du fichier seront conservées dans la fiche de provenance."
        )
        compteur = st.session_state.setdefault("_collecte_compteur", 0)
        url = st.text_input("Adresse (URL) du fichier", key=f"url_{compteur}",
                            placeholder="https://exemple.fr/donnees/essais.csv")
        col1, col2 = st.columns([1, 4])
        if col1.button("⬇️ Télécharger", type="primary"):
            try:
                with st.spinner("Téléchargement en cours…"):
                    st.session_state["_telechargement"] = collecte.telecharger(url)
            except ValueError as erreur:
                st.session_state.pop("_telechargement", None)
                st.error(str(erreur), icon="❌")

        tele: collecte.Telechargement | None = st.session_state.get("_telechargement")
        if tele is not None:
            if col2.button("✖ Abandonner ce fichier"):
                st.session_state.pop("_telechargement", None)
                st.rerun()
            with st.container(border=True, key="carte_telechargement"):
                st.markdown(f"**Fichier téléchargé :** {tele.nom_fichier} ({tele.format.upper()}, "
                            f"{collecte.taille_lisible(tele.taille)})")
                st.caption(tele.resume())
            message = ui_import.assistant_import(
                projet, tele.contenu, tele.nom_fichier, cle=f"url_import_{compteur}", type_source="url",
                fichier_ou_url=tele.url, nom_propose=PurePosixPath(tele.nom_fichier).stem,
                provenance_initiale={"source": collecte.source_proposee(tele.url), "remarques": tele.resume(),
                                     **collecte.PROVENANCES_CONNUES.get(tele.url, {})},
                details_supplementaires=tele.resume(),
            )
            if message:
                st.session_state.pop("_telechargement", None)
                st.session_state["_collecte_compteur"] = compteur + 1
                st.session_state["_collecte_message"] = message
                st.rerun()
