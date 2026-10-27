"""Contrôle qualité des données importées (phase 4).

Ce module ne modifie JAMAIS les données brutes et ne décide rien seul :
il analyse, signale et propose. Les choix sont faits par l'utilisateur
et transmis sous forme d'« interprétation » (dictionnaire) pour chaque colonne.

Règles appliquées (voir CLAUDE.md) :
- n° 1 : « 25 % », « 0,25 » et « 25 » dans une même colonne ne sont pas
  mélangés automatiquement : chaque groupe doit être interprété par l'utilisateur ;
- n° 2 : toute conversion d'unité est proposée avec son facteur, puis validée ;
- n° 4 : les valeurs atypiques sont signalées (méthode affichée), jamais supprimées ;
- n° 5 : la virgule décimale française est reconnue (« 0,25 » = 0.25).

Numérotation des lignes : « ligne n° k » = k-ième ligne de données du tableau
importé (la ligne des noms de colonnes n'est pas comptée), comme dans l'aperçu.
"""

import re
from collections import Counter
from dataclasses import dataclass, field

import pandas as pd

# ---------------------------------------------------------------------------
# Unités connues et facteurs de conversion vers l'unité de référence de chaque grandeur
# ---------------------------------------------------------------------------
UNITES = {
    "longueur": {"m": 1.0, "cm": 0.01, "mm": 0.001},
    "contrainte / pression": {"kPa": 1.0, "kN/m²": 1.0, "Pa": 0.001, "MPa": 1000.0,
                              "MN/m²": 1000.0, "bar": 100.0},
    "pourcentage": {"%": 1.0},
    "poids volumique": {"kN/m³": 1.0},
    "masse volumique": {"t/m³": 1.0, "g/cm³": 1.0, "kg/m³": 0.001},
    "perméabilité": {"m/s": 1.0, "cm/s": 0.01},
    "nombre de coups": {"coups": 1.0},
    "angle": {"°": 1.0},
}
# Écritures courantes → écriture normalisée (comparaison sans majuscules ni espaces)
_ALIAS_UNITES = {
    "m": "m", "cm": "cm", "mm": "mm", "metre": "m", "metres": "m", "mètre": "m", "mètres": "m",
    "kpa": "kPa", "kn/m2": "kN/m²", "kn/m²": "kN/m²", "pa": "Pa", "mpa": "MPa",
    "mn/m2": "MN/m²", "mn/m²": "MN/m²", "bar": "bar", "bars": "bar",
    "%": "%", "pourcent": "%", "pourcentage": "%",
    "kn/m3": "kN/m³", "kn/m³": "kN/m³",
    "t/m3": "t/m³", "t/m³": "t/m³", "g/cm3": "g/cm³", "g/cm³": "g/cm³",
    "kg/m3": "kg/m³", "kg/m³": "kg/m³",
    "m/s": "m/s", "cm/s": "cm/s",
    "coups": "coups", "coup": "coups", "cps": "coups",
    "°": "°", "degres": "°", "degrés": "°",
}
UNITES_PROPOSEES = [u for grandeur in UNITES.values() for u in grandeur] + ["sans unité"]

# Valeurs couramment utilisées pour dire « pas de mesure »
MARQUEURS_MANQUANTS = {"na", "n/a", "n.a.", "n.a", "nd", "n.d.", "n.d", "nc", "n.c.", "-", "--",
                       "—", "–", "?", "nan", "null", "néant", "neant", "/", "x", "sans objet"}

# Rôles possibles d'une colonne
ROLES = {
    "id_sondage": "Identifiant de sondage",
    "id_echantillon": "Identifiant d'échantillon",
    "profondeur": "Profondeur",
    "mesure": "Mesure numérique",
    "texte": "Texte / description",
    "date": "Date",
    "ignorer": "Ignorer",
}
ROLES_NUMERIQUES = ("profondeur", "mesure")

# Méthode de détection des valeurs atypiques (affichée à l'utilisateur, règle n° 4)
COEFF_TUKEY = 1.5
METHODE_ATYPIQUES = (
    "Règle de Tukey (boîte à moustaches) : une valeur est signalée si elle est inférieure à "
    f"Q1 − {COEFF_TUKEY} × IQR ou supérieure à Q3 + {COEFF_TUKEY} × IQR, où Q1 et Q3 sont le "
    "1er et le 3e quartile et IQR = Q3 − Q1 (écart interquartile). Les valeurs négatives d'une "
    "profondeur ou d'un pourcentage sont aussi signalées. Calcul sur les valeurs interprétées "
    "de la colonne (au moins 4 valeurs)."
)
N_MIN_ATYPIQUES = 4


# ---------------------------------------------------------------------------
# Unités
# ---------------------------------------------------------------------------
def normaliser_unite(texte: str | None) -> str | None:
    """Écriture normalisée d'une unité connue (« kpa » → « kPa »), sinon None."""
    if not texte:
        return None
    cle = texte.strip().lower().replace(" ", "").replace("^2", "2").replace("^3", "3")
    return _ALIAS_UNITES.get(cle)


def grandeur(unite: str | None) -> str | None:
    """Grandeur physique d'une unité normalisée (« kPa » → « contrainte / pression »)."""
    for nom, unites in UNITES.items():
        if unite in unites:
            return nom
    return None


def facteur_conversion(depuis: str, vers: str) -> float | None:
    """Facteur multiplicatif pour passer de l'unité `depuis` à l'unité `vers`
    (None si les deux unités ne mesurent pas la même grandeur)."""
    g = grandeur(depuis)
    if g is None or g != grandeur(vers):
        return None
    return UNITES[g][depuis] / UNITES[g][vers]


def unite_dans_nom(nom_colonne: str) -> tuple[str | None, str | None]:
    """Unité écrite entre parenthèses ou crochets à la fin d'un nom de colonne.
    Renvoie (texte trouvé, unité normalisée ou None si inconnue)."""
    m = re.search(r"[\(\[]\s*([^\)\]]+?)\s*[\)\]]\s*(?:\(\d+\))?\s*$", str(nom_colonne))
    if not m:
        return None, None
    return m.group(1), normaliser_unite(m.group(1))


def nom_sans_unite(nom_colonne: str) -> str:
    """« Profondeur (m) » → « Profondeur »."""
    return re.sub(r"\s*[\(\[][^\)\]]*[\)\]]\s*(?:\(\d+\))?\s*$", "", str(nom_colonne)).strip() or str(nom_colonne)


# ---------------------------------------------------------------------------
# Lecture d'une valeur
# ---------------------------------------------------------------------------
@dataclass
class Valeur:
    """Résultat de l'analyse d'une cellule.

    nature : 'manquant', 'marqueur' (ex. « nd »), 'nombre', 'pourcentage' (« 25 % »),
             'nombre_unite' (« 25 kPa »), 'censure' (« <0,5 »), 'format_ambigu'
             (« 1.234,5 »), 'unite_inconnue' (« 12 xyz »), 'texte'.
    """

    nature: str
    nombre: float | None = None
    unite: str | None = None  # unité écrite dans la cellule (normalisée si connue)
    separateur: str | None = None  # séparateur décimal utilisé : ',' ou '.'


_RE_NOMBRE = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$")
_RE_MILLIERS = re.compile(r"^[+-]?\d{1,3}([   ]\d{3})+([.,]\d+)?$")
_RE_NOMBRE_UNITE = re.compile(r"^([+-]?[\d.,\s  ]*\d(?:[eE][+-]?\d+)?)\s*([^\d\s].*)$")
_RE_CENSURE = re.compile(r"^(<=|>=|<|>|≤|≥)\s*(.+)$")


def lire_nombre(texte: str) -> tuple[float | None, str | None, bool]:
    """Lit un nombre écrit à la française ou à l'anglaise.
    Renvoie (nombre, séparateur décimal, ambigu). ambigu=True si l'écriture
    ne permet pas de savoir quel est le séparateur décimal (ex. « 1.234,5 »)."""
    s = texte.strip()
    if _RE_MILLIERS.match(s):  # « 1 234,5 » : espaces = séparateurs de milliers
        s = re.sub(r"[   ]", "", s)
    nb_virgules, nb_points = s.count(","), s.count(".")
    if nb_virgules and nb_points:
        return None, None, True
    if nb_virgules > 1 or nb_points > 1:
        return None, None, True
    separateur = "," if nb_virgules else ("." if nb_points else None)
    s = s.replace(",", ".")
    if not _RE_NOMBRE.match(s):
        return None, None, False
    return float(s), separateur, False


def analyser_valeur(brute) -> Valeur:
    """Détermine ce que représente une cellule, sans rien convertir."""
    if brute is None or (isinstance(brute, float) and pd.isna(brute)):
        return Valeur("manquant")
    s = str(brute).strip()
    if s == "":
        return Valeur("manquant")
    if s.lower() in MARQUEURS_MANQUANTS:
        return Valeur("marqueur")

    m = _RE_CENSURE.match(s)
    if m:
        n, sep, _ = lire_nombre(m.group(2).rstrip("%").strip())
        if n is not None:
            return Valeur("censure", n, separateur=sep)
        return Valeur("texte")

    if s.endswith("%"):
        n, sep, ambigu = lire_nombre(s[:-1])
        if n is not None:
            return Valeur("pourcentage", n, "%", sep)
        return Valeur("format_ambigu" if ambigu else "texte")

    n, sep, ambigu = lire_nombre(s)
    if n is not None:
        return Valeur("nombre", n, separateur=sep)
    if ambigu:
        return Valeur("format_ambigu")

    m = _RE_NOMBRE_UNITE.match(s)
    if m:
        n, sep, ambigu = lire_nombre(m.group(1))
        if n is not None:
            unite = normaliser_unite(m.group(2))
            if unite:
                return Valeur("nombre_unite", n, unite, sep)
            return Valeur("unite_inconnue", n, m.group(2).strip(), sep)
        if ambigu:
            return Valeur("format_ambigu")
    return Valeur("texte")


# ---------------------------------------------------------------------------
# Profil d'une colonne
# ---------------------------------------------------------------------------
NATURES_LIBELLES = {
    "nombre": "nombres simples",
    "pourcentage": "valeurs avec « % »",
    "nombre_unite": "nombres avec unité écrite",
    "manquant": "cellules vides",
    "marqueur": "marqueurs de valeur manquante (nd, -, NA…)",
    "censure": "valeurs censurées (<, >)",
    "format_ambigu": "formats ambigus (ex. 1.234,5)",
    "unite_inconnue": "unités non reconnues",
    "texte": "textes non numériques",
}
NATURES_NUMERIQUES = ("nombre", "pourcentage", "nombre_unite")

# Groupes de conventions pour les colonnes de type pourcentage (règle n° 1)
GROUPES_POURCENTAGE = {
    "avec_pct": "Valeurs écrites avec « % » (ex. « 25 % »)",
    "inf_1": "Nombres sans « % » compris entre 0 et 1 (ex. « 0,28 »)",
    "sup_1": "Nombres sans « % » supérieurs à 1 (ex. « 22 »)",
}
CHOIX_GROUPES = {
    "avec_pct": {"pourcent": "Pourcentage : « 25 % » = 25 %", "exclure": "À vérifier : exclure de l'analyse"},
    "inf_1": {"fraction": "Fraction : « 0,28 » = 28 % (multiplier par 100)",
              "pourcent": "Déjà en % : « 0,28 » = 0,28 %",
              "exclure": "À vérifier : exclure de l'analyse"},
    "sup_1": {"pourcent": "Déjà en % : « 22 » = 22 %",
              "exclure": "À vérifier : exclure de l'analyse"},
}
_MOTS_POURCENTAGE = re.compile(r"teneur|pourcent|taux|humidit|\bw\b|\bwn?\b|degr[ée] de satur|\bsr\b", re.I)


@dataclass
class ProfilColonne:
    """Tout ce que l'analyse automatique a trouvé dans une colonne."""

    nom: str
    natures: list[Valeur]
    comptes: Counter = field(default_factory=Counter)
    exemples: dict = field(default_factory=dict)  # nature -> [(ligne, texte)]
    unite_entete_texte: str | None = None
    unite_entete: str | None = None
    unites_valeurs: Counter = field(default_factory=Counter)
    separateurs: Counter = field(default_factory=Counter)

    @property
    def n_total(self) -> int:
        return len(self.natures)

    @property
    def n_numeriques(self) -> int:
        return sum(self.comptes[n] for n in NATURES_NUMERIQUES)

    @property
    def n_remplis(self) -> int:
        return self.n_total - self.comptes["manquant"]

    @property
    def type_detecte(self) -> str:
        """Type dominant : 'vide', 'numérique', 'texte' ou 'mixte'."""
        if self.n_remplis == 0:
            return "vide"
        part = self.n_numeriques / self.n_remplis
        if part >= 0.999:
            return "numérique"
        if part == 0 or self.n_numeriques <= 1 and self.n_remplis > 3:
            return "texte"
        return "mixte"


def profiler_colonne(nom: str, serie: pd.Series) -> ProfilColonne:
    """Analyse toutes les cellules d'une colonne."""
    natures = [analyser_valeur(v) for v in serie.tolist()]
    profil = ProfilColonne(nom, natures)
    profil.unite_entete_texte, profil.unite_entete = unite_dans_nom(nom)
    for ligne, (brute, v) in enumerate(zip(serie.tolist(), natures), start=1):
        profil.comptes[v.nature] += 1
        if v.nature != "manquant":
            profil.exemples.setdefault(v.nature, [])
            if len(profil.exemples[v.nature]) < 6:
                profil.exemples[v.nature].append((ligne, str(brute)))
        if v.unite and v.nature in ("pourcentage", "nombre_unite", "unite_inconnue"):
            profil.unites_valeurs[v.unite] += 1
        if v.separateur:
            profil.separateurs[v.separateur] += 1
    return profil


def suggerer_role(nom: str, profil: ProfilColonne) -> str:
    """Rôle proposé d'après le nom de la colonne et son contenu."""
    n = nom.lower()
    if re.search(r"sondage|forage|\bsc\b|borehole|\bbh\b|piézo|piezo|puits", n):
        return "id_sondage"
    if re.search(r"[ée]chantillon|\bech\b|\béch\b|sample|\bid\b|identifiant|code", n):
        return "id_echantillon"
    if re.search(r"profondeur|\bprof\b|depth|\bz\b|cote", n):
        return "profondeur"
    if re.search(r"date", n):
        return "date"
    if profil.type_detecte == "vide":
        return "ignorer"
    if profil.type_detecte in ("numérique", "mixte") and profil.n_numeriques >= max(1, profil.n_remplis // 2):
        return "mesure"
    return "texte"


def suggerer_unite(nom: str, profil: ProfilColonne, role: str) -> str | None:
    """Unité proposée : celle écrite dans le nom de colonne, sinon la plus fréquente
    dans les valeurs, sinon une valeur habituelle pour le rôle."""
    if profil.unite_entete:
        return profil.unite_entete
    connues = [u for u in profil.unites_valeurs if grandeur(u)]
    if connues:
        return Counter({u: profil.unites_valeurs[u] for u in connues}).most_common(1)[0][0]
    if role == "profondeur":
        return "m"
    if role == "mesure" and _MOTS_POURCENTAGE.search(nom):
        return "%"
    return None


def est_type_pourcentage(nom: str, profil: ProfilColonne, unite_cible: str | None) -> bool:
    """Vrai si la colonne exprime (ou semble exprimer) un pourcentage."""
    return unite_cible == "%" or profil.comptes["pourcentage"] > 0 or bool(_MOTS_POURCENTAGE.search(nom))


def groupes_pourcentage(profil: ProfilColonne) -> dict[str, list[tuple[int, str]]]:
    """Répartit les valeurs numériques d'une colonne de pourcentages en groupes de conventions.
    Renvoie {groupe: [(ligne, texte brut), …]} pour les groupes non vides."""
    groupes: dict[str, list] = {}
    for ligne, v in enumerate(profil.natures, start=1):
        if v.nature == "pourcentage":
            cle = "avec_pct"
        elif v.nature == "nombre":
            cle = "inf_1" if 0 <= v.nombre <= 1 else "sup_1"
        else:
            continue
        groupes.setdefault(cle, []).append((ligne, v))
    return groupes


def convention_ambigue(profil: ProfilColonne, groupes: dict) -> bool:
    """Règle n° 1 : plusieurs conventions coexistent, ou seulement des valeurs entre 0 et 1
    (fraction ? pourcentage ?) → l'utilisateur doit trancher."""
    return len(groupes) >= 2 or set(groupes) == {"inf_1"}


# ---------------------------------------------------------------------------
# Décisions à prendre pour une colonne
# ---------------------------------------------------------------------------
def decisions_requises(nom: str, profil: ProfilColonne, role: str, unite_cible: str | None) -> dict:
    """Liste ce que l'utilisateur doit trancher pour interpréter une colonne numérique.

    Renvoie un dictionnaire :
      groupes      : {groupe: [(ligne, Valeur)]} si convention de pourcentage ambiguë, sinon {}
      conversions  : {unité source: facteur vers l'unité cible} (unités différentes de la cible)
      incompatibles: unités écrites qui ne mesurent pas la même grandeur que la cible
      separateurs_mixtes : True si virgule ET point décimaux coexistent
    """
    resultat = {"groupes": {}, "conversions": {}, "incompatibles": [], "separateurs_mixtes": False}
    if role not in ROLES_NUMERIQUES:
        return resultat
    if est_type_pourcentage(nom, profil, unite_cible) and unite_cible in (None, "%"):
        groupes = groupes_pourcentage(profil)
        if convention_ambigue(profil, groupes):
            resultat["groupes"] = groupes
    # Unités sources : celle du nom de colonne (pour les nombres simples) + celles des cellules
    sources = set(profil.unites_valeurs)
    if profil.unite_entete and profil.comptes["nombre"]:
        sources.add(profil.unite_entete)
    for u in sorted(sources):
        if u == unite_cible or unite_cible is None or (u == "%" and unite_cible == "%"):
            continue
        f = facteur_conversion(u, unite_cible)
        if f is None:
            resultat["incompatibles"].append(u)
        else:
            resultat["conversions"][u] = f
    resultat["separateurs_mixtes"] = len(profil.separateurs) > 1
    return resultat


def interpretation_complete(requis: dict, interpretation: dict | None) -> bool:
    """Vrai si l'utilisateur a pris toutes les décisions nécessaires."""
    if interpretation is None:
        return False
    choix = interpretation.get("groupes", {})
    if any(g not in choix for g in requis["groupes"]):
        return False
    if requis["conversions"] and not interpretation.get("conversion_validee"):
        return False
    if requis["separateurs_mixtes"] and not interpretation.get("separateurs_verifies"):
        return False
    return True


# ---------------------------------------------------------------------------
# Application des décisions
# ---------------------------------------------------------------------------
def _net(x: float) -> float:
    """Supprime les imprécisions de calcul (0,28 × 100 = 28,000000000000004 → 28)."""
    return float(f"{x:.12g}")


def nombre_court(x: float) -> str:
    """Nombre court à la française pour les messages (39.3 → « 39,3 »)."""
    return f"{x:.4g}".replace(".", ",")

def interpreter_colonne(
    nom: str, serie: pd.Series, role: str, unite_cible: str | None, interpretation: dict
) -> pd.DataFrame:
    """Applique les décisions validées à une colonne numérique.

    Renvoie un tableau (une ligne par cellule) avec :
      valeur : nombre retenu, exprimé dans l'unité cible (None si non retenu)
      statut : 'retenue', 'convertie', 'manquante' ou 'exclue'
      detail : explication en clair
    """
    profil = profiler_colonne(nom, serie)
    choix = interpretation.get("groupes", {})
    conversion_ok = interpretation.get("conversion_validee", False)
    pct = est_type_pourcentage(nom, profil, unite_cible) and unite_cible in (None, "%")
    unite_simple = profil.unite_entete or unite_cible  # unité des nombres sans unité écrite

    lignes = []
    for brute, v in zip(serie.tolist(), profil.natures):
        if v.nature in ("manquant", "marqueur"):
            lignes.append((None, "manquante", "valeur absente" if v.nature == "manquant"
                           else f"marqueur « {brute} » lu comme valeur manquante"))
            continue
        if v.nature == "censure":
            lignes.append((None, "exclue", f"valeur censurée « {brute} » (limite de détection) : non chiffrable"))
            continue
        if v.nature in ("texte", "format_ambigu", "unite_inconnue"):
            lignes.append((None, "exclue", f"« {brute} » : {NATURES_LIBELLES[v.nature][:-1]}"))
            continue

        # Colonnes de pourcentage : convention décidée par groupe
        if pct and v.nature in ("nombre", "pourcentage"):
            groupe = "avec_pct" if v.nature == "pourcentage" else ("inf_1" if 0 <= v.nombre <= 1 else "sup_1")
            decision = choix.get(groupe, "pourcent")  # pas d'ambiguïté → valeur déjà en %
            if decision == "exclure":
                lignes.append((None, "exclue", f"« {brute} » : convention incertaine, à vérifier"))
            elif decision == "fraction":
                lignes.append((_net(v.nombre * 100), "convertie",
                               f"« {brute} » fraction × 100 = {nombre_court(_net(v.nombre * 100))} %"))
            else:
                lignes.append((v.nombre, "retenue", ""))
            continue

        # Autres colonnes : conversion d'unité éventuelle
        unite_source = v.unite if v.nature in ("nombre_unite", "pourcentage") else unite_simple
        if unite_cible is None or unite_source is None or unite_source == unite_cible:
            lignes.append((v.nombre, "retenue", ""))
            continue
        f = facteur_conversion(unite_source, unite_cible)
        if f is None:
            lignes.append((None, "exclue", f"« {brute} » : unité {unite_source} incompatible avec {unite_cible}"))
        elif not conversion_ok:
            lignes.append((None, "exclue", f"« {brute} » : conversion {unite_source} → {unite_cible} non validée"))
        else:
            lignes.append((_net(v.nombre * f), "convertie",
                           f"« {brute} » {unite_source} × {nombre_court(f)} = {nombre_court(_net(v.nombre * f))} {unite_cible}"))
    return pd.DataFrame(lignes, columns=["valeur", "statut", "detail"], index=serie.index)


# ---------------------------------------------------------------------------
# Doublons et identifiants
# ---------------------------------------------------------------------------
def doublons_exacts(df: pd.DataFrame) -> list[list[int]]:
    """Groupes de lignes strictement identiques (numéros de lignes à partir de 1)."""
    texte = df.astype(str)
    masque = texte.duplicated(keep=False)
    groupes: dict[tuple, list[int]] = {}
    for i in df.index[masque]:
        groupes.setdefault(tuple(texte.loc[i]), []).append(int(i) + 1)
    return list(groupes.values())


MOTS_SYNTHESE = {"mean", "moyenne", "moy", "average", "min", "minimum", "max", "maximum", "total", "somme",
                 "sum", "median", "médiane", "mediane", "std", "sd", "écart-type", "ecart-type", "ecarttype",
                 "écart type", "ecart type", "cv", "variance", "count", "effectif", "nombre"}


def lignes_synthese(df: pd.DataFrame) -> list[tuple[int, str]]:
    """Lignes qui ressemblent à des synthèses (« Mean », « Min. », « Total »…) et non à
    des observations : [(n° de ligne, texte trouvé)]. Elles sont signalées, pas supprimées."""
    resultat = []
    for i, ligne in df.iterrows():
        for v in ligne:
            if v is None or (isinstance(v, float) and pd.isna(v)):
                continue
            mot = str(v).strip().lower().rstrip(".:").strip()
            if mot in MOTS_SYNTHESE:
                resultat.append((int(i) + 1, str(v).strip()))
                break
    return resultat


def identifiants_dupliques(serie: pd.Series) -> dict[str, list[int]]:
    """Identifiants présents sur plusieurs lignes : {identifiant: [lignes]}."""
    resultat: dict[str, list[int]] = {}
    for i, v in serie.items():
        if v is not None and str(v).strip():
            resultat.setdefault(str(v).strip(), []).append(int(i) + 1)
    return {k: v for k, v in resultat.items() if len(v) > 1}


# ---------------------------------------------------------------------------
# Valeurs atypiques (règle n° 4)
# ---------------------------------------------------------------------------
def detecter_atypiques(valeurs: pd.Series, role: str, unite: str | None) -> tuple[pd.DataFrame, dict]:
    """Signale les valeurs atypiques d'une série de nombres déjà interprétés.

    Renvoie (tableau des valeurs signalées, informations sur le calcul).
    Le tableau contient : ligne, valeur, raison.
    """
    v = pd.to_numeric(valeurs, errors="coerce").dropna()
    infos = {"n": len(v), "methode": METHODE_ATYPIQUES}
    signalees = []
    if len(v) >= N_MIN_ATYPIQUES:
        q1, q3 = v.quantile(0.25), v.quantile(0.75)
        iqr = q3 - q1
        bas, haut = q1 - COEFF_TUKEY * iqr, q3 + COEFF_TUKEY * iqr
        infos.update(q1=q1, q3=q3, iqr=iqr, borne_basse=bas, borne_haute=haut)
        for i, x in v.items():
            if x < bas:
                signalees.append((int(i) + 1, x, f"inférieure à la borne basse ({nombre_court(bas)})"))
            elif x > haut:
                signalees.append((int(i) + 1, x, f"supérieure à la borne haute ({nombre_court(haut)})"))
    if role == "profondeur" or unite == "%":
        deja = {s[0] for s in signalees}
        for i, x in v.items():
            if x < 0 and int(i) + 1 not in deja:
                signalees.append((int(i) + 1, x, "valeur négative, physiquement suspecte"))
    tableau = pd.DataFrame(signalees, columns=["ligne", "valeur", "raison"]).sort_values("ligne")
    return tableau.reset_index(drop=True), infos


# ---------------------------------------------------------------------------
# Tableau validé
# ---------------------------------------------------------------------------
def construire_tableau_valide(
    brut: pd.DataFrame,
    colonnes: list[dict],
    exclusions: dict[str, set[int]],
    lignes_exclues: set[int],
) -> tuple[pd.DataFrame, dict]:
    """Construit la version validée des données, utilisée par les analyses.

    colonnes      : description de chaque colonne (nom_origine, variable, unite, role, interpretation)
    exclusions    : {nom_origine: {lignes}} valeurs atypiques exclues par l'utilisateur
    lignes_exclues: lignes entières exclues (doublons exacts), numéros à partir de 1
    La colonne « N° ligne » garde le numéro de la ligne d'origine (traçabilité).

    Renvoie (tableau, description) où description = {titre de colonne: {role, unite, origine}}.
    """
    resultat = pd.DataFrame({"N° ligne": [int(i) + 1 for i in brut.index]}, index=brut.index)
    description = {"N° ligne": {"role": "ligne", "unite": None, "origine": None}}
    for c in colonnes:
        role = c.get("role")
        if role in (None, "ignorer"):
            continue
        nom = c["nom_origine"]
        titre, k = c.get("variable") or nom, 2
        while titre in resultat.columns:  # deux colonnes avec la même variable
            titre, k = f"{c.get('variable') or nom} ({k})", k + 1
        description[titre] = {"role": role, "unite": c.get("unite"), "origine": nom}
        if role in ROLES_NUMERIQUES:
            interp = interpreter_colonne(nom, brut[nom], role, c.get("unite"), c.get("interpretation") or {})
            valeurs = interp["valeur"].astype(object)
            for ligne in exclusions.get(nom, set()):
                if ligne - 1 in valeurs.index:
                    valeurs.loc[ligne - 1] = None
            resultat[titre] = pd.to_numeric(valeurs, errors="coerce")
        else:
            resultat[titre] = brut[nom].map(lambda x: None if x is None or pd.isna(x) else str(x).strip())
            resultat[titre] = resultat[titre].astype(object).where(resultat[titre].notna(), None)
    resultat = resultat[~resultat["N° ligne"].isin(lignes_exclues)]
    return resultat.reset_index(drop=True), description
