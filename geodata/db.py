"""Accès à la base de données SQLite de GeoData Sol.

C'est le SEUL module qui dialogue directement avec SQLite. Les pages de
l'interface et les modules d'analyse passent par les fonctions ci-dessous.

Conventions :
- les dates sont stockées en texte ISO 8601 (AAAA-MM-JJTHH:MM:SS), heure locale ;
- les profondeurs sont en mètres (m), comptées positivement vers le bas
  depuis la surface du terrain naturel ;
- les contenus de jeux de données sont stockés en JSON (le contenu brut
  importé n'est jamais modifié ; les corrections validées vont dans une
  version séparée).
"""

import json
import sqlite3
import unicodedata
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

# Emplacement du fichier de base : <racine du projet>/data/geodata.db
DOSSIER_DATA = Path(__file__).resolve().parent.parent / "data"
CHEMIN_BASE = DOSSIER_DATA / "geodata.db"


# ---------------------------------------------------------------------------
# Schéma de la base
# ---------------------------------------------------------------------------
SCHEMA = """
-- Projets d'étude géotechnique
CREATE TABLE IF NOT EXISTS projets (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    nom                 TEXT NOT NULL,
    localisation        TEXT,
    type_ouvrage        TEXT,
    description         TEXT,
    auteur              TEXT,
    confidentialite     TEXT,          -- ex. « Public », « Interne », « Confidentiel »
    acces_autorise      TEXT,          -- personnes autorisées à consulter (texte libre)
    date_creation       TEXT NOT NULL,
    date_modification   TEXT NOT NULL
);

-- Jeux de données importés (fichier local, URL, jeu pédagogique, saisie)
CREATE TABLE IF NOT EXISTS jeux_donnees (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    projet_id           INTEGER NOT NULL REFERENCES projets(id) ON DELETE CASCADE,
    nom                 TEXT NOT NULL,
    type_source         TEXT NOT NULL, -- 'fichier', 'url', 'pedagogique', 'saisie'
    feuille             TEXT,          -- feuille Excel utilisée, le cas échéant
    nb_lignes           INTEGER,
    nb_colonnes         INTEGER,
    contenu_brut        TEXT,          -- JSON : données telles qu'importées
    contenu_valide      TEXT,          -- JSON : données après corrections validées
    statut_qc           TEXT NOT NULL DEFAULT 'non vérifié',
    est_fictif          INTEGER NOT NULL DEFAULT 0,
    date_import         TEXT NOT NULL
);

-- Fiche de provenance : une par jeu de données (règle n° 3)
CREATE TABLE IF NOT EXISTS provenance (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    jeu_id              INTEGER NOT NULL UNIQUE REFERENCES jeux_donnees(id) ON DELETE CASCADE,
    source              TEXT NOT NULL, -- organisme, laboratoire, rapport, base publique…
    fichier_ou_url      TEXT NOT NULL,
    date_import         TEXT NOT NULL,
    auteur_import       TEXT,
    producteur          TEXT,          -- qui a produit les données à l'origine
    date_donnees        TEXT,          -- date de réalisation des essais, si connue
    licence             TEXT,
    limites_usage       TEXT,
    remarques           TEXT
);

-- Description de chaque colonne d'un jeu de données
CREATE TABLE IF NOT EXISTS colonnes (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    jeu_id              INTEGER NOT NULL REFERENCES jeux_donnees(id) ON DELETE CASCADE,
    nom_origine         TEXT NOT NULL, -- nom dans le fichier importé
    variable            TEXT,          -- nom de variable retenu (ex. « Teneur en eau »)
    unite               TEXT,          -- unité confirmée par l'utilisateur
    role                TEXT,          -- 'mesure', 'profondeur', 'id_sondage', 'id_echantillon', 'texte'…
    type_detecte        TEXT,
    unite_confirmee     INTEGER NOT NULL DEFAULT 0
);

-- Décisions de contrôle qualité validées par l'utilisateur (règles n° 1, 2, 4)
CREATE TABLE IF NOT EXISTS decisions_qc (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    jeu_id              INTEGER NOT NULL REFERENCES jeux_donnees(id) ON DELETE CASCADE,
    colonne             TEXT,
    type_decision       TEXT NOT NULL, -- 'conversion', 'interpretation', 'atypique', 'doublon', 'manquant'…
    description         TEXT NOT NULL, -- ce qui a été décidé, en clair
    methode             TEXT,          -- méthode / formule appliquée
    lignes_concernees   TEXT,          -- JSON : liste des indices de lignes
    date_decision       TEXT NOT NULL,
    auteur              TEXT
);

-- Sondages (fiche 6.1 du cahier des charges)
CREATE TABLE IF NOT EXISTS sondages (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    projet_id           INTEGER NOT NULL REFERENCES projets(id) ON DELETE CASCADE,
    code                TEXT NOT NULL, -- identifiant du sondage (ex. SC1)
    site                TEXT,          -- site d'investigation (pour ne jamais fusionner des sites)
    x                   REAL,
    y                   REAL,
    z_terrain           REAL,          -- cote du terrain naturel (m)
    systeme_coord       TEXT,          -- ex. « WGS 84 (EPSG:4326) », « Lambert 93 (EPSG:2154) »
    localisation_connue INTEGER NOT NULL DEFAULT 0, -- règle n° 10
    profondeur_finale_m REAL,
    date_realisation    TEXT,
    type_sondage        TEXT,
    entreprise          TEXT,
    methode             TEXT,
    observations        TEXT,
    UNIQUE (projet_id, code)
);

-- Échantillons (fiche 6.2)
CREATE TABLE IF NOT EXISTS echantillons (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    projet_id           INTEGER NOT NULL REFERENCES projets(id) ON DELETE CASCADE,
    sondage_id          INTEGER REFERENCES sondages(id) ON DELETE SET NULL,
    code                TEXT NOT NULL,
    profondeur_haut_m   REAL,
    profondeur_bas_m    REAL,
    date_prelevement    TEXT,
    nature_sol          TEXT,
    type_echantillon    TEXT,
    observations        TEXT,
    UNIQUE (projet_id, code)
);

-- Résultats d'essais (6.3) : une ligne = une valeur mesurée ou calculée
CREATE TABLE IF NOT EXISTS essais (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    projet_id           INTEGER NOT NULL REFERENCES projets(id) ON DELETE CASCADE,
    jeu_id              INTEGER REFERENCES jeux_donnees(id) ON DELETE SET NULL,
    sondage_id          INTEGER REFERENCES sondages(id) ON DELETE SET NULL,
    echantillon_id      INTEGER REFERENCES echantillons(id) ON DELETE SET NULL,
    type_essai          TEXT NOT NULL, -- ex. « Teneur en eau », « Pénétromètre »
    parametre           TEXT NOT NULL,
    valeur              REAL,
    unite               TEXT,
    profondeur_m        REAL,
    nature_resultat     TEXT NOT NULL DEFAULT 'observation', -- 'observation' ou 'calculé'
    date_essai          TEXT,
    remarques           TEXT
);

-- Historique des opérations (traçabilité, 8.1)
CREATE TABLE IF NOT EXISTS historique (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    projet_id           INTEGER REFERENCES projets(id) ON DELETE CASCADE,
    jeu_id              INTEGER REFERENCES jeux_donnees(id) ON DELETE SET NULL,
    date_operation      TEXT NOT NULL,
    operation           TEXT NOT NULL, -- ex. « Import », « Conversion d'unité », « Export PDF »
    details             TEXT,
    auteur              TEXT
);

-- Réglages de l'application (ex. dernier projet ouvert)
CREATE TABLE IF NOT EXISTS parametres (
    cle                 TEXT PRIMARY KEY,
    valeur              TEXT
);

-- Analyses lancées (sert notamment à « date de la dernière analyse »)
CREATE TABLE IF NOT EXISTS analyses (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    projet_id           INTEGER NOT NULL REFERENCES projets(id) ON DELETE CASCADE,
    jeu_id              INTEGER REFERENCES jeux_donnees(id) ON DELETE SET NULL,
    type_analyse        TEXT NOT NULL,
    parametres          TEXT,          -- JSON : variables choisies, options
    date_analyse        TEXT NOT NULL
);

-- Statut d'une valeur signalée au contrôle qualité (ex. valeur atypique vérifiée)
CREATE TABLE IF NOT EXISTS statuts_valeurs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    jeu_id              INTEGER NOT NULL REFERENCES jeux_donnees(id) ON DELETE CASCADE,
    colonne             TEXT NOT NULL, -- nom d'origine de la colonne
    ligne               INTEGER NOT NULL, -- n° de ligne de données (à partir de 1)
    statut              TEXT NOT NULL, -- 'à vérifier', 'vérifiée - conservée', 'exclue de l''analyse'
    commentaire         TEXT,
    date_statut         TEXT NOT NULL,
    UNIQUE (jeu_id, colonne, ligne)
);
"""

# Colonnes ajoutées après la création initiale de certaines tables :
# elles sont ajoutées automatiquement aux bases déjà existantes.
MIGRATIONS = {
    "colonnes": {"interpretation": "TEXT"},  # JSON : décisions d'interprétation validées
    "jeux_donnees": {"options_qc": "TEXT"},  # JSON : options du contrôle qualité (doublons…)
}


# ---------------------------------------------------------------------------
# Connexion
# ---------------------------------------------------------------------------
def maintenant() -> str:
    """Date et heure actuelles au format ISO (à la seconde près)."""
    return datetime.now().isoformat(timespec="seconds")


@contextmanager
def connexion(chemin: Path | None = None):
    """Ouvre une connexion SQLite, valide les modifications puis la referme.

    Utilisation :
        with connexion() as cx:
            cx.execute(...)
    """
    chemin = Path(chemin) if chemin else CHEMIN_BASE
    chemin.parent.mkdir(parents=True, exist_ok=True)
    cx = sqlite3.connect(chemin)
    cx.row_factory = sqlite3.Row  # accès aux colonnes par leur nom
    cx.execute("PRAGMA foreign_keys = ON")
    try:
        yield cx
        cx.commit()
    except Exception:
        cx.rollback()
        raise
    finally:
        cx.close()


def initialiser_base(chemin: Path | None = None) -> None:
    """Crée le fichier de base et toutes les tables si elles n'existent pas,
    puis ajoute les colonnes apparues dans les versions suivantes."""
    with connexion(chemin) as cx:
        cx.executescript(SCHEMA)
        for table, colonnes in MIGRATIONS.items():
            existantes = {r["name"] for r in cx.execute(f"PRAGMA table_info({table})")}
            for nom, type_sql in colonnes.items():
                if nom not in existantes:
                    cx.execute(f"ALTER TABLE {table} ADD COLUMN {nom} {type_sql}")


# ---------------------------------------------------------------------------
# Indicateurs de la page d'accueil
# ---------------------------------------------------------------------------
def compter(table: str, chemin: Path | None = None) -> int:
    """Nombre de lignes d'une table (liste fermée de tables autorisées)."""
    if table not in {"projets", "jeux_donnees", "sondages", "echantillons", "essais"}:
        raise ValueError(f"Table inconnue : {table}")
    with connexion(chemin) as cx:
        return cx.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def date_derniere_analyse(chemin: Path | None = None) -> str | None:
    """Date ISO de la dernière analyse enregistrée, ou None s'il n'y en a pas."""
    with connexion(chemin) as cx:
        return cx.execute("SELECT MAX(date_analyse) FROM analyses").fetchone()[0]


def indicateurs(chemin: Path | None = None) -> dict:
    """Regroupe les indicateurs affichés sur la page d'accueil."""
    return {
        "projets": compter("projets", chemin),
        "jeux_donnees": compter("jeux_donnees", chemin),
        "sondages": compter("sondages", chemin),
        "derniere_analyse": date_derniere_analyse(chemin),
    }


# ---------------------------------------------------------------------------
# Projets
# ---------------------------------------------------------------------------
# Champs modifiables d'une fiche projet (l'ordre sert aussi aux formulaires)
CHAMPS_PROJET = (
    "nom",
    "localisation",
    "type_ouvrage",
    "description",
    "auteur",
    "confidentialite",
    "acces_autorise",
)


def _nettoyer_fiche(fiche: dict) -> dict:
    """Garde uniquement les champs connus et enlève les espaces superflus."""
    propre = {}
    for champ in CHAMPS_PROJET:
        valeur = fiche.get(champ)
        if isinstance(valeur, str):
            valeur = valeur.strip() or None
        propre[champ] = valeur
    if not propre["nom"]:
        raise ValueError("Le nom du projet est obligatoire.")
    return propre


def nom_projet_existe(nom: str, sauf_id: int | None = None, chemin: Path | None = None) -> bool:
    """Vrai si un autre projet porte déjà ce nom (sans tenir compte des majuscules,
    des accents ni des espaces en trop : « Lycée » = « LYCEE »)."""
    with connexion(chemin) as cx:
        autres = cx.execute("SELECT nom FROM projets WHERE id IS NOT ?", (sauf_id,)).fetchall()
    cible = _comparable(nom)
    return any(_comparable(r["nom"]) == cible for r in autres)


def _comparable(texte: str) -> str:
    """Forme simplifiée d'un texte pour comparer deux noms."""
    sans_accents = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode()
    return " ".join(sans_accents.lower().split())


def creer_projet(fiche: dict, chemin: Path | None = None) -> int:
    """Enregistre un nouveau projet et renvoie son identifiant."""
    propre = _nettoyer_fiche(fiche)
    if nom_projet_existe(propre["nom"], chemin=chemin):
        raise ValueError(f"Un projet nommé « {propre['nom']} » existe déjà.")
    date = maintenant()
    with connexion(chemin) as cx:
        curseur = cx.execute(
            f"INSERT INTO projets ({', '.join(CHAMPS_PROJET)}, date_creation, date_modification) "
            f"VALUES ({', '.join('?' * len(CHAMPS_PROJET))}, ?, ?)",
            (*propre.values(), date, date),
        )
        projet_id = curseur.lastrowid
    ajouter_historique(
        "Création du projet",
        f"Projet « {propre['nom']} » créé.",
        projet_id=projet_id,
        auteur=propre["auteur"],
        chemin=chemin,
    )
    return projet_id


def modifier_projet(projet_id: int, fiche: dict, chemin: Path | None = None) -> None:
    """Met à jour la fiche d'un projet et note les champs modifiés dans l'historique."""
    propre = _nettoyer_fiche(fiche)
    if nom_projet_existe(propre["nom"], sauf_id=projet_id, chemin=chemin):
        raise ValueError(f"Un autre projet porte déjà le nom « {propre['nom']} ».")
    ancien = obtenir_projet(projet_id, chemin)
    if ancien is None:
        raise ValueError("Ce projet n'existe plus.")
    changes = [c for c in CHAMPS_PROJET if (ancien[c] or None) != propre[c]]
    if not changes:
        return
    with connexion(chemin) as cx:
        cx.execute(
            f"UPDATE projets SET {', '.join(f'{c} = ?' for c in CHAMPS_PROJET)}, "
            "date_modification = ? WHERE id = ?",
            (*propre.values(), maintenant(), projet_id),
        )
    ajouter_historique(
        "Modification du projet",
        "Champs modifiés : " + ", ".join(changes),
        projet_id=projet_id,
        auteur=propre["auteur"],
        chemin=chemin,
    )


def obtenir_projet(projet_id: int, chemin: Path | None = None) -> dict | None:
    """Fiche complète d'un projet, ou None s'il n'existe pas."""
    with connexion(chemin) as cx:
        ligne = cx.execute("SELECT * FROM projets WHERE id = ?", (projet_id,)).fetchone()
    return dict(ligne) if ligne else None


def lister_projets(chemin: Path | None = None) -> list[dict]:
    """Tous les projets, du plus récemment modifié au plus ancien,
    avec le nombre de jeux de données et de sondages de chacun."""
    with connexion(chemin) as cx:
        lignes = cx.execute(
            """
            SELECT p.*,
                   (SELECT COUNT(*) FROM jeux_donnees j WHERE j.projet_id = p.id) AS nb_jeux,
                   (SELECT COUNT(*) FROM sondages s WHERE s.projet_id = p.id)     AS nb_sondages
            FROM projets p
            ORDER BY p.date_modification DESC, p.id DESC
            """
        ).fetchall()
    return [dict(l) for l in lignes]


def supprimer_projet(projet_id: int, chemin: Path | None = None) -> None:
    """Supprime un projet et tout ce qui lui est rattaché (jeux, sondages, essais…)."""
    with connexion(chemin) as cx:
        cx.execute("DELETE FROM projets WHERE id = ?", (projet_id,))


# ---------------------------------------------------------------------------
# Jeux de données et fiches de provenance
# ---------------------------------------------------------------------------
# Champs de la fiche de provenance saisis par l'utilisateur
CHAMPS_PROVENANCE = (
    "source",
    "auteur_import",
    "producteur",
    "date_donnees",
    "licence",
    "limites_usage",
    "remarques",
)
# Champs obligatoires (règle n° 3) — fichier_ou_url et date_import sont remplis automatiquement
PROVENANCE_OBLIGATOIRE = {
    "source": "Source des données",
    "auteur_import": "Auteur de l'import",
    "limites_usage": "Limites d'usage",
}
TYPES_SOURCE = {
    "fichier": "Fichier local",
    "url": "Fichier en ligne (URL)",
    "pedagogique": "Jeu pédagogique",
    "saisie": "Saisie manuelle",
}


def _nettoyer_provenance(fiche: dict) -> dict:
    """Garde les champs connus, retire les espaces et vérifie les champs obligatoires."""
    propre = {}
    for champ in CHAMPS_PROVENANCE:
        valeur = fiche.get(champ)
        propre[champ] = (valeur.strip() or None) if isinstance(valeur, str) else valeur
    manquants = [libelle for champ, libelle in PROVENANCE_OBLIGATOIRE.items() if not propre[champ]]
    if manquants:
        raise ValueError("Fiche de provenance incomplète : " + ", ".join(manquants) + ".")
    return propre


def creer_jeu_donnees(
    projet_id: int,
    nom: str,
    type_source: str,
    fichier_ou_url: str,
    contenu_json: str,
    nb_lignes: int,
    colonnes: list[str],
    provenance: dict,
    feuille: str | None = None,
    est_fictif: bool = False,
    details_import: str = "",
    chemin: Path | None = None,
) -> int:
    """Enregistre un jeu de données, sa fiche de provenance et ses colonnes
    (tout ou rien : si une étape échoue, rien n'est enregistré)."""
    if type_source not in TYPES_SOURCE:
        raise ValueError(f"Type de source inconnu : {type_source}")
    if not (nom or "").strip():
        raise ValueError("Le nom du jeu de données est obligatoire.")
    prov = _nettoyer_provenance(provenance)
    date = maintenant()
    with connexion(chemin) as cx:
        jeu_id = cx.execute(
            "INSERT INTO jeux_donnees (projet_id, nom, type_source, feuille, nb_lignes, nb_colonnes, "
            "contenu_brut, est_fictif, date_import) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (projet_id, nom.strip(), type_source, feuille, nb_lignes, len(colonnes),
             contenu_json, int(est_fictif), date),
        ).lastrowid
        cx.execute(
            f"INSERT INTO provenance (jeu_id, fichier_ou_url, date_import, {', '.join(CHAMPS_PROVENANCE)}) "
            f"VALUES (?, ?, ?, {', '.join('?' * len(CHAMPS_PROVENANCE))})",
            (jeu_id, fichier_ou_url, date, *prov.values()),
        )
        cx.executemany(
            "INSERT INTO colonnes (jeu_id, nom_origine) VALUES (?, ?)",
            [(jeu_id, c) for c in colonnes],
        )
        details = (
            f"{TYPES_SOURCE[type_source]} « {fichier_ou_url} »"
            + (f", feuille « {feuille} »" if feuille else "")
            + f" — {nb_lignes} ligne(s), {len(colonnes)} colonne(s). Source : {prov['source']}."
            + (f" {details_import}" if details_import else "")
            + (" Données FICTIVES." if est_fictif else "")
        )
        cx.execute(
            "INSERT INTO historique (projet_id, jeu_id, date_operation, operation, details, auteur) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (projet_id, jeu_id, date, "Import de données", details, prov["auteur_import"]),
        )
    return jeu_id


def lister_jeux(projet_id: int, chemin: Path | None = None) -> list[dict]:
    """Jeux de données d'un projet (sans leur contenu), du plus récent au plus ancien,
    avec les principaux éléments de provenance."""
    with connexion(chemin) as cx:
        lignes = cx.execute(
            """
            SELECT j.id, j.projet_id, j.nom, j.type_source, j.feuille, j.nb_lignes, j.nb_colonnes,
                   j.statut_qc, j.est_fictif, j.date_import,
                   p.source, p.fichier_ou_url, p.auteur_import, p.limites_usage
            FROM jeux_donnees j LEFT JOIN provenance p ON p.jeu_id = j.id
            WHERE j.projet_id = ?
            ORDER BY j.date_import DESC, j.id DESC
            """,
            (projet_id,),
        ).fetchall()
    return [dict(l) for l in lignes]


def obtenir_jeu(jeu_id: int, chemin: Path | None = None) -> dict | None:
    """Jeu de données complet (avec son contenu JSON), ou None."""
    with connexion(chemin) as cx:
        ligne = cx.execute("SELECT * FROM jeux_donnees WHERE id = ?", (jeu_id,)).fetchone()
    return dict(ligne) if ligne else None


def obtenir_provenance(jeu_id: int, chemin: Path | None = None) -> dict | None:
    """Fiche de provenance d'un jeu de données."""
    with connexion(chemin) as cx:
        ligne = cx.execute("SELECT * FROM provenance WHERE jeu_id = ?", (jeu_id,)).fetchone()
    return dict(ligne) if ligne else None


def modifier_provenance(jeu_id: int, fiche: dict, chemin: Path | None = None) -> None:
    """Complète ou corrige une fiche de provenance. Le fichier/URL d'origine et la date
    d'import ne sont pas modifiables : ce sont des faits enregistrés au moment de l'import."""
    propre = _nettoyer_provenance(fiche)
    ancienne = obtenir_provenance(jeu_id, chemin)
    jeu = obtenir_jeu(jeu_id, chemin)
    if ancienne is None or jeu is None:
        raise ValueError("Ce jeu de données n'existe plus.")
    changes = [c for c in CHAMPS_PROVENANCE if (ancienne[c] or None) != propre[c]]
    if not changes:
        return
    with connexion(chemin) as cx:
        cx.execute(
            f"UPDATE provenance SET {', '.join(f'{c} = ?' for c in CHAMPS_PROVENANCE)} WHERE jeu_id = ?",
            (*propre.values(), jeu_id),
        )
    ajouter_historique(
        "Modification de la provenance",
        f"Jeu « {jeu['nom']} » — champs modifiés : " + ", ".join(changes),
        projet_id=jeu["projet_id"],
        jeu_id=jeu_id,
        auteur=propre["auteur_import"],
        chemin=chemin,
    )


def supprimer_jeu(jeu_id: int, chemin: Path | None = None) -> None:
    """Supprime un jeu de données (et sa provenance) ; la suppression reste dans l'historique."""
    jeu = obtenir_jeu(jeu_id, chemin)
    if jeu is None:
        return
    with connexion(chemin) as cx:
        cx.execute("DELETE FROM jeux_donnees WHERE id = ?", (jeu_id,))
    ajouter_historique(
        "Suppression d'un jeu de données",
        f"Jeu « {jeu['nom']} » ({jeu['nb_lignes']} ligne(s)) supprimé.",
        projet_id=jeu["projet_id"],
        chemin=chemin,
    )


# ---------------------------------------------------------------------------
# Contrôle qualité
# ---------------------------------------------------------------------------
STATUTS_ATYPIQUES = ("à vérifier", "vérifiée - conservée", "exclue de l'analyse")


def _decision(cx, jeu_id: int, type_decision: str, description: str, colonne: str | None = None,
              methode: str | None = None, lignes: list[int] | None = None, auteur: str | None = None) -> None:
    """Note une décision de contrôle qualité (à appeler dans une connexion ouverte)."""
    cx.execute(
        "INSERT INTO decisions_qc (jeu_id, colonne, type_decision, description, methode, "
        "lignes_concernees, date_decision, auteur) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (jeu_id, colonne, type_decision, description, methode,
         json.dumps(lignes) if lignes else None, maintenant(), auteur),
    )


def _invalider(cx, jeu_id: int) -> None:
    """Toute nouvelle décision rend la version validée obsolète : on la retire."""
    cx.execute(
        "UPDATE jeux_donnees SET statut_qc = 'en cours', contenu_valide = NULL WHERE id = ?",
        (jeu_id,),
    )


def _historique_cx(cx, jeu_id: int, operation: str, details: str, auteur: str | None = None) -> None:
    """Ajoute une ligne d'historique dans une connexion déjà ouverte."""
    projet_id = cx.execute("SELECT projet_id FROM jeux_donnees WHERE id = ?", (jeu_id,)).fetchone()[0]
    cx.execute(
        "INSERT INTO historique (projet_id, jeu_id, date_operation, operation, details, auteur) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (projet_id, jeu_id, maintenant(), operation, details, auteur),
    )


def lister_colonnes(jeu_id: int, chemin: Path | None = None) -> list[dict]:
    """Description des colonnes d'un jeu, dans l'ordre du fichier (interprétation décodée)."""
    with connexion(chemin) as cx:
        lignes = cx.execute("SELECT * FROM colonnes WHERE jeu_id = ? ORDER BY id", (jeu_id,)).fetchall()
    resultat = []
    for l in lignes:
        d = dict(l)
        d["interpretation"] = json.loads(d["interpretation"]) if d["interpretation"] else None
        resultat.append(d)
    return resultat


def enregistrer_structure(jeu_id: int, structure: list[dict], auteur: str | None = None,
                          chemin: Path | None = None) -> list[str]:
    """Enregistre le rôle, le nom de variable et l'unité confirmés de chaque colonne.

    Si le rôle ou l'unité d'une colonne change, son interprétation précédente est effacée
    (elle devra être refaite). Renvoie la liste des changements, en clair.
    """
    anciennes = {c["nom_origine"]: c for c in lister_colonnes(jeu_id, chemin)}
    changements = []
    with connexion(chemin) as cx:
        for s in structure:
            ancienne = anciennes.get(s["nom_origine"])
            if ancienne is None:
                continue
            nouveau = {k: (s.get(k) or None) for k in ("variable", "unite", "role", "type_detecte")}
            modif = [k for k in ("variable", "unite", "role") if ancienne[k] != nouveau[k]]
            if not modif and ancienne["unite_confirmee"]:
                continue
            reinit = "role" in modif or "unite" in modif
            cx.execute(
                "UPDATE colonnes SET variable = ?, unite = ?, role = ?, type_detecte = ?, unite_confirmee = 1"
                + (", interpretation = NULL" if reinit else "") + " WHERE id = ?",
                (nouveau["variable"], nouveau["unite"], nouveau["role"], nouveau["type_detecte"], ancienne["id"]),
            )
            changements.append(
                f"« {s['nom_origine']} » : variable « {nouveau['variable'] or '—'} », "
                f"unité {nouveau['unite'] or 'aucune'}, rôle {nouveau['role']}"
            )
        if changements:
            _invalider(cx, jeu_id)
            _decision(cx, jeu_id, "structure", "Structure confirmée — " + " ; ".join(changements), auteur=auteur)
            _historique_cx(cx, jeu_id, "Contrôle qualité : structure",
                           f"{len(changements)} colonne(s) décrite(s) ou modifiée(s).", auteur)
    return changements


def enregistrer_interpretation(jeu_id: int, nom_origine: str, interpretation: dict, description: str,
                               methode: str | None = None, auteur: str | None = None,
                               chemin: Path | None = None) -> None:
    """Enregistre les décisions d'interprétation d'une colonne (conventions, conversions)."""
    with connexion(chemin) as cx:
        cx.execute(
            "UPDATE colonnes SET interpretation = ? WHERE jeu_id = ? AND nom_origine = ?",
            (json.dumps(interpretation, ensure_ascii=False), jeu_id, nom_origine),
        )
        _invalider(cx, jeu_id)
        type_decision = "conversion" if interpretation.get("conversion_validee") else "interprétation"
        _decision(cx, jeu_id, type_decision, description, colonne=nom_origine, methode=methode, auteur=auteur)
        _historique_cx(cx, jeu_id, "Contrôle qualité : interprétation", f"« {nom_origine} » : {description}", auteur)


def lire_statuts(jeu_id: int, chemin: Path | None = None) -> dict[tuple[str, int], dict]:
    """Statuts des valeurs signalées : {(colonne, ligne): {statut, commentaire, date_statut}}."""
    with connexion(chemin) as cx:
        lignes = cx.execute("SELECT * FROM statuts_valeurs WHERE jeu_id = ?", (jeu_id,)).fetchall()
    return {(l["colonne"], l["ligne"]): dict(l) for l in lignes}


def enregistrer_statuts(jeu_id: int, colonne: str, statuts: list[tuple[int, str, str | None]],
                        methode: str, auteur: str | None = None, chemin: Path | None = None) -> int:
    """Enregistre la décision prise pour chaque valeur atypique d'une colonne.
    statuts : [(ligne, statut, commentaire)]. Renvoie le nombre de statuts modifiés."""
    anciens = lire_statuts(jeu_id, chemin)
    modifies = []
    with connexion(chemin) as cx:
        for ligne, statut, commentaire in statuts:
            if statut not in STATUTS_ATYPIQUES:
                raise ValueError(f"Statut inconnu : {statut}")
            ancien = anciens.get((colonne, ligne))
            commentaire = (commentaire or "").strip() or None
            if ancien and ancien["statut"] == statut and ancien["commentaire"] == commentaire:
                continue
            cx.execute(
                "INSERT INTO statuts_valeurs (jeu_id, colonne, ligne, statut, commentaire, date_statut) "
                "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(jeu_id, colonne, ligne) DO UPDATE SET "
                "statut = excluded.statut, commentaire = excluded.commentaire, date_statut = excluded.date_statut",
                (jeu_id, colonne, ligne, statut, commentaire, maintenant()),
            )
            modifies.append((ligne, statut, commentaire))
        if modifies:
            _invalider(cx, jeu_id)
            for ligne, statut, commentaire in modifies:
                _decision(cx, jeu_id, "atypique",
                          f"Ligne {ligne} : {statut}" + (f" ({commentaire})" if commentaire else ""),
                          colonne=colonne, methode=methode, lignes=[ligne], auteur=auteur)
            _historique_cx(cx, jeu_id, "Contrôle qualité : valeurs atypiques",
                           f"« {colonne} » : {len(modifies)} décision(s) enregistrée(s).", auteur)
    return len(modifies)


def lire_options_qc(jeu_id: int, chemin: Path | None = None) -> dict:
    """Options du contrôle qualité d'un jeu (ex. {'exclure_doublons': True})."""
    with connexion(chemin) as cx:
        ligne = cx.execute("SELECT options_qc FROM jeux_donnees WHERE id = ?", (jeu_id,)).fetchone()
    return json.loads(ligne[0]) if ligne and ligne[0] else {}


def enregistrer_option_qc(jeu_id: int, cle: str, valeur, description: str, lignes: list[int] | None = None,
                          auteur: str | None = None, chemin: Path | None = None) -> None:
    """Modifie une option du contrôle qualité et note la décision."""
    options = lire_options_qc(jeu_id, chemin)
    if options.get(cle) == valeur:
        return
    options[cle] = valeur
    with connexion(chemin) as cx:
        cx.execute("UPDATE jeux_donnees SET options_qc = ? WHERE id = ?", (json.dumps(options), jeu_id))
        _invalider(cx, jeu_id)
        _decision(cx, jeu_id, "doublon", description, lignes=lignes, auteur=auteur)
        _historique_cx(cx, jeu_id, "Contrôle qualité : doublons", description, auteur)


def valider_jeu(jeu_id: int, contenu_valide: str, resume: str, auteur: str | None = None,
                chemin: Path | None = None) -> None:
    """Enregistre la version validée des données et marque le jeu comme « validé »."""
    with connexion(chemin) as cx:
        cx.execute(
            "UPDATE jeux_donnees SET statut_qc = 'validé', contenu_valide = ? WHERE id = ?",
            (contenu_valide, jeu_id),
        )
        _decision(cx, jeu_id, "validation", resume, auteur=auteur)
        _historique_cx(cx, jeu_id, "Contrôle qualité : validation", resume, auteur)


def lister_decisions(jeu_id: int, chemin: Path | None = None) -> list[dict]:
    """Journal des décisions de contrôle qualité d'un jeu (les plus récentes d'abord)."""
    with connexion(chemin) as cx:
        lignes = cx.execute(
            "SELECT * FROM decisions_qc WHERE jeu_id = ? ORDER BY date_decision DESC, id DESC", (jeu_id,)
        ).fetchall()
    return [dict(l) for l in lignes]


# ---------------------------------------------------------------------------
# Sondages, échantillons et essais
# ---------------------------------------------------------------------------
CHAMPS_SONDAGE = ("code", "site", "x", "y", "z_terrain", "systeme_coord", "profondeur_finale_m",
                  "date_realisation", "type_sondage", "entreprise", "methode", "observations")
CHAMPS_ECHANTILLON = ("code", "sondage_id", "profondeur_haut_m", "profondeur_bas_m", "date_prelevement",
                      "nature_sol", "type_echantillon", "observations")


def _propre(fiche: dict, champs: tuple) -> dict:
    """Garde les champs connus ; textes vides → None."""
    resultat = {}
    for c in champs:
        v = fiche.get(c)
        if isinstance(v, str):
            v = v.strip() or None
        resultat[c] = v
    return resultat


def _localisation_connue(fiche: dict) -> int:
    """Règle n° 10 : coordonnées x, y ET système renseignés."""
    return int(fiche.get("x") is not None and fiche.get("y") is not None
               and bool(fiche.get("systeme_coord")) and fiche.get("systeme_coord") != "Inconnu")


def enregistrer_sondage(projet_id: int, fiche: dict, sondage_id: int | None = None,
                        chemin: Path | None = None) -> int:
    """Crée (sondage_id=None) ou modifie un sondage. Renvoie son identifiant."""
    propre = _propre(fiche, CHAMPS_SONDAGE)
    if not propre["code"]:
        raise ValueError("L'identifiant du sondage est obligatoire.")
    if propre["profondeur_finale_m"] is not None and propre["profondeur_finale_m"] < 0:
        raise ValueError("La profondeur finale doit être positive (comptée vers le bas, en mètres).")
    with connexion(chemin) as cx:
        doublon = cx.execute(
            "SELECT id FROM sondages WHERE projet_id = ? AND code = ? AND id IS NOT ?",
            (projet_id, propre["code"], sondage_id),
        ).fetchone()
        if doublon:
            raise ValueError(f"Un sondage « {propre['code']} » existe déjà dans ce projet.")
        valeurs = (*propre.values(), _localisation_connue(propre))
        if sondage_id is None:
            sondage_id = cx.execute(
                f"INSERT INTO sondages (projet_id, {', '.join(CHAMPS_SONDAGE)}, localisation_connue) "
                f"VALUES (?, {', '.join('?' * len(CHAMPS_SONDAGE))}, ?)",
                (projet_id, *valeurs),
            ).lastrowid
            operation = "Création d'un sondage"
        else:
            cx.execute(
                f"UPDATE sondages SET {', '.join(f'{c} = ?' for c in CHAMPS_SONDAGE)}, localisation_connue = ? "
                "WHERE id = ? AND projet_id = ?",
                (*valeurs, sondage_id, projet_id),
            )
            operation = "Modification d'un sondage"
        cx.execute(
            "INSERT INTO historique (projet_id, date_operation, operation, details) VALUES (?, ?, ?, ?)",
            (projet_id, maintenant(), operation,
             f"Sondage « {propre['code']} »" + ("" if _localisation_connue(propre) else " — localisation inconnue")),
        )
    return sondage_id


def lister_sondages(projet_id: int, chemin: Path | None = None) -> list[dict]:
    """Sondages d'un projet, avec le nombre d'échantillons et d'essais rattachés."""
    with connexion(chemin) as cx:
        lignes = cx.execute(
            """
            SELECT s.*,
                   (SELECT COUNT(*) FROM echantillons e WHERE e.sondage_id = s.id) AS nb_echantillons,
                   (SELECT COUNT(*) FROM essais t WHERE t.sondage_id = s.id)       AS nb_essais
            FROM sondages s WHERE s.projet_id = ? ORDER BY s.code
            """,
            (projet_id,),
        ).fetchall()
    return [dict(l) for l in lignes]


def supprimer_sondage(sondage_id: int, chemin: Path | None = None) -> None:
    """Supprime un sondage. Ses échantillons et essais sont conservés mais ne sont plus
    rattachés à un sondage (leur localisation devient inconnue)."""
    with connexion(chemin) as cx:
        s = cx.execute("SELECT projet_id, code FROM sondages WHERE id = ?", (sondage_id,)).fetchone()
        if s is None:
            return
        cx.execute("DELETE FROM sondages WHERE id = ?", (sondage_id,))
        cx.execute(
            "INSERT INTO historique (projet_id, date_operation, operation, details) VALUES (?, ?, ?, ?)",
            (s["projet_id"], maintenant(), "Suppression d'un sondage",
             f"Sondage « {s['code']} » supprimé ; ses échantillons et essais sont conservés sans sondage."),
        )


def enregistrer_echantillon(projet_id: int, fiche: dict, echantillon_id: int | None = None,
                            chemin: Path | None = None) -> int:
    """Crée ou modifie un échantillon. Renvoie son identifiant."""
    propre = _propre(fiche, CHAMPS_ECHANTILLON)
    if not propre["code"]:
        raise ValueError("L'identifiant de l'échantillon est obligatoire.")
    haut, bas = propre["profondeur_haut_m"], propre["profondeur_bas_m"]
    if (haut is not None and haut < 0) or (bas is not None and bas < 0):
        raise ValueError("Les profondeurs doivent être positives (comptées vers le bas, en mètres).")
    if haut is not None and bas is not None and bas < haut:
        raise ValueError("La profondeur du bas doit être supérieure ou égale à celle du haut.")
    with connexion(chemin) as cx:
        if cx.execute("SELECT id FROM echantillons WHERE projet_id = ? AND code = ? AND id IS NOT ?",
                      (projet_id, propre["code"], echantillon_id)).fetchone():
            raise ValueError(f"Un échantillon « {propre['code']} » existe déjà dans ce projet.")
        if echantillon_id is None:
            echantillon_id = cx.execute(
                f"INSERT INTO echantillons (projet_id, {', '.join(CHAMPS_ECHANTILLON)}) "
                f"VALUES (?, {', '.join('?' * len(CHAMPS_ECHANTILLON))})",
                (projet_id, *propre.values()),
            ).lastrowid
            operation = "Création d'un échantillon"
        else:
            cx.execute(
                f"UPDATE echantillons SET {', '.join(f'{c} = ?' for c in CHAMPS_ECHANTILLON)} "
                "WHERE id = ? AND projet_id = ?",
                (*propre.values(), echantillon_id, projet_id),
            )
            operation = "Modification d'un échantillon"
        cx.execute(
            "INSERT INTO historique (projet_id, date_operation, operation, details) VALUES (?, ?, ?, ?)",
            (projet_id, maintenant(), operation, f"Échantillon « {propre['code']} »"),
        )
    return echantillon_id


def lister_echantillons(projet_id: int, chemin: Path | None = None) -> list[dict]:
    """Échantillons d'un projet avec le code de leur sondage et le nombre d'essais."""
    with connexion(chemin) as cx:
        lignes = cx.execute(
            """
            SELECT e.*, s.code AS code_sondage,
                   (SELECT COUNT(*) FROM essais t WHERE t.echantillon_id = e.id) AS nb_essais
            FROM echantillons e LEFT JOIN sondages s ON s.id = e.sondage_id
            WHERE e.projet_id = ? ORDER BY s.code, e.profondeur_haut_m, e.code
            """,
            (projet_id,),
        ).fetchall()
    return [dict(l) for l in lignes]


def supprimer_echantillon(echantillon_id: int, chemin: Path | None = None) -> None:
    """Supprime un échantillon (ses essais sont conservés, sans échantillon)."""
    with connexion(chemin) as cx:
        e = cx.execute("SELECT projet_id, code FROM echantillons WHERE id = ?", (echantillon_id,)).fetchone()
        if e is None:
            return
        cx.execute("DELETE FROM echantillons WHERE id = ?", (echantillon_id,))
        cx.execute(
            "INSERT INTO historique (projet_id, date_operation, operation, details) VALUES (?, ?, ?, ?)",
            (e["projet_id"], maintenant(), "Suppression d'un échantillon", f"Échantillon « {e['code']} » supprimé."),
        )


def rattacher_jeu(projet_id: int, jeu_id: int, essais: list[dict], sondages_a_creer: list[str],
                  echantillons_a_creer: dict[str, dict], site: str | None, details: str,
                  chemin: Path | None = None) -> int:
    """Enregistre les essais d'un jeu validé et crée les fiches manquantes (tout ou rien).

    Les essais déjà rattachés depuis ce jeu sont remplacés : on peut refaire le
    rattachement après une nouvelle validation sans créer de doublons.
    sondages_a_creer   : codes des sondages à créer (fiche minimale, localisation inconnue)
    echantillons_a_creer : {code: {"sondage": code_sondage, "profondeur": m}}
    Renvoie le nombre d'essais enregistrés.
    """
    with connexion(chemin) as cx:
        for code in sondages_a_creer:
            cx.execute(
                "INSERT OR IGNORE INTO sondages (projet_id, code, site, localisation_connue, observations) "
                "VALUES (?, ?, ?, 0, ?)",
                (projet_id, code, site, f"Fiche créée automatiquement lors du rattachement du jeu n° {jeu_id} : "
                                        "à compléter (coordonnées, profondeur finale…)."),
            )
        ids_sondages = {r["code"]: r["id"] for r in cx.execute(
            "SELECT id, code FROM sondages WHERE projet_id = ?", (projet_id,))}
        for code, info in echantillons_a_creer.items():
            cx.execute(
                "INSERT OR IGNORE INTO echantillons (projet_id, sondage_id, code, profondeur_haut_m, observations) "
                "VALUES (?, ?, ?, ?, ?)",
                (projet_id, ids_sondages.get(info.get("sondage")), code, info.get("profondeur"),
                 f"Fiche créée automatiquement lors du rattachement du jeu n° {jeu_id}."),
            )
        ids_echantillons = {r["code"]: r["id"] for r in cx.execute(
            "SELECT id, code FROM echantillons WHERE projet_id = ?", (projet_id,))}
        cx.execute("DELETE FROM essais WHERE jeu_id = ?", (jeu_id,))
        cx.executemany(
            "INSERT INTO essais (projet_id, jeu_id, sondage_id, echantillon_id, type_essai, parametre, valeur, "
            "unite, profondeur_m, nature_resultat, remarques) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'observation', ?)",
            [(projet_id, jeu_id, ids_sondages.get(e["code_sondage"]), ids_echantillons.get(e["code_echantillon"]),
              e["type_essai"], e["parametre"], e["valeur"], e["unite"], e["profondeur_m"], e["remarques"])
             for e in essais],
        )
        cx.execute(
            "INSERT INTO historique (projet_id, jeu_id, date_operation, operation, details) VALUES (?, ?, ?, ?, ?)",
            (projet_id, jeu_id, maintenant(), "Rattachement aux sondages", details),
        )
    return len(essais)


def lister_essais(projet_id: int, chemin: Path | None = None) -> list[dict]:
    """Résultats d'essais d'un projet, avec sondage, échantillon, jeu et localisation."""
    with connexion(chemin) as cx:
        lignes = cx.execute(
            """
            SELECT t.*, s.code AS code_sondage, s.site, s.localisation_connue,
                   e.code AS code_echantillon, j.nom AS jeu_nom
            FROM essais t
            LEFT JOIN sondages s ON s.id = t.sondage_id
            LEFT JOIN echantillons e ON e.id = t.echantillon_id
            LEFT JOIN jeux_donnees j ON j.id = t.jeu_id
            WHERE t.projet_id = ?
            ORDER BY s.code, t.profondeur_m, t.parametre
            """,
            (projet_id,),
        ).fetchall()
    return [dict(l) for l in lignes]


def jeux_rattaches(projet_id: int, chemin: Path | None = None) -> dict[int, int]:
    """{jeu_id: nombre d'essais rattachés} pour les jeux d'un projet."""
    with connexion(chemin) as cx:
        return {r[0]: r[1] for r in cx.execute(
            "SELECT jeu_id, COUNT(*) FROM essais WHERE projet_id = ? AND jeu_id IS NOT NULL GROUP BY jeu_id",
            (projet_id,))}


# ---------------------------------------------------------------------------
# Analyses
# ---------------------------------------------------------------------------
def enregistrer_analyse(projet_id: int, jeu_id: int | None, type_analyse: str, parametres: dict,
                        chemin: Path | None = None) -> None:
    """Note une analyse lancée (date de la dernière analyse, traçabilité)."""
    with connexion(chemin) as cx:
        cx.execute(
            "INSERT INTO analyses (projet_id, jeu_id, type_analyse, parametres, date_analyse) VALUES (?, ?, ?, ?, ?)",
            (projet_id, jeu_id, type_analyse, json.dumps(parametres, ensure_ascii=False), maintenant()),
        )
        cx.execute(
            "INSERT INTO historique (projet_id, jeu_id, date_operation, operation, details) VALUES (?, ?, ?, ?, ?)",
            (projet_id, jeu_id, maintenant(), "Analyse",
             f"{type_analyse} — " + ", ".join(f"{k} : {v}" for k, v in parametres.items())),
        )


def lister_analyses(projet_id: int, chemin: Path | None = None) -> list[dict]:
    """Analyses lancées sur un projet (les plus récentes d'abord)."""
    with connexion(chemin) as cx:
        lignes = cx.execute(
            "SELECT a.*, j.nom AS jeu_nom FROM analyses a LEFT JOIN jeux_donnees j ON j.id = a.jeu_id "
            "WHERE a.projet_id = ? ORDER BY a.date_analyse DESC, a.id DESC", (projet_id,)
        ).fetchall()
    return [{**dict(l), "parametres": json.loads(l["parametres"]) if l["parametres"] else {}} for l in lignes]


# ---------------------------------------------------------------------------
# Réglages
# ---------------------------------------------------------------------------
def lire_parametre(cle: str, chemin: Path | None = None) -> str | None:
    """Valeur d'un réglage enregistré, ou None."""
    with connexion(chemin) as cx:
        ligne = cx.execute("SELECT valeur FROM parametres WHERE cle = ?", (cle,)).fetchone()
    return ligne[0] if ligne else None


def ecrire_parametre(cle: str, valeur: str | None, chemin: Path | None = None) -> None:
    """Enregistre (ou efface si valeur est None) un réglage."""
    with connexion(chemin) as cx:
        if valeur is None:
            cx.execute("DELETE FROM parametres WHERE cle = ?", (cle,))
        else:
            cx.execute(
                "INSERT INTO parametres (cle, valeur) VALUES (?, ?) "
                "ON CONFLICT(cle) DO UPDATE SET valeur = excluded.valeur",
                (cle, valeur),
            )


# ---------------------------------------------------------------------------
# Historique
# ---------------------------------------------------------------------------
def ajouter_historique(
    operation: str,
    details: str = "",
    projet_id: int | None = None,
    jeu_id: int | None = None,
    auteur: str | None = None,
    chemin: Path | None = None,
) -> None:
    """Enregistre une opération dans le journal de traçabilité."""
    with connexion(chemin) as cx:
        cx.execute(
            "INSERT INTO historique (projet_id, jeu_id, date_operation, operation, details, auteur) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (projet_id, jeu_id, maintenant(), operation, details, auteur),
        )


def lister_historique(
    projet_id: int | None = None, limite: int | None = None, chemin: Path | None = None
) -> list[dict]:
    """Opérations enregistrées (les plus récentes d'abord), éventuellement pour un seul projet,
    avec le nom du projet et du jeu de données concernés."""
    requete = (
        "SELECT h.*, p.nom AS projet_nom, j.nom AS jeu_nom FROM historique h "
        "LEFT JOIN projets p ON p.id = h.projet_id "
        "LEFT JOIN jeux_donnees j ON j.id = h.jeu_id"
    )
    params: list = []
    if projet_id is not None:
        requete += " WHERE h.projet_id = ?"
        params.append(projet_id)
    requete += " ORDER BY h.date_operation DESC, h.id DESC"
    if limite:
        requete += " LIMIT ?"
        params.append(limite)
    with connexion(chemin) as cx:
        return [dict(l) for l in cx.execute(requete, params).fetchall()]
