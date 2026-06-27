"""
scripts/diagnose_ner_mismatch.py

Affiche, pour quelques documents, les valeurs BRUTES (sans normalisation)
attendues (ground truth) et prédites par l'agent NER, afin de diagnostiquer
pourquoi la comparaison automatique échoue malgré des extractions a priori
correctes.

Usage :
    py scripts\\diagnose_ner_mismatch.py
"""

import sys
import os
import json
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.agents.ner_agent import NERAgent

LABEL_TO_FIELD = {
    "ATA_CHAPTER": "ata_chapter",
    "DATE_AVIO": "document_date",
    "SERIAL_NUMBER": "serial_number",
    "DOC_REF": "sb_ad_reference",
    "PART_NUMBER": "part_number",
    "AIRCRAFT_REG": "aircraft_registration",
    "ES_REF": "es_reference",
}


async def main():
    gt_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "ner_eval_data.json")
    with open(gt_path, encoding="utf-8") as f:
        dataset = json.load(f)

    dataset = dataset[:3]
    agent = NERAgent()

    for i, doc in enumerate(dataset, 1):
        filename = doc.get("meta", {}).get("filename", f"doc_{i}")
        text = doc["text"]

        print("=" * 70)
        print(f"DOCUMENT {i} : {filename}")
        print("=" * 70)

        print("\n--- VERITE TERRAIN (valeurs brutes extraites des spans) ---")
        for start, end, label in doc["entities"]:
            value = text[start:end]
            print(f"  {label:<15} : {value!r}")

        result = await agent.process(text, filename=filename)

        print("\n--- PREDICTIONS DE L'AGENT (valeurs brutes) ---")
        for label, field in LABEL_TO_FIELD.items():
            value = getattr(result, field, None)
            print(f"  {label:<15} ({field:<22}) : {value!r}")

        print()


if __name__ == "__main__":
    asyncio.run(main())