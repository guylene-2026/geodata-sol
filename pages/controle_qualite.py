"""Page Contrôle qualité : structure, interprétation des valeurs, doublons,
valeurs atypiques et validation d'un jeu de données (phase 4).

Rien n'est corrigé automatiquement : la page montre ce qui a été détecté,
propose, et enregistre les décisions de l'utilisateur (avec leur justification).
"""

import pandas as pd
import streamlit as st

from geodata import db, importation, qualite as q, ui

projet = ui.exiger_projet()
st.title("🔎 Contrôle qualité")
st.caption(f"Projet : **{projet['nom']}**")

jeux = db.lister_jeux(projet["id"])
if not jeux:
    st.info("Aucun jeu de données dans ce projet. Importez d'abord un fichier.")
    if st.button("📥 Importer des données"):
        st.switch_page(ui.PAGE_IMPORT)
    st.stop()

if message := st.session_state.pop("_qc_message", None):
    st.success(message, icon="✅")

# --- Choix du jeu de données ------------------------------------------------
ids = [j["id"] for j in jeux]
if (suivant := st.session_state.pop("_qc_jeu_suivant", None)) in ids:
    st.session_state["qc_jeu_id"] = suivant
if st.session_state.get("qc_jeu_id") not in ids:
    st.session_state["qc_jeu_id"] = ids[0]
noms = {j["id"]: j for j in jeux}
LIBELLES_DECISION = {"à vérifier": "⏳ À vérifier", "vérifiée - conservée": "✅ Vérifiée — conservée",
                     "exclue de l'analyse": "🚫 Exclue de l'analyse"}
ICONES_STATUT = {"non vérifié": "⚪", "en cours": "🟠", "validé": "🟢"}
jeu_id = st.selectbox(
    "Jeu de données à contrôler", ids, key="qc_jeu_id",
    format_func=lambda i: f"{ICONES_STATUT.get(noms[i]['statut_qc'], '⚪')} {noms[i]['nom']} "
                          f"({noms[i]['nb_lignes']} lignes) — {noms[i]['statut_qc']}",
)
jeu = db.obtenir_jeu(jeu_id)
brut = importation.json_vers_tableau(jeu["contenu_brut"])
colonnes = db.lister_colonnes(jeu_id)
prov = db.obtenir_provenance(jeu_id) or {}
st.caption(
    f"Source : {prov.get('source') or '—'} · fichier « {prov.get('fichier_ou_url') or '—'} » · "
    f"limites d'usage : {prov.get('limites_usage') or '—'}"
    + (" · 🧪 **données fictives**" if jeu["est_fictif"] else "")
)

profils = {c["nom_origine"]: q.profiler_colonne(c["nom_origine"], brut[c["nom_origine"]]) for c in colonnes}
structure_ok = all(c["unite_confirmee"] for c in colonnes)
col_numeriques = [c for c in colonnes if c["role"] in q.ROLES_NUMERIQUES]
col_sondage = next((c for c in colonnes if c["role"] == "id_sondage"), None)
auteur = projet.get("auteur")
version = st.session_state.setdefault(f"_qc_version_{jeu_id}", 0)


def nouvelle_version() -> None:
    """Après un enregistrement : réinitialise les tableaux modifiables de la page."""
    st.session_state[f"_qc_version_{jeu_id}"] = version + 1


def titre_colonne(c: dict) -> str:
    """« Teneur en eau (%) » à partir de la description d'une colonne."""
    nom = c["variable"] or c["nom_origine"]
    return f"{nom} ({c['unite']})" if c["unite"] else nom


def requis_colonne(c: dict) -> dict:
    return q.decisions_requises(c["nom_origine"], profils[c["nom_origine"]], c["role"], c["unite"])


def colonne_interpretee(c: dict) -> bool:
    return q.interpretation_complete(requis_colonne(c), c["interpretation"])


def basculer_option(cle_widget: str, option: str, lignes: list[int], texte_oui: str, texte_non: str) -> None:
    """Enregistre immédiatement une option cochée/décochée (doublons, lignes de synthèse)."""
    exclure = bool(st.session_state[cle_widget])
    texte = texte_oui if exclure else texte_non
    db.enregistrer_option_qc(jeu_id, option, exclure, texte, lignes, auteur)
    st.session_state["_qc_message"] = texte


def lignes_hors_analyse() -> set[int]:
    """Lignes exclues par décision de l'utilisateur (copies de doublons, lignes de synthèse)."""
    options = db.lire_options_qc(jeu_id)
    exclues = set()
    if options.get("exclure_doublons"):
        exclues |= {l for g in q.doublons_exacts(brut) for l in g[1:]}
    if options.get("exclure_synthese"):
        exclues |= {l for l, _ in q.lignes_synthese(brut)}
    return exclues


def valeurs_pour_atypiques(c: dict) -> pd.Series:
    """Valeurs interprétées d'une colonne, sans les lignes exclues de l'analyse."""
    valeurs = q.interpreter_colonne(c["nom_origine"], brut[c["nom_origine"]], c["role"], c["unite"],
                                    c["interpretation"])["valeur"].astype(object)
    for l in lignes_hors_analyse():
        valeurs.loc[l - 1] = None
    return valeurs


onglets = st.tabs(["1. Structure", "2. Interprétation des valeurs", "3. Doublons et identifiants",
                   "4. Valeurs atypiques", "5. Validation"])

# ===========================================================================
# 1. Structure des colonnes
# ===========================================================================
with onglets[0]:
    st.markdown(
        "Pour chaque colonne, indiquez **ce qu'elle contient**, le **nom de la variable** et son "
        "**unité**. Les propositions viennent du nom de la colonne et de son contenu : "
        "vérifiez-les, elles ne sont pas enregistrées tant que vous n'avez pas confirmé."
    )
    lignes_editeur = []
    for c in colonnes:
        p = profils[c["nom_origine"]]
        role = c["role"] if c["unite_confirmee"] else q.suggerer_role(c["nom_origine"], p)
        unite = c["unite"] if c["unite_confirmee"] else q.suggerer_unite(c["nom_origine"], p, role)
        variable = c["variable"] if c["unite_confirmee"] else q.nom_sans_unite(c["nom_origine"])
        exemples = [str(v) for v in brut[c["nom_origine"]].dropna().head(3)]
        lignes_editeur.append({
            "Colonne du fichier": c["nom_origine"],
            "Exemples": " | ".join(exemples),
            "Type détecté": p.type_detecte,
            "Vides": p.comptes["manquant"],
            "Rôle": q.ROLES[role],
            "Nom de variable": variable,
            "Unité": unite if unite else ("sans unité" if c["unite_confirmee"] else None),
        })
    edite = st.data_editor(
        pd.DataFrame(lignes_editeur), hide_index=True, width="stretch",
        key=f"editeur_structure_{jeu_id}_{version}",
        disabled=["Colonne du fichier", "Exemples", "Type détecté", "Vides"],
        column_config={
            "Rôle": st.column_config.SelectboxColumn(options=list(q.ROLES.values()), required=True),
            "Unité": st.column_config.SelectboxColumn(
                options=q.UNITES_PROPOSEES,
                help="Obligatoire pour les profondeurs et les mesures (choisir « sans unité » si besoin).",
            ),
            "Vides": st.column_config.NumberColumn(help="Nombre de cellules vides"),
        },
    )
    st.caption("✏️ Pour modifier une case (Rôle, Nom de variable, Unité), **double-cliquez dessus** puis "
               "choisissez dans la liste.")
    st.caption(
        "Unités proposées : " + " · ".join(f"{g} : {', '.join(u)}" for g, u in q.UNITES.items())
    )
    if not any(r == q.ROLES["id_sondage"] for r in edite["Rôle"]):
        st.warning(
            "Aucune colonne n'est désignée comme **identifiant de sondage** : la localisation de ces "
            "données restera marquée **« inconnue »** (elles ne pourront pas être rattachées à un sondage).",
            icon="📍",
        )
    if st.button("✅ Confirmer la structure", type="primary"):
        roles_inverses = {v: k for k, v in q.ROLES.items()}
        erreurs, structure = [], []
        for _, ligne in edite.iterrows():
            role = roles_inverses[ligne["Rôle"]]
            unite = ligne["Unité"] if isinstance(ligne["Unité"], str) else None
            if role in q.ROLES_NUMERIQUES and not unite:
                erreurs.append(f"« {ligne['Colonne du fichier']} » : choisissez une unité (ou « sans unité »).")
            if role == "profondeur" and unite and q.grandeur(unite) != "longueur":
                erreurs.append(f"« {ligne['Colonne du fichier']} » : une profondeur doit être une longueur (m, cm, mm).")
            structure.append({
                "nom_origine": ligne["Colonne du fichier"],
                "variable": (ligne["Nom de variable"].strip() if isinstance(ligne["Nom de variable"], str)
                             else "") or ligne["Colonne du fichier"],
                "unite": None if unite == "sans unité" else unite,
                "role": role,
                "type_detecte": ligne["Type détecté"],
            })
        if erreurs:
            for e in erreurs:
                st.error(e, icon="❌")
        else:
            changements = db.enregistrer_structure(jeu_id, structure, auteur)
            nouvelle_version()
            st.session_state["_qc_message"] = (
                f"Structure enregistrée ({len(changements)} colonne(s) mise(s) à jour). "
                "Passez à l'onglet « 2. Interprétation des valeurs »."
                if changements else "Structure inchangée."
            )
            st.rerun()
    if structure_ok:
        st.caption("✅ Structure confirmée. Vous pouvez la modifier à tout moment : les interprétations "
                   "des colonnes dont le rôle ou l'unité change devront être refaites.")

# ===========================================================================
# 2. Interprétation des valeurs
# ===========================================================================
with onglets[1]:
    if not structure_ok:
        st.info("Confirmez d'abord la structure (onglet 1).")
    elif not col_numeriques:
        st.info("Aucune colonne de profondeur ou de mesure numérique : rien à interpréter.")
    else:
        st.markdown(
            "Pour chaque colonne numérique, l'application montre comment les valeurs sont écrites. "
            "Quand plusieurs **conventions** ou **unités** se mélangent, c'est **à vous de trancher** : "
            "rien n'est converti sans votre accord."
        )
        for c in col_numeriques:
            nom = c["nom_origine"]
            p, requis = profils[nom], requis_colonne(c)
            interp = c["interpretation"] or {}
            fait = q.interpretation_complete(requis, c["interpretation"])
            a_decider = bool(requis["groupes"] or requis["conversions"] or requis["separateurs_mixtes"])
            icone = "✅" if fait else ("⚠️" if a_decider else "🔵")
            with st.expander(f"{icone} {titre_colonne(c)} — colonne « {nom} »", expanded=not fait):
                # Ce qui a été trouvé
                resume = [f"{p.comptes[n]} {libelle}" for n, libelle in q.NATURES_LIBELLES.items() if p.comptes[n]]
                st.markdown("**Contenu détecté :** " + " · ".join(resume))
                if p.separateurs:
                    st.caption("Séparateur décimal : " + ", ".join(
                        f"« {s} » ({n} valeur(s))" for s, n in p.separateurs.items()))
                non_chiffrables = [n for n in ("marqueur", "censure", "format_ambigu", "unite_inconnue", "texte")
                                   if p.comptes[n]]
                for n in non_chiffrables:
                    ex = ", ".join(f"ligne {l} : « {t} »" for l, t in p.exemples[n])
                    consequence = ("lues comme valeurs manquantes" if n == "marqueur"
                                   else "exclues de l'analyse (conservées dans les données brutes)")
                    st.info(f"**{p.comptes[n]} {q.NATURES_LIBELLES[n]}** — {consequence}. Exemples : {ex}", icon="ℹ️")
                for u in requis["incompatibles"]:
                    st.warning(f"Des valeurs sont en **{u}**, unité qui ne mesure pas la même grandeur que "
                               f"**{c['unite']}** : elles seront exclues de l'analyse. Vérifiez le fichier "
                               "ou l'unité choisie.", icon="⚠️")

                with st.form(f"form_interp_{jeu_id}_{nom}_{version}"):
                    choix_groupes = {}
                    if requis["groupes"]:
                        st.warning(
                            "**Conventions mélangées** : cette colonne contient des valeurs qui peuvent "
                            "représenter des choses différentes (ex. « 25 % », « 0,25 » et « 25 »). "
                            "Indiquez comment lire **chaque groupe**.", icon="⚠️",
                        )
                        for g, valeurs in requis["groupes"].items():
                            ex = ", ".join(f"ligne {l} : « {brut.loc[l - 1, nom]} »" for l, _ in valeurs[:6])
                            options = list(q.CHOIX_GROUPES[g])
                            actuel = interp.get("groupes", {}).get(g)
                            choix_groupes[g] = st.radio(
                                f"{q.GROUPES_POURCENTAGE[g]} — {len(valeurs)} valeur(s) : {ex}",
                                options, format_func=q.CHOIX_GROUPES[g].get,
                                index=options.index(actuel) if actuel in options else None,
                                key=f"radio_{jeu_id}_{nom}_{g}_{version}",
                            )
                    conversion = False
                    if requis["conversions"]:
                        st.markdown(f"**Conversions d'unités proposées vers {c['unite']}** :")
                        st.table(pd.DataFrame([
                            {"Unité d'origine": u, "Unité retenue": c["unite"], "Opération": f"× {f:g}",
                             "Nombre de valeurs": p.unites_valeurs.get(u, 0) or p.comptes["nombre"]}
                            for u, f in requis["conversions"].items()
                        ]))
                        conversion = st.checkbox("Je valide ces conversions", value=bool(interp.get("conversion_validee")),
                                                 key=f"conv_{jeu_id}_{nom}_{version}")
                    separateurs = False
                    if requis["separateurs_mixtes"]:
                        st.warning("Cette colonne mélange la **virgule** et le **point** comme séparateur "
                                   "décimal. Vérifiez qu'aucun point ne sert de séparateur de milliers "
                                   "(ex. « 1.250 » pour mille deux cent cinquante).", icon="⚠️")
                        separateurs = st.checkbox("J'ai vérifié : virgule et point sont des séparateurs décimaux",
                                                  value=bool(interp.get("separateurs_verifies")),
                                                  key=f"sep_{jeu_id}_{nom}_{version}")
                    if not a_decider:
                        st.caption("Aucune ambiguïté détectée. Confirmez la lecture de cette colonne.")
                    valider = st.form_submit_button("Valider l'interprétation de cette colonne", type="primary")

                if valider:
                    manquants = [q.GROUPES_POURCENTAGE[g] for g, v in choix_groupes.items() if v is None]
                    if manquants:
                        st.error("Choisissez une interprétation pour : " + " ; ".join(manquants), icon="❌")
                    elif requis["conversions"] and not conversion:
                        st.error("Cochez « Je valide ces conversions » ou corrigez l'unité dans l'onglet 1.", icon="❌")
                    elif requis["separateurs_mixtes"] and not separateurs:
                        st.error("Confirmez la vérification des séparateurs décimaux.", icon="❌")
                    else:
                        nouvelle = {"groupes": choix_groupes, "conversion_validee": conversion,
                                    "separateurs_verifies": separateurs}
                        morceaux = [f"{q.GROUPES_POURCENTAGE[g]} → {q.CHOIX_GROUPES[g][v]}"
                                    for g, v in choix_groupes.items()]
                        methode = "; ".join(f"{u} → {c['unite']} : × {f:g}" for u, f in requis["conversions"].items())
                        if methode:
                            morceaux.append(f"conversion validée ({methode})")
                        description = ("; ".join(morceaux) or "lecture confirmée sans ambiguïté") + "."
                        db.enregistrer_interpretation(jeu_id, nom, nouvelle, description, methode or None, auteur)
                        nouvelle_version()
                        st.session_state["_qc_message"] = f"Interprétation de « {nom} » enregistrée."
                        st.rerun()

                if fait:
                    resultat = q.interpreter_colonne(nom, brut[nom], c["role"], c["unite"], c["interpretation"])
                    comptes = resultat["statut"].value_counts()
                    st.markdown("**Résultat :** " + " · ".join(f"{n} {s}(s)" for s, n in comptes.items()))
                    modifiees = resultat[resultat["statut"] != "retenue"]
                    if not modifiees.empty:
                        st.dataframe(pd.DataFrame({
                            "Ligne": modifiees.index + 1,
                            "Valeur du fichier": brut.loc[modifiees.index, nom],
                            f"Valeur retenue ({c['unite'] or 'sans unité'})": modifiees["valeur"],
                            "Statut": modifiees["statut"],
                            "Explication": modifiees["detail"],
                        }), hide_index=True, width="stretch")

# ===========================================================================
# 3. Doublons et identifiants
# ===========================================================================
with onglets[2]:
    synthese = q.lignes_synthese(brut)
    if synthese:
        st.warning(
            f"**{len(synthese)} ligne(s) de synthèse probable(s)** : "
            + ", ".join(f"ligne {l} (« {t} »)" for l, t in synthese)
            + ". Ces lignes résument d'autres lignes (moyenne, minimum…) : ce ne sont pas des observations. "
              "Les analyser avec les données compterait certaines valeurs deux fois.", icon="⚠️",
        )
        lignes_s = [l for l, _ in synthese]
        st.checkbox(
            "Exclure ces lignes de synthèse de l'analyse (les données brutes ne sont pas modifiées)",
            value=bool(db.lire_options_qc(jeu_id).get("exclure_synthese")), key=f"synthese_{jeu_id}_{version}",
            on_change=basculer_option, args=(f"synthese_{jeu_id}_{version}", "exclure_synthese", lignes_s,
                                             f"Lignes de synthèse exclues de l'analyse : {', '.join(map(str, lignes_s))}.",
                                             "Lignes de synthèse conservées dans l'analyse."),
        )
        st.caption("Le choix est enregistré dès que vous cochez ou décochez la case.")
        st.divider()

    groupes_doublons = q.doublons_exacts(brut)
    if groupes_doublons:
        st.warning(f"**{len(groupes_doublons)} groupe(s) de lignes strictement identiques** :", icon="⚠️")
        for g in groupes_doublons:
            st.markdown(f"- lignes {', '.join(map(str, g))}")
        copies = [l for g in groupes_doublons for l in g[1:]]
        st.checkbox(
            "Exclure les copies de l'analyse (la première ligne de chaque groupe est gardée ; "
            "les données brutes ne sont pas modifiées)",
            value=bool(db.lire_options_qc(jeu_id).get("exclure_doublons")), key=f"doublons_{jeu_id}_{version}",
            on_change=basculer_option, args=(f"doublons_{jeu_id}_{version}", "exclure_doublons", copies,
                                             f"Copies exactes exclues de l'analyse : lignes {', '.join(map(str, copies))}.",
                                             "Doublons exacts conservés dans l'analyse."),
        )
        st.caption("Le choix est enregistré dès que vous cochez ou décochez la case.")
    else:
        st.success("Aucune ligne en double (lignes strictement identiques).", icon="✅")

    for c in colonnes:
        if c["role"] not in ("id_sondage", "id_echantillon"):
            continue
        vides = [int(i) + 1 for i, v in brut[c["nom_origine"]].items() if v is None]
        if vides:
            consequence = (" Leur **localisation est inconnue** et restera marquée comme telle."
                           if c["role"] == "id_sondage" else "")
            st.warning(f"« {c['nom_origine']} » : identifiant manquant aux lignes "
                       f"{', '.join(map(str, vides))}.{consequence}", icon="📍")
        if c["role"] == "id_echantillon":
            dupliques = q.identifiants_dupliques(brut[c["nom_origine"]])
            if dupliques:
                st.warning(
                    f"« {c['nom_origine']} » : identifiants présents sur plusieurs lignes — "
                    + " ; ".join(f"{k} (lignes {', '.join(map(str, v))})" for k, v in dupliques.items())
                    + ". Cela peut être normal (plusieurs essais sur un même échantillon) ou une erreur "
                      "de saisie : à vérifier.", icon="⚠️",
                )
            elif not vides:
                st.success(f"« {c['nom_origine']} » : chaque identifiant est unique.", icon="✅")
        elif not vides:
            sondages = sorted({str(v) for v in brut[c["nom_origine"]].dropna()})
            st.success(f"« {c['nom_origine']} » : {len(sondages)} sondage(s) — {', '.join(sondages)}.", icon="✅")
    if structure_ok and col_sondage is None:
        st.warning("Aucune colonne d'identifiant de sondage : la localisation de toutes les lignes est "
                   "**inconnue** et restera marquée comme telle.", icon="📍")

# ===========================================================================
# 4. Valeurs atypiques
# ===========================================================================
with onglets[3]:
    with st.expander("ℹ️ Méthode de détection utilisée", expanded=False):
        st.markdown(q.METHODE_ATYPIQUES)
        st.markdown("Une valeur signalée **n'est pas forcément fausse** : elle mérite une vérification "
                    "(saisie, unité, essai). Elle n'est **jamais supprimée** automatiquement.")
    st.info("Pour chaque valeur signalée, choisissez **⏳ À vérifier**, **✅ Vérifiée — conservée** ou "
            "**🚫 Exclue de l'analyse**, puis cliquez sur **« Enregistrer les décisions de cette colonne »**.",
            icon="👇")
    statuts = db.lire_statuts(jeu_id)
    a_traiter = [c for c in col_numeriques if colonne_interpretee(c)]
    if not col_numeriques:
        st.info("Aucune colonne numérique.")
    elif not a_traiter:
        st.info("Validez d'abord l'interprétation des colonnes (onglet 2).")
    for c in a_traiter:
        nom = c["nom_origine"]
        signalees, infos = q.detecter_atypiques(valeurs_pour_atypiques(c), c["role"], c["unite"])
        st.markdown(f"##### {titre_colonne(c)}")
        if infos["n"] < q.N_MIN_ATYPIQUES:
            st.caption(f"n = {infos['n']} valeur(s) : trop peu pour appliquer la règle de Tukey.")
        else:
            st.caption(
                f"n = {infos['n']} · Q1 = {q.nombre_court(infos['q1'])} · Q3 = {q.nombre_court(infos['q3'])} · "
                f"IQR = {q.nombre_court(infos['iqr'])} · bornes : [{q.nombre_court(infos['borne_basse'])} ; "
                f"{q.nombre_court(infos['borne_haute'])}] {c['unite'] or ''}"
            )
        if signalees.empty:
            st.success("Aucune valeur atypique signalée.", icon="✅")
            continue
        restantes = sum(statuts.get((nom, int(l)), {}).get("statut", "à vérifier") == "à vérifier"
                        for l in signalees["ligne"])
        st.markdown(f"**{len(signalees)} valeur(s) signalée(s)**"
                    + (f" — ⏳ {restantes} en attente de votre décision" if restantes else " — ✅ toutes décidées"))
        with st.form(f"form_atyp_{jeu_id}_{nom}_{version}"):
            choix_valeurs = []
            for _, s in signalees.iterrows():
                l = int(s["ligne"])
                sondage = brut.loc[l - 1, col_sondage["nom_origine"]] if col_sondage else None
                echantillon = next((brut.loc[l - 1, x["nom_origine"]] for x in colonnes
                                    if x["role"] == "id_echantillon"), None)
                reperes = " · ".join(x for x in (f"sondage {sondage}" if sondage else "localisation inconnue",
                                                 f"échantillon {echantillon}" if echantillon else "") if x)
                st.markdown(f"**Ligne {l}** ({reperes}) — valeur du fichier « {brut.loc[l - 1, nom]} » → "
                            f"**{q.nombre_court(s['valeur'])} {c['unite'] or ''}** — *{s['raison']}*")
                actuel = statuts.get((nom, l), {})
                c1, c2 = st.columns([3, 2])
                decision = c1.radio(
                    f"Décision pour la ligne {l}", list(db.STATUTS_ATYPIQUES), horizontal=True,
                    index=list(db.STATUTS_ATYPIQUES).index(actuel.get("statut", "à vérifier")),
                    format_func=LIBELLES_DECISION.get, key=f"dec_{jeu_id}_{nom}_{l}_{version}",
                    label_visibility="collapsed",
                )
                commentaire = c2.text_input(f"Commentaire ligne {l}", value=actuel.get("commentaire") or "",
                                            placeholder="Commentaire (facultatif)", label_visibility="collapsed",
                                            key=f"com_{jeu_id}_{nom}_{l}_{version}")
                choix_valeurs.append((l, decision, commentaire))
            enregistrer = st.form_submit_button("💾 Enregistrer les décisions de cette colonne", type="primary")
        if enregistrer:
            n = db.enregistrer_statuts(jeu_id, nom, choix_valeurs, methode=f"Tukey, k = {q.COEFF_TUKEY}", auteur=auteur)
            nouvelle_version()
            st.session_state["_qc_message"] = f"« {nom} » : {n} décision(s) enregistrée(s)."
            st.rerun()
        st.divider()

# ===========================================================================
# 5. Validation
# ===========================================================================
with onglets[4]:
    statuts = db.lire_statuts(jeu_id)
    options = db.lire_options_qc(jeu_id)
    # Vérifications avant validation
    a_faire = []
    if not structure_ok:
        a_faire.append("confirmer la structure des colonnes (onglet 1)")
    non_interpretees = [c["nom_origine"] for c in col_numeriques if not colonne_interpretee(c)]
    if non_interpretees:
        a_faire.append("valider l'interprétation de : " + ", ".join(f"« {n} »" for n in non_interpretees))
    exclusions, en_attente = {}, []
    for c in col_numeriques:
        if c["nom_origine"] in non_interpretees:
            continue
        nom = c["nom_origine"]
        signalees, _ = q.detecter_atypiques(valeurs_pour_atypiques(c), c["role"], c["unite"])
        for l in signalees["ligne"]:
            statut = statuts.get((nom, int(l)), {}).get("statut", "à vérifier")
            if statut == "à vérifier":
                en_attente.append(f"« {nom} » ligne {l}")
            elif statut == "exclue de l'analyse":
                exclusions.setdefault(nom, set()).add(int(l))
    if en_attente:
        a_faire.append("décider pour les valeurs atypiques (onglet 4) : " + ", ".join(en_attente))

    st.markdown(f"**Statut actuel :** {ICONES_STATUT.get(jeu['statut_qc'], '⚪')} {jeu['statut_qc']}")
    if a_faire:
        st.info("Avant de valider, il reste à :\n" + "\n".join(f"- {t}" for t in a_faire), icon="📝")
    else:
        lignes_exclues = lignes_hors_analyse()
        tableau, description = q.construire_tableau_valide(brut, colonnes, exclusions, lignes_exclues)

        st.markdown("**Résumé de ce qui sera retenu pour l'analyse :**")
        resume_lignes = []
        for c in col_numeriques:
            r = q.interpreter_colonne(c["nom_origine"], brut[c["nom_origine"]], c["role"], c["unite"],
                                      c["interpretation"])
            r = r.drop(index=[l - 1 for l in lignes_exclues if l - 1 in r.index])  # lignes hors analyse
            comptes = r["statut"].value_counts()
            n_exclues_atyp = len(exclusions.get(c["nom_origine"], ()))
            resume_lignes.append({
                "Variable": titre_colonne(c),
                "Retenues telles quelles": int(comptes.get("retenue", 0)),
                "Converties (décision validée)": int(comptes.get("convertie", 0)),
                "Manquantes": int(comptes.get("manquante", 0)),
                "Exclues (non chiffrables / à vérifier)": int(comptes.get("exclue", 0)),
                "Atypiques exclues": n_exclues_atyp,
            })
        st.dataframe(pd.DataFrame(resume_lignes), hide_index=True, width="stretch")
        if lignes_exclues:
            st.caption(f"Lignes exclues de l'analyse (doublons, synthèses) : "
                       f"{', '.join(map(str, sorted(lignes_exclues)))}.")
        if col_sondage is None:
            st.caption("📍 Aucun identifiant de sondage : localisation **inconnue** pour toutes les lignes.")
        st.caption("Les données brutes restent intactes ; la version validée est une copie, "
                   "recalculée à partir de vos décisions.")
        if st.button("✅ Valider le jeu de données", type="primary"):
            n_valeurs = sum(r["Retenues telles quelles"] + r["Converties (décision validée)"] for r in resume_lignes)
            resume = (f"Jeu validé : {len(tableau)} ligne(s), {len(col_numeriques)} variable(s) numérique(s), "
                      f"{n_valeurs} valeur(s) retenue(s), "
                      f"{sum(len(v) for v in exclusions.values())} atypique(s) exclue(s), "
                      f"{len(lignes_exclues)} ligne(s) exclue(s) (doublons, synthèses).")
            db.valider_jeu(jeu_id, importation.tableau_vers_json(tableau, description), resume, auteur)
            nouvelle_version()
            st.session_state["_qc_message"] = resume + " Il est prêt pour les analyses."
            st.rerun()

    if jeu["statut_qc"] == "validé" and jeu["contenu_valide"]:
        with st.expander("📋 Données validées (utilisées par les analyses)"):
            st.dataframe(importation.json_vers_tableau(jeu["contenu_valide"]), hide_index=True, width="stretch")

    with st.expander("🗂️ Journal des décisions de contrôle qualité"):
        decisions = db.lister_decisions(jeu_id)
        if not decisions:
            st.caption("Aucune décision enregistrée.")
        for d in decisions:
            st.markdown(
                f"- {ui.date_fr(d['date_decision'])} — **{d['type_decision']}**"
                + (f" (« {d['colonne']} »)" if d["colonne"] else "")
                + f" : {d['description']}" + (f" — *méthode : {d['methode']}*" if d["methode"] else "")
            )
