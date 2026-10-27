"""Assistant d'import partagé : options de lecture, aperçu, fiche de provenance, enregistrement.

Utilisé par la page « Importer des données » (fichier local) et par la page
« Collecte en ligne » (fichier téléchargé depuis une URL).
"""

import streamlit as st

from geodata import db, importation, ui

LIGNES_APERCU = 50


@st.cache_data(show_spinner="Lecture du fichier…", max_entries=10)
def _lire(contenu: bytes, nom: str, feuille: str | None, ligne_entete: int, separateur: str | None):
    """Lecture mise en cache (évite de relire le fichier à chaque clic)."""
    return importation.lire_fichier(contenu, nom, feuille, ligne_entete, separateur)


@st.cache_data(max_entries=10)
def _feuilles(contenu: bytes, nom: str) -> list[str]:
    return importation.lister_feuilles(contenu, nom)


def assistant_import(
    projet: dict,
    contenu: bytes,
    nom_fichier: str,
    cle: str,
    type_source: str,
    fichier_ou_url: str,
    nom_propose: str,
    provenance_initiale: dict | None = None,
    details_supplementaires: str = "",
) -> str | None:
    """Affiche les étapes 1 (options), 2 (aperçu) et 3 (provenance) d'un import.

    Renvoie le message de succès si le jeu vient d'être enregistré, sinon None.
    nom_fichier sert à reconnaître le format (.xlsx, .xls, .csv).
    """
    ext = importation.extension(nom_fichier)

    # --- 1. Options de lecture ----------------------------------------------
    st.markdown("##### 1. Options de lecture")
    col1, col2 = st.columns(2)
    feuille = separateur = None
    try:
        if ext in ("xlsx", "xls"):
            liste_feuilles = _feuilles(contenu, nom_fichier)
            feuille = col1.selectbox(f"Feuille du classeur ({len(liste_feuilles)} disponible(s))",
                                     liste_feuilles, key=f"{cle}_feuille")
        else:
            choix_sep = col1.selectbox(
                "Séparateur de colonnes", ["auto", *importation.SEPARATEURS_CSV], key=f"{cle}_sep",
                format_func=lambda s: "Détection automatique" if s == "auto" else importation.SEPARATEURS_CSV[s],
            )
            separateur = None if choix_sep == "auto" else choix_sep
        ligne_entete = col2.number_input(
            "Les noms de colonnes sont sur la ligne n°", min_value=1, max_value=100, value=1, key=f"{cle}_entete",
            help="À changer si le fichier commence par un titre ou des lignes d'explication.",
        )
        lecture = _lire(contenu, nom_fichier, feuille, int(ligne_entete), separateur)
    except ValueError as erreur:
        st.error(str(erreur), icon="❌")
        return None
    except Exception as erreur:  # fichier abîmé, mauvais format…
        st.error("Impossible de lire ce fichier. Vérifiez qu'il s'ouvre bien dans Excel et qu'il n'est pas "
                 f"protégé par un mot de passe.\n\nDétail technique : {erreur}", icon="❌")
        return None

    # --- 2. Aperçu ----------------------------------------------------------
    df = lecture.donnees
    st.markdown("##### 2. Aperçu des données lues")
    c1, c2, c3 = st.columns(3)
    c1.metric("Lignes de données", len(df), border=True)
    c2.metric("Colonnes", df.shape[1], border=True)
    c3.metric("Cellules vides", int(df.isna().sum().sum()), border=True)
    if lecture.separateur:
        st.caption(
            f"Lecture CSV : séparateur **{importation.SEPARATEURS_CSV.get(lecture.separateur, lecture.separateur)}**, "
            f"encodage **{lecture.encodage}**. Si les colonnes semblent mal découpées, "
            "choisissez un autre séparateur ci-dessus."
        )
    for remarque in lecture.remarques:
        st.info(remarque, icon="ℹ️")
    st.dataframe(df.head(LIGNES_APERCU), width="stretch", hide_index=False)
    if len(df) > LIGNES_APERCU:
        st.caption(f"Seules les {LIGNES_APERCU} premières lignes sont affichées (sur {len(df)}).")
    st.caption("Colonnes trouvées : " + ", ".join(f"« {c} »" for c in df.columns))

    # --- 3. Fiche de provenance ---------------------------------------------
    st.markdown("##### 3. Fiche de provenance")
    st.caption("Elle est obligatoire : elle permet de savoir plus tard d'où viennent ces données "
               "et dans quelles limites on peut les utiliser.")
    with st.form(f"{cle}_form_provenance"):
        nom_jeu = st.text_input("Nom du jeu de données *", value=nom_propose)
        provenance = ui.champs_provenance({"auteur_import": projet.get("auteur"), **(provenance_initiale or {})})
        est_fictif = st.checkbox("Ces données sont fictives (exercice, exemple inventé)")
        valider = st.form_submit_button("💾 Enregistrer le jeu de données", type="primary")
    if not valider:
        return None

    details = " ".join(lecture.remarques)
    if lecture.separateur:
        details = (f"Séparateur « {lecture.separateur} », encodage {lecture.encodage}. " + details).strip()
    if ligne_entete > 1:
        details = (f"Noms de colonnes lus sur la ligne {ligne_entete}. " + details).strip()
    if details_supplementaires:
        details = (details_supplementaires + " " + details).strip()
    try:
        db.creer_jeu_donnees(
            projet_id=projet["id"], nom=nom_jeu, type_source=type_source, fichier_ou_url=fichier_ou_url,
            contenu_json=importation.tableau_vers_json(df), nb_lignes=len(df), colonnes=list(df.columns),
            provenance=provenance, feuille=feuille, est_fictif=est_fictif, details_import=details,
        )
    except ValueError as erreur:
        st.error(str(erreur), icon="❌")
        return None
    return (f"Jeu de données « {nom_jeu.strip()} » enregistré ({len(df)} lignes). Étape suivante : "
            "ouvrez « 📥 Importer des données → Jeux de données du projet » puis « 🔎 Contrôler ce jeu de données ».")
