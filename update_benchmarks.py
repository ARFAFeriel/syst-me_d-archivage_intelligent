import asyncio, sys
sys.path.insert(0, '.')
from sqlalchemy import text
from backend.database import AsyncSessionLocal

async def main():
    async with AsyncSessionLocal() as session:

        # TF-IDF + SVM : accuracy 95.2->95.9, f1_macro 95.2->87.0
        await session.execute(text('''
            UPDATE model_benchmarks
            SET accuracy = 95.9,
                f1_macro = 87.0,
                notes = 'Modele en production NouvelAir - Classifier 11 classes - CV F1=95.2% +/- 0.6%'
            WHERE id = 1
        '''))

        # DistilBERT : f1_macro 77.9->48.81, notes corrigees
        await session.execute(text('''
            UPDATE model_benchmarks
            SET accuracy = 78.77,
                f1_macro = 48.81,
                notes = 'distilbert-base-multilingual-cased - 3 epochs - dataset 2683 docs - 4 classes a zero (AMM ATL CMM IPC)'
            WHERE id = 2
        '''))

        # TF-IDF + LR : accuracy 88.1->94.4, f1_macro 64.5->87.1
        await session.execute(text('''
            UPDATE model_benchmarks
            SET accuracy = 94.4,
                f1_macro = 87.1,
                notes = 'Version precedente - remplacee par TF-IDF + SVM'
            WHERE id = 5
        '''))

        # Groq LLM : pas un classifieur sklearn - on retire les faux scores
        await session.execute(text('''
            UPDATE model_benchmarks
            SET accuracy = NULL,
                f1_macro = NULL,
                notes = 'Agent NER v6 - extraction immatriculations via Groq API - non evalue comme classifieur'
            WHERE id = 4
        '''))

        await session.commit()
        print('Mis a jour !')

        # Verification
        result = await session.execute(text('SELECT id, model_name, accuracy, f1_macro, notes FROM model_benchmarks ORDER BY id'))
        for r in result.fetchall():
            print(r)

asyncio.run(main())
