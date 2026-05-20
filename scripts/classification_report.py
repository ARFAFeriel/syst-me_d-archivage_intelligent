"""
Rapport de classification — vue complète de tous les documents
Usage: py -m scripts.classification_report
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


async def show():
    from backend.database import AsyncSessionLocal
    from backend.models import Document
    from sqlalchemy import select

    async with AsyncSessionLocal() as s:
        r = await s.execute(
            select(Document)
            .where(Document.ocr_confidence > 0)
            .order_by(Document.aircraft_registration, Document.doc_type, Document.filename)
        )
        docs = r.scalars().all()

    lines = []
    header = f"{'ID':>5} | {'AIRCRAFT':8} | {'TYPE':20} | {'CATEGORIE':15} | {'SOUS-CAT':12} | {'CONF OCR':9} | {'CLASSIF':7} | FICHIER"
    lines.append(header)
    lines.append("-" * 115)

    current_aircraft = None
    for d in docs:
        if d.aircraft_registration != current_aircraft:
            current_aircraft = d.aircraft_registration
            label = current_aircraft if current_aircraft else "SANS AIRCRAFT"
            lines.append(f"\n{'='*10} {label} {'='*10}")

        conf = d.ocr_confidence or 0
        conf_flag = "⚠️ " if conf < 60 else "✅ "
        doc_type = str(d.doc_type).replace("DocumentType.", "")
        category = str(d.category or "-")
        subcategory = str(d.subcategory or "-")

        lines.append(
            f"{d.id:5d} | "
            f"{str(d.aircraft_registration or '-'):8} | "
            f"{doc_type:20} | "
            f"{category:15} | "
            f"{subcategory:12} | "
            f"{conf_flag}{conf:5.1f}% | "
            f"{d.classifier_confidence or 0:6.2f} | "
            f"{d.filename}"
        )

    lines.append(f"\nTotal : {len(docs)} documents")

    # Stats par type
    lines.append("\n" + "=" * 60)
    lines.append("RESUME PAR TYPE")
    lines.append("=" * 60)

    from collections import Counter
    type_counts = Counter(str(d.doc_type).replace("DocumentType.", "") for d in docs)
    for doc_type, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        bar = "█" * min(count, 40)
        lines.append(f"  {doc_type:20s} {count:4d}  {bar}")

    lines.append("\n" + "=" * 60)
    lines.append("RESUME PAR AIRCRAFT")
    lines.append("=" * 60)

    aircraft_counts = Counter(str(d.aircraft_registration or "INCONNU") for d in docs)
    for aircraft, count in sorted(aircraft_counts.items()):
        lines.append(f"  {aircraft:10s}  {count:4d} documents")

    lines.append("\n" + "=" * 60)
    lines.append("DOCUMENTS A VERIFIER (conf < 60%)")
    lines.append("=" * 60)

    low_conf = [d for d in docs if (d.ocr_confidence or 0) < 60]
    lines.append(f"  {len(low_conf)} documents avec confiance OCR < 60%\n")
    for d in low_conf[:20]:
        lines.append(
            f"  [{d.id:4d}] conf={d.ocr_confidence or 0:5.1f}%  "
            f"{str(d.doc_type).replace('DocumentType.',''):15}  "
            f"{d.filename}"
        )
    if len(low_conf) > 20:
        lines.append(f"  ... et {len(low_conf)-20} autres")

    output = "\n".join(lines)
    print(output)

    with open("classification_report.txt", "w", encoding="utf-8") as f:
        f.write(output)
    print("\n-> Rapport sauvegarde dans classification_report.txt")


if __name__ == "__main__":
    asyncio.run(show())