# reclassify_other.py
"""
Reclassifie les documents OTHER avec le nouveau modèle ML.
"""
import sys
import pickle
import asyncio
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import text
from backend.database import AsyncSessionLocal

async def reclassify_other():
    # Charger le modèle
    model_path = ROOT / "backend" / "models" / "classifier_model.pkl"
    with open(model_path, 'rb') as f:
        model = pickle.load(f)
    print(f"✅ Modèle chargé")

    async with AsyncSessionLocal() as session:
        # Récupérer les OTHER avec texte OCR
        result = await session.execute(text("""
            SELECT id, ocr_text, filename
            FROM documents
            WHERE doc_type = 'OTHER'
              AND ocr_text IS NOT NULL
              AND LENGTH(ocr_text) > 50
        """))
        rows = result.fetchall()
        print(f"✅ {len(rows)} documents OTHER à reclassifier")

        updated = 0
        kept    = 0

        for doc_id, ocr_text, filename in rows:
            # Prédire
            pred   = model.predict([ocr_text])[0]
            proba  = model.predict_proba([ocr_text])[0]
            conf   = float(max(proba))

            # Ne mettre à jour que si confiance > 70%
            if conf >= 0.70 and pred != 'OTHER':
                await session.execute(text("""
                    UPDATE documents
                    SET doc_type = :doc_type,
                        classifier_confidence = :conf
                    WHERE id = :id
                """), {
                    "doc_type": pred,
                    "conf"    : conf,
                    "id"      : doc_id
                })
                updated += 1
                if updated % 50 == 0:
                    print(f"  [{updated}/{len(rows)}] "
                          f"{filename} → {pred} ({conf:.0%})")
            else:
                kept += 1

        await session.commit()

    print(f"\n=== Résultat ===")
    print(f"  Reclassifiés : {updated}")
    print(f"  Gardés OTHER : {kept}")

if __name__ == "__main__":
    asyncio.run(reclassify_other())