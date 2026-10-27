"""Statistiques descriptives et graphiques (phase 6).

Les calculs portent sur la version VALIDÉE d'un jeu de données (après contrôle
qualité). Chaque graphique respecte la règle n° 7 : titre explicite, noms des
variables avec unités, légende si plusieurs séries, nombre d'observations (n).

Vocabulaire (règle n° 9) :
- observations           : les valeurs mesurées retenues ;
- résultats calculés     : ce qui décrit exactement l'échantillon (n, moyenne, médiane, min, max…) ;
- estimations statistiques : ce que l'échantillon permet d'estimer pour l'ensemble du sol
  étudié (variance et écart-type corrigés, intervalle de confiance de la moyenne) ;
- hypothèses et limites  : conditions sous lesquelles ces estimations ont un sens.
"""

import math

import pandas as pd
import plotly.graph_objects as go
from scipy import stats as sps

# Palette catégorielle de référence (ordre fixe, validée pour les daltoniens).
# Au-delà de 3 séries sur un nuage de points, la forme des marqueurs complète la couleur.
PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
SYMBOLES = ["circle", "square", "diamond", "triangle-up", "cross", "x", "star", "hexagon"]
COULEUR_UNIQUE = PALETTE[0]
ENCRE, ENCRE_SECONDAIRE, GRILLE = "#111111", "#52514e", "#e6e3ee"
INCONNU = "localisation inconnue"
NON_RENSEIGNE = "non renseigné"
MAX_GROUPES = 8  # au-delà, les plus petits groupes sont regroupés dans « Autres »


# ---------------------------------------------------------------------------
# Variables
# ---------------------------------------------------------------------------
def variables_numeriques(description: dict) -> list[str]:
    """Colonnes numériques d'un tableau validé : les mesures d'abord, puis les profondeurs."""
    mesures = [t for t, info in description.items() if info.get("role") == "mesure"]
    return mesures + [t for t, info in description.items() if info.get("role") == "profondeur"]


def variables_groupement(description: dict) -> list[str]:
    """Colonnes de texte utilisables pour comparer des groupes (sondage, nature du sol…)."""
    return [t for t, info in description.items() if info.get("role") in ("id_sondage", "texte", "id_echantillon")]


def libelle(variable: str, description: dict) -> str:
    """« Teneur en eau (%) » : nom de variable + unité."""
    unite = description.get(variable, {}).get("unite")
    return f"{variable} ({unite})" if unite else f"{variable} (sans unité)"


def nombre_fr(x, chiffres: int = 4) -> str:
    """Nombre écrit à la française (virgule décimale), chiffres significatifs."""
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return "—"
    return f"{x:.{chiffres}g}".replace(".", ",").replace("e+0", "e+").replace("e-0", "e-")


def groupes(tableau: pd.DataFrame, colonne: str, description: dict) -> pd.Series:
    """Étiquette de groupe de chaque ligne ; les valeurs absentes restent visibles
    (« localisation inconnue » pour un sondage, sinon « non renseigné »)."""
    absent = INCONNU if description.get(colonne, {}).get("role") == "id_sondage" else NON_RENSEIGNE
    return tableau[colonne].map(lambda v: absent if v is None or pd.isna(v) or str(v).strip() == "" else str(v))


# ---------------------------------------------------------------------------
# Statistiques descriptives
# ---------------------------------------------------------------------------
def statistiques(valeurs: pd.Series, niveau: float = 0.95) -> dict:
    """Statistiques descriptives d'une série de nombres (valeurs absentes ignorées).

    Quartiles : interpolation linéaire (méthode par défaut de pandas, dite « type 7 »).
    Variance et écart-type : estimateurs corrigés (division par n − 1).
    """
    v = pd.to_numeric(valeurs, errors="coerce").dropna()
    n = len(v)
    r = {"n": n, "n_absentes": int(len(valeurs) - n)}
    if n == 0:
        return r
    r.update(
        moyenne=v.mean(), mediane=v.median(), minimum=v.min(), maximum=v.max(),
        q1=v.quantile(0.25), q3=v.quantile(0.75),
    )
    r["etendue"] = r["maximum"] - r["minimum"]
    r["iqr"] = r["q3"] - r["q1"]
    if n >= 2:
        r["variance"] = v.var(ddof=1)
        r["ecart_type"] = v.std(ddof=1)
        r["cv"] = r["ecart_type"] / abs(r["moyenne"]) * 100 if r["moyenne"] else float("nan")
        t = sps.t.ppf((1 + niveau) / 2, df=n - 1)
        marge = t * r["ecart_type"] / math.sqrt(n)
        r["ic"] = (r["moyenne"] - marge, r["moyenne"] + marge)
        r["niveau_ic"] = niveau
    return r


def tableau_statistiques(r: dict, unite: str | None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Deux tableaux lisibles : résultats calculés et estimations statistiques."""
    u = f" {unite}" if unite else ""
    calcules = [
        ("Nombre d'observations (n)", str(r["n"]), "nombre de valeurs utilisées"),
        ("Moyenne", nombre_fr(r.get("moyenne")) + u, "somme des valeurs ÷ n"),
        ("Médiane", nombre_fr(r.get("mediane")) + u, "valeur centrale : 50 % des valeurs au-dessous"),
        ("Minimum", nombre_fr(r.get("minimum")) + u, ""),
        ("1er quartile (Q1)", nombre_fr(r.get("q1")) + u, "25 % des valeurs au-dessous"),
        ("3e quartile (Q3)", nombre_fr(r.get("q3")) + u, "75 % des valeurs au-dessous"),
        ("Maximum", nombre_fr(r.get("maximum")) + u, ""),
        ("Étendue", nombre_fr(r.get("etendue")) + u, "maximum − minimum"),
        ("Écart interquartile (IQR)", nombre_fr(r.get("iqr")) + u, "Q3 − Q1"),
    ]
    estimations = []
    if r["n"] >= 2:
        unite_carre = f" ({unite})²" if unite else ""
        lo, hi = r["ic"]
        estimations = [
            ("Variance", nombre_fr(r["variance"]) + unite_carre, "dispersion ; estimateur corrigé (÷ n − 1)"),
            ("Écart-type", nombre_fr(r["ecart_type"]) + u, "racine de la variance ; même unité que les valeurs"),
            ("Coefficient de variation", nombre_fr(r["cv"], 3) + " %", "écart-type ÷ moyenne"),
            (f"Intervalle de confiance à {r['niveau_ic'] * 100:.0f} % de la moyenne",
             f"[{nombre_fr(lo)} ; {nombre_fr(hi)}]{u}", "loi de Student, n − 1 degrés de liberté"),
        ]
    colonnes = ["Indicateur", "Valeur", "Signification"]
    return pd.DataFrame(calcules, columns=colonnes), pd.DataFrame(estimations, columns=colonnes)


HYPOTHESES = [
    "Les valeurs sont considérées comme des observations indépendantes d'un même ensemble de sol.",
    "L'intervalle de confiance suppose une distribution à peu près normale (en cloche) ou un n assez grand "
    "(au moins une trentaine de valeurs).",
    "Les unités et conventions retenues sont celles validées au contrôle qualité.",
]
LIMITES = [
    "Avec peu de valeurs, toutes ces statistiques sont très incertaines.",
    "La moyenne et l'écart-type sont sensibles aux valeurs atypiques ; la médiane et l'IQR le sont beaucoup moins.",
    "Mélanger des couches de sol ou des sondages différents peut masquer des différences réelles : "
    "comparez aussi par groupe.",
    "Ces résultats décrivent des données ; ils ne constituent pas une conclusion sur la sécurité d'un ouvrage, "
    "qui relève d'une étude par un ingénieur qualifié.",
]


def classes_sturges(n: int) -> int:
    """Nombre de classes d'un histogramme selon la règle de Sturges : 1 + log2(n)."""
    return max(1, math.ceil(1 + math.log2(n))) if n > 0 else 1


# ---------------------------------------------------------------------------
# Graphiques (plotly)
# ---------------------------------------------------------------------------
def _mise_en_page(fig: go.Figure, titre: str, sous_titre: str, x: str, y: str, legende: bool = False) -> go.Figure:
    """Style commun : fond blanc, grille discrète, titre + n, axes nommés avec unités."""
    fig.update_layout(
        title={"text": f"{titre}<br><sup>{sous_titre}</sup>", "x": 0, "xanchor": "left",
               "font": {"size": 17, "color": ENCRE}},
        paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF",
        font={"color": ENCRE, "size": 13},
        margin={"l": 70, "r": 30, "t": 90, "b": 60},
        showlegend=legende,
        legend={"title": {"text": ""}, "orientation": "h", "yanchor": "bottom", "y": 1.0, "x": 1, "xanchor": "right"},
        hoverlabel={"bgcolor": "#FFFFFF", "font": {"color": ENCRE}},
        separators=", ",  # virgule décimale, espace pour les milliers
    )
    axes = {"showgrid": True, "gridcolor": GRILLE, "zeroline": False, "linecolor": ENCRE_SECONDAIRE,
            "tickfont": {"color": ENCRE_SECONDAIRE}, "title_font": {"color": ENCRE}}
    fig.update_xaxes(title_text=x, **axes)
    fig.update_yaxes(title_text=y, **axes)
    return fig


def figure_histogramme(valeurs: pd.Series, nom: str, nb_classes: int) -> go.Figure:
    """Histogramme : distribution des valeurs d'une variable."""
    v = pd.to_numeric(valeurs, errors="coerce").dropna()
    fig = go.Figure(go.Histogram(
        x=v, nbinsx=nb_classes, marker={"color": COULEUR_UNIQUE, "line": {"color": "#FFFFFF", "width": 2}},
        hovertemplate="Classe : %{x}<br>Nombre de valeurs : %{y}<extra></extra>",
    ))
    fig.update_layout(bargap=0.02)
    return _mise_en_page(fig, f"Distribution de {nom}", f"Histogramme · n = {len(v)} · {nb_classes} classes",
                         nom, "Nombre de valeurs")


def figure_boite(valeurs: pd.Series, nom: str, lignes: pd.Series | None = None) -> go.Figure:
    """Boîte à moustaches d'une variable (moustaches à 1,5 × IQR, points au-delà affichés)."""
    v = pd.to_numeric(valeurs, errors="coerce")
    masque = v.notna()
    fig = go.Figure(go.Box(
        y=v[masque], name=nom, boxpoints="outliers", quartilemethod="linear",
        marker={"color": COULEUR_UNIQUE, "size": 9}, line={"color": COULEUR_UNIQUE, "width": 2},
        fillcolor="rgba(42,120,214,0.15)",
        customdata=lignes[masque] if lignes is not None else None,
        hovertemplate="%{y}" + ("<br>ligne n° %{customdata}" if lignes is not None else "") + "<extra></extra>",
    ))
    fig.update_xaxes(showticklabels=False)
    return _mise_en_page(fig, f"Boîte à moustaches de {nom}",
                         f"n = {int(masque.sum())} · boîte = Q1 à Q3, trait = médiane, "
                         "moustaches jusqu'à 1,5 × IQR, points isolés = valeurs atypiques potentielles",
                         "", nom)


def _ordre_groupes(etiquettes: pd.Series) -> list[str]:
    """Groupes du plus fréquent au moins fréquent ; « inconnu / non renseigné » en dernier."""
    comptes = etiquettes.value_counts()
    ordre = [g for g in comptes.index if g not in (INCONNU, NON_RENSEIGNE)]
    ordre = sorted(ordre, key=lambda g: (-comptes[g], g))
    return ordre + [g for g in (INCONNU, NON_RENSEIGNE) if g in comptes.index]


def replier_groupes(etiquettes: pd.Series) -> pd.Series:
    """Au-delà de MAX_GROUPES, regroupe les plus petits groupes dans « Autres »
    (on ne génère jamais de couleur supplémentaire)."""
    ordre = _ordre_groupes(etiquettes)
    if len(ordre) <= MAX_GROUPES:
        return etiquettes
    gardes = set(ordre[: MAX_GROUPES - 1])
    return etiquettes.map(lambda g: g if g in gardes else "Autres")


def figure_nuage(x: pd.Series, y: pd.Series, nom_x: str, nom_y: str,
                 etiquettes: pd.Series | None, lignes: pd.Series, titre_groupe: str = "") -> go.Figure:
    """Nuage de points de deux variables, coloré par groupe si demandé."""
    xx, yy = pd.to_numeric(x, errors="coerce"), pd.to_numeric(y, errors="coerce")
    masque = xx.notna() & yy.notna()
    fig = go.Figure()
    if etiquettes is None:
        fig.add_trace(go.Scatter(
            x=xx[masque], y=yy[masque], mode="markers", customdata=lignes[masque],
            marker={"color": COULEUR_UNIQUE, "size": 10, "line": {"color": "#FFFFFF", "width": 2}},
            hovertemplate=f"{nom_x} : %{{x}}<br>{nom_y} : %{{y}}<br>ligne n° %{{customdata}}<extra></extra>",
        ))
    else:
        etiquettes = replier_groupes(etiquettes[masque])
        for i, g in enumerate(_ordre_groupes(etiquettes)):
            m = etiquettes == g
            fig.add_trace(go.Scatter(
                x=xx[masque][m], y=yy[masque][m], mode="markers", name=f"{g} (n = {int(m.sum())})",
                customdata=lignes[masque][m],
                marker={"color": PALETTE[i % len(PALETTE)], "symbol": SYMBOLES[i % len(SYMBOLES)], "size": 10,
                        "line": {"color": "#FFFFFF", "width": 2}},
                hovertemplate=f"{titre_groupe} : {g}<br>{nom_x} : %{{x}}<br>{nom_y} : %{{y}}"
                              "<br>ligne n° %{customdata}<extra></extra>",
            ))
    sous = f"n = {int(masque.sum())} couples de valeurs (lignes où les deux variables sont renseignées)"
    if etiquettes is not None:
        sous += f" · couleur = {titre_groupe}"
    return _mise_en_page(fig, f"{nom_y} en fonction de {nom_x}", sous, nom_x, nom_y, legende=etiquettes is not None)


def figure_comparaison(valeurs: pd.Series, etiquettes: pd.Series, nom: str, titre_groupe: str,
                       lignes: pd.Series) -> go.Figure:
    """Comparaison des distributions d'une variable entre groupes (une boîte par groupe, tous les points)."""
    v = pd.to_numeric(valeurs, errors="coerce")
    masque = v.notna()
    etiquettes = replier_groupes(etiquettes[masque])
    fig = go.Figure()
    for i, g in enumerate(_ordre_groupes(etiquettes)):
        m = etiquettes == g
        couleur = PALETTE[i % len(PALETTE)]
        fig.add_trace(go.Box(
            y=v[masque][m], name=f"{g}<br>(n = {int(m.sum())})", boxpoints="all", jitter=0.35, pointpos=0,
            quartilemethod="linear", marker={"color": couleur, "size": 8}, line={"color": couleur, "width": 2},
            customdata=lignes[masque][m],
            hovertemplate=f"{titre_groupe} : {g}<br>{nom} : %{{y}}<br>ligne n° %{{customdata}}<extra></extra>",
        ))
    return _mise_en_page(fig, f"Comparaison de {nom} par {titre_groupe.lower()}",
                         f"n = {int(masque.sum())} valeurs · {len(_ordre_groupes(etiquettes))} groupe(s) · "
                         "chaque point est une observation",
                         titre_groupe, nom)


def statistiques_par_groupe(valeurs: pd.Series, etiquettes: pd.Series, unite: str | None) -> pd.DataFrame:
    """Tableau récapitulatif par groupe (n, moyenne, médiane, écart-type, min, max)."""
    v = pd.to_numeric(valeurs, errors="coerce")
    lignes = []
    for g in _ordre_groupes(etiquettes[v.notna()]):
        r = statistiques(v[etiquettes == g])
        lignes.append({
            "Groupe": g, "n": r["n"],
            "Moyenne": nombre_fr(r.get("moyenne")), "Médiane": nombre_fr(r.get("mediane")),
            "Écart-type": nombre_fr(r.get("ecart_type")),
            "Minimum": nombre_fr(r.get("minimum")), "Maximum": nombre_fr(r.get("maximum")),
        })
    tableau = pd.DataFrame(lignes)
    if unite:
        tableau = tableau.rename(columns={c: f"{c} ({unite})" for c in
                                          ("Moyenne", "Médiane", "Écart-type", "Minimum", "Maximum")})
    return tableau


# ---------------------------------------------------------------------------
# Corrélations (phase 7, règle n° 8)
# ---------------------------------------------------------------------------
N_MIN_CORRELATION = 3
AVERTISSEMENTS_CORRELATION = [
    "**Corrélation n'est pas causalité** : deux grandeurs peuvent varier ensemble parce qu'elles dépendent "
    "toutes deux d'une troisième (profondeur, nature du sol, état de l'échantillon…).",
    "**Sensibilité aux valeurs atypiques** : une seule valeur extrême peut créer ou masquer une corrélation "
    "de Pearson. Spearman, fondé sur les rangs, y est moins sensible.",
    "Pearson ne mesure que les relations **linéaires** ; une relation courbe peut donner un coefficient faible.",
    "Mélanger des sondages ou des couches différents peut faire apparaître (ou disparaître) une tendance "
    "qui n'existe pas à l'intérieur de chaque groupe : vérifiez avec la couleur par sondage.",
    "Avec peu de couples de valeurs, le coefficient est très incertain, même si la p-value est faible.",
    "Une corrélation ne permet pas de conclure sur la sécurité d'un ouvrage.",
]


def force(coefficient: float) -> str:
    """Qualificatif usuel (indicatif) de l'intensité d'une corrélation."""
    a = abs(coefficient)
    if a < 0.3:
        intensite = "faible"
    elif a < 0.7:
        intensite = "modérée"
    else:
        intensite = "forte"
    sens = "positive (les deux augmentent ensemble)" if coefficient > 0 else "négative (l'une augmente quand l'autre diminue)"
    return f"{intensite}, {sens}" if a >= 0.05 else "quasi nulle"


def p_value_fr(p: float) -> str:
    return "< 0,001" if p < 0.001 else nombre_fr(p, 2)


def correlations(x: pd.Series, y: pd.Series) -> dict:
    """Coefficients de Pearson et de Spearman sur les couples où x et y sont renseignés.

    Renvoie aussi, pour juger de la sensibilité, les coefficients recalculés sans les
    couples dont x ou y est atypique selon la règle de Tukey (1,5 × IQR).
    """
    xx, yy = pd.to_numeric(x, errors="coerce"), pd.to_numeric(y, errors="coerce")
    masque = xx.notna() & yy.notna()
    xx, yy = xx[masque], yy[masque]
    r = {"n": int(masque.sum())}
    if r["n"] < N_MIN_CORRELATION or xx.nunique() < 2 or yy.nunique() < 2:
        return r
    r["pearson"], r["p_pearson"] = (float(v) for v in sps.pearsonr(xx, yy))
    r["spearman"], r["p_spearman"] = (float(v) for v in sps.spearmanr(xx, yy))

    def atypiques(s: pd.Series) -> pd.Series:
        q1, q3 = s.quantile(0.25), s.quantile(0.75)
        return (s < q1 - 1.5 * (q3 - q1)) | (s > q3 + 1.5 * (q3 - q1))

    garder = ~(atypiques(xx) | atypiques(yy))
    r["n_atypiques"] = int((~garder).sum())
    if r["n_atypiques"] and garder.sum() >= N_MIN_CORRELATION and xx[garder].nunique() > 1 and yy[garder].nunique() > 1:
        r["pearson_sans"] = float(sps.pearsonr(xx[garder], yy[garder])[0])
        r["spearman_sans"] = float(sps.spearmanr(xx[garder], yy[garder])[0])
        r["n_sans"] = int(garder.sum())
    return r


def tableau_correlations(r: dict) -> pd.DataFrame:
    """Tableau lisible des deux coefficients."""
    lignes = [
        ("Pearson (r)", nombre_fr(r["pearson"], 3), p_value_fr(r["p_pearson"]), r["n"],
         "relation **linéaire** entre les valeurs", force(r["pearson"])),
        ("Spearman (ρ)", nombre_fr(r["spearman"], 3), p_value_fr(r["p_spearman"]), r["n"],
         "relation **monotone** (toujours croissante ou décroissante), calculée sur les rangs",
         force(r["spearman"])),
    ]
    return pd.DataFrame(lignes, columns=["Méthode", "Coefficient", "p-value", "n", "Ce qu'elle mesure", "Intensité"])


# ---------------------------------------------------------------------------
# Profils en fonction de la profondeur (phase 7, règle n° 6)
# ---------------------------------------------------------------------------
def figure_profils(tableau: pd.DataFrame, variable: str, col_profondeur: str, col_sondage: str,
                   description: dict, site: str, par_sondage: bool = False) -> go.Figure:
    """Profil d'une variable en fonction de la profondeur, une courbe par sondage d'un même site.

    La profondeur est sur l'axe vertical, croissante vers le bas. Les points d'un sondage
    sont reliés dans l'ordre des profondeurs ; deux sondages ne sont jamais reliés entre eux.
    """
    from plotly.subplots import make_subplots

    nom_v, nom_p = libelle(variable, description), libelle(col_profondeur, description)
    v = pd.to_numeric(tableau[variable], errors="coerce")
    p = pd.to_numeric(tableau[col_profondeur], errors="coerce")
    masque = v.notna() & p.notna()
    codes = tableau[col_sondage].where(masque)
    ordre = sorted({str(c) for c in codes.dropna()})
    n = int(masque.sum())

    if par_sondage and len(ordre) > 1:
        fig = make_subplots(rows=1, cols=len(ordre), shared_yaxes=True, horizontal_spacing=0.03,
                            subplot_titles=ordre)
    else:
        fig = go.Figure()
    for i, code in enumerate(ordre):
        m = masque & (tableau[col_sondage].astype(str) == code)
        donnees = pd.DataFrame({"v": v[m], "p": p[m], "ligne": tableau.loc[m, "N° ligne"]}).sort_values("p")
        couleur = PALETTE[i % len(PALETTE)]
        trace = go.Scatter(
            x=donnees["v"], y=donnees["p"], mode="lines+markers", name=f"{code} (n = {len(donnees)})",
            line={"color": couleur, "width": 2},
            marker={"color": couleur, "symbol": SYMBOLES[i % len(SYMBOLES)], "size": 9,
                    "line": {"color": "#FFFFFF", "width": 2}},
            customdata=donnees["ligne"],
            hovertemplate=f"Sondage {code}<br>{nom_p} : %{{y}}<br>{nom_v} : %{{x}}<br>ligne n° %{{customdata}}<extra></extra>",
        )
        if par_sondage and len(ordre) > 1:
            fig.add_trace(trace, row=1, col=i + 1)
        else:
            fig.add_trace(trace)
    titre = f"Profil de {nom_v} en fonction de la profondeur — site : {site}"
    sous = (f"n = {n} valeurs · {len(ordre)} sondage(s) · profondeur croissante vers le bas · "
            "points d'un même sondage reliés par profondeur croissante")
    fig = _mise_en_page(fig, titre, sous, nom_v, nom_p, legende=len(ordre) > 1 and not par_sondage)
    # Axe vertical : 0 (surface du terrain) en haut, profondeurs croissantes vers le bas
    p_max = float(p[masque].max()) if n else 1.0
    fig.update_yaxes(range=[max(p_max, 0) * 1.08 or 1.0, 0], autorange=False)
    if par_sondage and len(ordre) > 1:
        fig.update_xaxes(title_text="")
        fig.update_layout(annotations=list(fig.layout.annotations) + [
            {"text": nom_v, "xref": "paper", "yref": "paper", "x": 0.5, "y": -0.12, "showarrow": False,
             "font": {"color": ENCRE, "size": 13}}])
        fig.update_yaxes(title_text="")
        fig.update_yaxes(title_text=nom_p, row=1, col=1)
    fig.update_layout(height=600)
    return fig
