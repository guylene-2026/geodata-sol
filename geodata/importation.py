"""Lecture des fichiers importés (XLSX, XLS, CSV) et conversion pour le stockage.

Principe (règles n° 1 et 5) : à l'import, AUCUNE valeur n'est interprétée.
Toutes les cellules sont lues comme du texte, exactement comme elles sont
écrites (« 25 % », « 0,25 », « 25 »…). L'interprétation (nombres, unités,
virgules décimales) se fait ensuite au contrôle qualité, sous le contrôle
de l'utilisateur.

Seules transformations faites à la lecture, toujours signalées à l'utilisateur :
- les lignes et colonnes entièrement vides sont ignorées ;
- les colonnes sans nom reçoivent un nom provisoire (« Colonne 4 ») ;
- les noms de colonnes en double sont rendus uniques (« Profondeur (2) »).
"""

import csv
import io
import json
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

EXTENSIONS_ACCEPTEES = ("xlsx", "xls", "csv")
SEPARATEURS_CSV = {";": "point-virgule ( ; )", ",": "virgule ( , )", "\t": "tabulation", "|": "barre verticale ( | )"}
ENCODAGES_ESSAYES = ("utf-8-sig", "cp1252")  # UTF-8 (avec ou sans BOM), puis Windows occidental


@dataclass
class ResultatLecture:
    """Données lues dans un fichier, avec les remarques à montrer à l'utilisateur."""

    donnees: pd.DataFrame
    remarques: list[str] = field(default_factory=list)
    separateur: str | None = None  # CSV uniquement
    encodage: str | None = None  # CSV uniquement


# ---------------------------------------------------------------------------
# Détection du format
# ---------------------------------------------------------------------------
def extension(nom_fichier: str) -> str:
    """Extension en minuscules, sans le point (« xlsx », « csv »…)."""
    return Path(nom_fichier).suffix.lower().lstrip(".")


def lister_feuilles(contenu: bytes, nom_fichier: str) -> list[str]:
    """Noms des feuilles d'un classeur Excel."""
    moteur = "xlrd" if extension(nom_fichier) == "xls" else "openpyxl"
    with pd.ExcelFile(io.BytesIO(contenu), engine=moteur) as classeur:
        return [str(f) for f in classeur.sheet_names]


def decoder_texte(contenu: bytes) -> tuple[str, str]:
    """Décode un fichier texte : renvoie (texte, encodage utilisé)."""
    for encodage in ENCODAGES_ESSAYES:
        try:
            return contenu.decode(encodage), encodage
        except UnicodeDecodeError:
            continue
    # cp1252 échoue rarement ; en dernier recours latin-1 décode tout
    return contenu.decode("latin-1"), "latin-1"


def detecter_separateur(texte: str) -> str:
    """Devine le séparateur de colonnes d'un CSV (« ; » est courant en France)."""
    extrait = "\n".join(texte.splitlines()[:20])
    try:
        return csv.Sniffer().sniff(extrait, delimiters="".join(SEPARATEURS_CSV)).delimiter
    except csv.Error:
        # Repli : le séparateur le plus fréquent sur la première ligne
        premiere = texte.splitlines()[0] if texte else ""
        return max(SEPARATEURS_CSV, key=premiere.count)


# ---------------------------------------------------------------------------
# Lecture
# ---------------------------------------------------------------------------
def lire_fichier(
    contenu: bytes,
    nom_fichier: str,
    feuille: str | None = None,
    ligne_entete: int = 1,
    separateur: str | None = None,
) -> ResultatLecture:
    """Lit un fichier XLSX, XLS ou CSV ; toutes les valeurs restent du texte.

    ligne_entete : numéro (à partir de 1) de la ligne qui contient les noms de colonnes.
    separateur   : pour les CSV ; None = détection automatique.
    """
    ext = extension(nom_fichier)
    if ext not in EXTENSIONS_ACCEPTEES:
        raise ValueError(
            f"Format « .{ext} » non pris en charge. Formats acceptés : "
            + ", ".join(f".{e}" for e in EXTENSIONS_ACCEPTEES)
        )
    options = dict(header=ligne_entete - 1, dtype=str, keep_default_na=False)
    resultat_sep = resultat_enc = None

    if ext == "csv":
        texte, resultat_enc = decoder_texte(contenu)
        if not texte.strip():
            raise ValueError("Le fichier est vide.")
        resultat_sep = separateur or detecter_separateur(texte)
        df = pd.read_csv(io.StringIO(texte), sep=resultat_sep, engine="python", **options)
    else:
        moteur = "xlrd" if ext == "xls" else "openpyxl"
        df = pd.read_excel(io.BytesIO(contenu), sheet_name=feuille or 0, engine=moteur, **options)

    df, remarques = nettoyer_tableau(df)
    if df.empty:
        raise ValueError("Aucune donnée trouvée (vérifiez la feuille et la ligne des noms de colonnes).")
    return ResultatLecture(df, remarques, resultat_sep, resultat_enc)


def nettoyer_tableau(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Retire les lignes/colonnes vides et rend les noms de colonnes utilisables.
    Les valeurs des cellules ne sont pas modifiées (sauf cellules vides → None)."""
    remarques = []

    # Cellules vides ou ne contenant que des espaces → valeur manquante (None)
    df = df.astype(object).map(lambda v: None if pd.isna(v) or str(v).strip() == "" else str(v))
    df = df.astype(object).where(df.notna(), None)  # pandas remet NaN : on force None

    # Lignes et colonnes entièrement vides
    nb_lignes, nb_colonnes = df.shape
    df = df.dropna(how="all")
    colonnes_vides = [c for c in df.columns if df[c].isna().all() and _nom_auto(c)]
    df = df.drop(columns=colonnes_vides)
    if (n := nb_lignes - len(df)) > 0:
        remarques.append(f"{n} ligne(s) entièrement vide(s) ignorée(s).")
    if (n := nb_colonnes - df.shape[1]) > 0:
        remarques.append(f"{n} colonne(s) entièrement vide(s) et sans nom ignorée(s).")

    # Noms de colonnes : provisoires si absents, uniques si répétés
    originaux = {str(c).strip() for c in df.columns}
    nouveaux, vus = [], {}
    for position, nom in enumerate(df.columns, start=1):
        nom_propre = str(nom).strip()
        if _nom_auto(nom):
            nom_propre = f"Colonne {position}"
            remarques.append(f"La colonne n° {position} n'avait pas de nom : elle s'appelle « {nom_propre} ».")
        else:
            nom_propre = _nom_sans_suffixe(nom_propre, originaux)
        if nom_propre in vus:
            vus[nom_propre] += 1
            nom_unique = f"{nom_propre} ({vus[nom_propre]})"
            remarques.append(f"Le nom « {nom_propre} » apparaît plusieurs fois : renommé « {nom_unique} ».")
            nom_propre = nom_unique
        else:
            vus[nom_propre] = 1
        nouveaux.append(nom_propre)
    df.columns = nouveaux
    return df.reset_index(drop=True), remarques


def _nom_auto(nom) -> bool:
    """Vrai si pandas a inventé ce nom car la cellule d'en-tête était vide."""
    return str(nom).strip() == "" or str(nom).startswith("Unnamed:")


def _nom_sans_suffixe(nom: str, originaux: set[str]) -> str:
    """pandas renomme les doublons « x » en « x.1 », « x.2 » : on retire ce suffixe
    pour appliquer notre propre règle de nommage, plus lisible.
    Le suffixe n'est retiré que si « x » existe bien parmi les colonnes
    (ainsi « Profondeur 2.5 » reste intact)."""
    base, point, fin = nom.rpartition(".")
    return base if point and fin.isdigit() and base in originaux else nom


# ---------------------------------------------------------------------------
# Stockage (JSON) — le tableau est conservé tel quel dans la base
# ---------------------------------------------------------------------------
def tableau_vers_json(df: pd.DataFrame, description: dict | None = None) -> str:
    """Convertit un tableau en texte JSON (colonnes + lignes, ordre conservé).
    description : informations facultatives sur les colonnes (rôle, unité…)."""
    lignes = [[None if pd.isna(v) else v for v in ligne] for ligne in df.itertuples(index=False)]
    contenu = {"colonnes": list(df.columns), "lignes": lignes}
    if description is not None:
        contenu["description"] = description
    return json.dumps(contenu, ensure_ascii=False)


def json_description(texte: str | None) -> dict:
    """Description des colonnes enregistrée avec un tableau (vide si absente)."""
    return json.loads(texte).get("description", {}) if texte else {}


def json_vers_tableau(texte: str | None) -> pd.DataFrame:
    """Reconstruit le tableau enregistré par tableau_vers_json."""
    if not texte:
        return pd.DataFrame()
    contenu = json.loads(texte)
    return pd.DataFrame(contenu["lignes"], columns=contenu["colonnes"], dtype=object)
