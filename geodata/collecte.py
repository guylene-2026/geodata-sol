"""Collecte de données en ligne (phase 8) : sources publiques et téléchargement par URL.

Première version (cahier des charges, 2.2.B) : l'utilisateur fournit l'URL DIRECTE
d'un fichier CSV ou Excel accessible publiquement. Le fichier téléchargé suit
ensuite exactement le même chemin qu'un fichier local (aperçu, provenance,
contrôle qualité). La provenance réelle est conservée : URL, date et heure de
téléchargement, taille, type annoncé par le serveur et empreinte SHA-256 (qui
permet de vérifier plus tard que le fichier n'a pas changé).
"""

import hashlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePosixPath
from urllib.parse import unquote, urlparse

import requests

TAILLE_MAX_MO = 20
DELAI_SECONDES = 30
_TYPES_CONTENU = {
    "text/csv": "csv",
    "application/csv": "csv",
    "text/comma-separated-values": "csv",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "application/vnd.ms-excel": "xls",
}

# Ressources publiques utiles en géotechnique, en commençant par le Cameroun.
# Les liens mènent souvent à des portails : il faut y repérer le lien de
# téléchargement DIRECT d'un fichier CSV ou Excel. Liens vérifiés le 26/10/2026.
_NGAOUNDAL = "https://data.mendeley.com/public-files/datasets/vn59kcyhb3/files/"
SOURCES = [
    {
        "pays": "Cameroun",
        "nom": "Sols latéritiques de Ngaoundal (Adamaoua) — données géotechniques",
        "organisme": "Université de Dschang — A. Aboubakar, publié sur Mendeley Data (DOI 10.17632/vn59kcyhb3.3)",
        "url": "https://data.mendeley.com/datasets/vn59kcyhb3/3",
        "contenu": "15 échantillons de sols latéritiques prélevés à 1,3 m : granulométrie, teneur en eau, limites "
                   "d'Atterberg, densité des grains, gonflement, Proctor (densité sèche max., OPM), CBR ; "
                   "coordonnées GPS des prélèvements.",
        "formats": "CSV (téléchargement direct ci-dessous). Licence CC BY 4.0 (citer l'auteur).",
        "remarques": "Le fichier géotechnique se termine par 3 lignes de synthèse (Mean, Min., Max.) qui ne sont "
                     "pas des échantillons : le contrôle qualité les signale.",
        "fichiers": {
            "Données géotechniques (CSV)": _NGAOUNDAL + "adf316e9-e71a-4ff7-abd7-b523f8e0c441/file_downloaded",
            "Coordonnées des prélèvements (CSV)": _NGAOUNDAL + "00c4c926-8ea0-4c4b-b408-a0d4f8dfd0aa/file_downloaded",
        },
    },
    {
        "pays": "Cameroun / Afrique",
        "nom": "Mendeley Data et Zenodo — jeux de données de recherche",
        "organisme": "Elsevier (Mendeley Data) ; CERN / OpenAIRE (Zenodo)",
        "url": "https://data.mendeley.com/",
        "contenu": "Données publiées avec des articles et mémoires : rechercher « Cameroon laterite », "
                   "« Cameroon soil geotechnical », « Yaoundé clay », « Douala soil »… "
                   "Zenodo : https://zenodo.org/",
        "formats": "Fichiers déposés par les auteurs (souvent CSV ou XLSX) avec lien de téléchargement direct.",
        "remarques": "Vérifiez la licence et citez le DOI du dépôt dans la fiche de provenance.",
    },
    {
        "pays": "Afrique (dont Cameroun)",
        "nom": "ISRIC — profils de sols (WoSIS, Africa Soil Profiles Database)",
        "organisme": "ISRIC — World Soil Information (Pays-Bas)",
        "url": "https://data.isric.org/",
        "contenu": "Profils de sols géoréférencés (texture, densité apparente, pH, carbone…) issus de nombreux "
                   "pays africains, dont le Cameroun.",
        "formats": "TSV / CSV dans des archives ZIP volumineuses (à extraire et filtrer sur le Cameroun avant import).",
        "remarques": "Données pédologiques (agronomie) plus que géotechniques ; licence indiquée profil par profil "
                     "(CC-BY ou CC-BY-NC).",
    },
    {
        "pays": "Cameroun",
        "nom": "Africa Groundwater Atlas — Hydrogéologie du Cameroun",
        "organisme": "British Geological Survey (BGS)",
        "url": "https://earthwise.bgs.ac.uk/index.php/Hydrogeology_of_Cameroon",
        "contenu": "Synthèse de la géologie et des aquifères du Cameroun, cartes au 1/5 000 000, bibliographie.",
        "formats": "Pages web et cartes ; pas de tableaux de mesures.",
        "remarques": "Utile pour le contexte géologique et hydrogéologique d'un site, pas comme données d'essais.",
    },
    {
        "pays": "Cameroun",
        "nom": "Institutions nationales (pas de portail de données en ligne identifié)",
        "organisme": "LABOGENIE (Laboratoire National de Génie Civil, Yaoundé) ; IRGM ; universités "
                     "(Yaoundé I, Dschang, Douala, ENSP de Yaoundé)",
        "url": "",
        "contenu": "Rapports d'essais, études géotechniques de projets, mémoires et thèses.",
        "formats": "Généralement des rapports PDF ou papier, obtenus sur demande.",
        "remarques": "Les résultats doivent être ressaisis dans un tableur (Excel/CSV) puis importés comme fichier "
                     "local, avec une fiche de provenance précise (rapport, date, auteur, autorisation d'usage).",
    },
    {
        "pays": "Autres pays",
        "nom": "France : BRGM InfoTerre (Banque du sous-sol), Géorisques, data.gouv.fr",
        "organisme": "BRGM ; Ministère de la Transition écologique ; Etalab",
        "url": "https://infoterre.brgm.fr/",
        "contenu": "Sondages et forages en France ; aléas naturels ; données publiques. "
                   "Autres portails : https://www.georisques.gouv.fr/ et https://www.data.gouv.fr/",
        "formats": "Fiches web, PDF, CSV selon les services.",
        "remarques": "Données françaises : utiles pour s'exercer, pas pour un site au Cameroun.",
    },
]

# Provenance connue de certains fichiers : pré-remplit la fiche quand on importe ces URL
PROVENANCES_CONNUES = {
    _NGAOUNDAL + "adf316e9-e71a-4ff7-abd7-b523f8e0c441/file_downloaded": {
        "source": "Mendeley Data — Dataset of Soil, Geotechnical, and Mineralogical Data from Ngaoundal, Cameroon "
                  "(DOI 10.17632/vn59kcyhb3.3)",
        "producteur": "Abdoul Aboubakar, Faculté des Sciences, Université de Dschang (Cameroun)",
        "date_donnees": "publié le 02/10/2025 (version 3)",
        "licence": "CC BY 4.0 — citer l'auteur et le DOI",
        "limites_usage": "Sols latéritiques de la zone de Ngaoundal (Adamaoua), prélevés à 1,3 m : non transposable "
                         "à un autre site sans essais. Les 3 dernières lignes (Mean, Min., Max.) sont des synthèses.",
    },
    _NGAOUNDAL + "00c4c926-8ea0-4c4b-b408-a0d4f8dfd0aa/file_downloaded": {
        "source": "Mendeley Data — Dataset of Soil, Geotechnical, and Mineralogical Data from Ngaoundal, Cameroon "
                  "(DOI 10.17632/vn59kcyhb3.3)",
        "producteur": "Abdoul Aboubakar, Faculté des Sciences, Université de Dschang (Cameroun)",
        "date_donnees": "publié le 29/09/2025",
        "licence": "CC BY 4.0 — citer l'auteur et le DOI",
        "limites_usage": "Coordonnées des points de prélèvement (latitude/longitude en degrés, WGS 84 supposé : "
                         "système non précisé par l'auteur).",
    },
}


@dataclass
class Telechargement:
    """Fichier téléchargé et informations de provenance."""

    url: str
    contenu: bytes
    nom_fichier: str  # nom utilisé pour reconnaître le format (ex. donnees.csv)
    format: str  # 'csv', 'xlsx' ou 'xls'
    type_annonce: str  # type de contenu annoncé par le serveur
    taille: int
    sha256: str
    date: str  # date et heure du téléchargement (ISO)

    def resume(self) -> str:
        """Texte de traçabilité pour l'historique et la provenance."""
        return (f"Téléchargé le {self.date.replace('T', ' à ')} depuis {self.url} — {taille_lisible(self.taille)}, "
                f"type annoncé « {self.type_annonce or 'inconnu'} », empreinte SHA-256 {self.sha256}.")


def taille_lisible(octets: int) -> str:
    if octets < 1024:
        return f"{octets} octets"
    if octets < 1024 ** 2:
        return f"{octets / 1024:.1f} ko".replace(".", ",")
    return f"{octets / 1024 ** 2:.1f} Mo".replace(".", ",")


def verifier_url(url: str) -> str:
    """Contrôle l'adresse saisie ; renvoie l'URL nettoyée ou lève ValueError."""
    url = (url or "").strip()
    if not url:
        raise ValueError("Saisissez l'adresse (URL) du fichier.")
    if " " in url:
        raise ValueError("L'adresse ne doit pas contenir d'espaces.")
    morceaux = urlparse(url)
    if morceaux.scheme not in ("http", "https") or not morceaux.netloc:
        raise ValueError("L'adresse doit commencer par http:// ou https:// (ex. https://exemple.fr/donnees.csv).")
    return url


def _format_depuis(url: str, type_contenu: str, nom_annonce: str | None) -> str | None:
    """Format du fichier d'après le nom annoncé, l'URL puis le type de contenu."""
    for nom in (nom_annonce, unquote(PurePosixPath(urlparse(url).path).name)):
        if nom:
            ext = PurePosixPath(nom.lower()).suffix.lstrip(".")
            if ext in ("csv", "xlsx", "xls"):
                return ext
    return _TYPES_CONTENU.get(type_contenu)


def _nom_annonce(entetes) -> str | None:
    """Nom de fichier donné par l'en-tête Content-Disposition, s'il existe."""
    cd = entetes.get("Content-Disposition", "")
    for morceau in cd.split(";"):
        morceau = morceau.strip()
        if morceau.lower().startswith("filename="):
            return morceau.split("=", 1)[1].strip().strip('"')
    return None


def telecharger(url: str, taille_max_mo: int = TAILLE_MAX_MO, delai: int = DELAI_SECONDES) -> Telechargement:
    """Télécharge un fichier CSV ou Excel public. Lève ValueError avec un message clair en cas de problème."""
    url = verifier_url(url)
    try:
        reponse = requests.get(url, stream=True, timeout=delai, allow_redirects=True,
                               headers={"User-Agent": "GeoData-Sol/1.0 (application pedagogique)"})
    except requests.exceptions.Timeout:
        raise ValueError(f"Le serveur n'a pas répondu en {delai} secondes. Réessayez plus tard.") from None
    except requests.exceptions.ConnectionError:
        raise ValueError("Connexion impossible : vérifiez votre accès à Internet et l'adresse saisie.") from None
    except requests.exceptions.RequestException as e:
        raise ValueError(f"Téléchargement impossible : {e}") from None

    with reponse:
        if reponse.status_code == 404:
            raise ValueError("Fichier introuvable à cette adresse (erreur 404).")
        if reponse.status_code in (401, 403):
            raise ValueError("Accès refusé (erreur %d) : ce fichier n'est pas public." % reponse.status_code)
        if reponse.status_code >= 400:
            raise ValueError(f"Le serveur a répondu par une erreur ({reponse.status_code}).")
        type_contenu = reponse.headers.get("Content-Type", "").split(";")[0].strip().lower()
        nom = _nom_annonce(reponse.headers)
        fmt = _format_depuis(reponse.url, type_contenu, nom)
        if fmt is None:
            if "html" in type_contenu:
                raise ValueError("Cette adresse mène à une **page web**, pas à un fichier. Sur le site, cherchez le "
                                 "lien de **téléchargement direct** du fichier CSV ou Excel (clic droit → "
                                 "« Copier l'adresse du lien »).")
            raise ValueError(f"Format non reconnu (type annoncé : « {type_contenu or 'inconnu'} »). "
                             "Seuls les fichiers CSV, XLSX et XLS sont acceptés.")
        limite = taille_max_mo * 1024 * 1024
        annonce = reponse.headers.get("Content-Length")
        if annonce and annonce.isdigit() and int(annonce) > limite:
            raise ValueError(f"Fichier trop volumineux ({taille_lisible(int(annonce))} ; maximum {taille_max_mo} Mo).")
        morceaux, total = [], 0
        for bloc in reponse.iter_content(64 * 1024):
            total += len(bloc)
            if total > limite:
                raise ValueError(f"Fichier trop volumineux (plus de {taille_max_mo} Mo).")
            morceaux.append(bloc)
        contenu = b"".join(morceaux)
    if not contenu:
        raise ValueError("Le fichier téléchargé est vide.")
    nom_fichier = nom or unquote(PurePosixPath(urlparse(reponse.url).path).name) or "fichier"
    if PurePosixPath(nom_fichier.lower()).suffix.lstrip(".") != fmt:
        nom_fichier = f"{PurePosixPath(nom_fichier).stem or 'fichier'}.{fmt}"
    return Telechargement(
        url=url, contenu=contenu, nom_fichier=nom_fichier, format=fmt, type_annonce=type_contenu,
        taille=len(contenu), sha256=hashlib.sha256(contenu).hexdigest(),
        date=datetime.now().isoformat(timespec="seconds"),
    )


def source_proposee(url: str) -> str:
    """Source proposée par défaut dans la fiche de provenance : le nom de domaine."""
    return urlparse(url).netloc.removeprefix("www.")
