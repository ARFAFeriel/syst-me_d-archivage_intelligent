import asyncio
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.database import AsyncSessionLocal
from backend.models import Document
from sqlalchemy import select, func


async def show():
    async with AsyncSessionLocal() as s:

        # ── Distribution par type + catégorie ─────────────────────────────
        r = await s.execute(
            select(Document.doc_type, Document.category, func.count())
            .group_by(Document.doc_type, Document.category)
            .order_by(Document.doc_type)
        )
        rows = r.all()

        print("\n" + "═"*60)
        print("  DISTRIBUTION PAR TYPE ET CATÉGORIE")
        print("═"*60)
        print(f"  {'TYPE':<28} {'CATÉGORIE':<18} {'DOCS':>5}")
        print("  " + "-"*56)
        total_docs = 0
        for doc_type, cat, count in rows:
            t = str(doc_type).replace("DocumentType.", "")
            c = str(cat or "—")
            print(f"  {t:<28} {c:<18} {count:>5}")
            total_docs += count
        print("  " + "-"*56)
        print(f"  {'TOTAL':<28} {'':18} {total_docs:>5}")

        # ── Confiance OCR et classifier par type ──────────────────────────
        r2 = await s.execute(
            select(
                Document.doc_type,
                func.count().label("total"),
                func.avg(Document.ocr_confidence).label("conf_ocr"),
                func.avg(Document.classifier_confidence).label("conf_classif"),
                func.sum(func.cast(Document.needs_review, func.Integer()
                    if False else func.Integer())).label("needs_review")
            )
            .group_by(Document.doc_type)
            .order_by(func.count().desc())
        )
        rows2 = r2.all()

        print("\n" + "═"*60)
        print("  QUALITÉ PAR TYPE")
        print("═"*60)
        print(f"  {'TYPE':<20} {'TOTAL':>6} {'OCR MOY':>9} {'CLASSIF MOY':>12}")
        print("  " + "-"*54)
        for row in rows2:
            doc_type, total, conf_ocr, conf_classif, _ = row
            t = str(doc_type).replace("DocumentType.", "")
            ocr = conf_ocr or 0
            cl = conf_classif or 0
            ocr_flag = "⚠️ " if ocr < 60 else "✅ "
            cl_flag  = "⚠️ " if cl < 0.5 else "✅ "
            print(f"  {t:<20} {total:>6} {ocr_flag}{ocr:>6.1f}%  {cl_flag}{cl:>8.2f}")
        print("═"*60)

        # ── Docs avec needs_review ────────────────────────────────────────
        r3 = await s.execute(
            select(func.count()).where(Document.needs_review == True)
        )
        needs_review_count = r3.scalar()

        r4 = await s.execute(
            select(func.count()).where(Document.is_critical == True)
        )
        critical_count = r4.scalar()

        r5 = await s.execute(
            select(func.count()).where(Document.manually_corrected == True)
        )
        manual_count = r5.scalar()

        print("\n  FLAGS GLOBAUX")
        print("  " + "-"*30)
        print(f"  ⚠️  needs_review      : {needs_review_count}")
        print(f"  🔴 is_critical        : {critical_count}")
        print(f"  ✏️  manually_corrected : {manual_count}")
        print("═"*60 + "\n")


asyncio.run(show())