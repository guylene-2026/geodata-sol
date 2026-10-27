"""Rattachement des données validées aux sondages, échantillons et profondeurs (phase 5).

Ce module prépare un « plan de rattachement » à partir d'un jeu de données validé :
quels sondages et échantillons sont cités, lesquels existent déjà, quels résultats
d'essais seront créés. Il ne touche pas à la base : l'enregistrement est fait par db.py
après confirmation de l'utilisateur.

Règle n° 10 : une ligne sans identifiant de sondage donne des essais SANS sondage,
explicitement marqués « localisation inconnue ».
"""

import re
from dataclasses import dataclass, field

import pandas as pd

from geodata.qualite import facteur_conversion

TYPES_SONDAGE = [
    "Sondage carotté",
    "Sondage destructif",
    "Sondage à la tarière",
    "Pénétromètre statique (CPT)",
    "Pénétromètre dynamique",
    "Essai SPT",
    "Sondage pressiométrique",
    "Fouille / puits à la pelle",
    "Piézomètre",
    "Autre",
]
SYSTEMES_COORDONNEES = [
    "WGS 84 — latitude / longitude en degrés (EPSG:4326)",
    "Lambert 93 — mètres (EPSG:2154)",
    "UTM — mètres (préciser la zone dans les observations)",
    "Repère local du chantier — mètres",
    "Inconnu",
]
TYPES_ECHANTILLON = ["Intact", "Remanié", "Carotte", "Sac", "Autre"]
TYPES_ESSAI = [
    "Teneur en eau",
    "Résistance / compression",
    "Cisaillement",
    "Pénétromètre",
    "Essai SPT",
    "Pressiomètre",
    "Limites d'Atterberg",
    "Granulométrie",
    "Masse / poids volumique",
    "Perméabilité",
    "Œdomètre / compressibilité",
    "Autre",
]


def localisation_connue(x, y, systeme: str | None) -> bool:
    """Règle n° 10 : la localisation n'est « connue » que si les deux coordonnées
    ET leur système de référence sont renseignés."""
    return x is not None and y is not None and bool(systeme) and systeme != "Inconnu"


def suggerer_type_essai(variable: str) -> str:
    """Type d'essai proposé d'après le nom de la variable."""
    v = variable.lower()
    regles = [
        (r"teneur en eau|\bw\b|humidit", "Teneur en eau"),
        (r"r[ée]sistance|compression|\bqu\b|\brc\b", "Résistance / compression"),
        (r"cisaillement|coh[ée]sion|frottement|\bc'|\bphi|angle", "Cisaillement"),
        (r"spt|\bn\b|coups", "Essai SPT"),
        (r"\bqc\b|p[ée]n[ée]tr|cpt", "Pénétromètre"),
        (r"pressio|\bem\b|\bpl\b", "Pressiomètre"),
        (r"atterberg|\bwl\b|\bwp\b|\bip\b|plasticit|liquidit", "Limites d'Atterberg"),
        (r"granulo|passant|tamis|\bd50\b|fines", "Granulométrie"),
        (r"masse volumique|poids volumique|densit|gamma|\bγ", "Masse / poids volumique"),
        (r"perm[ée]abilit|\bk\b", "Perméabilité"),
        (r"[œo]edom|compressibilit|\bcc\b|\bcs\b", "Œdomètre / compressibilité"),
    ]
    for motif, type_essai in regles:
        if re.search(motif, v):
            return type_essai
    return "Autre"


@dataclass
class PlanRattachement:
    """Ce que le rattachement va créer, à montrer à l'utilisateur avant confirmation."""

    col_sondage: str | None
    col_echantillon: str | None
    col_profondeur: str | None
    mesures: list[str]
    sondages_cites: list[str] = field(default_factory=list)
    sondages_nouveaux: list[str] = field(default_factory=list)
    echantillons_cites: dict = field(default_factory=dict)  # code -> {sondage, profondeur}
    echantillons_nouveaux: list[str] = field(default_factory=list)
    echantillons_conflits: list[str] = field(default_factory=list)  # même code, sondages différents
    lignes_sans_sondage: list[int] = field(default_factory=list)
    nb_essais: int = 0
    unite_profondeur: str | None = None
    facteur_profondeur: float = 1.0  # passage de l'unité de profondeur aux mètres (règle n° 2 : affiché)

    def profondeur_m(self, valeur) -> float | None:
        """Profondeur d'une ligne exprimée en mètres (None si absente)."""
        if valeur is None or pd.isna(valeur):
            return None
        return float(valeur) * self.facteur_profondeur


def colonnes_par_role(description: dict) -> dict[str, list[str]]:
    """Regroupe les colonnes du tableau validé par rôle."""
    roles: dict[str, list[str]] = {}
    for titre, info in description.items():
        roles.setdefault(info.get("role"), []).append(titre)
    return roles


def _texte(v) -> str | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip()
    return s or None


def preparer_rattachement(
    tableau: pd.DataFrame,
    description: dict,
    codes_sondages_existants: set[str],
    codes_echantillons_existants: set[str],
    col_profondeur: str | None = None,
) -> PlanRattachement:
    """Analyse un tableau validé et prépare le plan de rattachement."""
    roles = colonnes_par_role(description)
    col_s = (roles.get("id_sondage") or [None])[0]
    col_e = (roles.get("id_echantillon") or [None])[0]
    if col_profondeur is None:
        col_profondeur = (roles.get("profondeur") or [None])[0]
    mesures = roles.get("mesure", [])
    plan = PlanRattachement(col_s, col_e, col_profondeur, mesures)
    if col_profondeur:
        plan.unite_profondeur = description[col_profondeur].get("unite") or "m"
        plan.facteur_profondeur = facteur_conversion(plan.unite_profondeur, "m") or 1.0

    for _, ligne in tableau.iterrows():
        code_s = _texte(ligne[col_s]) if col_s else None
        if code_s is None:
            plan.lignes_sans_sondage.append(int(ligne["N° ligne"]))
        elif code_s not in plan.sondages_cites:
            plan.sondages_cites.append(code_s)
        code_e = _texte(ligne[col_e]) if col_e else None
        if code_e:
            prof = plan.profondeur_m(ligne[col_profondeur]) if col_profondeur else None
            info = plan.echantillons_cites.setdefault(code_e, {"sondage": code_s, "profondeur": prof})
            if info["sondage"] != code_s and code_e not in plan.echantillons_conflits:
                plan.echantillons_conflits.append(code_e)
        plan.nb_essais += sum(1 for m in mesures if ligne[m] is not None and not pd.isna(ligne[m]))

    plan.sondages_nouveaux = [c for c in plan.sondages_cites if c not in codes_sondages_existants]
    plan.echantillons_nouveaux = [c for c in plan.echantillons_cites if c not in codes_echantillons_existants]
    return plan


def generer_essais(
    tableau: pd.DataFrame,
    description: dict,
    plan: PlanRattachement,
    types_essai: dict[str, str],
) -> list[dict]:
    """Une ligne d'essai par valeur de mesure non vide du tableau validé.
    Les identifiants (codes) de sondage/échantillon sont convertis en id par db.py."""
    essais = []
    for _, ligne in tableau.iterrows():
        code_s = _texte(ligne[plan.col_sondage]) if plan.col_sondage else None
        code_e = _texte(ligne[plan.col_echantillon]) if plan.col_echantillon else None
        prof = plan.profondeur_m(ligne[plan.col_profondeur]) if plan.col_profondeur else None
        for m in plan.mesures:
            valeur = ligne[m]
            if valeur is None or pd.isna(valeur):
                continue
            essais.append({
                "code_sondage": code_s,
                "code_echantillon": code_e,
                "type_essai": types_essai.get(m, "Autre"),
                "parametre": m,
                "valeur": float(valeur),
                "unite": description[m].get("unite"),
                "profondeur_m": prof,
                "remarques": f"ligne {int(ligne['N° ligne'])} du fichier"
                             + ("" if code_s else " — localisation inconnue"),
            })
    return essais
