"""
Reentrainement du classifier 
Inclut original_path comme feature principale.
"""
import sys
import pickle
import asyncio
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import text
from backend.database import AsyncSessionLocal


async def fetch_training_data():
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("""
            SELECT 
                COALESCE(ocr_text, '') as ocr_text,
                doc_type,
                filename,
                original_path,
                manually_corrected
            FROM documents
            WHERE doc_type IS NOT NULL
              AND doc_type != 'OTHER'
              AND (
                  (ocr_text IS NOT NULL AND LENGTH(ocr_text) > 50)
                  OR original_path IS NOT NULL
              )
        """))
        rows = result.fetchall()
    print(f"Documents recuperes : {len(rows)}")
    return rows


def prepare_text(ocr_text, filename, original_path):
    parts = []
    if ocr_text and len(ocr_text) > 50:
        parts.append(ocr_text[:3000].lower())
    if filename:
        fn = filename.replace("-", " ").replace("_", " ").replace(".", " ").lower()
        parts.append(f"FILENAME {fn} FILENAME {fn}")
    if original_path:
        path_clean = original_path.replace("\\", "/")
        path_parts = path_clean.split("/")
        path_text = " ".join(path_parts).lower()
        parts.append(f"PATH {path_text} PATH {path_text} PATH {path_text}")
    return " ".join(parts)


def train_classifier(rows):
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.svm import LinearSVC
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.model_selection import train_test_split, cross_val_score, StratifiedKFold
    from sklearn.metrics import classification_report
    import numpy as np

    texts, labels = [], []
    n_corrected = 0

    for ocr_text, doc_type, filename, original_path, manually_corrected in rows:
        combined = prepare_text(ocr_text, filename, original_path)
        if not combined.strip():
            continue
        if manually_corrected:
            texts.extend([combined] * 3)
            labels.extend([doc_type] * 3)
            n_corrected += 1
        else:
            texts.append(combined)
            labels.append(doc_type)

    print(f"\n=== Distribution des classes ===")
    counts = Counter(labels)
    for cls, count in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {cls:<20} : {count}")
    print(f"  Documents corriges (boost x3) : {n_corrected}")

    valid = [(t, l) for t, l in zip(texts, labels) if counts[l] >= 3]
    texts  = [x[0] for x in valid]
    labels = [x[1] for x in valid]
    print(f"  Apres filtrage : {len(texts)} documents")

    X_train, X_test, y_train, y_test = train_test_split(
        texts, labels, test_size=0.2, random_state=42, stratify=labels
    )
    print(f"\n=== Entrainement ===")
    print(f"  Train : {len(X_train)} | Test : {len(X_test)}")

    vectorizer = TfidfVectorizer(
        max_features=20000, ngram_range=(1, 3),
        sublinear_tf=True, min_df=1, analyzer="word"
    )
    X_train_vec = vectorizer.fit_transform(X_train)
    X_test_vec  = vectorizer.transform(X_test)

    base_svm = LinearSVC(C=1.0, class_weight="balanced", max_iter=2000)
    model = CalibratedClassifierCV(base_svm, cv=3)
    model.fit(X_train_vec, y_train)

    y_pred = model.predict(X_test_vec)
    accuracy = np.mean(np.array(y_pred) == np.array(y_test))
    print(f"\n=== Resultats ===")
    print(f"  Accuracy : {accuracy:.1%}")
    print(classification_report(y_test, y_pred))

    base_svm_cv = LinearSVC(C=1.0, class_weight="balanced", max_iter=2000)
    X_all = vectorizer.transform(texts)
    cv_scores = cross_val_score(
        base_svm_cv, X_all, labels,
        cv=StratifiedKFold(n_splits=5, shuffle=True, random_state=42),
        scoring="f1_weighted"
    )
    print(f"  CV F1 : {cv_scores.mean():.1%} +/- {cv_scores.std():.1%}")

    return model, vectorizer, cv_scores.mean()


def save_model(model, vectorizer):
    model_path = ROOT / "backend" / "models" / "classifier_model.pkl"
    model_path.parent.mkdir(parents=True, exist_ok=True)

    if model_path.exists():
        import shutil
        backup = model_path.with_suffix('.pkl.backup')
        shutil.copy(model_path, backup)
        print(f"\nBackup : {backup}")

    with open(model_path, 'wb') as f:
        pickle.dump({"model": model, "vectorizer": vectorizer}, f)
    print(f"Nouveau modele sauvegarde : {model_path}")


async def main():
    print("=== Reentrainement du Classifier ===\n")
    rows = await fetch_training_data()
    if len(rows) < 100:
        print("Pas assez de donnees.")
        return
    model, vectorizer, f1 = train_classifier(rows)
    if f1 < 0.70:
        print(f"F1 trop bas ({f1:.1%}) - ancien modele conserve.")
        return
    save_model(model, vectorizer)
    print(f"\nReentrainement termine ! F1 = {f1:.1%}")
    print("Relancez le backend pour utiliser le nouveau modele.")


if __name__ == "__main__":
    asyncio.run(main())
