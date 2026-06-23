"""
import sys
# Bloquer l'import cv2 pour ce script (non nécessaire pour la classification)
sys.modules['cv2'] = type(sys)('cv2')
sys.modules['cv2'].cv2 = None

Script de VALIDATION CROISÉE 5-FOLD — LogisticRegression vs SVM
sur les données réelles de la DB NouvelAir MRO

Complète train_classifier_compare.py (qui utilise un seul split fixe
80/20) par une validation croisée à 5 plis sur l'ensemble du dataset.
Objectif : vérifier que les résultats ne dépendent pas d'un découpage
particulier (random_state=42) et obtenir une mesure de variance
(écart-type) en plus de la moyenne.

Lecture : si l'écart-type entre les 5 folds est élevé (> quelques points),
la performance du modèle dépend beaucoup du découpage — signal de
fragilité, pas forcément d'overfitting au sens classique, mais une
indication que le modèle est sensible à quels documents tombent où.

Ce script est AUTONOME et ne touche à aucun fichier de production.

Usage :
    python scripts/train_classifier_kfold.py

Résultat :
    - scripts/kfold_report.json   (moyenne ± écart-type par modèle, 5 folds)
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

import numpy as np
import asyncpg
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import f1_score, accuracy_score
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

# Seuil plus strict que train_classifier_compare.py : StratifiedKFold à
# 5 plis exige au moins 5 exemples par classe (sinon impossible de
# garantir au moins 1 exemple par fold pour cette classe).
N_FOLDS = 5
MIN_DOCS_PER_CLASS = N_FOLDS + 1  # marge de sécurité


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


def make_svm():
    return CalibratedClassifierCV(LinearSVC(class_weight="balanced"), cv=3)


def make_lr():
    return LogisticRegression(max_iter=1000, C=1.0, solver="lbfgs", class_weight="balanced")


async def main():
    print("=" * 70)
    print(f"  VALIDATION CROISÉE {N_FOLDS}-FOLD — LogisticRegression vs SVM")
    print("  NouvelAir MRO — robustesse au découpage train/test")
    print("=" * 70)

    # ── 1. Charger les données ────────────────────────────────────────────────
    print("\n[1/4] Chargement des données depuis la DB...")
    rows = await fetch_training_data()
    print(f"      → {len(rows)} documents chargés")

    # ── 2. Préparer le dataset ────────────────────────────────────────────────
    print("\n[2/4] Préparation du dataset...")
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
        print(f"\n      ⚠ Classes exclues (< {MIN_DOCS_PER_CLASS} exemples, insuffisant pour {N_FOLDS}-fold) :")
        for cls in sorted(EXCLUDED_CLASSES):
            print(f"          - {cls} : {label_counts[cls]} document(s)")
        training_data = [d for d in training_data if d["label"] not in EXCLUDED_CLASSES]
        print(f"      → {len(training_data)} exemples après exclusion")

    texts  = [d["text"] for d in training_data]
    labels = [LABEL_NORM.get(d["label"], d["label"]) for d in training_data]
    fnames = [d["filename"] for d in training_data]
    paths  = [d["path"] for d in training_data]
    labels_arr = np.array(labels)

    # ── 3. Validation croisée 5-fold stratifiée ──────────────────────────────
    # StratifiedKFold garantit que chaque fold a une proportion représentative
    # de chaque classe (sinon un fold pourrait ne contenir aucun exemple
    # d'une classe rare, faussant l'évaluation).
    print(f"\n[3/4] Validation croisée à {N_FOLDS} plis (stratifiée)...")
    skf = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=42)

    results = {"lr": {"acc": [], "f1_macro": [], "f1_weighted": []},
               "svm": {"acc": [], "f1_macro": [], "f1_weighted": []}}

    for fold_idx, (train_idx, test_idx) in enumerate(skf.split(texts, labels_arr), 1):
        print(f"\n      --- Fold {fold_idx}/{N_FOLDS} ---")
        X_train_txt = [texts[i] for i in train_idx]
        X_test_txt  = [texts[i] for i in test_idx]
        y_train     = [labels[i] for i in train_idx]
        y_test      = [labels[i] for i in test_idx]
        fn_train    = [fnames[i] for i in train_idx]
        fn_test     = [fnames[i] for i in test_idx]
        p_train     = [paths[i]  for i in train_idx]
        p_test      = [paths[i]  for i in test_idx]

        X_train_prepared = [prepare_text(t, f, p) for t, f, p in zip(X_train_txt, fn_train, p_train)]
        X_test_prepared  = [prepare_text(t, f, p) for t, f, p in zip(X_test_txt,  fn_test,  p_test)]

        vectorizer = TfidfVectorizer(max_features=20000, ngram_range=(1, 3), min_df=1, analyzer="word")
        X_train_vec = vectorizer.fit_transform(X_train_prepared)
        X_test_vec  = vectorizer.transform(X_test_prepared)

        # LogisticRegression
        model_lr = make_lr()
        model_lr.fit(X_train_vec, y_train)
        y_pred_lr = model_lr.predict(X_test_vec)
        acc_lr = accuracy_score(y_test, y_pred_lr)
        f1m_lr = f1_score(y_test, y_pred_lr, average="macro", zero_division=0)
        f1w_lr = f1_score(y_test, y_pred_lr, average="weighted", zero_division=0)
        results["lr"]["acc"].append(acc_lr)
        results["lr"]["f1_macro"].append(f1m_lr)
        results["lr"]["f1_weighted"].append(f1w_lr)
        print(f"      LogisticRegression : acc={acc_lr*100:.2f}% f1_macro={f1m_lr*100:.2f}% f1_weighted={f1w_lr*100:.2f}%")

        # SVM
        model_svm = make_svm()
        model_svm.fit(X_train_vec, y_train)
        y_pred_svm = model_svm.predict(X_test_vec)
        acc_svm = accuracy_score(y_test, y_pred_svm)
        f1m_svm = f1_score(y_test, y_pred_svm, average="macro", zero_division=0)
        f1w_svm = f1_score(y_test, y_pred_svm, average="weighted", zero_division=0)
        results["svm"]["acc"].append(acc_svm)
        results["svm"]["f1_macro"].append(f1m_svm)
        results["svm"]["f1_weighted"].append(f1w_svm)
        print(f"      SVM (LinearSVC)    : acc={acc_svm*100:.2f}% f1_macro={f1m_svm*100:.2f}% f1_weighted={f1w_svm*100:.2f}%")

    # ── 4. Synthèse — moyenne ± écart-type sur les 5 folds ───────────────────
    print("\n[4/4] Synthèse...")

    def summarize(values):
        arr = np.array(values) * 100
        return float(arr.mean()), float(arr.std())

    acc_lr_mean, acc_lr_std   = summarize(results["lr"]["acc"])
    f1m_lr_mean, f1m_lr_std   = summarize(results["lr"]["f1_macro"])
    f1w_lr_mean, f1w_lr_std   = summarize(results["lr"]["f1_weighted"])

    acc_svm_mean, acc_svm_std = summarize(results["svm"]["acc"])
    f1m_svm_mean, f1m_svm_std = summarize(results["svm"]["f1_macro"])
    f1w_svm_mean, f1w_svm_std = summarize(results["svm"]["f1_weighted"])

    print("\n" + "=" * 70)
    print(f"  RÉSULTATS — Moyenne ± écart-type sur {N_FOLDS} folds")
    print("=" * 70)
    print(f"  {'Métrique':<16} {'LogisticRegression':>24} {'SVM (LinearSVC)':>24}")
    print(f"  {'-'*16} {'-'*24} {'-'*24}")
    print(f"  {'Accuracy':<16} {acc_lr_mean:>17.2f}% ± {acc_lr_std:>4.2f}pt {acc_svm_mean:>17.2f}% ± {acc_svm_std:>4.2f}pt")
    print(f"  {'F1 macro':<16} {f1m_lr_mean:>17.2f}% ± {f1m_lr_std:>4.2f}pt {f1m_svm_mean:>17.2f}% ± {f1m_svm_std:>4.2f}pt")
    print(f"  {'F1 weighted':<16} {f1w_lr_mean:>17.2f}% ± {f1w_lr_std:>4.2f}pt {f1w_svm_mean:>17.2f}% ± {f1w_svm_std:>4.2f}pt")
    print("=" * 70)
    print("  Repère : un écart-type élevé (> 3-5 points) signale une forte")
    print("  dépendance au découpage — résultat moins fiable/généralisable.")
    print("=" * 70)

    # ── Sauvegarde ─────────────────────────────────────────────────────────
    report_path = Path("scripts/kfold_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({
            "date": datetime.now().isoformat(),
            "n_folds": N_FOLDS,
            "excluded_classes": sorted(EXCLUDED_CLASSES),
            "total_documents": len(training_data),
            "logistic_regression": {
                "accuracy_mean":    round(acc_lr_mean, 2), "accuracy_std":    round(acc_lr_std, 2),
                "f1_macro_mean":    round(f1m_lr_mean, 2), "f1_macro_std":    round(f1m_lr_std, 2),
                "f1_weighted_mean": round(f1w_lr_mean, 2), "f1_weighted_std": round(f1w_lr_std, 2),
                "per_fold_accuracy": [round(v * 100, 2) for v in results["lr"]["acc"]],
            },
            "svm": {
                "accuracy_mean":    round(acc_svm_mean, 2), "accuracy_std":    round(acc_svm_std, 2),
                "f1_macro_mean":    round(f1m_svm_mean, 2), "f1_macro_std":    round(f1m_svm_std, 2),
                "f1_weighted_mean": round(f1w_svm_mean, 2), "f1_weighted_std": round(f1w_svm_std, 2),
                "per_fold_accuracy": [round(v * 100, 2) for v in results["svm"]["acc"]],
            },
        }, f, indent=2, ensure_ascii=False)

    print(f"\n  Rapport sauvegardé → {report_path}")
    print("\n  Aucun fichier de production n'a été modifié par ce script.")


if __name__ == "__main__":
    asyncio.run(main())