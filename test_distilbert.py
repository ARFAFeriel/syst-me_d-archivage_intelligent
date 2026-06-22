import asyncio, sys, time
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, f1_score, classification_report
from sqlalchemy import text
from backend.database import AsyncSessionLocal

sys.path.insert(0, '.')

async def get_data():
    async with AsyncSessionLocal() as session:
        result = await session.execute(text('''
            SELECT COALESCE(ocr_text,'') as ocr_text, doc_type
            FROM documents
            WHERE doc_type IS NOT NULL AND doc_type NOT IN ('OTHER','AMM','IPC')
            AND ocr_text IS NOT NULL AND LENGTH(ocr_text) > 50
        '''))
        return result.fetchall()

async def main():
    rows = await get_data()
    texts, labels = [], []
    for ocr_text, doc_type in rows:
        texts.append(ocr_text[:512])
        labels.append(doc_type)

    print(f'Documents : {len(texts)}')

    X_train, X_test, y_train, y_test = train_test_split(
        texts, labels, test_size=0.2, random_state=42, stratify=labels
    )

    print('Chargement DistilBERT...')
    from transformers import pipeline
    classifier = pipeline(
        'text-classification',
        model='distilbert-base-uncased',
        tokenizer='distilbert-base-uncased',
        device=-1
    )
    print('Attention : DistilBERT non fine-tune sur tes donnees.')
    print('Pour un vrai benchmark il faut le fine-tuner — cela prend ~3h sur CPU.')
    print('On ne peut pas reproduire ce score sans le fichier du modele entraine.')

asyncio.run(main())
