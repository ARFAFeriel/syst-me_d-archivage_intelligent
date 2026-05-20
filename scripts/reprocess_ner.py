"""
reprocess_ner.py
Retraitement NER ciblé sur les documents avec needs_review = true
(immatriculation non détectée lors de l'import initial)

Usage:
    cd C:\\Users\\ferie\\Desktop\\sys_archivage_intelligent
    venv\\Scripts\\activate
    py backend/reprocess_ner.py
"""

import psycopg2
import re
import json
import sys
from datetime import datetime

# ── CONFIG ──────────────────────────────────────────────────────────────────
DB_CONFIG = {
    "host": "localhost",
    "port": 5434,
    "database": "nouv_db",
    "user": "postgres",
    "password": "Nouv26",
}

# Immatriculations connues de la flotte NouvelAir
KNOWN_REGISTRATIONS = [
    "TS-INC","TS-IND","TS-INE","TS-INF","TS-ING","TS-INH","TS-INI",
    "TS-INJ","TS-INK","TS-INL","TS-INM","TS-INN","TS-INO","TS-INP",
    "TS-INQ","TS-INR","TS-INT","TS-INU",
]

# MSN → immatriculation
MSN_TO_REG = {
    "1597": "TS-INP",
    "6333": "TS-INQ",
    "2158": "TS-INP",   # ancien MSN dans les docs
    "3012": "TS-INQ",   # ancien MSN dans les docs
}

# aircraft_id en DB
REG_TO_ID = {
    "TS-INP": 51,
    "TS-INQ": 53,
}

# ── NER PATTERNS ────────────────────────────────────────────────────────────

def extract_registration(text: str, filename: str) -> str | None:
    """
    Tente d'extraire une immatriculation depuis le texte OCR ou le nom du fichier.
    Retourne la première immatriculation trouvée ou None.
    """
    if not text:
        text = ""

    sources = [text, filename]

    for source in sources:
        # Pattern direct TS-INx
        matches = re.findall(
            r'\bTS[\s\-]?IN[A-Z]\b',
            source,
            re.IGNORECASE
        )
        for m in matches:
            reg = re.sub(r'\s', '', m).upper()
            if not reg.startswith("TS-"):
                reg = "TS-" + reg[2:]
            if reg in KNOWN_REGISTRATIONS:
                return reg

        # Recherche directe de chaque immatriculation connue
        for reg in KNOWN_REGISTRATIONS:
            pattern = reg.replace("-", r"[\s\-]?")
            if re.search(pattern, source, re.IGNORECASE):
                return reg

    return None


def extract_msn(text: str, filename: str) -> str | None:
    """Tente d'extraire un MSN depuis le texte ou le nom de fichier."""
    sources = [text or "", filename]
    for source in sources:
        m = re.search(r'\bMSN[\s:]*([0-9]{3,6})\b', source, re.IGNORECASE)
        if m:
            return m.group(1)
        # Aussi chercher directement les MSN connus
        for msn in MSN_TO_REG:
            if msn in source:
                return msn
    return None


def infer_registration(text: str, filename: str) -> tuple[str | None, str]:
    """
    Essaie d'inférer l'immatriculation par :
    1. Pattern direct dans texte/filename
    2. MSN → immatriculation
    3. Chemin original (si disponible)
    Retourne (registration, méthode)
    """
    # 1. Pattern direct
    reg = extract_registration(text, filename)
    if reg:
        return reg, "NER_direct"

    # 2. Via MSN
    msn = extract_msn(text, filename)
    if msn and msn in MSN_TO_REG:
        return MSN_TO_REG[msn], f"NER_msn_{msn}"

    # 3. Contexte filename
    fn_upper = filename.upper()
    if "INP" in fn_upper or "TS-INP" in fn_upper:
        return "TS-INP", "filename_context"
    if "INQ" in fn_upper or "TS-INQ" in fn_upper:
        return "TS-INQ", "filename_context"

    # 4. MSN dans filename
    for msn, reg in MSN_TO_REG.items():
        if msn in filename:
            return reg, f"filename_msn_{msn}"

    return None, "non_détecté"


# ── MAIN ────────────────────────────────────────────────────────────────────

def main():
    print("=" * 65)
    print("  RETRAITEMENT NER — Documents sans immatriculation")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 65)

    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    # Charger les 179 documents à retraiter
    cur.execute("""
        SELECT id, filename, original_path, ocr_text, aircraft_registration
        FROM documents
        WHERE needs_review = true
        AND validation_warnings::text LIKE '%immatriculation%'
        ORDER BY id
    """)
    docs = cur.fetchall()
    print(f"\n📋 {len(docs)} documents à retraiter\n")

    stats = {"trouve": 0, "non_trouve": 0, "deja_ok": 0}
    resultats = []

    for doc_id, filename, original_path, ocr_text, current_reg in docs:
        # Contexte supplémentaire depuis le chemin original
        path_context = original_path or ""
        full_text = f"{ocr_text or ''} {path_context}"

        reg, methode = infer_registration(full_text, filename)

        if reg:
            aircraft_id = REG_TO_ID.get(reg)
            try:
                cur.execute("""
                    UPDATE documents
                    SET aircraft_registration = %s,
                        aircraft_id = %s,
                        needs_review = false,
                        validation_warnings = '[]',
                        manually_corrected = false,
                        updated_at = NOW()
                    WHERE id = %s
                """, (reg, aircraft_id, doc_id))
                stats["trouve"] += 1
                resultats.append(f"  ✅ [{doc_id:4d}] {filename[:50]:<50} → {reg} ({methode})")
            except Exception as e:
                resultats.append(f"  ❌ [{doc_id:4d}] {filename[:50]:<50} → ERREUR: {e}")
                conn.rollback()
                continue
        else:
            stats["non_trouve"] += 1
            resultats.append(f"  ⚠️  [{doc_id:4d}] {filename[:50]:<50} → non résolu")

    # Afficher résultats
    for r in resultats:
        print(r)

    conn.commit()
    cur.close()
    conn.close()

    print("\n" + "=" * 65)
    print(f"  ✅ Immatriculation trouvée  : {stats['trouve']}")
    print(f"  ⚠️  Non résolus             : {stats['non_trouve']}")
    print("=" * 65)

    # Vérification finale
    print("\n📊 Vérification en base :")
    conn2 = psycopg2.connect(**DB_CONFIG)
    cur2 = conn2.cursor()
    cur2.execute("SELECT COUNT(*) FROM documents WHERE needs_review = true AND validation_warnings::text LIKE '%immatriculation%'")
    remaining = cur2.fetchone()[0]
    cur2.execute("SELECT COUNT(*) FROM documents WHERE aircraft_registration IS NULL")
    null_reg = cur2.fetchone()[0]
    cur2.close()
    conn2.close()

    print(f"  needs_review restants  : {remaining}")
    print(f"  Sans immatriculation   : {null_reg}")
    print("\n✅ Retraitement NER terminé.")


if __name__ == "__main__":
    main()