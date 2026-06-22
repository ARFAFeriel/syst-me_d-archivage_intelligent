import asyncio, sys
sys.path.insert(0, ".")
async def run():
    from backend.database import engine
    from sqlalchemy import text
    async with engine.begin() as conn:
        r = await conn.execute(text("""
            SELECT id, filename, aircraft_registration, es_reference,
                   part_number, serial_number, ata_chapter, doc_type,
                   ocr_text, ocr_confidence
            FROM documents
            WHERE ocr_text IS NOT NULL
              AND LENGTH(ocr_text) > 200
              AND aircraft_registration IS NOT NULL
            ORDER BY ocr_confidence DESC
            LIMIT 3
        """))
        rows = r.fetchall()
        for row in rows:
            print("=====")
            print("FILE:", row[1])
            print("REG:", row[2])
            print("ES_REF:", row[3])
            print("P/N:", row[4])
            print("S/N:", row[5])
            print("ATA:", row[6])
            print("TYPE:", row[7])
            print("OCR_CONF:", row[9])
            print("OCR_TEXT[:500]:", (row[8] or "")[:500])
            print()
asyncio.run(run())
