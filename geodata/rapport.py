"""Rapports PDF et exports Excel / CSV (phase 9).

Les résultats exportés sont toujours accompagnés du projet et de la provenance
des données (étape 8 du parcours). Le rapport PDF sépare observations, résultats
calculés, estimations statistiques, hypothèses et limites (règle n° 9) et ne
contient aucune conclusion sur la sécurité d'un ouvrage.
"""

import io
import itertools
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # dessin en mémoire, sans fenêtre
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from fpdf import FPDF  # noqa: E402
from fpdf.fonts import FontFace  # noqa: E402

from geodata import AUTEUR_APPLICATION, NOM_APPLICATION, VERSION, analyse as an, db, importation  # noqa: E402

DOSSIER_POLICES = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
AVERTISSEMENT_SECURITE = (
    "Ce document présente des données et des résultats statistiques. Il ne constitue en aucun cas une "
    "conclusion sur la sécurité, la stabilité ou le dimensionnement d'un ouvrage : cette appréciation relève "
    "d'une étude géotechnique conduite par un ingénieur qualifié, selon les normes en vigueur."
)


# ---------------------------------------------------------------------------
# Rassemblement des informations
# ---------------------------------------------------------------------------
def collecter(projet_id: int, jeu_ids: list[int] | None = None) -> dict:
    """Toutes les informations d'un projet utiles aux exports.
    jeu_ids : jeux de données validés à inclure (tous les jeux validés si None)."""
    projet = db.obtenir_projet(projet_id)
    jeux = []
    for j in db.lister_jeux(projet_id):
        if j["statut_qc"] != "validé" or (jeu_ids is not None and j["id"] not in jeu_ids):
            continue
        complet = db.obtenir_jeu(j["id"])
        jeux.append({
            **j,
            "provenance": db.obtenir_provenance(j["id"]) or {},
            "tableau": importation.json_vers_tableau(complet["contenu_valide"]),
            "description": importation.json_description(complet["contenu_valide"]),
            "decisions": list(reversed(db.lister_decisions(j["id"]))),  # ordre chronologique
        })
    return {
        "projet": projet,
        "jeux": jeux,
        "tous_jeux": db.lister_jeux(projet_id),
        "sondages": db.lister_sondages(projet_id),
        "echantillons": db.lister_echantillons(projet_id),
        "essais": db.lister_essais(projet_id),
        "historique": db.lister_historique(projet_id),
        "date": datetime.now().isoformat(timespec="seconds"),
    }


def date_fr(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        return datetime.fromisoformat(iso).strftime("%d/%m/%Y à %H:%M")
    except ValueError:
        return iso


# ---------------------------------------------------------------------------
# Tableaux d'export
# ---------------------------------------------------------------------------
def tableau_projet(d: dict) -> pd.DataFrame:
    p = d["projet"]
    lignes = [("Nom", p["nom"]), ("Localisation", p["localisation"]), ("Type d'ouvrage", p["type_ouvrage"]),
              ("Description", p["description"]), ("Auteur", p["auteur"]), ("Confidentialité", p["confidentialite"]),
              ("Personnes autorisées", p["acces_autorise"]), ("Créé le", date_fr(p["date_creation"])),
              ("Export réalisé le", date_fr(d["date"])), ("Application", f"{NOM_APPLICATION} {VERSION} — réalisée par {AUTEUR_APPLICATION}"),
              ("Avertissement", AVERTISSEMENT_SECURITE)]
    return pd.DataFrame(lignes, columns=["Champ", "Valeur"])


def tableau_provenance(d: dict) -> pd.DataFrame:
    lignes = []
    for j in d["tous_jeux"]:
        prov = db.obtenir_provenance(j["id"]) or {}
        lignes.append({
            "Jeu de données": j["nom"], "Type de source": db.TYPES_SOURCE.get(j["type_source"], j["type_source"]),
            "Fichier ou URL": prov.get("fichier_ou_url"), "Source": prov.get("source"),
            "Producteur": prov.get("producteur"), "Date des données": prov.get("date_donnees"),
            "Licence": prov.get("licence"), "Limites d'usage": prov.get("limites_usage"),
            "Date d'import": date_fr(prov.get("date_import")), "Auteur de l'import": prov.get("auteur_import"),
            "Remarques": prov.get("remarques"), "Données fictives": "oui" if j["est_fictif"] else "non",
            "Contrôle qualité": j["statut_qc"],
        })
    return pd.DataFrame(lignes)


def tableau_statistiques_export(d: dict) -> pd.DataFrame:
    """Statistiques descriptives de chaque variable numérique de chaque jeu validé."""
    lignes = []
    for j in d["jeux"]:
        for var in an.variables_numeriques(j["description"]):
            r = an.statistiques(j["tableau"][var])
            ic = r.get("ic", (None, None))
            lignes.append({
                "Jeu de données": j["nom"], "Variable": var, "Unité": j["description"][var].get("unite"),
                "n": r["n"], "Moyenne": r.get("moyenne"), "Médiane": r.get("mediane"),
                "Minimum": r.get("minimum"), "Q1": r.get("q1"), "Q3": r.get("q3"), "Maximum": r.get("maximum"),
                "Variance (n-1)": r.get("variance"), "Écart-type (n-1)": r.get("ecart_type"),
                "CV (%)": r.get("cv"), "IC 95 % moyenne - bas": ic[0], "IC 95 % moyenne - haut": ic[1],
                "Source": j["provenance"].get("source"),
            })
    return pd.DataFrame(lignes)


def tableau_essais(d: dict) -> pd.DataFrame:
    return pd.DataFrame([{
        "Sondage": t["code_sondage"] or "localisation inconnue", "Site": t["site"],
        "Échantillon": t["code_echantillon"], "Profondeur (m)": t["profondeur_m"], "Type d'essai": t["type_essai"],
        "Paramètre": t["parametre"], "Valeur": t["valeur"], "Unité": t["unite"], "Nature": t["nature_resultat"],
        "Jeu de données": t["jeu_nom"], "Remarques": t["remarques"],
    } for t in d["essais"]])


def tableau_sondages(d: dict) -> pd.DataFrame:
    return pd.DataFrame([{
        "Sondage": s["code"], "Site": s["site"], "Localisation": "connue" if s["localisation_connue"] else "inconnue",
        "X": s["x"], "Y": s["y"], "Système de coordonnées": s["systeme_coord"], "Cote Z (m)": s["z_terrain"],
        "Profondeur finale (m)": s["profondeur_finale_m"], "Type": s["type_sondage"],
        "Date": s["date_realisation"], "Entreprise": s["entreprise"], "Méthode": s["methode"],
        "Observations": s["observations"], "Échantillons": s["nb_echantillons"], "Essais": s["nb_essais"],
    } for s in d["sondages"]])


def tableau_echantillons(d: dict) -> pd.DataFrame:
    return pd.DataFrame([{
        "Échantillon": e["code"], "Sondage": e["code_sondage"] or "aucun (localisation inconnue)",
        "Profondeur haut (m)": e["profondeur_haut_m"], "Profondeur bas (m)": e["profondeur_bas_m"],
        "Date": e["date_prelevement"], "Nature du sol": e["nature_sol"], "Type": e["type_echantillon"],
        "Observations": e["observations"],
    } for e in d["echantillons"]])


def tableau_decisions(d: dict) -> pd.DataFrame:
    return pd.DataFrame([{
        "Jeu de données": j["nom"], "Date": date_fr(x["date_decision"]), "Type": x["type_decision"],
        "Colonne": x["colonne"], "Décision": x["description"], "Méthode": x["methode"],
    } for j in d["jeux"] for x in j["decisions"]])


def tableau_historique(d: dict) -> pd.DataFrame:
    return pd.DataFrame([{
        "Date": date_fr(h["date_operation"]), "Opération": h["operation"], "Jeu de données": h["jeu_nom"],
        "Détails": h["details"], "Auteur": h["auteur"],
    } for h in d["historique"]])


def tables_export(d: dict) -> dict[str, pd.DataFrame]:
    """Toutes les tables exportables, par nom lisible."""
    tables = {"Projet": tableau_projet(d), "Provenance": tableau_provenance(d)}
    for j in d["jeux"]:
        tables[f"Données validées — {j['nom']}"] = j["tableau"]
    tables.update({
        "Statistiques": tableau_statistiques_export(d), "Sondages": tableau_sondages(d),
        "Échantillons": tableau_echantillons(d), "Résultats d'essais": tableau_essais(d),
        "Décisions de contrôle qualité": tableau_decisions(d), "Historique": tableau_historique(d),
    })
    return tables


# ---------------------------------------------------------------------------
# Excel et CSV
# ---------------------------------------------------------------------------
def _nom_feuille(nom: str, deja: set[str]) -> str:
    """Nom de feuille Excel valide (31 caractères max, sans caractères interdits, unique)."""
    propre = "".join(" " if c in '[]:*?/\\' else c for c in nom)[:31].strip()
    base, k = propre, 2
    while propre in deja:
        suffixe = f" ({k})"
        propre, k = base[: 31 - len(suffixe)] + suffixe, k + 1
    deja.add(propre)
    return propre


def export_excel(d: dict) -> bytes:
    """Classeur Excel : une feuille par table, colonnes élargies, première ligne figée."""
    sortie = io.BytesIO()
    noms: set[str] = set()
    with pd.ExcelWriter(sortie, engine="openpyxl") as classeur:
        for titre, table in tables_export(d).items():
            feuille = _nom_feuille(titre, noms)
            (table if not table.empty else pd.DataFrame({"Information": ["Aucune donnée"]})).to_excel(
                classeur, sheet_name=feuille, index=False)
            ws = classeur.sheets[feuille]
            ws.freeze_panes = "A2"
            for colonne in ws.columns:
                largeur = max(len(str(c.value)) if c.value is not None else 0 for c in colonne[:200])
                ws.column_dimensions[colonne[0].column_letter].width = min(max(10, largeur + 2), 60)
    return sortie.getvalue()


def export_csv(table: pd.DataFrame) -> bytes:
    """CSV « à la française » : séparateur point-virgule, virgule décimale, UTF-8 avec BOM
    (s'ouvre directement et correctement dans Excel en français)."""
    return table.to_csv(sep=";", decimal=",", index=False).encode("utf-8-sig")


# ---------------------------------------------------------------------------
# Graphiques pour le PDF (matplotlib)
# ---------------------------------------------------------------------------
plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 9, "axes.titlesize": 10, "axes.edgecolor": "#52514e",
    "axes.grid": True, "grid.color": "#e6e3ee", "grid.linewidth": 0.6, "axes.axisbelow": True,
    "axes.formatter.use_locale": False,
})


def _png(fig) -> bytes:
    tampon = io.BytesIO()
    fig.savefig(tampon, format="png", dpi=160, bbox_inches="tight")
    plt.close(fig)
    return tampon.getvalue()


def _virgule(ax) -> None:
    """Virgule décimale sur les graduations."""
    from matplotlib.ticker import FuncFormatter
    fmt = FuncFormatter(lambda x, _: f"{x:g}".replace(".", ","))
    ax.xaxis.set_major_formatter(fmt)
    ax.yaxis.set_major_formatter(fmt)


def figure_variable(valeurs: pd.Series, nom: str) -> bytes:
    """Histogramme + boîte à moustaches d'une variable."""
    v = pd.to_numeric(valeurs, errors="coerce").dropna()
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.2, 2.8), gridspec_kw={"width_ratios": [3, 1.3]})
    ax1.hist(v, bins=an.classes_sturges(len(v)), color=an.COULEUR_UNIQUE, edgecolor="white", linewidth=1.5)
    ax1.set_title(f"Distribution de {nom}\nhistogramme · n = {len(v)}", loc="left")
    ax1.set_xlabel(nom)
    ax1.set_ylabel("Nombre de valeurs")
    ax2.boxplot(v, widths=0.5, patch_artist=True, whis=1.5,
                boxprops={"facecolor": "#dbe8f8", "edgecolor": an.COULEUR_UNIQUE},
                medianprops={"color": an.COULEUR_UNIQUE, "linewidth": 2},
                flierprops={"marker": "o", "markerfacecolor": an.COULEUR_UNIQUE, "markeredgecolor": "white"})
    ax2.set_title(f"Boîte à moustaches\nn = {len(v)}", loc="left")
    ax2.set_ylabel(nom)
    ax2.set_xticks([])
    _virgule(ax1)
    _virgule(ax2)
    fig.tight_layout()
    return _png(fig)


def figure_nuage(x: pd.Series, y: pd.Series, nom_x: str, nom_y: str) -> bytes:
    xx, yy = pd.to_numeric(x, errors="coerce"), pd.to_numeric(y, errors="coerce")
    m = xx.notna() & yy.notna()
    fig, ax = plt.subplots(figsize=(5.2, 3.4))
    ax.scatter(xx[m], yy[m], s=36, color=an.COULEUR_UNIQUE, edgecolor="white", linewidth=1)
    ax.set_title(f"{nom_y} en fonction de {nom_x}\nnuage de points · n = {int(m.sum())} couples", loc="left")
    ax.set_xlabel(nom_x)
    ax.set_ylabel(nom_y)
    _virgule(ax)
    fig.tight_layout()
    return _png(fig)


def figure_profil(tableau: pd.DataFrame, var: str, col_prof: str, col_sondage: str, description: dict,
                  site: str) -> bytes:
    """Profil en profondeur d'un site : profondeur verticale de 0 vers le bas, une courbe par sondage."""
    nom_v, nom_p = an.libelle(var, description), an.libelle(col_prof, description)
    v, p = pd.to_numeric(tableau[var], errors="coerce"), pd.to_numeric(tableau[col_prof], errors="coerce")
    m = v.notna() & p.notna() & tableau[col_sondage].notna()
    fig, ax = plt.subplots(figsize=(5.2, 4.6))
    codes = sorted({str(c) for c in tableau.loc[m, col_sondage]})
    for i, code in enumerate(codes):
        mm = m & (tableau[col_sondage].astype(str) == code)
        donnees = pd.DataFrame({"v": v[mm], "p": p[mm]}).sort_values("p")
        ax.plot(donnees["v"], donnees["p"], marker="osD^Px*h"[i % 8], color=an.PALETTE[i % 8], linewidth=1.8,
                markersize=6, markeredgecolor="white", label=f"{code} (n = {len(donnees)})")
    p_max = float(p[m].max()) if m.any() else 1.0
    ax.set_ylim(p_max * 1.08 or 1.0, 0)
    ax.set_title(f"Profil de {nom_v} — site : {site}\nn = {int(m.sum())} valeurs · {len(codes)} sondage(s) · "
                 "profondeur croissante vers le bas", loc="left")
    ax.set_xlabel(nom_v)
    ax.set_ylabel(nom_p)
    if len(codes) > 1:
        ax.legend(frameon=False, fontsize=8)
    _virgule(ax)
    fig.tight_layout()
    return _png(fig)


# ---------------------------------------------------------------------------
# Rapport PDF
# ---------------------------------------------------------------------------
class RapportPDF(FPDF):
    """Mise en page commune : en-tête avec le projet, pied de page numéroté."""

    def __init__(self, titre_projet: str, date: str):
        super().__init__(format="A4")
        self.titre_projet, self.date_rapport = titre_projet, date
        self.add_font("DejaVu", "", str(DOSSIER_POLICES / "DejaVuSans.ttf"))
        self.add_font("DejaVu", "B", str(DOSSIER_POLICES / "DejaVuSans-Bold.ttf"))
        self.add_font("DejaVu", "I", str(DOSSIER_POLICES / "DejaVuSans-Oblique.ttf"))
        self.add_font("DejaVu", "BI", str(DOSSIER_POLICES / "DejaVuSans-BoldOblique.ttf"))
        self.set_auto_page_break(True, margin=18)
        self.set_margins(18, 18, 18)
        self.alias_nb_pages()

    def header(self):
        if self.page_no() == 1:
            return
        self.set_font("DejaVu", "", 8)
        self.set_text_color(110, 110, 110)
        self.cell(0, 6, f"{NOM_APPLICATION} — {self.titre_projet}", align="L")
        self.ln(8)
        self.set_text_color(17, 17, 17)

    def footer(self):
        self.set_y(-13)
        self.set_font("DejaVu", "", 8)
        self.set_text_color(110, 110, 110)
        self.cell(0, 6, f"{NOM_APPLICATION} (réalisée par {AUTEUR_APPLICATION}) — rapport généré le "
                        f"{date_fr(self.date_rapport)} — page {self.page_no()}/{{nb}}", align="C")
        self.set_text_color(17, 17, 17)

    # --- éléments de texte ---------------------------------------------------
    def titre(self, texte: str):
        if self.get_y() > 240:
            self.add_page()
        self.ln(3)
        self.set_font("DejaVu", "B", 14)
        self.set_text_color(194, 24, 91)  # rose de l'application
        self.multi_cell(0, 8, texte, new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(17, 17, 17)
        self.ln(1)

    def sous_titre(self, texte: str):
        if self.get_y() > 250:
            self.add_page()
        self.ln(2)
        self.set_font("DejaVu", "B", 11)
        self.multi_cell(0, 6, texte, new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def paragraphe(self, texte: str, taille: int = 9.5, italique: bool = False):
        self.set_font("DejaVu", "I" if italique else "", taille)
        self.multi_cell(0, 5, texte, markdown=True, new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def puces(self, elements: list[str]):
        self.set_font("DejaVu", "", 9.5)
        for e in elements:
            self.multi_cell(0, 5, f"•  {e}", markdown=True, new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def encadre(self, texte: str, couleur=(253, 236, 200)):
        self.set_fill_color(*couleur)
        self.set_font("DejaVu", "", 9)
        self.multi_cell(0, 5, texte, fill=True, markdown=True, padding=2, new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def tableau(self, df: pd.DataFrame, largeurs: tuple | None = None, taille: float = 8):
        """Tableau simple ; les valeurs vides deviennent « — »."""
        if df.empty:
            self.paragraphe("*Aucune donnée.*")
            return
        self.set_font("DejaVu", "", taille)
        entete = FontFace(emphasis="BOLD", fill_color=(232, 223, 245))
        with self.table(col_widths=largeurs, headings_style=entete, line_height=4.6,
                        text_align="LEFT", first_row_as_headings=True) as t:
            t.row([str(c) for c in df.columns])
            for _, ligne in df.iterrows():
                t.row([_texte_cellule(v) for v in ligne])
        self.ln(2)

    def image_png(self, png: bytes, largeur: float = 170):
        hauteur_estimee = largeur * 0.6
        if self.get_y() + hauteur_estimee > 275:
            self.add_page()
        self.image(io.BytesIO(png), w=largeur, x=(210 - largeur) / 2)
        self.ln(3)


def _texte_cellule(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    if isinstance(v, float):
        return an.nombre_fr(v)
    return str(v)


def rapport_pdf(d: dict, variables: dict[int, list[str]], correlations: dict[int, list[tuple[str, str]]],
                profils: bool = True) -> bytes:
    """Construit le rapport PDF.

    variables     : {jeu_id: [variables à détailler]}
    correlations  : {jeu_id: [(variable x, variable y)]}
    profils       : inclure les profils en profondeur (par site)
    """
    p = d["projet"]
    pdf = RapportPDF(p["nom"], d["date"])

    # --- Page de garde ---------------------------------------------------------
    pdf.add_page()
    pdf.ln(30)
    pdf.set_font("DejaVu", "B", 24)
    pdf.set_text_color(194, 24, 91)
    pdf.cell(0, 12, NOM_APPLICATION, align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(17, 17, 17)
    pdf.set_font("DejaVu", "", 13)
    pdf.cell(0, 8, "Rapport de collecte, de contrôle et d'analyse de données géotechniques", align="C",
             new_x="LMARGIN", new_y="NEXT")
    pdf.ln(14)
    pdf.set_font("DejaVu", "B", 16)
    pdf.multi_cell(0, 9, p["nom"], align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("DejaVu", "", 11)
    for texte in (p["localisation"], p["type_ouvrage"], f"Auteur : {p['auteur']}" if p["auteur"] else None,
                  f"Date du rapport : {date_fr(d['date'])}"):
        if texte:
            pdf.cell(0, 7, texte, align="C", new_x="LMARGIN", new_y="NEXT")
    if any(j["est_fictif"] for j in d["jeux"]):
        pdf.ln(6)
        pdf.encadre("**DONNÉES FICTIVES** : ce rapport contient des données inventées à des fins d'exercice.",
                    (248, 215, 218))
    if p["confidentialite"] and p["confidentialite"] != "Public":
        pdf.encadre(f"**Document {p['confidentialite'].lower()}** — personnes autorisées : "
                    f"{p['acces_autorise'] or 'non précisé'}.", (232, 223, 245))
    pdf.ln(10)
    pdf.encadre("**Avertissement.** " + AVERTISSEMENT_SECURITE)
    pdf.set_font("DejaVu", "I", 8.5)
    pdf.multi_cell(0, 4.5, "Lecture du rapport : les **observations** sont les valeurs mesurées retenues ; les "
                           "**résultats calculés** décrivent exactement ces valeurs ; les **estimations "
                           "statistiques** extrapolent à l'ensemble du sol étudié sous des **hypothèses** "
                           "explicites ; les **limites** précisent ce qu'on ne peut pas en conclure.",
                   markdown=True, align="C")

    # --- 1. Projet ---------------------------------------------------------------
    pdf.add_page()
    pdf.titre("1. Projet")
    pdf.tableau(tableau_projet(d).iloc[:-3], largeurs=(45, 129))
    if p["description"]:
        pdf.paragraphe(p["description"])

    # --- 2. Sources et provenance -----------------------------------------------------
    pdf.titre("2. Sources des données et provenance")
    if not d["jeux"]:
        pdf.paragraphe("Aucun jeu de données validé n'est inclus dans ce rapport.")
    for j in d["jeux"]:
        prov = j["provenance"]
        pdf.sous_titre(f"Jeu « {j['nom']} »" + (" — DONNÉES FICTIVES" if j["est_fictif"] else ""))
        pdf.tableau(pd.DataFrame([
            ("Source", prov.get("source")), ("Fichier ou URL d'origine", prov.get("fichier_ou_url")),
            ("Producteur", prov.get("producteur")), ("Date des données", prov.get("date_donnees")),
            ("Licence", prov.get("licence")), ("Limites d'usage", prov.get("limites_usage")),
            ("Date d'import", date_fr(prov.get("date_import"))), ("Auteur de l'import", prov.get("auteur_import")),
            ("Lignes retenues après contrôle", len(j["tableau"])),
        ], columns=["Champ", "Valeur"]), largeurs=(48, 126))

    # --- 3. Contrôle qualité ----------------------------------------------------------
    pdf.titre("3. Contrôle qualité des données")
    pdf.paragraphe("Aucune valeur n'a été modifiée ou supprimée automatiquement. Les décisions ci-dessous ont été "
                   "prises par l'utilisateur ; les données brutes importées sont conservées intactes.")
    for j in d["jeux"]:
        pdf.sous_titre(f"Jeu « {j['nom']} » — décisions enregistrées")
        dec = pd.DataFrame([{"Date": date_fr(x["date_decision"]), "Type": x["type_decision"],
                             "Colonne": x["colonne"] or "—", "Décision": x["description"],
                             "Méthode": x["methode"] or "—"} for x in j["decisions"]])
        pdf.tableau(dec, largeurs=(25, 20, 26, 78, 25), taille=7)

    # --- 4. Sondages et échantillons --------------------------------------------------
    pdf.titre("4. Sondages et échantillons")
    if d["sondages"]:
        inconnus = sum(1 for s in d["sondages"] if not s["localisation_connue"])
        pdf.paragraphe(f"{len(d['sondages'])} sondage(s), dont **{inconnus} de localisation inconnue** "
                       "(coordonnées ou système non renseignés). Profondeurs en mètres, comptées vers le bas "
                       "depuis le terrain naturel.")
        s = tableau_sondages(d)[["Sondage", "Site", "Localisation", "X", "Y", "Système de coordonnées",
                                 "Profondeur finale (m)", "Type", "Essais"]]
        pdf.tableau(s, taille=7)
    else:
        pdf.paragraphe("Aucune fiche de sondage enregistrée.")
    sans = sum(1 for t in d["essais"] if not t["code_sondage"])
    if sans:
        pdf.paragraphe(f"**{sans} résultat(s) d'essai de localisation inconnue** (sans sondage) : ils restent "
                       "identifiés comme tels et ne figurent dans aucun profil.")

    # --- 5. Résultats par variable ------------------------------------------------------
    pdf.titre("5. Résultats statistiques")
    for j in d["jeux"]:
        for var in variables.get(j["id"], []):
            if var not in j["tableau"].columns:
                continue
            unite = j["description"][var].get("unite")
            nom = an.libelle(var, j["description"])
            r = an.statistiques(j["tableau"][var])
            pdf.sous_titre(f"{nom} — jeu « {j['nom']} »")
            pdf.paragraphe(f"**Observations** : {r['n']} valeur(s) retenue(s) sur {len(j['tableau'])} ligne(s) "
                           f"({r['n_absentes']} sans valeur : absente, non chiffrable ou exclue au contrôle qualité).")
            if r["n"] == 0:
                continue
            calcules, estimations = an.tableau_statistiques(r, unite)
            pdf.paragraphe("**Résultats calculés** (décrivent exactement les valeurs observées) :")
            pdf.tableau(calcules, largeurs=(55, 35, 84), taille=7.5)
            if not estimations.empty:
                pdf.paragraphe("**Estimations statistiques** (sous les hypothèses de la section 8) :")
                pdf.tableau(estimations, largeurs=(55, 45, 74), taille=7.5)
            if r["n"] < 5:
                pdf.paragraphe(f"*Seulement {r['n']} valeur(s) : statistiques très peu fiables.*")
            pdf.image_png(figure_variable(j["tableau"][var], nom))

    # --- 6. Corrélations ---------------------------------------------------------------
    paires = [(j, x, y) for j in d["jeux"] for x, y in correlations.get(j["id"], [])]
    if paires:
        pdf.titre("6. Relations entre paramètres (corrélations)")
        for j, x, y in paires:
            nx, ny = an.libelle(x, j["description"]), an.libelle(y, j["description"])
            pdf.sous_titre(f"{ny} et {nx} — jeu « {j['nom']} »")
            rc = an.correlations(j["tableau"][x], j["tableau"][y])
            pdf.image_png(figure_nuage(j["tableau"][x], j["tableau"][y], nx, ny), largeur=120)
            if "pearson" not in rc:
                pdf.paragraphe(f"Calcul impossible (n = {rc['n']} couples).")
                continue
            tab = an.tableau_correlations(rc).drop(columns=["Ce qu'elle mesure"])
            pdf.paragraphe("**Estimations statistiques** :")
            pdf.tableau(tab, largeurs=(30, 25, 22, 12, 85), taille=7.5)
            pdf.paragraphe("Pearson mesure une relation linéaire ; Spearman une relation monotone, calculée sur les "
                           "rangs.", taille=8.5, italique=True)
            if rc.get("pearson_sans") is not None:
                pdf.paragraphe(f"Sensibilité : sans les {rc['n_atypiques']} couple(s) contenant une valeur atypique "
                               f"(n = {rc['n_sans']}), Pearson r = {an.nombre_fr(rc['pearson_sans'], 3)} et "
                               f"Spearman ρ = {an.nombre_fr(rc['spearman_sans'], 3)}.", taille=8.5)
        pdf.sous_titre("Limites d'interprétation des corrélations")
        pdf.puces(an.AVERTISSEMENTS_CORRELATION)

    # --- 7. Profils ------------------------------------------------------------------------
    if profils:
        sections = []
        sites_fiches = {s["code"]: (s["site"] or "site non renseigné") for s in d["sondages"]}
        for j in d["jeux"]:
            desc = j["description"]
            col_s = next((t for t, i in desc.items() if i.get("role") == "id_sondage"), None)
            col_p = next((t for t, i in desc.items() if i.get("role") == "profondeur"), None)
            if not (col_s and col_p):
                continue
            site_de = j["tableau"][col_s].map(lambda c: None if c is None or pd.isna(c)
                                              else sites_fiches.get(str(c), "site non renseigné"))
            for var in variables.get(j["id"], []):
                if desc.get(var, {}).get("role") != "mesure":
                    continue
                for site in sorted(site_de.dropna().unique()):
                    sections.append((j, var, col_p, col_s, site, j["tableau"][site_de == site]))
        if sections:
            pdf.titre("7. Profils en fonction de la profondeur")
            pdf.paragraphe("Un graphique par site : les sondages de sites différents ne sont jamais fusionnés. "
                           "Les points d'un même sondage sont reliés par profondeur croissante.")
            for j, var, col_p, col_s, site, selection in sections:
                pdf.image_png(figure_profil(selection, var, col_p, col_s, j["description"], site), largeur=120)

    # --- 8. Hypothèses et limites ----------------------------------------------------------------
    pdf.titre("8. Hypothèses et limites d'interprétation")
    pdf.sous_titre("Hypothèses")
    pdf.puces(an.HYPOTHESES)
    pdf.sous_titre("Limites")
    pdf.puces(an.LIMITES)
    for j in d["jeux"]:
        if j["provenance"].get("limites_usage"):
            pdf.puces([f"Limites d'usage du jeu « {j['nom']} » (fiche de provenance) : "
                       f"{j['provenance']['limites_usage']}"])
    pdf.encadre("**Rappel.** " + AVERTISSEMENT_SECURITE)

    # --- Annexe : historique ------------------------------------------------------------------------
    pdf.titre("Annexe — Historique des opérations")
    h = tableau_historique(d).head(80)[["Date", "Opération", "Détails"]]
    pdf.tableau(h, largeurs=(28, 38, 108), taille=6.5)
    return bytes(pdf.output())


def paires_possibles(description: dict) -> list[tuple[str, str]]:
    """Toutes les paires de mesures numériques d'un jeu (pour proposer des corrélations)."""
    return list(itertools.combinations([v for v in an.variables_numeriques(description)], 2))
