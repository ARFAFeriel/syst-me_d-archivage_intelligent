"""
entity_augmented_classifier.py
===============================
Classifieur de documents amélioré qui combine :
  - TF-IDF sur le texte OCR  (50 000 features)
  - 12 features NER binaires  (présence d'entités)

POURQUOI ça améliore la classification ?
  Le TF-IDF seul confond parfois :
  - Work Order vs Job Card (texte similaire)
  - SB vs AD (structure proche)
  - Documents multilingues (même concept, mots différents)

  Les features NER ajoutent un signal structurel fort :
  ┌──────────────────────────────────────────────────────┐
  │  has_es_ref=1 + has_aircraft_reg=1 + has_ata=1       │
  │  → signal fort Work Order / Job Card                 │
  │                                                      │
  │  doc_ref_is_ad=1 + has_part_number=1                 │
  │  → signal fort Airworthiness Directive               │
  │                                                      │
  │  doc_ref_is_sb=1 + has_ata=1                         │
  │  → signal fort Service Bulletin                      │
  └──────────────────────────────────────────────────────┘

ARCHITECTURE :
  texte  →  TfidfVectorizer (sparse, 50k)  ──┐
                                              ├→ hstack → LogisticRegression
  entités → 12 features NER (dense)         ──┘

DATASET :
  Même corpus que le classifieur existant : ~2 627 docs NouvelAir
  Labels : doc_type (Work Order, AD, SB, AMM, CMM, IPC, MEL, CRS, COA, Job Card...)
  + Règles de chemin (path rules) appliquées en post-processing

USAGE :
  # Entraînement
  py scripts/entity_augmented_classifier.py --train

  # Évaluation
  py scripts/entity_augmented_classifier.py --eval

  # Prédiction sur un texte
  py scripts/entity_augmented_classifier.py --predict "Work Order ES001778 TS-INQ ATA 32-40"

  # Benchmark vs classifieur existant
  py scripts/entity_augmented_classifier.py --benchmark
"""

import os
import json
import pickle
import argparse
import numpy as np
from pathlib import Path
from collections import Counter

# ─── Configuration ────────────────────────────────────────────────────────────
from dotenv import load_dotenv; load_dotenv(); DB_URL = os.getenv('DATABASE_URL', 'postgresql://postgres:Nouv26@localhost:5434/nouv_db')
MODEL_PATH = Path("models/entity_augmented_classifier.pkl")
LOGS_DIR   = Path("logs")

# Règles de chemin (path rules) — priorité absolue sur le modèle ML
PATH_RULES = {
    "ES":        "Work Order",
    "Check_A":   "Check A",
    "Check_C":   "Check C",
    "Check_D":   "Check D",
    "AD":        "Airworthiness Directive",
    "SB":        "Service Bulletin",
    "AMM":       "Aircraft Maintenance Manual",
    "CMM":       "Component Maintenance Manual",
    "IPC":       "Illustrated Parts Catalog",
    "MEL":       "Minimum Equipment List",
}


# ─── Chargement des données ───────────────────────────────────────────────────

def fetch_training_data() -> tuple[list[str], list[str], list[str]]:
    """
    Récupère texte + doc_type + filename depuis PostgreSQL.
    Retourne (texts, labels, filenames).
    """
    try:
        import psycopg2
    except ImportError:
        raise ImportError("pip install psycopg2-binary --break-system-packages")

    conn = psycopg2.connect(DB_URL)
    cur  = conn.cursor()
    cur.execute("""
        SELECT ocr_text, doc_type, filename
        FROM documents
        WHERE ocr_text IS NOT NULL
          AND doc_type IS NOT NULL
          AND length(ocr_text) > 50
        ORDER BY id
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    texts     = [r[0] for r in rows]
    labels    = [r[1] for r in rows]
    filenames = [r[2] for r in rows]
    return texts, labels, filenames


# ─── Features NER ─────────────────────────────────────────────────────────────

def compute_ner_features(texts: list[str]) -> np.ndarray:
    """
    Calcule les 12 features NER pour une liste de textes.
    Retourne un array numpy (n_docs, 12).
    """
    # Import ici pour ne pas bloquer si le modèle n'est pas disponible
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent / 'backend' / 'agents'))
        from ner_agent_v7 import extract_entities, entities_to_features
    except ImportError:
        # Fallback : uniquement regex
        from ner_agent_v7 import extract_entities, entities_to_features

    print(f"   Calcul features NER sur {len(texts)} documents...")
    features = []
    for i, text in enumerate(texts):
        if i % 200 == 0:
            print(f"   {i}/{len(texts)}", end="\r")
        ents  = extract_entities(text[:3000])
        feats = entities_to_features(ents)
        features.append(list(feats.values()))

    print(f"   {len(texts)}/{len(texts)} ✅")
    return np.array(features, dtype=np.float32)


def apply_path_rules(filename: str) -> str | None:
    """
    Retourne le doc_type si le nom de fichier matche une règle de chemin.
    None sinon → utiliser le modèle ML.
    """
    fname_upper = filename.upper()
    for pattern, label in PATH_RULES.items():
        if pattern.upper() in fname_upper:
            return label
    return None


# ─── Entraînement ─────────────────────────────────────────────────────────────

def train():
    from sklearn.linear_model import LogisticRegression
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import classification_report, f1_score
    from sklearn.preprocessing import LabelEncoder
    from scipy.sparse import hstack, csr_matrix

    print("📂 Chargement des données depuis PostgreSQL...")
    texts, labels, filenames = fetch_training_data()
    print(f"   {len(texts)} documents chargés")
    print(f"   Distribution des labels :")
    for label, count in sorted(Counter(labels).items(), key=lambda x: -x[1]):
        print(f"     {label:40s} {count:4d}")

    # Split train/test
    (X_train_txt, X_test_txt,
     y_train,     y_test,
     fn_train,    fn_test) = train_test_split(
        texts, labels, filenames,
        test_size=0.2, random_state=42
    )

    print(f"\n   Train : {len(X_train_txt)} | Test : {len(X_test_txt)}")

    # ── Features TF-IDF ───────────────────────────────────────────────────────
    print("\n🔤 Calcul features TF-IDF...")
    tfidf = TfidfVectorizer(
        max_features=50_000,
        ngram_range=(1, 2),        # unigrammes + bigrammes
        sublinear_tf=True,         # log(1+tf) pour atténuer les tokens fréquents
        min_df=2,                  # ignorer tokens apparaissant < 2 fois
        strip_accents="unicode",
        analyzer="word",
    )
    X_train_tfidf = tfidf.fit_transform(X_train_txt)
    X_test_tfidf  = tfidf.transform(X_test_txt)
    print(f"   Vocabulaire TF-IDF : {len(tfidf.vocabulary_):,} tokens")

    # ── Features NER ──────────────────────────────────────────────────────────
    print("\n🏷️  Calcul features NER...")
    X_train_ner = compute_ner_features(X_train_txt)
    X_test_ner  = compute_ner_features(X_test_txt)
    print(f"   Features NER : {X_train_ner.shape[1]} features binaires")

    # Poids NER × 5 pour amplifier leur signal
    # (compenser le déséquilibre avec 50k features TF-IDF)
    NER_WEIGHT = 0.5
    X_train_ner_weighted = csr_matrix(X_train_ner * NER_WEIGHT)
    X_test_ner_weighted  = csr_matrix(X_test_ner  * NER_WEIGHT)

    # ── Combinaison horizontale ───────────────────────────────────────────────
    X_train = hstack([X_train_tfidf, X_train_ner_weighted])
    X_test  = hstack([X_test_tfidf,  X_test_ner_weighted])
    print(f"\n   Shape finale : {X_train.shape} (TF-IDF + NER)")

    # ── Entraînement LR ───────────────────────────────────────────────────────
    print("\n🚀 Entraînement LogisticRegression...")
    clf = LogisticRegression(
        C=5.0,
        max_iter=1000,
        class_weight="balanced",   # compenser les déséquilibres de classes
        solver="lbfgs",
        multi_class="multinomial",
        n_jobs=-1,
    )
    clf.fit(X_train, y_train)
    print("   Entraînement terminé ✅")

    # ── Évaluation ────────────────────────────────────────────────────────────
    print("\n📊 Évaluation sur le test set...")

    # Prédictions ML seules
    y_pred_ml = clf.predict(X_test)

    # Prédictions avec path rules (override ML sur les filenames connus)
    y_pred_final = []
    for pred_ml, fname in zip(y_pred_ml, fn_test):
        rule_label = apply_path_rules(fname)
        y_pred_final.append(rule_label if rule_label else pred_ml)

    f1_ml    = f1_score(y_test, y_pred_ml,    average="macro", zero_division=0)
    f1_final = f1_score(y_test, y_pred_final, average="macro", zero_division=0)

    print(f"\n   F1 Macro (ML seul)          : {f1_ml:.4f}")
    print(f"   F1 Macro (ML + path rules)  : {f1_final:.4f}")
    print(f"\n{classification_report(y_test, y_pred_final, zero_division=0)}")

    # ── Sauvegarde ────────────────────────────────────────────────────────────
    MODEL_PATH.parent.mkdir(exist_ok=True)
    LOGS_DIR.mkdir(exist_ok=True)

    model_bundle = {
        "tfidf":      tfidf,
        "classifier": clf,
        "ner_weight": NER_WEIGHT,
        "f1_macro":   f1_final,
        "labels":     list(set(labels)),
    }
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(model_bundle, f)
    print(f"\n💾 Modèle sauvegardé : {MODEL_PATH}")

    # Log
    log = {"f1_ml": f1_ml, "f1_final": f1_final,
           "n_train": len(X_train_txt), "n_test": len(X_test_txt)}
    with open(LOGS_DIR / "classifier_log.json", "w") as f:
        json.dump(log, f, indent=2)

    return f1_final


# ─── Prédiction ──────────────────────────────────────────────────────────────

def load_model() -> dict:
    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            f"Modèle absent : {MODEL_PATH}\n"
            f"Lance d'abord : py scripts/entity_augmented_classifier.py --train"
        )
    with open(MODEL_PATH, "rb") as f:
        return pickle.load(f)


def predict(text: str, filename: str = "") -> dict:
    """
    Prédit le doc_type d'un document.
    Retourne {"label": str, "confidence": float, "method": str}
    """
    # Path rule en priorité
    rule = apply_path_rules(filename)
    if rule:
        return {"label": rule, "confidence": 1.0, "method": "path_rule"}

    # Modèle ML
    bundle = load_model()
    tfidf  = bundle["tfidf"]
    clf    = bundle["classifier"]
    weight = bundle["ner_weight"]

    from scipy.sparse import hstack, csr_matrix
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / 'backend' / 'agents'))
    from ner_agent_v7 import extract_entities, entities_to_features

    X_tfidf = tfidf.transform([text])
    ents    = extract_entities(text[:3000])
    feats   = list(entities_to_features(ents).values())
    X_ner   = csr_matrix(np.array(feats, dtype=np.float32).reshape(1, -1) * weight)
    X       = hstack([X_tfidf, X_ner])

    proba  = clf.predict_proba(X)[0]
    idx    = np.argmax(proba)
    label  = clf.classes_[idx]
    conf   = float(proba[idx])

    return {"label": label, "confidence": conf, "method": "entity_augmented_ml",
            "entities": ents}


# ─── Benchmark vs classifieur existant ───────────────────────────────────────

def benchmark():
    """Compare Entity-Augmented vs TF-IDF seul."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import f1_score
    from scipy.sparse import hstack, csr_matrix

    print("⚡ Benchmark : TF-IDF seul vs Entity-Augmented\n")
    texts, labels, filenames = fetch_training_data()

    (X_tr, X_te, y_tr, y_te, fn_tr, fn_te) = train_test_split(
        texts, labels, filenames, test_size=0.2, random_state=42
    )

    # ── Baseline : TF-IDF seul ────────────────────────────────────────────────
    print("1️⃣  Baseline TF-IDF seul...")
    tfidf_base = TfidfVectorizer(max_features=50_000, ngram_range=(1,2),
                                  sublinear_tf=True, min_df=2)
    clf_base   = LogisticRegression(C=5.0, max_iter=1000, class_weight="balanced",
                                    solver="lbfgs", n_jobs=-1)
    clf_base.fit(tfidf_base.fit_transform(X_tr), y_tr)
    pred_base  = clf_base.predict(tfidf_base.transform(X_te))
    f1_base    = f1_score(y_te, pred_base, average="macro", zero_division=0)
    print(f"   F1 Macro (TF-IDF seul)      : {f1_base:.4f}")

    # ── Augmenté : TF-IDF + NER ───────────────────────────────────────────────
    print("2️⃣  Entity-Augmented (TF-IDF + NER)...")
    tfidf_aug  = TfidfVectorizer(max_features=50_000, ngram_range=(1,2),
                                  sublinear_tf=True, min_df=2)
    X_tr_tfidf = tfidf_aug.fit_transform(X_tr)
    X_te_tfidf = tfidf_aug.transform(X_te)
    X_tr_ner   = csr_matrix(compute_ner_features(X_tr) * 5.0)
    X_te_ner   = csr_matrix(compute_ner_features(X_te) * 5.0)
    X_tr_aug   = hstack([X_tr_tfidf, X_tr_ner])
    X_te_aug   = hstack([X_te_tfidf, X_te_ner])
    clf_aug    = LogisticRegression(C=5.0, max_iter=1000, class_weight="balanced",
                                    solver="lbfgs", n_jobs=-1)
    clf_aug.fit(X_tr_aug, y_tr)
    pred_aug   = clf_aug.predict(X_te_aug)
    f1_aug     = f1_score(y_te, pred_aug, average="macro", zero_division=0)
    print(f"   F1 Macro (TF-IDF + NER)     : {f1_aug:.4f}")

    # ── Résultats ─────────────────────────────────────────────────────────────
    gain = (f1_aug - f1_base) * 100
    print(f"\n{'='*50}")
    print(f"  Gain  : +{gain:.1f} points de F1 Macro")
    print(f"{'='*50}")

    # Analyse par label
    from sklearn.metrics import classification_report
    print("\nDétail par label (modèle augmenté) :")
    print(classification_report(y_te, pred_aug, zero_division=0))


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--train",     action="store_true", help="Entraîner le modèle")
    parser.add_argument("--eval",      action="store_true", help="Évaluer le modèle existant")
    parser.add_argument("--benchmark", action="store_true", help="Comparer avec baseline")
    parser.add_argument("--predict",   type=str,            help="Prédire sur un texte")
    parser.add_argument("--filename",  type=str, default="", help="Nom de fichier (pour path rules)")
    args = parser.parse_args()

    if args.train:
        train()
    elif args.benchmark:
        benchmark()
    elif args.predict:
        result = predict(args.predict, args.filename)
        print(f"\nPrédiction : {result['label']}")
        print(f"Confiance  : {result['confidence']:.3f}")
        print(f"Méthode    : {result['method']}")
        if result.get("entities"):
            print(f"Entités    : {result['entities']}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
