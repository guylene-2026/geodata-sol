"""Page Analyses : statistiques descriptives et graphiques (phase 6).

Les analyses portent sur la version validée d'un jeu de données. Les résultats
sont présentés en distinguant observations, résultats calculés, estimations,
hypothèses et limites (règle n° 9).
"""

import pandas as pd
import streamlit as st

from geodata import analyse as an, db, importation, ui

projet = ui.exiger_projet()
st.title("📊 Analyses")
st.caption(f"Projet : **{projet['nom']}**")

valides = [j for j in db.lister_jeux(projet["id"]) if j["statut_qc"] == "validé"]
if not valides:
    st.info("Aucun jeu de données validé dans ce projet. Les analyses ne portent que sur des données "
            "contrôlées : terminez d'abord le contrôle qualité.")
    if st.button("🔎 Aller au contrôle qualité"):
        st.switch_page(ui.PAGE_CONTROLE)
    st.stop()

# --- Choix des données ------------------------------------------------------
par_id = {j["id"]: j for j in valides}
jeu_id = st.selectbox("Jeu de données validé", list(par_id), key="analyse_jeu",
                      format_func=lambda i: f"{par_id[i]['nom']} ({par_id[i]['nb_lignes']} lignes)")
jeu = db.obtenir_jeu(jeu_id)
tableau = importation.json_vers_tableau(jeu["contenu_valide"])
description = importation.json_description(jeu["contenu_valide"])
prov = db.obtenir_provenance(jeu_id) or {}
st.caption(f"Source : {prov.get('source') or '—'} · fichier « {prov.get('fichier_ou_url') or '—'} » · "
           f"limites d'usage : {prov.get('limites_usage') or '—'}")
if jeu["est_fictif"]:
    st.warning("Données **FICTIVES** : résultats à usage d'exercice uniquement.", icon="🧪")

numeriques = an.variables_numeriques(description)
groupements = an.variables_groupement(description)
lignes = tableau["N° ligne"]
if not numeriques:
    st.warning("Ce jeu ne contient aucune variable numérique validée.")
    st.stop()


def noter_analyse(type_analyse: str, parametres: dict) -> None:
    """Enregistre l'analyse une seule fois par session et par réglage (pas à chaque clic)."""
    cle = (jeu_id, type_analyse, tuple(sorted(parametres.items())))
    deja = st.session_state.setdefault("_analyses_notees", set())
    if cle not in deja:
        db.enregistrer_analyse(projet["id"], jeu_id, type_analyse, parametres)
        deja.add(cle)


def bloc_hypotheses_limites() -> None:
    col1, col2 = st.columns(2)
    with col1.container(border=True, key="carte_hypotheses"):
        st.markdown("**🧩 Hypothèses**")
        for h in an.HYPOTHESES:
            st.markdown(f"- {h}")
    with col2.container(border=True, key="carte_limites"):
        st.markdown("**⚠️ Limites d'interprétation**")
        for l in an.LIMITES:
            st.markdown(f"- {l}")


def donnees_du_graphique(colonnes: list[str]) -> None:
    """Vue tableau des données tracées (accessibilité, vérification)."""
    with st.expander("📋 Voir les données du graphique"):
        st.dataframe(tableau[["N° ligne", *colonnes]], hide_index=True, width="stretch")


onglets = st.tabs(["📈 Une variable", "🔵 Deux variables et corrélation", "📦 Comparaison de groupes",
                   "📏 Profils en profondeur"])

# ===========================================================================
# Une variable : statistiques + histogramme + boîte à moustaches
# ===========================================================================
with onglets[0]:
    var = st.selectbox("Variable à étudier", numeriques, format_func=lambda v: an.libelle(v, description),
                       key="var_unique")
    unite = description[var].get("unite")
    nom = an.libelle(var, description)
    r = an.statistiques(tableau[var])
    noter_analyse("Statistiques descriptives", {"variable": nom})

    with st.container(border=True, key="carte_observations"):
        st.markdown("**👁️ Observations**")
        st.markdown(
            f"**{r['n']}** valeur(s) de *{nom}* issues du jeu « {jeu['nom']} » "
            f"({len(tableau)} lignes ; {r['n_absentes']} sans valeur retenue : absente, non chiffrable "
            "ou exclue au contrôle qualité)."
        )
    if r["n"] == 0:
        st.warning("Aucune valeur disponible pour cette variable.")
    else:
        calcules, estimations = an.tableau_statistiques(r, unite)
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**🧮 Résultats calculés** *(décrivent exactement les valeurs observées)*")
            st.dataframe(calcules, hide_index=True, width="stretch")
        with col2:
            st.markdown("**📐 Estimations statistiques** *(ce que l'échantillon laisse estimer)*")
            if estimations.empty:
                st.caption("Il faut au moins 2 valeurs pour estimer une dispersion.")
            else:
                st.dataframe(estimations, hide_index=True, width="stretch")
        if r["n"] < 5:
            st.warning(f"Seulement {r['n']} valeur(s) : les statistiques sont très peu fiables.", icon="⚠️")

        proposition = an.classes_sturges(r["n"])
        nb_classes = st.slider("Nombre de classes de l'histogramme", 2, max(30, proposition), proposition,
                               help=f"Proposition : {proposition} classes (règle de Sturges : 1 + log₂ n).")
        col1, col2 = st.columns(2)
        col1.plotly_chart(an.figure_histogramme(tableau[var], nom, nb_classes), width="stretch")
        col2.plotly_chart(an.figure_boite(tableau[var], nom, lignes), width="stretch")
        donnees_du_graphique([var])
        bloc_hypotheses_limites()

# ===========================================================================
# Deux variables : nuage de points
# ===========================================================================
with onglets[1]:
    if len(numeriques) < 2:
        st.info("Il faut au moins deux variables numériques.")
    else:
        col1, col2, col3 = st.columns(3)
        var_x = col1.selectbox("Variable en abscisse (horizontale)", numeriques,
                               format_func=lambda v: an.libelle(v, description), key="var_x")
        autres = [v for v in numeriques if v != var_x]
        var_y = col2.selectbox("Variable en ordonnée (verticale)", autres,
                               format_func=lambda v: an.libelle(v, description), key="var_y")
        couleur = col3.selectbox("Couleur des points selon", [None, *groupements], key="var_couleur",
                                 format_func=lambda v: "Aucune (une seule série)" if v is None else v)
        etiquettes = an.groupes(tableau, couleur, description) if couleur else None
        noter_analyse("Nuage de points", {"x": an.libelle(var_x, description), "y": an.libelle(var_y, description)})
        st.plotly_chart(an.figure_nuage(tableau[var_x], tableau[var_y], an.libelle(var_x, description),
                                        an.libelle(var_y, description), etiquettes, lignes, couleur or ""),
                        width="stretch")
        donnees_du_graphique([var_x, var_y] + ([couleur] if couleur else []))

        # --- Corrélation (règle n° 8) ---------------------------------------
        st.markdown("#### 🔗 Corrélation")
        rc = an.correlations(tableau[var_x], tableau[var_y])
        if "pearson" not in rc:
            st.info(f"Calcul impossible : il faut au moins {an.N_MIN_CORRELATION} couples de valeurs, "
                    f"non toutes identiques (n = {rc['n']}).")
        else:
            noter_analyse("Corrélation", {"x": an.libelle(var_x, description), "y": an.libelle(var_y, description)})
            st.markdown("**📐 Estimations statistiques** *(coefficients calculés sur les n couples du graphique)*")
            st.dataframe(an.tableau_correlations(rc), hide_index=True, width="stretch")
            st.caption("La p-value est la probabilité d'observer une corrélation au moins aussi marquée si, en "
                       "réalité, il n'y en avait aucune. Une p-value < 0,05 est souvent jugée « significative », "
                       "mais elle ne dit rien de l'importance pratique de la relation.")
            if rc["n"] < 10:
                st.warning(f"Seulement {rc['n']} couples de valeurs : coefficients très incertains.", icon="⚠️")
            if rc.get("n_atypiques"):
                if "pearson_sans" in rc:
                    st.info(
                        f"**Sensibilité aux valeurs atypiques** : {rc['n_atypiques']} couple(s) contiennent une "
                        f"valeur atypique (règle de Tukey sur x ou y). Sans eux (n = {rc['n_sans']}) : "
                        f"Pearson r = {an.nombre_fr(rc['pearson_sans'], 3)}, "
                        f"Spearman ρ = {an.nombre_fr(rc['spearman_sans'], 3)}. Un grand écart avec le tableau "
                        "ci-dessus signifie que le résultat dépend de ces quelques valeurs.", icon="🔍")
                else:
                    st.info(f"{rc['n_atypiques']} couple(s) contiennent une valeur atypique ; trop peu de valeurs "
                            "restantes pour recalculer sans eux.", icon="🔍")
            with st.container(border=True, key="carte_limites_correlation"):
                st.markdown("**⚠️ Limites d'interprétation d'une corrélation**")
                for a in an.AVERTISSEMENTS_CORRELATION:
                    st.markdown(f"- {a}")

# ===========================================================================
# Comparaison de groupes
# ===========================================================================
with onglets[2]:
    if not groupements:
        st.info("Aucune colonne de groupe (sondage, nature du sol…) dans ce jeu validé.")
    else:
        col1, col2 = st.columns(2)
        var_c = col1.selectbox("Variable à comparer", numeriques, format_func=lambda v: an.libelle(v, description),
                               key="var_comp")
        groupe = col2.selectbox("Comparer selon", groupements, key="var_groupe")
        etiquettes = an.groupes(tableau, groupe, description)
        nom_c = an.libelle(var_c, description)
        noter_analyse("Comparaison de groupes", {"variable": nom_c, "groupes": groupe})
        st.plotly_chart(an.figure_comparaison(tableau[var_c], etiquettes, nom_c, groupe, lignes), width="stretch")
        st.markdown("**🧮 Résultats calculés par groupe**")
        st.dataframe(an.statistiques_par_groupe(tableau[var_c], etiquettes, description[var_c].get("unite")),
                     hide_index=True, width="stretch")
        st.caption("Des moyennes différentes entre groupes ne prouvent pas une différence réelle de sol : "
                   "avec peu de valeurs par groupe, l'écart peut être dû au hasard.")
        donnees_du_graphique([groupe, var_c])

# ===========================================================================
# Profils en fonction de la profondeur (règle n° 6)
# ===========================================================================
with onglets[3]:
    profondeurs = [t for t, info in description.items() if info.get("role") == "profondeur"]
    mesures = [t for t, info in description.items() if info.get("role") == "mesure"]
    col_sondage = next((t for t, info in description.items() if info.get("role") == "id_sondage"), None)
    if not profondeurs or not mesures:
        st.info("Il faut une colonne de profondeur et au moins une mesure numérique.")
    elif col_sondage is None:
        st.warning("Ce jeu n'a pas d'identifiant de sondage : la localisation des valeurs est inconnue, "
                   "on ne peut pas tracer de profil par sondage sans risquer de mélanger des points "
                   "sans lien entre eux.", icon="📍")
    else:
        col1, col2, col3 = st.columns(3)
        var_p = col1.selectbox("Paramètre", mesures, format_func=lambda v: an.libelle(v, description), key="var_profil")
        col_prof = col2.selectbox("Colonne de profondeur", profondeurs, key="col_prof",
                                  format_func=lambda v: an.libelle(v, description))
        # Site de chaque sondage, d'après les fiches de sondage du projet
        fiches = {s["code"]: s for s in db.lister_sondages(projet["id"])}
        SANS_SITE = "site non renseigné"
        codes = tableau[col_sondage]
        site_de = codes.map(lambda c: None if c is None or pd.isna(c)
                            else (fiches.get(str(c), {}).get("site") or SANS_SITE))
        sites = sorted({s for s in site_de.dropna()})
        if not sites:  # dernier onglet de la page : on peut arrêter ici sans masquer les autres
            st.info("Aucune ligne n'a d'identifiant de sondage : localisation inconnue, pas de profil possible.")
            st.stop()
        site = col3.selectbox("Site", sites, key="site_profil",
                              help="Un profil ne représente qu'un seul site : les sondages de sites "
                                   "différents ne sont jamais fusionnés.")
        if len(sites) > 1:
            st.info(f"Ce jeu contient des sondages de **{len(sites)} sites** ({', '.join(sites)}). "
                    "Ils sont présentés séparément : choisissez le site ci-dessus.", icon="🗺️")
        sans_fiche = sorted({str(c) for c in codes.dropna() if str(c) not in fiches})
        if sans_fiche:
            st.caption(f"Sondages sans fiche dans le projet (site non renseigné) : {', '.join(sans_fiche)}. "
                       "Rattachez ce jeu dans « Sondages et échantillons » pour leur créer une fiche.")
        inconnus = int(codes.isna().sum())
        if inconnus:
            st.caption(f"📍 {inconnus} ligne(s) de localisation inconnue (sans sondage) : non représentées, "
                       "car elles ne peuvent être rattachées à aucun site.")
        selection = tableau[site_de == site]
        par_sondage = st.toggle("Un graphique par sondage (côte à côte)", key="profil_separe")
        noter_analyse("Profil en profondeur", {"paramètre": an.libelle(var_p, description), "site": site})
        st.plotly_chart(an.figure_profils(selection, var_p, col_prof, col_sondage, description, site, par_sondage),
                        width="stretch")
        st.caption("Lecture : chaque courbe est un sondage. Les variations verticales signalent des zones qui "
                   "méritent une analyse complémentaire (changement de couche, erreur possible…) ; elles ne "
                   "suffisent pas à conclure sur le comportement du sol ou la sécurité d'un ouvrage.")
        with st.expander("📋 Voir les données du graphique"):
            st.dataframe(selection[["N° ligne", col_sondage, col_prof, var_p]].sort_values([col_sondage, col_prof]),
                         hide_index=True, width="stretch")
