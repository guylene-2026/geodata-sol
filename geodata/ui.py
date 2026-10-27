"""Petits éléments d'interface partagés entre les pages Streamlit."""

from datetime import datetime

import streamlit as st

from geodata import db

# Chemins des pages (utilisés par st.switch_page et le menu de navigation)
PAGE_ACCUEIL = "pages/accueil.py"
PAGE_PROJETS = "pages/projets.py"
PAGE_IMPORT = "pages/import_donnees.py"
PAGE_SOURCES = "pages/sources_en_ligne.py"
PAGE_CONTROLE = "pages/controle_qualite.py"
PAGE_SONDAGES = "pages/sondages.py"
PAGE_ANALYSES = "pages/analyses.py"
PAGE_RAPPORTS = "pages/rapports.py"
PAGE_HISTORIQUE = "pages/historique.py"


def date_fr(date_iso: str | None, avec_heure: bool = True) -> str:
    """Convertit une date ISO en format français lisible (23/10/2026 à 14:05)."""
    if not date_iso:
        return "—"
    try:
        d = datetime.fromisoformat(date_iso)
    except ValueError:
        return date_iso
    return d.strftime("%d/%m/%Y à %H:%M") if avec_heure else d.strftime("%d/%m/%Y")


# ---------------------------------------------------------------------------
# Style visuel
# ---------------------------------------------------------------------------
# Les couleurs principales sont dans .streamlit/config.toml. Ce complément met
# en blanc les éléments que le thème ne règle pas : chiffres clés, formulaires,
# sections dépliables et cadres (conteneurs créés avec une clé « carte_… »).
STYLE = """
<style>
[data-testid="stMetric"],
[data-testid="stForm"],
[data-testid="stExpander"] details,
[class*="st-key-carte_"] {
    background-color: #FFFFFF;
    border-radius: 0.5rem;
}
[data-testid="stMetric"] { padding: 0.6rem 0.9rem; }
</style>
"""


def appliquer_style() -> None:
    """Applique le complément de style à la page affichée."""
    st.html(STYLE)


# ---------------------------------------------------------------------------
# Projet actif
# ---------------------------------------------------------------------------
# Le projet ouvert est gardé dans st.session_state (pour la session en cours)
# et dans la base (réglage « dernier_projet ») pour être rouvert au prochain lancement.

def ouvrir_projet(projet_id: int) -> None:
    """Fait d'un projet le projet actif."""
    projet = db.obtenir_projet(projet_id)
    if projet is None:
        fermer_projet()
        return
    st.session_state["projet_id"] = projet["id"]
    st.session_state["projet_nom"] = projet["nom"]
    db.ecrire_parametre("dernier_projet", str(projet["id"]))


def fermer_projet() -> None:
    """Plus aucun projet actif."""
    st.session_state.pop("projet_id", None)
    st.session_state.pop("projet_nom", None)
    db.ecrire_parametre("dernier_projet", None)


def restaurer_dernier_projet() -> None:
    """Au début d'une nouvelle session, rouvre le dernier projet utilisé (s'il existe encore)."""
    if st.session_state.get("_session_initialisee"):
        return
    st.session_state["_session_initialisee"] = True
    dernier = db.lire_parametre("dernier_projet")
    if dernier and dernier.isdigit():
        ouvrir_projet(int(dernier))


def projet_actif() -> dict | None:
    """Fiche du projet actif (relue dans la base), ou None."""
    projet_id = st.session_state.get("projet_id")
    if projet_id is None:
        return None
    projet = db.obtenir_projet(projet_id)
    if projet is None:  # projet supprimé entre-temps
        fermer_projet()
    return projet


def exiger_projet() -> dict:
    """À appeler en haut des pages qui ont besoin d'un projet ouvert.
    S'il n'y en a pas, affiche un message et arrête la page."""
    projet = projet_actif()
    if projet is None:
        st.warning("Aucun projet n'est ouvert. Créez ou ouvrez d'abord un projet.", icon="📁")
        if st.button("Aller à la page Projets"):
            st.switch_page(PAGE_PROJETS)
        st.stop()
    return projet


def page_en_construction(titre: str, phase: int, contenu_prevu: list[str]) -> None:
    """Affiche une page provisoire indiquant ce qui y sera disponible."""
    st.title(titre)
    st.info(f"🚧 Cette page sera construite lors de la **phase {phase}**.")
    st.markdown("**Ce que vous y trouverez :**")
    for element in contenu_prevu:
        st.markdown(f"- {element}")
    if st.button("⬅ Retour à l'accueil"):
        st.switch_page(PAGE_ACCUEIL)


# ---------------------------------------------------------------------------
# Fiche de provenance (règle n° 3)
# ---------------------------------------------------------------------------
def champs_provenance(valeurs: dict) -> dict:
    """Champs de saisie de la fiche de provenance, à placer DANS un st.form.
    Renvoie les valeurs saisies."""
    col1, col2 = st.columns(2)
    saisie = {
        "source": col1.text_input(
            "Source des données *", value=valeurs.get("source") or "",
            placeholder="ex. Laboratoire de l'école, rapport G2 AVP 2024, base publique…",
        ),
        "auteur_import": col2.text_input(
            "Auteur de l'import *", value=valeurs.get("auteur_import") or "",
        ),
    }
    col3, col4 = st.columns(2)
    saisie["producteur"] = col3.text_input(
        "Producteur des données (qui a réalisé les essais)", value=valeurs.get("producteur") or "",
    )
    saisie["date_donnees"] = col4.text_input(
        "Date des essais / des données", value=valeurs.get("date_donnees") or "",
        placeholder="ex. mars 2025",
    )
    saisie["licence"] = st.text_input(
        "Licence ou conditions de réutilisation", value=valeurs.get("licence") or "",
        placeholder="ex. Licence Ouverte Etalab 2.0, usage interne uniquement…",
    )
    saisie["limites_usage"] = st.text_area(
        "Limites d'usage *", value=valeurs.get("limites_usage") or "",
        placeholder="ex. Données d'un seul site ; essais non normalisés ; à ne pas utiliser "
                    "pour un dimensionnement ; usage pédagogique uniquement…",
    )
    saisie["remarques"] = st.text_area("Remarques", value=valeurs.get("remarques") or "")
    st.caption("* champ obligatoire")
    return saisie


def afficher_provenance(prov: dict, est_fictif: bool = False) -> None:
    """Affiche une fiche de provenance sous forme de tableau lisible."""
    if est_fictif:
        st.warning("Données **FICTIVES** : à utiliser uniquement pour s'exercer.", icon="🧪")
    lignes = [
        ("Source", prov.get("source")),
        ("Fichier ou URL d'origine", prov.get("fichier_ou_url")),
        ("Date d'import", date_fr(prov.get("date_import"))),
        ("Auteur de l'import", prov.get("auteur_import")),
        ("Producteur des données", prov.get("producteur")),
        ("Date des données", prov.get("date_donnees")),
        ("Licence / conditions", prov.get("licence")),
        ("Limites d'usage", prov.get("limites_usage")),
        ("Remarques", prov.get("remarques")),
    ]
    st.markdown(
        "| | |\n|---|---|\n"
        + "\n".join(f"| **{libelle}** | {_cellule_md(valeur)} |" for libelle, valeur in lignes)
    )


def _cellule_md(valeur) -> str:
    """Texte sûr pour une cellule de tableau Markdown."""
    if not valeur:
        return "*non renseigné*"
    return " ".join(str(valeur).replace("|", "\\|").split())
