# scripts/check_ner.py
import asyncio
from backend.database import AsyncSessionLocal
from backend.models import Document
from sqlalchemy import select
import json, re

VALIDATION_RULES = {
    "ata_chapter":       r"\d{2}(-\d{2,4})?",
    "serial_number":     r"[A-Z0-9\-]{3,20}",
    "es_reference":      r"(ES\d{6,8}|\d{6,8})",
    "document_date":     r"\d{4}-\d{2}-\d{2}",
    "effectivity":       r"(TS-[A-Z]{3}|\d{3,6}|[A-Z0-9,\s-]{3,30})",
    "part_number":       r"[A-Z0-9\-]{4,20}",
    "sb_ad_reference": r"(\d{2}-\d{2,5}-\d{2,6}|(?:SB|AD)[-\s]?\w+)",
    "work_order_number": r"[A-Z0-9\-]{3,20}",
}

async def check_ner(filename_filter: str = None, limit: int = 20):
    async with AsyncSessionLocal() as session:
        query = select(Document).where(Document.ocr_confidence > 0)
        if filename_filter:
            query = query.where(Document.filename.contains(filename_filter))
        query = query.limit(limit)

        result = await session.execute(query)
        docs = result.scalars().all()

        print(f"\n{'='*70}")
        print(f"  {len(docs)} document(s) analysé(s)")
        print(f"{'='*70}\n")

        ok_total, ko_total = 0, 0

        for doc in docs:
            print(f"📄 {doc.filename} | OCR conf={doc.ocr_confidence:.1f}% | status={doc.status}")
            print(f"   aircraft={doc.aircraft_registration} | type={doc.doc_type} | ATA={doc.ata_chapter}")

            # Champs NER directs
            fields = {
                "serial_number":     doc.serial_number,
                "part_number":       doc.part_number,
                "es_reference":      doc.es_reference,
                "document_date":     str(doc.document_date) if doc.document_date else None,
                "effectivity":       doc.effectivity,
                "sb_ad_reference":   doc.sb_ad_reference,
                "work_order_number": doc.work_order_number,
                "ata_chapter":       doc.ata_chapter,
            }

            doc_ok, doc_ko = 0, 0
            for field, value in fields.items():
                if not value:
                    print(f"   ⬜ {field:20s} → (vide)")
                    continue
                pattern = VALIDATION_RULES.get(field)
                valid = bool(re.fullmatch(pattern, str(value).strip())) if pattern else True
                status = "✅" if valid else "❌"
                print(f"   {status} {field:20s} → {value}")
                if valid: doc_ok += 1
                else: doc_ko += 1

            # JSON extracted_entities si présent
            if doc.extracted_entities:
                entities = doc.extracted_entities
                if isinstance(entities, str):
                    try: entities = json.loads(entities)
                    except: entities = {}
                print(f"   📦 extracted_entities: {list(entities.keys()) if isinstance(entities, dict) else entities}")

            # Flag needs_review
            if doc.needs_review:
                print(f"   ⚠️  needs_review=True")

            print(f"   → {doc_ok} valides | {doc_ko} suspects\n")
            ok_total += doc_ok
            ko_total += doc_ko

        print(f"{'='*70}")
        print(f"  TOTAL : {ok_total} valides | {ko_total} suspects")
        print(f"{'='*70}\n")

asyncio.run(check_ner("244"))