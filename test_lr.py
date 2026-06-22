import asyncio, sys
from sklearn.linear_model import LogisticRegression
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, f1_score, classification_report
from sqlalchemy import text
from backend.database import AsyncSessionLocal

sys.path.insert(0, '.')

async def get_data():
    async with AsyncSessionLocal() as session:
        result = await session.execute(text('''
            SELECT COALESCE(ocr_text,'') as ocr_text, doc_type, filename, original_path
            FROM documents
            WHERE doc_type IS NOT NULL AND doc_type NOT IN ('OTHER','AMM','IPC')
            AND ((ocr_text IS NOT NULL AND LENGTH(ocr_text) > 50) OR original_path IS NOT NULL)
        '''))
        return result.fetchall()

def prepare_text(ocr_text, filename, original_path):
    parts = []
    if ocr_text and len(ocr_text) > 50:
        parts.append(ocr_text[:3000].lower())
    if filename:
        fn = filename.replace('-',' ').replace('_',' ').replace('.',' ').lower()
        parts.append('FILENAME ' + fn + ' FILENAME ' + fn)
    if original_path:
        path_clean = original_path.replace(chr(92),'/')
        path_text = ' '.join(path_clean.split('/')).lower()
        parts.append('PATH ' + path_text + ' PATH ' + path_text + ' PATH ' + path_text)
    return ' '.join(parts)

async def main():
    rows = await get_data()
    texts, labels = [], []
    for ocr_text, doc_type, filename, original_path in rows:
        t = prepare_text(ocr_text, filename, original_path)
        if t.strip():
            texts.append(t)
            labels.append(doc_type)

    X_train, X_test, y_train, y_test = train_test_split(
        texts, labels, test_size=0.2, random_state=42, stratify=labels
    )

    vec = TfidfVectorizer(max_features=20000, ngram_range=(1,3), sublinear_tf=True)
    X_train_vec = vec.fit_transform(X_train)
    X_test_vec  = vec.transform(X_test)

    lr = LogisticRegression(class_weight='balanced', max_iter=1000, random_state=42)
    lr.fit(X_train_vec, y_train)
    y_pred = lr.predict(X_test_vec)

    print('=== TF-IDF + LR ===')
    print('Accuracy   :', round(accuracy_score(y_test, y_pred)*100, 1))
    print('F1-Macro   :', round(f1_score(y_test, y_pred, average='macro', zero_division=0)*100, 1))
    print('F1-Weighted:', round(f1_score(y_test, y_pred, average='weighted', zero_division=0)*100, 1))
    print(classification_report(y_test, y_pred, zero_division=0))

asyncio.run(main())
