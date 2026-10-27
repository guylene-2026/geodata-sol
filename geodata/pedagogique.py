"""Jeu de données pédagogique FICTIF (phase 10).

Toutes les valeurs sont INVENTÉES : elles ne représentent aucun site réel.
Le jeu contient volontairement des pièges, pour s'exercer à tout le parcours
(import, contrôle qualité, rattachement, analyses, rapport). La liste des pièges
et la conduite attendue figurent dans PIEGES (guide de l'exercice).
"""

import io

import pandas as pd

from geodata import db, importation, organisation as org

NOM_PROJET = "Exercice GeoData Sol (données fictives)"
NOM_JEU = "Jeu pédagogique FICTIF — essais de laboratoire"
NOM_FICHIER = "jeu_pedagogique_fictif.xlsx"
SITE_A, SITE_B = "Site d'exercice A (fictif)", "Site d'exercice B (fictif)"

COLONNES = ["Sondage", "Échantillon", "Profondeur (m)", "Nature du sol", "Teneur en eau",
            "Limite de liquidité (%)", "Résistance (kPa)", "Observations"]
# Valeurs écrites comme dans un vrai fichier de laboratoire (texte), pièges compris
LIGNES = [
    ["SP1", "E01", "1", "Argile limoneuse", "22,4", "45.5", "110", ""],
    ["SP1", "E02", "2", "Argile limoneuse", "24 %", "47,2", "98", ""],
    ["SP1", "E03", "3", "Argile", "0,28", "51,0", "0,085 MPa", "résistance notée en MPa"],
    ["SP1", "E04", "4", "Argile", "30,1", "53.4", "76", ""],
    ["SP1", "E05", "5", "Argile", "300", "55,0", "72", "valeur de teneur en eau à vérifier"],
    ["SP2", "E06", "1", "Limon sableux", "18,9", "38,4", "135", ""],
    ["SP2", "E07", "2", "Limon sableux", "20,5", "40,1", "", "résistance non mesurée"],
    ["SP2", "E08", "3", "Argile limoneuse", "nd", "44,8", "102", "teneur en eau non déterminée"],
    ["SP2", "E09", "4", "Argile", "27 %", "49,9", "0,12 MPa", ""],
    ["SP3", "E10", "0,5", "Sable latéritique", "12,3", "32,0", "160", ""],
    ["SP3", "E11", "1,5", "Sable latéritique", "13,8", "33,5", "152", ""],
    ["SP3", "E12", "2,5", "Grave latéritique", "11,2", "30,9", "171", ""],
    ["SP3", "E13", "3,5", "Grave latéritique", "", "29,8", "< 20", "essai interrompu (valeur inférieure à 20)"],
    ["SP4", "E14", "1", "Sable argileux", "15,6", "35,2", "140", ""],
    ["SP4", "E15", "2", "Sable argileux", "0,169", "36,8", "131", ""],
    ["SP4", "E16", "3", "Argile sableuse", "19,4", "41,0", "118", ""],
    ["", "E17", "2", "Argile", "23,5", "46,1", "95", "fiche de terrain perdue : sondage inconnu"],
    ["SP2", "E06", "1", "Limon sableux", "18,9", "38,4", "135", ""],  # copie exacte de E06
    ["Moyenne", "", "", "", "35,1", "41,9", "118", "ligne de synthèse ajoutée par l'opérateur"],
]
# Fiches de sondage fictives (repère local du chantier, en mètres)
SONDAGES = [
    {"code": "SP1", "site": SITE_A, "x": 0.0, "y": 0.0, "systeme_coord": org.SYSTEMES_COORDONNEES[3],
     "profondeur_finale_m": 6.0, "type_sondage": "Sondage carotté", "entreprise": "Entreprise fictive",
     "observations": "Sondage FICTIF (exercice)."},
    {"code": "SP2", "site": SITE_A, "x": 25.0, "y": 10.0, "systeme_coord": org.SYSTEMES_COORDONNEES[3],
     "profondeur_finale_m": 5.0, "type_sondage": "Sondage carotté", "entreprise": "Entreprise fictive",
     "observations": "Sondage FICTIF (exercice)."},
    {"code": "SP3", "site": SITE_B, "x": 0.0, "y": 0.0, "systeme_coord": org.SYSTEMES_COORDONNEES[3],
     "profondeur_finale_m": 4.0, "type_sondage": "Sondage à la tarière", "entreprise": "Entreprise fictive",
     "observations": "Sondage FICTIF (exercice)."},
    {"code": "SP4", "site": SITE_B, "type_sondage": "Sondage à la tarière",
     "observations": "Sondage FICTIF (exercice) : coordonnées non relevées → localisation inconnue."},
]
PROVENANCE = {
    "source": "GeoData Sol — jeu pédagogique FICTIF intégré à l'application",
    "auteur_import": None,  # complété avec l'auteur du projet
    "producteur": "Données inventées pour l'exercice (aucune mesure réelle)",
    "date_donnees": "sans objet (données fictives)",
    "licence": "Libre pour l'enseignement",
    "limites_usage": "Données INVENTÉES : elles ne représentent aucun site réel et ne doivent jamais servir à une "
                     "étude ou à un dimensionnement. Usage pédagogique uniquement.",
    "remarques": "Contient volontairement des pièges (conventions mélangées, unités mixtes, manquants, valeur "
                 "aberrante, doublon, ligne de synthèse, sondage inconnu…).",
}

# Guide de l'exercice : piège → ce que l'application signale → conduite attendue
PIEGES = [
    ("Teneur en eau : « 24 % », « 0,28 », « 22,4 » dans la même colonne",
     "Contrôle qualité, onglet 2 : conventions mélangées (3 groupes)",
     "Lire « 24 % » comme 24 %, « 0,28 » et « 0,169 » comme des fractions (× 100), « 22,4 » comme des %."),
    ("Résistance : « 0,085 MPa » et « 0,12 MPa » parmi des kPa",
     "Onglet 2 : conversion MPa → kPa (× 1000) proposée",
     "Valider la conversion : 85 kPa et 120 kPa."),
    ("Limite de liquidité : « 45.5 » (point) et « 47,2 » (virgule)",
     "Onglet 2 : séparateurs décimaux mélangés",
     "Vérifier puis confirmer que le point et la virgule sont décimaux."),
    ("Cases vides et « nd »", "Onglet 2 : valeurs manquantes et marqueurs",
     "Elles restent manquantes : ne jamais les remplacer par 0."),
    ("Teneur en eau de 300 (ligne 5)", "Onglet 4 : valeur atypique (règle de Tukey)",
     "Vérifier : probable erreur de saisie (30,0 ?). L'exclure de l'analyse en le justifiant, sans la supprimer."),
    ("Résistance « < 20 » (ligne 13)", "Onglet 2 : valeur censurée",
     "Non chiffrable : exclue de l'analyse, conservée dans les données brutes."),
    ("Ligne 18 identique à la ligne 6", "Onglet 3 : doublon exact", "Exclure la copie de l'analyse."),
    ("Ligne 19 « Moyenne »", "Onglet 3 : ligne de synthèse", "L'exclure : ce n'est pas une observation."),
    ("Ligne 17 sans sondage", "Onglets 3 et rattachement : localisation inconnue",
     "La garder, marquée « localisation inconnue » : elle n'apparaît dans aucun profil."),
    ("Deux sites (A : SP1, SP2 ; B : SP3, SP4) ; SP4 sans coordonnées",
     "Profils : un graphique par site ; SP4 en localisation inconnue",
     "Ne jamais fusionner les profils des sites A et B."),
]


def fichier_excel() -> bytes:
    """Le jeu pédagogique sous forme de classeur Excel (feuille « Données » + « LISEZ-MOI »)."""
    sortie = io.BytesIO()
    with pd.ExcelWriter(sortie, engine="openpyxl") as classeur:
        pd.DataFrame(LIGNES, columns=COLONNES).to_excel(classeur, sheet_name="Données", index=False)
        pd.DataFrame({"LISEZ-MOI": [
            "JEU DE DONNÉES PÉDAGOGIQUE ENTIÈREMENT FICTIF — GeoData Sol.",
            "Les valeurs sont inventées et ne représentent aucun site réel.",
            "Elles contiennent volontairement des pièges pour s'exercer au contrôle qualité.",
            "Usage pédagogique uniquement : ne jamais utiliser pour une étude ou un dimensionnement.",
        ]}).to_excel(classeur, sheet_name="LISEZ-MOI", index=False)
    return sortie.getvalue()


def charger(projet_id: int, auteur: str | None = None) -> int:
    """Importe le jeu pédagogique dans un projet et crée les fiches de sondage fictives.
    Renvoie l'identifiant du jeu de données créé."""
    lecture = importation.lire_fichier(fichier_excel(), NOM_FICHIER, feuille="Données")
    df = lecture.donnees
    jeu_id = db.creer_jeu_donnees(
        projet_id=projet_id, nom=NOM_JEU, type_source="pedagogique", fichier_ou_url=NOM_FICHIER,
        contenu_json=importation.tableau_vers_json(df), nb_lignes=len(df), colonnes=list(df.columns),
        provenance={**PROVENANCE, "auteur_import": auteur or "Utilisateur de GeoData Sol"},
        feuille="Données", est_fictif=True, details_import=" ".join(lecture.remarques),
    )
    existants = {s["code"] for s in db.lister_sondages(projet_id)}
    for fiche in SONDAGES:
        if fiche["code"] not in existants:
            db.enregistrer_sondage(projet_id, fiche)
    return jeu_id


def projet_exercice() -> tuple[int, int | None]:
    """Crée (ou retrouve) le projet d'exercice et y charge le jeu pédagogique s'il n'y est pas.
    Renvoie (projet_id, jeu_id du jeu pédagogique)."""
    projet = next((p for p in db.lister_projets() if p["nom"] == NOM_PROJET), None)
    if projet is None:
        projet_id = db.creer_projet({
            "nom": NOM_PROJET, "localisation": "Sites d'exercice A et B (fictifs)",
            "type_ouvrage": "Travail pédagogique (TP)", "auteur": "Étudiant",
            "description": "Projet d'exercice créé automatiquement avec le jeu de données pédagogique FICTIF de "
                           "GeoData Sol. Suivez le parcours : contrôle qualité, rattachement aux sondages, "
                           "analyses, rapport.",
            "confidentialite": "Public",
        })
    else:
        projet_id = projet["id"]
    jeu = next((j for j in db.lister_jeux(projet_id) if j["type_source"] == "pedagogique"), None)
    jeu_id = jeu["id"] if jeu else charger(projet_id, "Étudiant")
    return projet_id, jeu_id
