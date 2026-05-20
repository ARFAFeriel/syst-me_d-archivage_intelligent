"""
Seed Database
Insère des données de test basées sur l'arborescence réelle NouvelAir.
Usage: py scripts/seed_db.py
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime
from loguru import logger


SAMPLE_DOCUMENTS = [
    # ── TS-INP · Check A · ES001778 ────────────────────────────────────────
    {"filename":"RCT.pdf","aircraft":"TS-INP","doc_type":"RCT","category":"Check A",
     "es_ref":"ES001778","ocr_conf":96.4,"classifier_conf":0.94,"ata":None},
    {"filename":"0034.pdf","aircraft":"TS-INP","doc_type":"Jobcard","category":"Check A",
     "es_ref":"ES001778","item":"0034","ocr_conf":93.8,"classifier_conf":0.91,"ata":"ATA 12"},
    {"filename":"0035.pdf","aircraft":"TS-INP","doc_type":"Jobcard","category":"Check A",
     "es_ref":"ES001778","item":"0035","ocr_conf":92.1,"classifier_conf":0.89,"ata":"ATA 21"},
    {"filename":"0036.pdf","aircraft":"TS-INP","doc_type":"Jobcard","category":"Check A",
     "es_ref":"ES001778","item":"0036","ocr_conf":95.0,"classifier_conf":0.92,"ata":"ATA 27"},
    {"filename":"ES00272829.pdf","aircraft":"TS-INP","doc_type":"Work Order","category":"Check A",
     "es_ref":"ES001778","ocr_conf":97.2,"classifier_conf":0.96,"ata":"ATA 05"},
    {"filename":"ES00245294.pdf","aircraft":"TS-INP","doc_type":"Work Order","category":"Check A",
     "es_ref":"ES001778","ocr_conf":93.1,"classifier_conf":0.93,"ata":"ATA 71"},

    # ── TS-INP · Check C · ES001392 ────────────────────────────────────────
    {"filename":"1.pdf","aircraft":"TS-INP","doc_type":"Defect Report","category":"Check C",
     "es_ref":"ES001392","item":"1","ocr_conf":91.1,"classifier_conf":0.88,"ata":"ATA 32"},
    {"filename":"2.pdf","aircraft":"TS-INP","doc_type":"Defect Report","category":"Check C",
     "es_ref":"ES001392","item":"2","ocr_conf":89.4,"classifier_conf":0.86,"ata":"ATA 53"},
    {"filename":"100.pdf","aircraft":"TS-INP","doc_type":"Defect Report","category":"Check C",
     "es_ref":"ES001392","item":"100","ocr_conf":88.3,"classifier_conf":0.85,"ata":"ATA 32"},
    {"filename":"NCR001.pdf","aircraft":"TS-INP","doc_type":"NCR","category":"Check C",
     "es_ref":"ES001392","ocr_conf":94.7,"classifier_conf":0.91,"ata":"ATA 53"},

    # ── TS-INP · ATL ────────────────────────────────────────────────────────
    {"filename":"TL01JAN-30JUN2025.pdf","aircraft":"TS-INP","doc_type":"ATL","category":"ATL",
     "es_ref":None,"ocr_conf":98.2,"classifier_conf":0.97,"ata":None},
    {"filename":"TL01JUL-31DEC2025.pdf","aircraft":"TS-INP","doc_type":"ATL","category":"ATL",
     "es_ref":None,"ocr_conf":98.5,"classifier_conf":0.97,"ata":None},
    {"filename":"TL01JAN-13JAN2026.pdf","aircraft":"TS-INP","doc_type":"ATL","category":"ATL",
     "es_ref":None,"ocr_conf":99.1,"classifier_conf":0.98,"ata":None},

    # ── TS-INP · SB / AD ────────────────────────────────────────────────────
    {"filename":"A320-27-1154.pdf","aircraft":"TS-INP","doc_type":"AD","category":"AD",
     "es_ref":None,"sb_ad":"A320-27-1154","ocr_conf":99.1,"classifier_conf":0.98,"ata":"ATA 27","critical":True},
    {"filename":"A320-57A1146.pdf","aircraft":"TS-INP","doc_type":"SB","category":"SB",
     "es_ref":None,"sb_ad":"A320-57A1146","ocr_conf":97.8,"classifier_conf":0.95,"ata":"ATA 57"},
    {"filename":"A320-32-1592.pdf","aircraft":"TS-INP","doc_type":"SB","category":"SB",
     "es_ref":None,"sb_ad":"A320-32-1592","ocr_conf":98.3,"classifier_conf":0.96,"ata":"ATA 32"},

    # ── TS-INP · Specs ─────────────────────────────────────────────────────
    {"filename":"MSN 2158 Specs.pdf","aircraft":"TS-INP","doc_type":"Specs","category":"Specs",
     "es_ref":None,"ocr_conf":96.4,"classifier_conf":0.93,"ata":None},

    # ── TS-IML ────────────────────────────────────────────────────────────
    {"filename":"ES00281743.pdf","aircraft":"TS-IML","doc_type":"Work Order","category":"Check A",
     "es_ref":"ES001845","ocr_conf":95.3,"classifier_conf":0.91,"ata":"ATA 05"},
    {"filename":"0012.pdf","aircraft":"TS-IML","doc_type":"Jobcard","category":"Check A",
     "es_ref":"ES001845","item":"0012","ocr_conf":92.7,"classifier_conf":0.88,"ata":"ATA 24"},
    {"filename":"TL01JAN-30JUN2025.pdf","aircraft":"TS-IML","doc_type":"ATL","category":"ATL",
     "es_ref":None,"ocr_conf":97.9,"classifier_conf":0.97,"ata":None},

    # ── TS-INQ ────────────────────────────────────────────────────────────
    {"filename":"A320-32-1489.pdf","aircraft":"TS-INQ","doc_type":"SB","category":"SB",
     "es_ref":None,"sb_ad":"A320-32-1489","ocr_conf":98.0,"classifier_conf":0.95,"ata":"ATA 32"},
    {"filename":"NCR-027.pdf","aircraft":"TS-INQ","doc_type":"NCR","category":"Check C",
     "es_ref":"ES001523","ocr_conf":90.2,"classifier_conf":0.87,"ata":"ATA 53"},
]


async def seed():
    from backend.database import init_db, AsyncSessionLocal
    from backend.models.aircraft import Aircraft
    from backend.models.document import Document, DocumentType, DocumentStatus
    from backend.models.check import AircraftCheck, CheckType
    from sqlalchemy import select

    logger.info("Seeding database ...")
    await init_db()

    async with AsyncSessionLocal() as db:
        # Créer avions si inexistants
        fleet = [
            {"registration":"TS-INP","msn":"2158","model":"A320-214","archive_path":r"C:\Aircraft\TS-INP"},
            {"registration":"TS-IML","msn":"2480","model":"A320-214","archive_path":r"C:\Aircraft\TS-IML"},
            {"registration":"TS-INQ","msn":"3012","model":"A320-214","archive_path":r"C:\Aircraft\TS-INQ"},
            {"registration":"TS-INN","msn":"4821","model":"A320-214","archive_path":r"C:\Aircraft\TS-INN"},
        ]
        aircraft_map = {}
        for a in fleet:
            res = await db.execute(select(Aircraft).where(Aircraft.registration == a["registration"]))
            ac = res.scalar_one_or_none()
            if not ac:
                ac = Aircraft(**a, manufacturer="Airbus", airline="NouvelAir")
                db.add(ac)
                await db.flush()
                logger.info(f"  Aéronef créé: {a['registration']}")
            aircraft_map[a["registration"]] = ac.id

        # Créer checks
        checks_data = [
            {"es":"ES001778","type":CheckType.CHECK_A,"aircraft":"TS-INP"},
            {"es":"ES001392","type":CheckType.CHECK_C,"aircraft":"TS-INP"},
            {"es":"ES001019","type":CheckType.CHECK_A,"aircraft":"TS-INN"},
            {"es":"ES001165","type":CheckType.CHECK_C,"aircraft":"TS-INN"},
            {"es":"ES001440","type":CheckType.CHECK_A,"aircraft":"TS-INN"},
            {"es":"ES001845","type":CheckType.CHECK_A,"aircraft":"TS-IML"},
            {"es":"ES001523","type":CheckType.CHECK_C,"aircraft":"TS-INQ"},
        ]
        check_map = {}
        for c in checks_data:
            res = await db.execute(select(AircraftCheck).where(AircraftCheck.es_reference == c["es"]))
            ck = res.scalar_one_or_none()
            if not ck:
                aid = aircraft_map.get(c["aircraft"])
                if aid:
                    ck = AircraftCheck(
                        es_reference=c["es"],
                        check_type=c["type"],
                        aircraft_id=aid,
                        station="NouvelAir MRO — Enfidha"
                    )
                    db.add(ck)
                    await db.flush()
                    logger.info(f"  Check créé: {c['es']} [{c['type']}]")
            if ck:
                check_map[c["es"]] = ck.id

        # Insérer documents de test
        import hashlib, random
        count = 0
        for doc_data in SAMPLE_DOCUMENTS:
            fake_hash = hashlib.sha256(f"{doc_data['filename']}{doc_data['aircraft']}".encode()).hexdigest()
            res = await db.execute(select(Document).where(Document.sha256_hash == fake_hash))
            if res.scalar_one_or_none():
                continue

            try:
                dt = DocumentType(doc_data["doc_type"])
            except ValueError:
                dt = DocumentType.OTHER

            aircraft_id = aircraft_map.get(doc_data["aircraft"])
            es_ref = doc_data.get("es_ref")
            check_id = check_map.get(es_ref) if es_ref else None

            doc = Document(
                sha256_hash=fake_hash,
                filename=doc_data["filename"],
                original_path=rf"C:\Aircraft\{doc_data['aircraft']}\{doc_data['category']}\{doc_data['filename']}",
                file_size_kb=round(random.uniform(50, 2000), 1),
                doc_type=dt,
                category=doc_data.get("category"),
                ata_chapter=doc_data.get("ata"),
                status=DocumentStatus.ARCHIVED,
                aircraft_registration=doc_data["aircraft"],
                aircraft_id=aircraft_id,
                check_id=check_id,
                es_reference=es_ref,
                item_number=doc_data.get("item"),
                sb_ad_reference=doc_data.get("sb_ad"),
                ocr_confidence=doc_data.get("ocr_conf", 95.0),
                ocr_pages=random.randint(1, 8),
                ocr_engine="pdfplumber+tesseract",
                classifier_confidence=doc_data.get("classifier_conf", 0.90),
                is_critical=doc_data.get("critical", False),
                archived_at=datetime.utcnow(),
                ocr_text=f"Document {doc_data['filename']} — {doc_data['aircraft']} — {doc_data.get('category','')} — Référence ES: {es_ref or 'N/A'} — ATA: {doc_data.get('ata','N/A')}",
            )
            db.add(doc)
            count += 1

        await db.commit()
        logger.info(f"Seed terminé: {count} documents insérés")
        logger.info(f"Avions: {len(aircraft_map)}, Checks: {len(check_map)}")


if __name__ == "__main__":
    asyncio.run(seed())
