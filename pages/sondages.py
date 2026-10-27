"""Page Sondages et échantillons : fiches, rattachement des données validées, essais (phase 5)."""

from datetime import date

import pandas as pd
import streamlit as st

from geodata import db, importation, organisation as org, ui

projet = ui.exiger_projet()
st.title("🕳️ Sondages et échantillons")
st.caption(f"Projet : **{projet['nom']}**")
st.caption("Convention : profondeurs en **mètres**, comptées **positivement vers le bas** depuis la surface "
           "du terrain naturel. Une localisation n'est « connue » que si X, Y **et** le système de "
           "coordonnées sont renseignés.")

if message := st.session_state.pop("_sondages_message", None):
    st.success(message, icon="✅")

pid = projet["id"]
# Compteur incrémenté après chaque enregistrement : le formulaire suivant repart vide
compteur = st.session_state.setdefault("_sondages_compteur", 0)
sondages = db.lister_sondages(pid)
echantillons = db.lister_echantillons(pid)
NOUVEAU = 0


def date_iso(d: date | None) -> str | None:
    return d.isoformat() if d else None


def date_depuis_iso(texte: str | None) -> date | None:
    try:
        return date.fromisoformat(texte) if texte else None
    except ValueError:
        return None


def localisation(connue) -> str:
    return "✅ connue" if connue else "❓ inconnue"


onglets = st.tabs([f"Sondages ({len(sondages)})", f"Échantillons ({len(echantillons)})",
                   "🔗 Rattacher un jeu validé", "Résultats d'essais"])

# ===========================================================================
# Sondages
# ===========================================================================
with onglets[0]:
    if sondages:
        st.dataframe(pd.DataFrame([{
            "Sondage": s["code"], "Site": s["site"] or "—", "Localisation": localisation(s["localisation_connue"]),
            "X": s["x"], "Y": s["y"], "Système": s["systeme_coord"] or "—",
            "Profondeur finale (m)": s["profondeur_finale_m"], "Type": s["type_sondage"] or "—",
            "Date": ui.date_fr(s["date_realisation"], False) if s["date_realisation"] else "—",
            "Échantillons": s["nb_echantillons"], "Essais": s["nb_essais"],
        } for s in sondages]), hide_index=True, width="stretch")
    else:
        st.info("Aucun sondage. Créez-en un ci-dessous, ou rattachez un jeu de données validé "
                "(onglet « Rattacher ») pour créer automatiquement les sondages qu'il cite.")

    par_id = {s["id"]: s for s in sondages}
    choix = st.selectbox("Fiche de sondage", [NOUVEAU] + list(par_id), key="choix_sondage",
                         format_func=lambda i: "➕ Nouveau sondage" if i == NOUVEAU else f"✏️ Modifier « {par_id[i]['code']} »")
    s = par_id.get(choix, {})
    with st.form(f"form_sondage_{choix}_{compteur}"):
        c1, c2, c3 = st.columns(3)
        code = c1.text_input("Identifiant du sondage *", value=s.get("code") or "", placeholder="ex. SC1")
        site = c2.text_input("Site", value=s.get("site") or projet.get("localisation") or "",
                             help="Deux sites différents ne sont jamais fusionnés dans les profils.")
        type_actuel = s.get("type_sondage")
        type_sondage = c3.selectbox("Type de sondage", org.TYPES_SONDAGE,
                                    index=org.TYPES_SONDAGE.index(type_actuel) if type_actuel in org.TYPES_SONDAGE else None,
                                    placeholder="Choisir…")
        st.markdown("**Localisation**")
        c1, c2, c3, c4 = st.columns([1, 1, 1, 2])
        x = c1.number_input("X (ou longitude)", value=s.get("x"), format="%.6f", step=None)
        y = c2.number_input("Y (ou latitude)", value=s.get("y"), format="%.6f", step=None)
        z = c3.number_input("Cote du terrain Z (m)", value=s.get("z_terrain"), format="%.2f", step=None)
        sys_actuel = s.get("systeme_coord")
        systeme = c4.selectbox("Système de coordonnées", org.SYSTEMES_COORDONNEES,
                               index=org.SYSTEMES_COORDONNEES.index(sys_actuel)
                               if sys_actuel in org.SYSTEMES_COORDONNEES else len(org.SYSTEMES_COORDONNEES) - 1)
        st.markdown("**Réalisation**")
        c1, c2, c3, c4 = st.columns(4)
        prof = c1.number_input("Profondeur finale (m)", value=s.get("profondeur_finale_m"), min_value=0.0,
                               format="%.2f", step=None)
        date_real = c2.date_input("Date de réalisation", value=date_depuis_iso(s.get("date_realisation")),
                                  format="DD/MM/YYYY")
        entreprise = c3.text_input("Entreprise responsable", value=s.get("entreprise") or "")
        methode = c4.text_input("Méthode d'investigation", value=s.get("methode") or "",
                                placeholder="ex. carottier double, Ø 100 mm")
        observations = st.text_area("Observations de terrain", value=s.get("observations") or "")
        envoyer = st.form_submit_button("Enregistrer le sondage", type="primary")
    if envoyer:
        fiche = {"code": code, "site": site, "x": x, "y": y, "z_terrain": z, "systeme_coord": systeme,
                 "profondeur_finale_m": prof, "date_realisation": date_iso(date_real),
                 "type_sondage": type_sondage, "entreprise": entreprise, "methode": methode,
                 "observations": observations}
        try:
            db.enregistrer_sondage(pid, fiche, None if choix == NOUVEAU else choix)
        except ValueError as e:
            st.error(str(e), icon="❌")
        else:
            connue = org.localisation_connue(x, y, systeme)
            st.session_state["_sondages_compteur"] = compteur + 1
            st.session_state["_sondages_message"] = (
                f"Sondage « {code.strip()} » enregistré — localisation {'connue' if connue else 'inconnue'}.")
            st.rerun()
    if choix != NOUVEAU:
        with st.expander("🗑️ Supprimer ce sondage"):
            st.warning("Ses échantillons et résultats d'essais sont conservés, mais ne seront plus rattachés "
                       "à un sondage : leur localisation deviendra **inconnue**.")
            if st.checkbox("Je confirme la suppression", key=f"conf_s_{choix}") and \
                    st.button("Supprimer le sondage", key=f"suppr_s_{choix}"):
                db.supprimer_sondage(choix)
                st.session_state.pop("choix_sondage", None)
                st.session_state["_sondages_message"] = f"Sondage « {s['code']} » supprimé."
                st.rerun()

# ===========================================================================
# Échantillons
# ===========================================================================
with onglets[1]:
    if echantillons:
        st.dataframe(pd.DataFrame([{
            "Échantillon": e["code"], "Sondage": e["code_sondage"] or "❓ aucun (localisation inconnue)",
            "Profondeur haut (m)": e["profondeur_haut_m"], "Profondeur bas (m)": e["profondeur_bas_m"],
            "Nature du sol": e["nature_sol"] or "—", "Type": e["type_echantillon"] or "—",
            "Date": ui.date_fr(e["date_prelevement"], False) if e["date_prelevement"] else "—",
            "Essais": e["nb_essais"],
        } for e in echantillons]), hide_index=True, width="stretch")
    else:
        st.info("Aucun échantillon pour l'instant.")

    par_id_e = {e["id"]: e for e in echantillons}
    choix_e = st.selectbox("Fiche d'échantillon", [NOUVEAU] + list(par_id_e), key="choix_echantillon",
                           format_func=lambda i: "➕ Nouvel échantillon" if i == NOUVEAU
                           else f"✏️ Modifier « {par_id_e[i]['code']} »")
    e = par_id_e.get(choix_e, {})
    options_sondage = [None] + [s["id"] for s in sondages]
    with st.form(f"form_echantillon_{choix_e}_{compteur}"):
        c1, c2, c3 = st.columns(3)
        code_e = c1.text_input("Identifiant de l'échantillon *", value=e.get("code") or "", placeholder="ex. ECH-01")
        sondage_id = c2.selectbox(
            "Sondage", options_sondage,
            index=options_sondage.index(e.get("sondage_id")) if e.get("sondage_id") in options_sondage else 0,
            format_func=lambda i: "Aucun — localisation inconnue" if i is None else par_id[i]["code"],
        )
        type_e = c3.selectbox("Type d'échantillon", org.TYPES_ECHANTILLON,
                              index=org.TYPES_ECHANTILLON.index(e["type_echantillon"])
                              if e.get("type_echantillon") in org.TYPES_ECHANTILLON else None,
                              placeholder="Choisir…")
        c1, c2, c3 = st.columns(3)
        haut = c1.number_input("Profondeur de prélèvement — haut (m)", value=e.get("profondeur_haut_m"),
                               min_value=0.0, format="%.2f", step=None)
        bas = c2.number_input("Profondeur de prélèvement — bas (m)", value=e.get("profondeur_bas_m"),
                              min_value=0.0, format="%.2f", step=None)
        date_e = c3.date_input("Date de prélèvement", value=date_depuis_iso(e.get("date_prelevement")),
                               format="DD/MM/YYYY")
        nature = st.text_input("Nature du sol observée", value=e.get("nature_sol") or "",
                               placeholder="ex. argile limoneuse brune")
        obs_e = st.text_area("Observations", value=e.get("observations") or "")
        envoyer_e = st.form_submit_button("Enregistrer l'échantillon", type="primary")
    if envoyer_e:
        fiche = {"code": code_e, "sondage_id": sondage_id, "profondeur_haut_m": haut, "profondeur_bas_m": bas,
                 "date_prelevement": date_iso(date_e), "nature_sol": nature, "type_echantillon": type_e,
                 "observations": obs_e}
        try:
            db.enregistrer_echantillon(pid, fiche, None if choix_e == NOUVEAU else choix_e)
        except ValueError as err:
            st.error(str(err), icon="❌")
        else:
            st.session_state["_sondages_compteur"] = compteur + 1
            st.session_state["_sondages_message"] = f"Échantillon « {code_e.strip()} » enregistré."
            st.rerun()
    if choix_e != NOUVEAU:
        with st.expander("🗑️ Supprimer cet échantillon"):
            if st.checkbox("Je confirme la suppression", key=f"conf_e_{choix_e}") and \
                    st.button("Supprimer l'échantillon", key=f"suppr_e_{choix_e}"):
                db.supprimer_echantillon(choix_e)
                st.session_state.pop("choix_echantillon", None)
                st.session_state["_sondages_message"] = f"Échantillon « {e['code']} » supprimé."
                st.rerun()

# ===========================================================================
# Rattacher un jeu validé
# ===========================================================================
with onglets[2]:
    st.markdown("Relie chaque résultat d'un jeu de données **validé** à son **sondage**, son **échantillon** "
                "et sa **profondeur**. Les fiches manquantes sont créées (à compléter ensuite).")
    valides = [j for j in db.lister_jeux(pid) if j["statut_qc"] == "validé"]
    deja = db.jeux_rattaches(pid)
    if not valides:
        st.info("Aucun jeu de données validé dans ce projet. Terminez d'abord le contrôle qualité.")
        if st.button("🔎 Aller au contrôle qualité"):
            st.switch_page(ui.PAGE_CONTROLE)
    else:
        par_id_j = {j["id"]: j for j in valides}
        jeu_id = st.selectbox(
            "Jeu de données validé", list(par_id_j),
            format_func=lambda i: f"{par_id_j[i]['nom']} ({par_id_j[i]['nb_lignes']} lignes)"
                                  + (f" — déjà rattaché : {deja[i]} essai(s)" if i in deja else ""),
        )
        jeu = db.obtenir_jeu(jeu_id)
        tableau = importation.json_vers_tableau(jeu["contenu_valide"])
        description = importation.json_description(jeu["contenu_valide"])
        roles = org.colonnes_par_role(description)
        col_prof = None
        if len(roles.get("profondeur", [])) > 1:
            col_prof = st.selectbox("Plusieurs colonnes de profondeur : laquelle utiliser ?", roles["profondeur"])
        plan = org.preparer_rattachement(tableau, description, {s["code"] for s in sondages},
                                         {e["code"] for e in echantillons}, col_prof)

        if not plan.mesures:
            st.warning("Ce jeu ne contient aucune colonne de **mesure numérique** : rien à rattacher.")
        else:
            c1, c2, c3 = st.columns(3)
            c1.metric("Sondages cités", len(plan.sondages_cites), border=True)
            c2.metric("Échantillons cités", len(plan.echantillons_cites), border=True)
            c3.metric("Résultats d'essais", plan.nb_essais, border=True)

            if plan.col_sondage is None:
                st.warning("Ce jeu n'a pas de colonne d'identifiant de sondage : **tous** ses résultats seront "
                           "enregistrés avec une localisation **inconnue**.", icon="📍")
            else:
                existants = [c for c in plan.sondages_cites if c not in plan.sondages_nouveaux]
                if existants:
                    st.markdown("**Sondages existants :** " + ", ".join(existants))
                if plan.sondages_nouveaux:
                    st.markdown("**Fiches de sondage qui seront créées** (localisation inconnue, à compléter) : "
                                + ", ".join(plan.sondages_nouveaux))
            if plan.lignes_sans_sondage and plan.col_sondage:
                st.warning(f"Lignes sans identifiant de sondage : {', '.join(map(str, plan.lignes_sans_sondage))}. "
                           "Leurs résultats seront marqués **localisation inconnue**.", icon="📍")
            if plan.echantillons_nouveaux:
                st.markdown("**Fiches d'échantillon qui seront créées :** " + ", ".join(plan.echantillons_nouveaux))
            if plan.echantillons_conflits:
                st.warning("Identifiants d'échantillon cités avec des sondages différents : "
                           + ", ".join(plan.echantillons_conflits) + ". Ils seront rattachés au premier sondage "
                           "rencontré : vérifiez le fichier.", icon="⚠️")
            if plan.col_profondeur is None:
                st.info("Pas de colonne de profondeur : les résultats n'auront pas de profondeur.")
            elif plan.facteur_profondeur != 1:
                st.warning(f"Les profondeurs de ce jeu sont en **{plan.unite_profondeur}** : elles seront "
                           f"converties en mètres (× {plan.facteur_profondeur:g}) pour les fiches et les essais. "
                           "En cliquant sur « Rattacher », vous validez cette conversion.", icon="📏")

            site = st.text_input("Site des nouveaux sondages", value=projet.get("localisation") or "",
                                 help="Les profils en profondeur ne mélangent jamais deux sites différents.")
            st.markdown("**Type d'essai de chaque mesure :**")
            types_essai = {}
            colonnes_types = st.columns(min(3, len(plan.mesures)))
            for i, m in enumerate(plan.mesures):
                proposition = org.suggerer_type_essai(m)
                types_essai[m] = colonnes_types[i % 3].selectbox(
                    f"{m} ({description[m].get('unite') or 'sans unité'})", org.TYPES_ESSAI,
                    index=org.TYPES_ESSAI.index(proposition), key=f"type_{jeu_id}_{m}")
            if jeu_id in deja:
                st.caption(f"Ce jeu est déjà rattaché ({deja[jeu_id]} essais) : le rattachement sera "
                           "**remplacé**, sans créer de doublons.")
            if st.button("🔗 Rattacher les résultats", type="primary"):
                essais = org.generer_essais(tableau, description, plan, types_essai)
                details = (f"Jeu « {jeu['nom']} » : {len(essais)} résultat(s) d'essais, "
                           f"{len(plan.sondages_nouveaux)} sondage(s) créé(s), "
                           f"{len(plan.echantillons_nouveaux)} échantillon(s) créé(s)"
                           + (f", {len(plan.lignes_sans_sondage)} ligne(s) sans sondage (localisation inconnue)"
                              if plan.lignes_sans_sondage else "")
                           + (f", profondeurs converties {plan.unite_profondeur} → m (× {plan.facteur_profondeur:g})"
                              if plan.facteur_profondeur != 1 else "") + ".")
                nouveaux_e = {c: plan.echantillons_cites[c] for c in plan.echantillons_nouveaux}
                db.rattacher_jeu(pid, jeu_id, essais, plan.sondages_nouveaux, nouveaux_e, site or None, details)
                st.session_state["_sondages_message"] = details
                st.rerun()

# ===========================================================================
# Résultats d'essais
# ===========================================================================
with onglets[3]:
    essais = db.lister_essais(pid)
    if not essais:
        st.info("Aucun résultat d'essai rattaché. Utilisez l'onglet « Rattacher un jeu validé ».")
    else:
        tableau = pd.DataFrame([{
            "Sondage": t["code_sondage"] or "❓ localisation inconnue",
            "Site": t["site"] or "—",
            "Échantillon": t["code_echantillon"] or "—",
            "Profondeur (m)": t["profondeur_m"],
            "Type d'essai": t["type_essai"],
            "Paramètre": t["parametre"],
            "Valeur": t["valeur"],
            "Unité": t["unite"] or "—",
            "Nature": t["nature_resultat"],
            "Jeu de données": t["jeu_nom"] or "—",
            "Remarques": t["remarques"] or "",
        } for t in essais])
        c1, c2 = st.columns(2)
        f_sondage = c1.multiselect("Filtrer par sondage", sorted(tableau["Sondage"].unique()), placeholder="Tous")
        f_type = c2.multiselect("Filtrer par type d'essai", sorted(tableau["Type d'essai"].unique()), placeholder="Tous")
        if f_sondage:
            tableau = tableau[tableau["Sondage"].isin(f_sondage)]
        if f_type:
            tableau = tableau[tableau["Type d'essai"].isin(f_type)]
        inconnus = (tableau["Sondage"] == "❓ localisation inconnue").sum()
        st.caption(f"{len(tableau)} résultat(s)" + (f", dont {inconnus} de localisation inconnue" if inconnus else "")
                   + ". « observation » = valeur mesurée (éventuellement convertie d'unité après validation).")
        st.dataframe(tableau, hide_index=True, width="stretch")
