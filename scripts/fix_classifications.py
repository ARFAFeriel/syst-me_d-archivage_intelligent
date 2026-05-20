"""
Correction des classifications erronées
Usage: py -m scripts.fix_classifications
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


async def fix():
    from backend.database import AsyncSessionLocal
    from backend.models import Document
    from backend.models.document import DocumentType
    from sqlalchemy import select, update

    async with AsyncSessionLocal() as db:

        # ── Fix 1 : TS-INC → TS-INP (immatriculation mal extraite) ──────────
        r = await db.execute(
            select(Document.id, Document.filename, Document.original_path)
            .where(Document.aircraft_registration == "TS-INC")
        )
        tsinc_docs = r.all()
        print(f"\n[Fix 1] TS-INC → TS-INP : {len(tsinc_docs)} doc(s)")
        for id, filename, path in tsinc_docs:
            # Vérifier que le chemin contient TS-INP
            if "TS-INP" in (path or "").upper():
                await db.execute(
                    update(Document)
                    .where(Document.id == id)
                    .values(aircraft_registration="TS-INP", manually_corrected=True)
                )
                print(f"  ✅ [{id}] {filename} → TS-INP")
            else:
                print(f"  ⚠️  [{id}] {filename} — chemin ambigu, skip")

        # ── Fix 2 : TS-OFM → TS-INQ (doc dans dossier TS-INQ) ───────────────
        r = await db.execute(
            select(Document.id, Document.filename, Document.original_path)
            .where(Document.aircraft_registration == "TS-OFM")
        )
        tsofm_docs = r.all()
        print(f"\n[Fix 2] TS-OFM → TS-INQ : {len(tsofm_docs)} doc(s)")
        for id, filename, path in tsofm_docs:
            if "TS-INQ" in (path or "").upper():
                await db.execute(
                    update(Document)
                    .where(Document.id == id)
                    .values(aircraft_registration="TS-INQ", manually_corrected=True)
                )
                print(f"  ✅ [{id}] {filename} → TS-INQ")

        # ── Fix 3 : Faux ADs → CERTIFICATE ───────────────────────────────────
        cert_keywords = [
            "EASA F1", "EASA Form", "FAA Form", "FAA 8130", "8130-3",
            "Form One", "Form 1", "EASA0001", "EASA ECB",
            "Acceptance Certificate", "Release Certificate",
            "BTB Complete", "BTB Compleete",
            "Air Arabia-1", "Air Arabia-2",
        ]
        cert_ids = []
        r = await db.execute(
            select(Document.id, Document.filename)
            .where(Document.doc_type == "AD")
            .where(Document.classifier_confidence < 0.36)
        )
        false_ads = r.all()

        for id, filename in false_ads:
            fn_upper = filename.upper()
            if any(kw.upper() in fn_upper for kw in cert_keywords):
                cert_ids.append(id)

        print(f"\n[Fix 3] Faux ADs → CERTIFICATE : {len(cert_ids)} doc(s)")
        if cert_ids:
            await db.execute(
                update(Document)
                .where(Document.id.in_(cert_ids))
                .values(
                    doc_type=DocumentType.CERTIFICATE,
                    category="Certificates",
                    manually_corrected=True,
                )
            )
            for id, filename in false_ads:
                if id in cert_ids:
                    print(f"  ✅ [{id}] {filename}")

        # ── Fix 4 : Faux ADs → SPECS ─────────────────────────────────────────
        specs_keywords = [
            "Oil consumption", "Flight Summary", "General Overview",
            "Weight Report", "Weight And Balance", "AFM", "LLP Status",
            "LLP Sheet", "Installation and Removal", "Non-Operation Statement",
            "Trend report", "Engine Change", "Totals-Statement",
            "LOPA", "Start.pdf", "ReadMe", "MSN 2158 General",
            "MSN 2158 Flight", "ELA_A320", "ETOPS", "CDSS",
        ]
        specs_ids = []
        for id, filename in false_ads:
            if id in cert_ids:
                continue
            fn_upper = filename.upper()
            if any(kw.upper() in fn_upper for kw in specs_keywords):
                specs_ids.append(id)

        print(f"\n[Fix 4] Faux ADs → SPECS : {len(specs_ids)} doc(s)")
        if specs_ids:
            await db.execute(
                update(Document)
                .where(Document.id.in_(specs_ids))
                .values(
                    doc_type=DocumentType.SPECS,
                    category="Specs",
                    manually_corrected=True,
                )
            )
            for id, filename in false_ads:
                if id in specs_ids:
                    print(f"  ✅ [{id}] {filename}")

        # ── Fix 5 : Faux ADs restants → OTHER ────────────────────────────────
        fixed_ids = set(cert_ids) | set(specs_ids)
        other_ids = [id for id, _ in false_ads if id not in fixed_ids]

        # Afficher les restants pour décision manuelle
        print(f"\n[Fix 5] ADs restants non reclassifiés : {len(other_ids)} doc(s)")
        print("  → Ces docs nécessitent une vérification manuelle :")
        for id, filename in false_ads:
            if id in other_ids:
                print(f"  ❓ [{id}] {filename}")

        # ── Commit ────────────────────────────────────────────────────────────
        await db.commit()

        total_fixed = len(tsinc_docs) + len(tsofm_docs) + len(cert_ids) + len(specs_ids)
        print(f"\n{'='*50}")
        print(f"  TOTAL CORRIGÉ : {total_fixed} documents")
        print(f"  À VÉRIFIER    : {len(other_ids)} documents")
        print(f"{'='*50}")


if __name__ == "__main__":
    asyncio.run(fix())