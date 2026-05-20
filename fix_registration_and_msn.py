"""
fix_registration_and_msn.py
───────────────────────────
1. Réassigne les 1246 documents TS-INO → TS-INQ (erreur NER OCR O/Q)
2. Auto-détecte le MSN depuis ocr_text et extracted_entities
   puis propage vers la table aircraft
"""

import re
import json
import psycopg2
from loguru import logger

# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

import sys
sys.path.insert(0, r"C:\Users\ferie\Desktop\système_darchivage_intelligent")
from backend.config import settings

DB_CONFIG = {
    "host":     settings.db_host,
    "port":     settings.db_port,
    "dbname":   settings.db_name,
    "user":     settings.db_user,
    "password": settings.db_password,
}
# Patterns MSN dans le texte OCR (4 chiffres typiquement pour A320)
MSN_PATTERNS = [
    re.compile(r"(?:MSN|S/N|SERIAL\s*NO?\.?|MANUFACTURER\s*SERIAL)[\s:.\-]+(\d{3,5})", re.I),
    re.compile(r"\bMSN[\s:]*(\d{3,5})\b", re.I),
    re.compile(r"\b(2158|3012)\b"),   # MSN connus TS-INP / TS-INQ
]

# MSN connus — vérification croisée
KNOWN_MSN = {
    "TS-INP": "2158",
    "TS-INQ": "3012",
}

# ══════════════════════════════════════════════════════════════════════════════
# CONNEXION
# ══════════════════════════════════════════════════════════════════════════════

def get_conn():
    return psycopg2.connect(**DB_CONFIG)

# ══════════════════════════════════════════════════════════════════════════════
# ÉTAPE 1 : FIXER TS-INO → TS-INQ
# ══════════════════════════════════════════════════════════════════════════════

def fix_tsino_registration(conn):
    logger.info("═══ ÉTAPE 1 : Réassignation TS-INO → TS-INQ ═══")

    with conn.cursor() as cur:
        # Compter
        cur.execute("SELECT COUNT(*) FROM documents WHERE aircraft_registration = 'TS-INO'")
        count = cur.fetchone()[0]
        logger.info(f"Documents TS-INO trouvés : {count}")

        if count == 0:
            logger.info("Rien à corriger.")
            return

        # Récupérer aircraft_id de TS-INQ
        cur.execute("SELECT id FROM aircraft WHERE registration = 'TS-INQ'")
        row = cur.fetchone()
        if not row:
            logger.error("TS-INQ introuvable dans la table aircraft !")
            return
        tsing_id = row[0]

        # Mise à jour
        cur.execute("""
            UPDATE documents
            SET aircraft_registration = 'TS-INQ',
                aircraft_id           = %s,
                updated_at            = NOW()
            WHERE aircraft_registration = 'TS-INO'
        """, (tsing_id,))

        updated = cur.rowcount
        conn.commit()
        logger.success(f"✅ {updated} documents réassignés TS-INO → TS-INQ")

    # Supprimer l'avion fantôme TS-INO si plus de documents
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM documents WHERE aircraft_registration = 'TS-INO'")
        remaining = cur.fetchone()[0]
        if remaining == 0:
            cur.execute("DELETE FROM aircraft WHERE registration = 'TS-INO'")
            deleted = cur.rowcount
            conn.commit()
            if deleted:
                logger.success("✅ Avion fantôme TS-INO supprimé de la table aircraft")

# ══════════════════════════════════════════════════════════════════════════════
# ÉTAPE 2 : AUTO-DÉTECTION MSN
# ══════════════════════════════════════════════════════════════════════════════

def extract_msn_from_text(text: str) -> str | None:
    """Extrait le MSN depuis le texte OCR."""
    if not text:
        return None
    for pattern in MSN_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1)
    return None

def extract_msn_from_entities(entities_json) -> str | None:
    """Extrait le MSN depuis extracted_entities JSON."""
    if not entities_json:
        return None
    try:
        if isinstance(entities_json, str):
            entities = json.loads(entities_json)
        else:
            entities = entities_json
        # Chercher dans les clés communes
        for key in ["msn", "serial_number", "manufacturer_serial"]:
            val = entities.get(key)
            if val and re.match(r"^\d{3,5}$", str(val).strip()):
                return str(val).strip()
    except Exception:
        pass
    return None

def auto_detect_msn(conn):
    logger.info("═══ ÉTAPE 2 : Auto-détection MSN ═══")

    with conn.cursor() as cur:
        # Charger tous les avions sans MSN
        cur.execute("SELECT id, registration FROM aircraft WHERE msn IS NULL OR msn = ''")
        aircraft_without_msn = cur.fetchall()

    if not aircraft_without_msn:
        logger.info("Tous les avions ont déjà un MSN.")
        return

    logger.info(f"Avions sans MSN : {[r[1] for r in aircraft_without_msn]}")

    for aircraft_id, registration in aircraft_without_msn:
        logger.info(f"  Recherche MSN pour {registration}...")

        msn_candidates = {}

        with conn.cursor() as cur:
            # Scanner ocr_text + extracted_entities de tous les docs de cet avion
            cur.execute("""
                SELECT id, filename, ocr_text, extracted_entities
                FROM documents
                WHERE aircraft_registration = %s
                  AND (ocr_text IS NOT NULL OR extracted_entities IS NOT NULL)
                LIMIT 500
            """, (registration,))
            docs = cur.fetchall()

        for doc_id, filename, ocr_text, extracted_entities in docs:
            msn = None

            # Priorité 1 : extracted_entities
            msn = extract_msn_from_entities(extracted_entities)

            # Priorité 2 : ocr_text
            if not msn:
                msn = extract_msn_from_text(ocr_text)

            if msn:
                msn_candidates[msn] = msn_candidates.get(msn, 0) + 1

        if not msn_candidates:
            logger.warning(f"  Aucun MSN détecté pour {registration}")
            continue

        # Prendre le MSN le plus fréquent
        best_msn = max(msn_candidates, key=msn_candidates.get)
        best_count = msn_candidates[best_msn]

        logger.info(f"  Candidats MSN : {msn_candidates}")
        logger.info(f"  → MSN retenu : {best_msn} (trouvé {best_count} fois)")

        # Vérification croisée avec les MSN connus
        if registration in KNOWN_MSN and KNOWN_MSN[registration] != best_msn:
            logger.warning(
                f"  ⚠️  MSN détecté ({best_msn}) différent du MSN connu "
                f"({KNOWN_MSN[registration]}) pour {registration} — skip"
            )
            continue

        # Mise à jour
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE aircraft SET msn = %s WHERE id = %s",
                (best_msn, aircraft_id)
            )
            conn.commit()
        logger.success(f"  ✅ MSN {best_msn} enregistré pour {registration}")

# ══════════════════════════════════════════════════════════════════════════════
# ÉTAPE 3 : RAPPORT FINAL
# ══════════════════════════════════════════════════════════════════════════════

def rapport_final(conn):
    logger.info("═══ RAPPORT FINAL ═══")

    with conn.cursor() as cur:
        cur.execute("""
            SELECT a.registration, a.msn, COUNT(d.id) as docs
            FROM aircraft a
            LEFT JOIN documents d ON d.aircraft_registration = a.registration
            GROUP BY a.registration, a.msn
            ORDER BY a.registration
        """)
        rows = cur.fetchall()

    logger.info(f"{'Registration':<15} {'MSN':<10} {'Documents'}")
    logger.info("-" * 40)
    for reg, msn, docs in rows:
        msn_str = msn if msn else "MANQUANT"
        logger.info(f"{reg:<15} {msn_str:<10} {docs}")

# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    logger.info("Démarrage fix_registration_and_msn.py")

    conn = get_conn()
    try:
        fix_tsino_registration(conn)
        auto_detect_msn(conn)
        rapport_final(conn)
    finally:
        conn.close()

    logger.info("Terminé.")