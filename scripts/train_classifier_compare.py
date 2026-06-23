"""
import sys
# Bloquer l'import cv2 pour ce script (non nécessaire pour la classification)
sys.modules['cv2'] = type(sys)('cv2')
sys.modules['cv2'].cv2 = None

Script de COMPARAISON RIGOUREUSE — LogisticRegression vs SVM
sur les données réelles de la DB NouvelAir MRO

Contrairement à une comparaison entre deux runs séparés (training_report.json
vs training_report_svm.json), ce script garantit une comparaison équitable :
  - mêmes données chargées une seule fois
  - même filtre d'exclusion des classes rares
  - même split train/test (random_state=42 identique)
  - même vectorizer TF-IDF (donc mêmes features pour les deux modèles)
  - seule variable qui change : l'algorithme (LogisticRegression vs LinearSVC calibré)

Ce script est AUTONOME et ne touche à aucun fichier de production.

Usage :
    python scripts/train_classifier_compare.py

Résultat :
    - scripts/comparison_report.json   (métriques des deux modèles, côte à côte)
    - Tableau comparatif affiché en console
"""
import sys
import os
import json
import asyncio
from pathlib import Path
from datetime import datetime
from collections import Counter

sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncpg
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, f1_score, accuracy_score
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.svm import LinearSVC
from sklearn.calibration import CalibratedClassifierCV

# ── Config DB ─────────────────────────────────────────────────────────────────
DB_PASSWORD = input("Mot de passe PostgreSQL : ")
DB_CONFIG = {
    "host":     "localhost",
    "port":     5434,
    "database": "nouv_db",
    "user":     "postgres",
    "password": DB_PASSWORD,
}

DOC_TYPE_MAP = {
    "WORK_ORDER":    "WORK_ORDER",
    "JOBCARD":       "JOBCARD",
    "DEFECT_REPORT": "DEFECT_REPORT",
    "NCR":           "NCR",
    "AD":            "AD",
    "SB":            "SB",
    "ATL":           "ATL",
    "AMM":           "AMM",
    "CMM":           "CMM",
    "IPC":           "IPC",
    "SPECS":         "SPECS",
    "CERTIFICATE":   "CERTIFICATE",
    "RCT":           "RCT",
}

LABEL_NORM = {
    "WORK_ORDER": "Work Order", "JOBCARD": "Jobcard",
    "DEFECT_REPORT": "Defect Report", "CERTIFICATE": "Certificate",
    "SPECS": "Specs", "AD": "AD", "SB": "SB", "ATL": "ATL",
    "AMM": "AMM", "CMM": "CMM", "IPC": "IPC", "NCR": "NCR", "RCT": "RCT",
}

MIN_DOCS_PER_CLASS = 6  # cf. justification dans train_classifier_svm.py


async def fetch_training_data():
    conn = await asyncpg.connect(**DB_CONFIG)
    rows = await conn.fetch("""
        SELECT id, filename, original_path, ocr_text, doc_type
        FROM documents
        WHERE doc_type IS NOT NULL
          AND ocr_text IS NOT NULL
          AND ocr_text != ''
          AND doc_type IN (
            'WORK_ORDER','JOBCARD','DEFECT_REPORT','NCR',
            'AD','SB','ATL','AMM','CMM','IPC','SPECS','CERTIFICATE','RCT'
          )
        ORDER BY id
    """)
    await conn.close()
    return rows


def prepare_text(text: str, filename: str, file_path: str) -> str:
    """Identique à ClassifierAgent._prepare_text() (classifier_agent.py)."""
    parts = []
    if text:
        parts.append(text[:3000].lower())
    if filename:
        fn = filename.replace("-", " ").replace("_", " ").replace(".", " ").lower()
        parts.append(f"FILENAME {fn}")
    if file_path:
        path_parts = file_path.replace("\\", "/").split("/")
        parts.append(f"PATH {' '.join(path_parts).lower()}")
    return " ".join(parts)


def evaluate(y_test, y_pred):
    accuracy    = accuracy_score(y_test, y_pred)
    f1_macro    = f1_score(y_test, y_pred, average="macro",    zero_division=0)
    f1_weighted = f1_score(y_test, y_pred, average="weighted", zero_division=0)
    report_dict = classification_report(y_test, y_pred, zero_division=0, output_dict=True)
    return accuracy, f1_macro, f1_weighted, report_dict


async def main():
    print("=" * 70)
    print("  COMPARAISON RIGOUREUSE — LogisticRegression vs SVM (LinearSVC)")
    print("  Même données, même split, même vectorizer TF-IDF")
    print("=" * 70)

    # ── 1. Charger les données ────────────────────────────────────────────────
    print("\n[1/6] Chargement des données depuis la DB...")
    rows = await fetch_training_data()
    print(f"      → {len(rows)} documents chargés")

    # ── 2. Préparer le dataset ────────────────────────────────────────────────
    print("\n[2/6] Préparation du dataset...")
    training_data = []
    label_counts = {}
    for row in rows:
        doc_type = row["doc_type"]
        if doc_type not in DOC_TYPE_MAP:
            continue
        training_data.append({
            "text":     row["ocr_text"],
            "label":    DOC_TYPE_MAP[doc_type],
            "filename": row["filename"] or "",
            "path":     row["original_path"] or "",
        })
        label_counts[doc_type] = label_counts.get(doc_type, 0) + 1

    print(f"      → {len(training_data)} exemples valides")
    print("\n      Distribution par classe :")
    for cls, cnt in sorted(label_counts.items(), key=lambda x: -x[1]):
        bar = "█" * (cnt // 20)
        print(f"      {cls:<20} {cnt:>4}  {bar}")

    EXCLUDED_CLASSES = {cls for cls, cnt in label_counts.items() if cnt < MIN_DOCS_PER_CLASS}
    if EXCLUDED_CLASSES:
        print(f"\n      ⚠ Classes exclues (< {MIN_DOCS_PER_CLASS} exemples, insuffisant pour cv=3 fiable) :")
        for cls in sorted(EXCLUDED_CLASSES):
            print(f"          - {cls} : {label_counts[cls]} document(s)")
        training_data = [d for d in training_data if d["label"] not in EXCLUDED_CLASSES]
        print(f"      → {len(training_data)} exemples après exclusion")

    # ── 3. Split train/test — UNIQUE, partagé par les deux modèles ──────────
    print("\n[3/6] Split train/test (80/20, random_state=42 — identique pour les deux modèles)...")
    texts  = [d["text"]     for d in training_data]
    labels = [LABEL_NORM.get(d["label"], d["label"]) for d in training_data]
    fnames = [d["filename"] for d in training_data]
    paths  = [d["path"]     for d in training_data]

    (X_train_txt, X_test_txt,
     y_train,     y_test,
     fn_train,    fn_test,
     p_train,     p_test) = train_test_split(
        texts, labels, fnames, paths,
        test_size=0.2,
        random_state=42,
    )
    print(f"      → Train : {len(X_train_txt)} | Test : {len(X_test_txt)}")

    train_counts = Counter(y_train)
    min_class_count = min(train_counts.values())
    if min_class_count < 3:
        smallest = min(train_counts, key=train_counts.get)
        raise RuntimeError(
            f"Classe '{smallest}' n'a que {min_class_count} exemple(s) au train — "
            f"augmente MIN_DOCS_PER_CLASS et relance."
        )

    # ── 4. Vectorisation TF-IDF — UNE SEULE FOIS, partagée par les deux modèles
    print("\n[4/6] Vectorisation TF-IDF (config identique à ClassifierAgent)...")
    X_train_prepared = [prepare_text(t, f, p) for t, f, p in zip(X_train_txt, fn_train, p_train)]
    X_test_prepared  = [prepare_text(t, f, p) for t, f, p in zip(X_test_txt,  fn_test,  p_test)]

    vectorizer = TfidfVectorizer(
        max_features=20000,
        ngram_range=(1, 3),
        min_df=1,
        analyzer="word",
    )
    X_train_vec = vectorizer.fit_transform(X_train_prepared)
    X_test_vec  = vectorizer.transform(X_test_prepared)
    print(f"      → {X_train_vec.shape[1]} features TF-IDF")

    # ── 5. Entraînement des DEUX modèles sur les MÊMES données ──────────────
    print("\n[5/6] Entraînement des deux modèles...")

    print("      → LogisticRegression (max_iter=1000, C=1.0, class_weight=balanced)...")
    model_lr = LogisticRegression(
        max_iter=1000, C=1.0, solver="lbfgs", class_weight="balanced"
    )
    model_lr.fit(X_train_vec, y_train)
    y_pred_lr_test  = model_lr.predict(X_test_vec)
    y_pred_lr_train = model_lr.predict(X_train_vec)

    print("      → CalibratedClassifierCV(LinearSVC, cv=3)...")
    model_svm = CalibratedClassifierCV(
        LinearSVC(class_weight="balanced"), cv=3
    )
    model_svm.fit(X_train_vec, y_train)
    y_pred_svm_test  = model_svm.predict(X_test_vec)
    y_pred_svm_train = model_svm.predict(X_train_vec)

    # ── 6. Évaluation comparative — TEST (généralisation) ───────────────────
    print("\n[6/6] Évaluation comparative...")
    acc_lr, f1m_lr, f1w_lr, report_lr = evaluate(y_test, y_pred_lr_test)
    acc_svm, f1m_svm, f1w_svm, report_svm = evaluate(y_test, y_pred_svm_test)

    # ── Évaluation sur TRAIN — pour diagnostiquer l'overfitting ─────────────
    # Si train >> test (écart > ~10-15 points), le modèle mémorise les
    # données d'entraînement au lieu de généraliser. Un écart faible
    # (quelques points) est normal et attendu, pas un signe d'overfitting.
    acc_lr_train, f1m_lr_train, f1w_lr_train, _  = evaluate(y_train, y_pred_lr_train)
    acc_svm_train, f1m_svm_train, f1w_svm_train, _ = evaluate(y_train, y_pred_svm_train)

    print("\n" + "=" * 70)
    print("  DIAGNOSTIC OVERFITTING — Train vs Test")
    print("=" * 70)
    print(f"  {'Modèle':<20} {'Accuracy train':>16} {'Accuracy test':>16} {'Écart':>10}")
    print(f"  {'-'*20} {'-'*16} {'-'*16} {'-'*10}")
    ecart_lr  = (acc_lr_train - acc_lr) * 100
    ecart_svm = (acc_svm_train - acc_svm) * 100
    print(f"  {'LogisticRegression':<20} {acc_lr_train*100:>15.2f}% {acc_lr*100:>15.2f}% {ecart_lr:>9.1f}pt")
    print(f"  {'SVM (LinearSVC)':<20} {acc_svm_train*100:>15.2f}% {acc_svm*100:>15.2f}% {ecart_svm:>9.1f}pt")
    print("=" * 70)
    print("  Repère : un écart train-test > 10-15 points suggère un surapprentissage.")
    print("  Un écart faible (quelques points) est normal et attendu.")
    print("=" * 70)

    print("\n" + "=" * 70)
    print("  RÉSULTATS GLOBAUX (même split, même TF-IDF, même données)")
    print("=" * 70)
    print(f"  {'Métrique':<20} {'LogisticRegression':>20} {'SVM (LinearSVC)':>20}")
    print(f"  {'-'*20} {'-'*20} {'-'*20}")
    print(f"  {'Accuracy':<20} {acc_lr*100:>19.2f}% {acc_svm*100:>19.2f}%")
    print(f"  {'F1 macro':<20} {f1m_lr*100:>19.2f}% {f1m_svm*100:>19.2f}%")
    print(f"  {'F1 weighted':<20} {f1w_lr*100:>19.2f}% {f1w_svm*100:>19.2f}%")
    print("=" * 70)

    print("\n  DÉTAIL PAR CLASSE (F1-score) :")
    print(f"  {'Classe':<16} {'Support':>8} {'LR F1':>10} {'SVM F1':>10} {'Écart':>10}")
    print(f"  {'-'*16} {'-'*8} {'-'*10} {'-'*10} {'-'*10}")
    all_classes = sorted(set(report_lr.keys()) & set(report_svm.keys()) - {"accuracy", "macro avg", "weighted avg"})
    for cls in all_classes:
        support = report_lr[cls]["support"]
        f1_lr_cls  = report_lr[cls]["f1-score"] * 100
        f1_svm_cls = report_svm[cls]["f1-score"] * 100
        ecart = f1_svm_cls - f1_lr_cls
        signe = "+" if ecart >= 0 else ""
        print(f"  {cls:<16} {support:>8.0f} {f1_lr_cls:>9.1f}% {f1_svm_cls:>9.1f}% {signe}{ecart:>8.1f}pt")

    # ── Sauvegarde rapport unique ─────────────────────────────────────────────
    report_path = Path("scripts/comparison_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({
            "date":        datetime.now().isoformat(),
            "note":        "Comparaison sur split et données strictement identiques (random_state=42)",
            "excluded_classes": sorted(EXCLUDED_CLASSES),
            "train_size":  len(X_train_txt),
            "test_size":   len(X_test_txt),
            "logistic_regression": {
                "accuracy":          round(acc_lr * 100, 2),
                "f1_macro":          round(f1m_lr * 100, 2),
                "f1_weighted":       round(f1w_lr * 100, 2),
                "accuracy_train":    round(acc_lr_train * 100, 2),
                "f1_macro_train":    round(f1m_lr_train * 100, 2),
                "f1_weighted_train": round(f1w_lr_train * 100, 2),
                "overfitting_gap_accuracy_pt": round(ecart_lr, 2),
                "per_class": {
                    cls: {
                        "precision": round(m["precision"] * 100, 1),
                        "recall":    round(m["recall"] * 100, 1),
                        "f1":        round(m["f1-score"] * 100, 1),
                        "support":   m["support"],
                    }
                    for cls, m in report_lr.items()
                    if cls not in ("accuracy", "macro avg", "weighted avg") and isinstance(m, dict)
                },
            },
            "svm": {
                "accuracy":          round(acc_svm * 100, 2),
                "f1_macro":          round(f1m_svm * 100, 2),
                "f1_weighted":       round(f1w_svm * 100, 2),
                "accuracy_train":    round(acc_svm_train * 100, 2),
                "f1_macro_train":    round(f1m_svm_train * 100, 2),
                "f1_weighted_train": round(f1w_svm_train * 100, 2),
                "overfitting_gap_accuracy_pt": round(ecart_svm, 2),
                "per_class": {
                    cls: {
                        "precision": round(m["precision"] * 100, 1),
                        "recall":    round(m["recall"] * 100, 1),
                        "f1":        round(m["f1-score"] * 100, 1),
                        "support":   m["support"],
                    }
                    for cls, m in report_svm.items()
                    if cls not in ("accuracy", "macro avg", "weighted avg") and isinstance(m, dict)
                },
            },
        }, f, indent=2, ensure_ascii=False)

    print(f"\n  Rapport comparatif sauvegardé → {report_path}")
    print("\n  Aucun fichier de production n'a été modifié par ce script.")


if __name__ == "__main__":
    asyncio.run(main())