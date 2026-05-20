# scripts/fix_engine_docs.py
import asyncio
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

async def fix():
    from backend.database import AsyncSessionLocal
    from backend.models import Document
    from backend.models.document import DocumentType
    from sqlalchemy import select, update

    async with AsyncSessionLocal() as db:
        # Vérifier ce qu'on va changer
        r = await db.execute(
            select(Document.id, Document.filename, Document.doc_type, Document.category)
            .where(Document.filename.like("0%.%.pdf"))
            .order_by(Document.filename)
        )
        docs = r.all()
        print(f"\n{len(docs)} documents moteur trouvés :\n")
        for d in docs:
            print(f"  [{d.id:4d}] {d.filename:30s} type={d.doc_type} cat={d.category}")

        confirm = input("\nReclassifier tous en SPECS / Engine File ? (o/n) : ")
        if confirm.lower() != "o":
            print("Annulé.")
            return

        await db.execute(
            update(Document)
            .where(Document.filename.like("0%.%.pdf"))
            .values(
                doc_type=DocumentType.SPECS,
                category="Engine File",
                subcategory="DQ10406",
                manually_corrected=True,
            )
        )
        await db.commit()
        print(f"\n✅ {len(docs)} documents reclassifiés → SPECS / Engine File")

asyncio.run(fix())