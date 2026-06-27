"""
scripts/confusion_and_kfold.py

Génère deux livrables pour le rapport, en réutilisant exactement la même
configuration que train_classifier_kfold.py (TF-IDF max_features=20000,
ngram (1,3), CalibratedClassifierCV(LinearSVC(class_weight="balanced"), cv=3)) :

  1. La matrice de confusion complète du classificateur TF-IDF+SVM,
     sur un split holdout 80/20 (même logique que training_report_svm.json).
  2. Le détail du 5-fold cross-validation, pli par pli (pas seulement
     la moyenne ± écart-type déjà connue), avec sauvegarde de la matrice
     de confusion agrégée sur l'ensemble des plis de test.

Sorties :
    scripts/confusion_matrix_report.json
    scripts/kfold_detailed_report.json

Usage :
    py scripts\\confusion_and_kfold.py
"""

import sys
import os
import json
import asyncio
from datetime import datetime

import numpy as np
import asyncpg
import matplotlib
matplotlib.use("Agg")  # backend sans interface graphique, pour génération de fichier uniquement
import matplotlib.pyplot as plt
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.svm import LinearSVC
from sklearn.calibration import CalibratedClassifierCV
from sklearn.model_selection import train_test_split, StratifiedKFold
from sklearn.metrics import confusion_matrix, classification_report, accuracy_score, f1_score

DB_CONFIG = {
    "host": "localhost",
    "port": 5434,
    "database": "nouv_db",
    "user": "postgres",
    "password": "Nouv26",
}

N_FOLDS = 5
RANDOM_STATE = 42

# Aucune classe exclue : toutes les 13 classes documentaires sont incluses,
# y compris celles à très faible effectif (AMM, IPC, RCT).
EXCLUDED_CLASSES = set()


async def fetch_training_data():
    conn = await asyncpg.connect(**DB_CONFIG)
    rows = await conn.fetch("""
        SELECT id, filename, original_path, ocr_text, doc_type
        FROM documents
        WHERE doc_type IS NOT NULL
          AND ocr_text IS NOT NULL
          AND LENGTH(ocr_text) > 20
    """)
    await conn.close()
    return rows


def prepare_text(text: str, filename: str, file_path: str) -> str:
    """Identique à ClassifierAgent._prepare_text() (classifier_agent.py)."""
    parts = []
    if text:
        parts.append(text[:3000].lower())
    if filename:
        parts.append(filename.lower())
    if file_path:
        parts.append(file_path.lower())
    return " ".join(parts)


def make_svm(y_train=None):
    """
    CalibratedClassifierCV effectue une validation croisée interne (cv=3
    par défaut) pour calibrer les probabilités. Avec des classes très rares
    dans l'ensemble d'entraînement (RCT, parfois moins de 3 documents),
    ce cv interne doit être réduit en conséquence, sous peine d'échec.
    """
    cv = 3
    if y_train is not None:
        from collections import Counter
        counts = Counter(y_train)
        min_count = min(counts.values())
        cv = max(2, min(3, min_count))
        if min_count < 2:
            # Une seule occurrence dans le train : la calibration par
            # validation croisée est impossible pour cette classe.
            # On utilise un LinearSVC non calibré (pas de scores de probabilité),
            # ce qui reste suffisant pour produire des prédictions de classe.
            return LinearSVC(class_weight="balanced")
    return CalibratedClassifierCV(LinearSVC(class_weight="balanced"), cv=cv)


def plot_confusion_matrix_dual(cm, classes, accuracy, out_path, min_reliable_support=5):
    """
    Génère une figure à deux panels :
    (a) effectifs absolus (bleu)
    (b) taux de classification en % par classe réelle (jaune-rouge)

    Les classes dont le support de test est inférieur à min_reliable_support
    sont grisées dans le panel (b) plutôt que coloriées sur l'échelle 0-100%,
    car un pourcentage calculé sur 0 ou 1 document n'est pas statistiquement
    interprétable au même titre qu'un pourcentage calculé sur des dizaines
    ou centaines de documents.
    """
    n = len(classes)
    row_totals = cm.sum(axis=1)

    # Division sécurisée : pas d'avertissement, résultat à 0 pour les lignes vides
    with np.errstate(invalid="ignore", divide="ignore"):
        cm_pct = np.where(
            row_totals[:, None] > 0,
            cm.astype(float) / np.maximum(row_totals[:, None], 1) * 100,
            0.0,
        )

    reliable_mask = row_totals >= min_reliable_support

    fig, axes = plt.subplots(2, 1, figsize=(max(10, n * 1.0), max(14, n * 1.6)))
    fig.suptitle(
        f"Matrice de confusion — Classificateur TF-IDF + SVM\n(Jeu de test, accuracy = {accuracy:.1f} %)",
        fontsize=15, fontweight="bold", y=0.98,
    )

    # ── Panel (a) : effectifs absolus ──────────────────────────────
    ax = axes[0]
    im = ax.imshow(cm, cmap="Blues")
    ax.set_title("(a) Effectifs absolus", fontsize=13, fontweight="bold", pad=10)
    ax.set_xticks(np.arange(n))
    ax.set_yticks(np.arange(n))
    ax.set_xticklabels(classes, rotation=45, ha="right", fontsize=9)
    ax.set_yticklabels(
        [c if reliable_mask[i] else f"{c}*" for i, c in enumerate(classes)],
        fontsize=9,
    )
    ax.set_xlabel("Classe prédite", fontsize=11)
    ax.set_ylabel("Classe réelle", fontsize=11)
    threshold = cm.max() / 2.0
    for i in range(n):
        for j in range(n):
            value = cm[i, j]
            color = "white" if value > threshold else "black"
            weight = "bold" if i == j else "normal"
            ax.text(j, i, f"{value}", ha="center", va="center", color=color, fontsize=8, fontweight=weight)
    fig.colorbar(im, ax=ax, fraction=0.04, pad=0.02)

    # ── Panel (b) : taux de classification (%) par classe réelle ──
    ax = axes[1]
    # Masque les lignes peu fiables (effectif insuffisant) avec un gris uniforme,
    # plutôt que de les coloriser sur l'échelle 0-100% comme les classes fiables.
    cm_pct_display = np.ma.masked_array(cm_pct, mask=~reliable_mask[:, None] * np.ones((1, n), dtype=bool))
    cmap_b = plt.get_cmap("YlOrRd").copy()
    cmap_b.set_bad(color="#d9d9d9")
    im2 = ax.imshow(cm_pct_display, cmap=cmap_b, vmin=0, vmax=100)
    ax.set_title(
        "(b) Taux de classification (% par classe réelle)\n"
        f"Classes grisées (*) : effectif de test < {min_reliable_support} documents, non interprétable",
        fontsize=12, fontweight="bold", pad=10,
    )
    ax.set_xticks(np.arange(n))
    ax.set_yticks(np.arange(n))
    ax.set_xticklabels(classes, rotation=45, ha="right", fontsize=9)
    ax.set_yticklabels(
        [c if reliable_mask[i] else f"{c}*" for i, c in enumerate(classes)],
        fontsize=9,
    )
    ax.set_xlabel("Classe prédite", fontsize=11)
    ax.set_ylabel("Classe réelle", fontsize=11)
    for i in range(n):
        for j in range(n):
            value = cm_pct[i, j]
            if not reliable_mask[i]:
                ax.text(j, i, f"{value:.0f}%", ha="center", va="center", color="dimgray", fontsize=7, style="italic")
                continue
            color = "white" if value > 50 else "black"
            weight = "bold" if i == j else "normal"
            ax.text(j, i, f"{value:.1f}%", ha="center", va="center", color=color, fontsize=8, fontweight=weight)
    fig.colorbar(im2, ax=ax, fraction=0.04, pad=0.02)

    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"      Graphique sauvegardé : {out_path}")
    print(f"      Classes non fiables (support < {min_reliable_support}, marquées *) : "
          f"{[c for i, c in enumerate(classes) if not reliable_mask[i]]}")


def plot_confusion_matrix(cm, classes, title, out_path, normalize=False):
    """Génère et sauvegarde une heatmap simple de la matrice de confusion."""
    if normalize:
        cm_display = cm.astype(float) / cm.sum(axis=1, keepdims=True)
        cm_display = np.nan_to_num(cm_display)
        fmt = ".2f"
    else:
        cm_display = cm
        fmt = "d"

    n = len(classes)
    fig, ax = plt.subplots(figsize=(max(8, n * 0.9), max(6, n * 0.75)))
    im = ax.imshow(cm_display, cmap="Blues")

    ax.set_xticks(np.arange(n))
    ax.set_yticks(np.arange(n))
    ax.set_xticklabels(classes, rotation=45, ha="right", fontsize=9)
    ax.set_yticklabels(classes, fontsize=9)
    ax.set_xlabel("Classe prédite", fontsize=11)
    ax.set_ylabel("Classe réelle", fontsize=11)
    ax.set_title(title, fontsize=13, pad=12)

    # Annotation de chaque case avec sa valeur
    threshold = cm_display.max() / 2.0
    for i in range(n):
        for j in range(n):
            value = cm_display[i, j]
            text_color = "white" if value > threshold else "black"
            label = f"{value:{fmt}}" if value > 0 or i == j else ""
            ax.text(j, i, label, ha="center", va="center", color=text_color, fontsize=8)

    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.tight_layout()
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"      Graphique sauvegardé : {out_path}")


def build_dataset(rows):
    texts, labels = [], []
    for row in rows:
        label = row["doc_type"]
        if label in EXCLUDED_CLASSES:
            continue
        text = prepare_text(row["ocr_text"], row["filename"], row["original_path"])
        texts.append(text)
        labels.append(label)
    return texts, labels


async def main():
    print("=" * 70)
    print("  MATRICE DE CONFUSION + K-FOLD DÉTAILLÉ — TF-IDF + SVM")
    print("  NouvelAir MRO")
    print("=" * 70)

    print("\n[1/4] Chargement des données depuis la DB...")
    rows = await fetch_training_data()
    texts, labels = build_dataset(rows)
    print(f"      → {len(texts)} documents utilisables (classes exclues : {EXCLUDED_CLASSES})")

    classes = sorted(set(labels))
    print(f"      → {len(classes)} classes : {classes}")

    # ────────────────────────────────────────────────────────────
    # 1. MATRICE DE CONFUSION (holdout 80/20)
    # ────────────────────────────────────────────────────────────
    print("\n[2/4] Split holdout 80/20 et entraînement...")

    # Avec des classes à très faible effectif (parfois 1 seul document),
    # une stratification stricte peut échouer. On tente d'abord avec
    # stratify=labels ; en cas d'échec, on bascule sur un split non stratifié.
    try:
        X_train, X_test, y_train, y_test = train_test_split(
            texts, labels, test_size=0.2, random_state=RANDOM_STATE, stratify=labels
        )
    except ValueError as e:
        print(f"      [ATTENTION] Stratification impossible ({e}).")
        print("      → Split non stratifié utilisé à la place.")
        X_train, X_test, y_train, y_test = train_test_split(
            texts, labels, test_size=0.2, random_state=RANDOM_STATE
        )

    classes_in_test = sorted(set(y_test))
    missing_from_test = sorted(set(classes) - set(classes_in_test))
    if missing_from_test:
        print(f"      [INFO] Classes absentes du jeu de test (effectif trop faible) : {missing_from_test}")

    vectorizer = TfidfVectorizer(max_features=20000, ngram_range=(1, 3), min_df=1, analyzer="word")
    X_train_vec = vectorizer.fit_transform(X_train)
    X_test_vec = vectorizer.transform(X_test)

    model = make_svm(y_train)
    model.fit(X_train_vec, y_train)
    y_pred = model.predict(X_test_vec)

    acc = accuracy_score(y_test, y_pred)
    f1_macro = f1_score(y_test, y_pred, average="macro")
    f1_weighted = f1_score(y_test, y_pred, average="weighted")

    print(f"      → accuracy={acc*100:.2f}%  f1_macro={f1_macro*100:.2f}%  f1_weighted={f1_weighted*100:.2f}%")

    print("\n[3/4] Calcul de la matrice de confusion...")
    cm = confusion_matrix(y_test, y_pred, labels=classes)
    report_dict = classification_report(y_test, y_pred, labels=classes, output_dict=True, zero_division=0)

    confusion_report = {
        "date": datetime.now().isoformat(),
        "classes": classes,
        "accuracy": round(acc * 100, 2),
        "f1_macro": round(f1_macro * 100, 2),
        "f1_weighted": round(f1_weighted * 100, 2),
        "test_size": len(y_test),
        "confusion_matrix": cm.tolist(),
        "per_class": {
            cls: {
                "precision": round(report_dict[cls]["precision"] * 100, 2),
                "recall": round(report_dict[cls]["recall"] * 100, 2),
                "f1": round(report_dict[cls]["f1-score"] * 100, 2),
                "support": int(report_dict[cls]["support"]),
            }
            for cls in classes
        },
    }

    out_path_cm = os.path.join(os.path.dirname(__file__), "confusion_matrix_report.json")
    with open(out_path_cm, "w", encoding="utf-8") as f:
        json.dump(confusion_report, f, indent=2, ensure_ascii=False)

    print("\n      Génération du graphique...")
    out_path_png = os.path.join(os.path.dirname(__file__), "confusion_matrix3.png")
    plot_confusion_matrix_dual(
        cm, classes,
        accuracy=acc * 100,
        out_path=out_path_png,
    )

    print(f"\n      Matrice de confusion ({len(classes)}x{len(classes)}) :")
    header = "".join(f"{c[:8]:>10}" for c in classes)
    print(f"      {'':>18}{header}")
    for i, cls in enumerate(classes):
        row_str = "".join(f"{cm[i][j]:>10}" for j in range(len(classes)))
        print(f"      {cls[:16]:<18}{row_str}")

    print(f"\n[OK] Rapport sauvegardé : {out_path_cm}")

    # ────────────────────────────────────────────────────────────
    # 2. K-FOLD DÉTAILLÉ (pli par pli)
    # ────────────────────────────────────────────────────────────
    print(f"\n[4/4] Validation croisée {N_FOLDS}-fold détaillée...")

    # StratifiedKFold exige au moins N_FOLDS exemples par classe.
    # Avec des classes à 1 ou 2 documents (AMM, IPC...), on doit soit
    # réduire le nombre de plis, soit accepter qu'un KFold simple (non
    # stratifié) soit utilisé pour ces classes très rares.
    from collections import Counter
    class_counts = Counter(labels)
    min_class_count = min(class_counts.values())

    effective_n_folds = min(N_FOLDS, min_class_count)
    if effective_n_folds < N_FOLDS:
        print(f"      [ATTENTION] Classe(s) avec seulement {min_class_count} document(s) "
              f"(ex: {[c for c, n in class_counts.items() if n == min_class_count]}).")
        print(f"      → Nombre de plis réduit de {N_FOLDS} à {effective_n_folds} pour permettre la stratification.")

    if effective_n_folds < 2:
        print("      [ERREUR] Au moins une classe a un seul document : la validation croisée "
              "stratifiée est impossible. Le k-fold est ignoré pour cette classe ; "
              "un KFold non stratifié est utilisé à la place sur l'ensemble du corpus.")
        from sklearn.model_selection import KFold
        skf = KFold(n_splits=N_FOLDS, shuffle=True, random_state=RANDOM_STATE)
        actual_n_folds = N_FOLDS
    else:
        skf = StratifiedKFold(n_splits=effective_n_folds, shuffle=True, random_state=RANDOM_STATE)
        actual_n_folds = effective_n_folds

    texts_arr = np.array(texts)
    labels_arr = np.array(labels)

    fold_results = []
    all_y_true, all_y_pred = [], []

    for fold_idx, (train_idx, test_idx) in enumerate(skf.split(texts_arr, labels_arr), 1):
        X_tr, X_te = texts_arr[train_idx], texts_arr[test_idx]
        y_tr, y_te = labels_arr[train_idx], labels_arr[test_idx]

        vec_fold = TfidfVectorizer(max_features=20000, ngram_range=(1, 3), min_df=1, analyzer="word")
        X_tr_vec = vec_fold.fit_transform(X_tr)
        X_te_vec = vec_fold.transform(X_te)

        model_fold = make_svm(y_tr)
        model_fold.fit(X_tr_vec, y_tr)
        y_pred_fold = model_fold.predict(X_te_vec)

        fold_acc = accuracy_score(y_te, y_pred_fold)
        fold_f1m = f1_score(y_te, y_pred_fold, average="macro")
        fold_f1w = f1_score(y_te, y_pred_fold, average="weighted")

        fold_results.append({
            "fold": fold_idx,
            "accuracy": round(fold_acc * 100, 2),
            "f1_macro": round(fold_f1m * 100, 2),
            "f1_weighted": round(fold_f1w * 100, 2),
            "train_size": len(train_idx),
            "test_size": len(test_idx),
        })

        all_y_true.extend(y_te.tolist())
        all_y_pred.extend(y_pred_fold.tolist())

        print(f"      Pli {fold_idx}/{actual_n_folds} : acc={fold_acc*100:.2f}%  "
              f"f1_macro={fold_f1m*100:.2f}%  f1_weighted={fold_f1w*100:.2f}%")

    accs = [r["accuracy"] for r in fold_results]
    f1ms = [r["f1_macro"] for r in fold_results]
    f1ws = [r["f1_weighted"] for r in fold_results]

    cm_aggregated = confusion_matrix(all_y_true, all_y_pred, labels=classes)

    kfold_report = {
        "date": datetime.now().isoformat(),
        "n_folds": actual_n_folds,
        "classes": classes,
        "per_fold": fold_results,
        "summary": {
            "accuracy_mean": round(float(np.mean(accs)), 2),
            "accuracy_std": round(float(np.std(accs)), 2),
            "f1_macro_mean": round(float(np.mean(f1ms)), 2),
            "f1_macro_std": round(float(np.std(f1ms)), 2),
            "f1_weighted_mean": round(float(np.mean(f1ws)), 2),
            "f1_weighted_std": round(float(np.std(f1ws)), 2),
        },
        "confusion_matrix_aggregated": cm_aggregated.tolist(),
    }

    out_path_kfold = os.path.join(os.path.dirname(__file__), "kfold_detailed_report3.json")
    with open(out_path_kfold, "w", encoding="utf-8") as f:
        json.dump(kfold_report, f, indent=2, ensure_ascii=False)

    print("\n      Génération du graphique (matrice agrégée k-fold)...")
    out_path_png_kfold = os.path.join(os.path.dirname(__file__), "confusion_matrix_kfold3.png")
    plot_confusion_matrix(
        cm_aggregated, classes,
        title=f"Matrice de confusion agrégée — {actual_n_folds}-fold cross-validation",
        out_path=out_path_png_kfold,
    )

    print("\n" + "=" * 70)
    print(f"  SYNTHÈSE {actual_n_folds}-FOLD")
    print("=" * 70)
    print(f"  Accuracy    : {kfold_report['summary']['accuracy_mean']:.2f}% ± {kfold_report['summary']['accuracy_std']:.2f}")
    print(f"  F1-Macro    : {kfold_report['summary']['f1_macro_mean']:.2f}% ± {kfold_report['summary']['f1_macro_std']:.2f}")
    print(f"  F1-Weighted : {kfold_report['summary']['f1_weighted_mean']:.2f}% ± {kfold_report['summary']['f1_weighted_std']:.2f}")
    print("=" * 70)
    print(f"\n[OK] Rapport sauvegardé : {out_path_kfold}")


if __name__ == "__main__":
    asyncio.run(main())