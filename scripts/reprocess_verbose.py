import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from loguru import logger
from pathlib import Path
from backend.agents.ocr_agent import OCRAgent
from backend.agents.ner_agent import NERAgent

# Active tous les logs DEBUG
logger.remove()
logger.add(sys.stdout, level="DEBUG", 
           format="<green>{time:HH:mm:ss}</green> | <level>{level}</level> | {message}")

async def demo():
    ocr = OCRAgent()
    ner = NERAgent()

    # Prends un vrai jobcard de ta base
    path = r"\\?\C:\Users\ferie\Desktop\stage nvl\AviationArchive\Aircraft\TS-INP\Check C\ES001392\JobCard\698.pdf"
    
    print("\n" + "="*60)
    print("ETAPE 1 : OCR v5")
    print("="*60)
    ocr_result = await ocr.process(path)
    print(f"\n  Moteur utilisé  : {ocr_result.engine}")
    print(f"  Confiance       : {ocr_result.confidence:.1f}%")
    print(f"  Caractères      : {len(ocr_result.text)}")
    print(f"  needs_review    : {ocr_result.needs_review}")
    print(f"\n  Texte extrait :\n{'-'*40}")
    print(ocr_result.text[:500])

    print("\n" + "="*60)
    print("ETAPE 2 : NER")
    print("="*60)
    ner_result = await ner.process(ocr_result.text, "698.pdf")
    print(f"\n  Immatriculation : {ner_result.aircraft_registration}")
    print(f"  ATA chapter     : {ner_result.ata_chapter}")
    print(f"  ES reference    : {ner_result.es_reference}")
    print(f"  Part Number     : {ner_result.part_number}")
    print(f"  Serial Number   : {ner_result.serial_number}")
    print(f"  Work Order      : {ner_result.work_order_number}")
    print(f"\n  Toutes entités brutes :")
    import json
    print(json.dumps(ner_result.raw_entities, indent=4, ensure_ascii=False))

asyncio.run(demo())