"""
scripts/manual_ner_annotation.py

Outil interactif pour construire une vraie vérité terrain NER,
annotée à la main, sans passer par les regex ni le LLM.

Pour chaque document tiré au hasard du corpus, affiche le texte
(OCR ou natif) et demande, pour chacune des 7 entités, la valeur
réellement présente dans le texte (laisser vide si absente).

Les annotations sont sauvegardées au fur et à mesure dans
data/ner_manual_ground_truth.json, donc tu peux interrompre
la session à tout moment (Ctrl+C) et reprendre plus tard :
le script ignore automatiquement les documents déjà annotés.

Usage :
    py scripts\\manual_ner_annotation.py --n 30
"""

import sys
import os
import json
import argparse
import random

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
import psycopg2.extras

DB_CONFIG = dict(host="localhost", port=5434, dbname="nouv_db", user="postgres", password="Nouv26")
OUTPUT_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "ner_manual_ground_truth.json")

ENTITIES = [
    ("AIRCRAFT_REG", "Immatriculation avion (ex: TS-INP)"),
    ("ATA_CHAPTER", "Chapitre ATA (ex: 32-40 ou ATA 32)"),
    ("DATE_AVIO", "Date d'intervention (ex: 01/06/2023)"),
    ("DOC_REF", "Référence AD/SB/CMM (ex: SB 34-1412)"),
    ("ES_REF", "Référence Work Order ES (ex: ES001392)"),
    ("PART_NUMBER", "Numéro de pièce P/N (ex: EAD2020-0280)"),
    ("SERIAL_NUMBER", "Numéro de série S/N ou MSN (ex: 1597)"),
]


def load_existing():
    if os.path.exists(OUTPUT_PATH):
        with open(OUTPUT_PATH, encoding="utf-8") as f:
            return json.load(f)
    return []


def save(data):
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def fetch_candidates(n: int, exclude_ids: set):
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT id, filename, ocr_text
        FROM documents
        WHERE ocr_text IS NOT NULL AND LENGTH(ocr_text) > 50
        ORDER BY RANDOM()
        LIMIT %s
    """, (n * 3,))  # marge pour compenser les exclusions
    rows = [dict(r) for r in cur.fetchall() if r["id"] not in exclude_ids]
    conn.close()
    return rows[:n]


def main():
    parser = argparse.ArgumentParser(description="Annotation manuelle de vérité terrain NER")
    parser.add_argument("--n", type=int, default=30, help="Nombre de documents à annoter")
    args = parser.parse_args()

    annotated = load_existing()
    done_ids = {a["doc_id"] for a in annotated}

    print(f"[Info] {len(annotated)} documents déjà annotés dans {OUTPUT_PATH}")
    remaining = args.n - len(annotated)
    if remaining <= 0:
        print(f"[OK] Objectif de {args.n} documents déjà atteint.")
        return

    print(f"[Info] {remaining} documents restants à annoter.\n")
    candidates = fetch_candidates(remaining, done_ids)

    for i, doc in enumerate(candidates, 1):
        print("\n" + "=" * 70)
        print(f"DOCUMENT {len(annotated) + 1}/{args.n}  (fichier : {doc['filename']})")
        print("=" * 70)
        print(doc["ocr_text"][:1500])
        print("-" * 70)
        print("Pour chaque entité, tape la valeur trouvée dans le texte ci-dessus,")
        print("ou appuie sur Entrée si elle est absente.\n")

        entry = {"doc_id": doc["id"], "filename": doc["filename"], "entities": {}}

        try:
            for label, hint in ENTITIES:
                value = input(f"  {label:<15} ({hint}) : ").strip()
                if value:
                    entry["entities"][label] = value
        except KeyboardInterrupt:
            print("\n\n[Interrompu] Sauvegarde de la progression effectuée jusqu'ici.")
            save(annotated)
            return

        annotated.append(entry)
        save(annotated)
        print(f"  [Sauvegardé] {len(annotated)}/{args.n} documents annotés.")

    print(f"\n[OK] Annotation terminée : {len(annotated)} documents dans {OUTPUT_PATH}")


if __name__ == "__main__":
    main()