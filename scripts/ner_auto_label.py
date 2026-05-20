"""
ner_auto_label.py
=================
Génère automatiquement un dataset NER annoté au format spaCy
à partir du corpus NouvelAir existant en base PostgreSQL.

PRINCIPE (Weak Supervision) :
  Les regex déjà validées servent d'annotateurs automatiques.
  On extrait le texte OCR de chaque document et on localise
  les entités avec leurs positions caractère-à-caractère.

ENTITÉS COUVERTES :
  AIRCRAFT_REG  → TS-INP, TS-INQ, TS-IML, TS-INN
  ES_REF        → ES001778, ES001392, ES154313...
  ATA_CHAPTER   → 32-40, 27-00-00, ATA 32...
  PART_NUMBER   → P/N 123456, PN-7890A...
  SERIAL_NUMBER → S/N ABC123, MSN 2158...
  DOC_REF       → AD 2023-12-04, SB 737-28-1234...
  DATE_AVIO     → 01 JAN 2023, 2023-01-15...

OUTPUT :
  data/ner_training_data.json   → dataset d'entraînement (80%)
  data/ner_eval_data.json       → dataset d'évaluation (20%)
  data/ner_stats.json           → statistiques du corpus

USAGE :
  py ner_auto_label.py
  py ner_auto_label.py --limit 500    # sur 500 docs seulement (test rapide)
  py ner_auto_label.py --min-entities 2  # docs avec au moins 2 entités
"""

import re
import json
import random
import argparse
import os
import sys
from pathlib import Path
from datetime import datetime

# ─── Configuration ────────────────────────────────────────────────────────────
DB_URL = "postgresql://postgres:Nouv26@localhost:5434/nouv_db"  # adapte si besoin
OUTPUT_DIR = Path("data")
RANDOM_SEED = 42

# ─── Patterns NER (cohérents avec ner_agent_v6) ───────────────────────────────
PATTERNS = {
    "AIRCRAFT_REG": [
        r'\b(TS-[A-Z]{3})\b',
    ],
    "ES_REF": [
        r'\b(ES\d{6})\b',
        r'\b(ES\s?\d{6})\b',
    ],
    "ATA_CHAPTER": [
        r'\bATA\s*(\d{2}[-–]\d{2}(?:[-–]\d{2})?)\b',
        r'\b(\d{2}[-–]\d{2}[-–]\d{2})\b',
        r'\bATA\s*(\d{2})\b',
    ],
    "PART_NUMBER": [
        r'\bP/?N[:\s#]?\s*([A-Z0-9][-A-Z0-9]{3,20})\b',
        r'\bPart\s+No\.?\s*:?\s*([A-Z0-9][-A-Z0-9]{3,20})\b',
        r'\bPN[:\s]([A-Z0-9][-A-Z0-9]{3,20})\b',
    ],
    "SERIAL_NUMBER": [
        r'\bS/?N[:\s#]?\s*([A-Z0-9][-A-Z0-9]{3,20})\b',
        r'\bMSN\s*:?\s*(\d{3,6})\b',
        r'\bSerial\s+No\.?\s*:?\s*([A-Z0-9]{4,20})\b',
    ],
    "DOC_REF": [
        r'\b(AD\s+\d{4}[-–]\d{2}[-–]\d{2,4})\b',
        r'\b(SB\s+[\w][-\w]{3,25})\b',
        r'\b(AMM\s+\d{2}[-–]\d{2}[-–]\d{2,4})\b',
        r'\b(CMM\s+[\w][-\w]{3,20})\b',
    ],
    "DATE_AVIO": [
        r'\b(\d{1,2}\s+(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC|'
        r'JANV?|FÉVR?|MARS|AVR|JUIN|JUIL|AOÛT|SEPT?|OCT|NOV|DÉC)\s+\d{4})\b',
        r'\b(\d{4}[-/]\d{2}[-/]\d{2})\b',
        r'\b(\d{2}[-/]\d{2}[-/]\d{4})\b',
    ],
    "AIRLINE": [
        r'\b(NouvelAir|Nouvelair|NOUVELAIR)\b',
        r'\b(Tunisair|TunisAir|TUNISAIR)\b',
    ],
}

# ─── Helpers ──────────────────────────────────────────────────────────────────

def compile_patterns():
    """Compile tous les patterns en dict {label: [compiled_regex]}."""
    compiled = {}
    for label, pats in PATTERNS.items():
        compiled[label] = [re.compile(p, re.IGNORECASE | re.UNICODE) for p in pats]
    return compiled


def extract_entities(text: str, compiled_pats: dict) -> list[tuple[int,int,str]]:
    """
    Retourne une liste de (start, end, label) sans chevauchement.
    En cas de conflit, la première entité trouvée gagne.
    """
    found = []
    occupied = set()  # positions déjà couvertes

    for label, regexes in compiled_pats.items():
        for rx in regexes:
            for m in rx.finditer(text):
                # Utiliser le groupe 1 si disponible (valeur extraite)
                start = m.start(1) if m.lastindex else m.start()
                end   = m.end(1)   if m.lastindex else m.end()
                span  = set(range(start, end))
                if span & occupied:
                    continue  # chevauchement → ignorer
                found.append((start, end, label))
                occupied |= span

    return sorted(found, key=lambda x: x[0])


def fetch_documents(limit: int | None = None) -> list[dict]:
    """Récupère les documents depuis PostgreSQL."""
    try:
        import psycopg2
    except ImportError:
        print("❌ psycopg2 non installé. Lance : pip install psycopg2-binary")
        sys.exit(1)

    conn = psycopg2.connect(DB_URL)
    cur  = conn.cursor()

    query = """
        SELECT id, filename, ocr_text, doc_type, category, aircraft_registration
        FROM documents
        WHERE ocr_text IS NOT NULL
          AND length(ocr_text) > 100
        ORDER BY id
    """
    if limit:
        query += f" LIMIT {limit}"

    cur.execute(query)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    docs = []
    for row in rows:
        docs.append({
            "id":          row[0],
            "filename":    row[1],
            "text":        row[2],
            "doc_type":    row[3],
            "category":    row[4],
            "aircraft":    row[5],
        })
    return docs


def text_to_spacy_example(text: str, entities: list, doc_meta: dict) -> dict | None:
    """
    Convertit en format spaCy DocBin :
    {"text": "...", "entities": [(start, end, label), ...], "meta": {...}}

    Vérifie la cohérence des offsets caractère par caractère.
    """
    # Limiter le texte à 1000 tokens (~5000 chars) pour éviter la troncature spaCy
    MAX_CHARS = 4800
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS]
        entities = [(s, e, l) for s, e, l in entities if e <= MAX_CHARS]

    # Vérifier que les entités correspondent au texte
    valid_entities = []
    for start, end, label in entities:
        span_text = text[start:end]
        if len(span_text.strip()) > 0:
            valid_entities.append((start, end, label))

    if not valid_entities:
        return None

    return {
        "text":     text,
        "entities": valid_entities,
        "meta":     doc_meta,
    }


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Auto-labeling NER pour NouvelAir")
    parser.add_argument("--limit",        type=int, default=None, help="Nombre max de docs")
    parser.add_argument("--min-entities", type=int, default=1,    help="Min entités par doc")
    parser.add_argument("--split",        type=float, default=0.8, help="Train/eval split")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(exist_ok=True)
    random.seed(RANDOM_SEED)

    print("🔍 Chargement des documents depuis PostgreSQL...")
    docs = fetch_documents(limit=args.limit)
    print(f"   {len(docs)} documents chargés")

    compiled_pats = compile_patterns()

    print("🏷️  Annotation automatique en cours...")
    examples = []
    stats = {label: 0 for label in PATTERNS}
    stats["docs_annotated"] = 0
    stats["docs_skipped"]   = 0

    for doc in docs:
        text     = doc["text"]
        entities = extract_entities(text, compiled_pats)

        # Filtrer par nombre minimum d'entités
        if len(entities) < args.min_entities:
            stats["docs_skipped"] += 1
            continue

        meta = {
            "doc_id":   doc["id"],
            "filename": doc["filename"],
            "doc_type": doc["doc_type"],
            "category": doc["category"],
            "aircraft": doc["aircraft"],
        }

        ex = text_to_spacy_example(text, entities, meta)
        if ex:
            examples.append(ex)
            stats["docs_annotated"] += 1
            for _, _, label in ex["entities"]:
                stats[label] = stats.get(label, 0) + 1

    print(f"\n📊 Résultats annotation :")
    print(f"   Documents annotés : {stats['docs_annotated']}")
    print(f"   Documents ignorés : {stats['docs_skipped']}")
    print(f"\n   Entités par type :")
    for label in PATTERNS:
        count = stats.get(label, 0)
        bar = "█" * min(40, count // 10)
        print(f"   {label:20s} {count:5d}  {bar}")

    # Shuffle et split
    random.shuffle(examples)
    split_idx  = int(len(examples) * args.split)
    train_data = examples[:split_idx]
    eval_data  = examples[split_idx:]

    # Sauvegarde JSON
    train_path = OUTPUT_DIR / "ner_training_data.json"
    eval_path  = OUTPUT_DIR / "ner_eval_data.json"
    stats_path = OUTPUT_DIR / "ner_stats.json"

    with open(train_path, "w", encoding="utf-8") as f:
        json.dump(train_data, f, ensure_ascii=False, indent=2)
    with open(eval_path, "w", encoding="utf-8") as f:
        json.dump(eval_data, f, ensure_ascii=False, indent=2)

    stats["total_examples"] = len(examples)
    stats["train_examples"] = len(train_data)
    stats["eval_examples"]  = len(eval_data)
    stats["generated_at"]   = datetime.now().isoformat()
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Dataset généré :")
    print(f"   Train : {len(train_data)} exemples → {train_path}")
    print(f"   Eval  : {len(eval_data)} exemples  → {eval_path}")
    print(f"   Stats : {stats_path}")
    print(f"\n👉 Prochaine étape : py ner_fine_tune_spacy.py")


if __name__ == "__main__":
    main()