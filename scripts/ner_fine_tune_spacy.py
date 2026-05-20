"""
ner_fine_tune_spacy.py
======================
Entraîne un modèle NER spaCy personnalisé sur le corpus NouvelAir.

ARCHITECTURE :
  Base    : fr_core_news_md (pré-entraîné sur le français)
  Fine-tune : ajout de 7 nouvelles entités aéronautiques
  Méthode : transfer learning — on garde les layers bas du modèle de base
             et on spécialise la couche NER sur nos données.

FEATURES UTILISÉES PAR spaCy NER (automatiques) :
  - Token : forme, forme minuscule, suffixe (3 chars), préfixe (1 char)
  - POS tag : catégorie grammaticale
  - Dépendance syntaxique : relation au parent
  - Contexte : fenêtre de 4 tokens à gauche et 4 à droite
  - Embeddings : vecteurs de tokens (from fr_core_news_md)
  - Entité précédente (BIO tagging)

ALGORITHME :
  Transition-based NER (Lample et al. 2016) avec :
  - Architecture CNN → BiLSTM → CRF (dans spaCy)
  - Optimiseur Adam avec warm-up
  - Dropout 0.2 pour régularisation

OUTPUT :
  models/ner_nouvelair/         → modèle spaCy sauvegardé
  models/ner_nouvelair_best/    → meilleur checkpoint (selon F1 eval)
  logs/ner_training_log.json    → courbe d'entraînement

USAGE :
  # Installer d'abord :
  pip install spacy --break-system-packages
  py -m spacy download fr_core_news_md

  # Lancer :
  py ner_fine_tune_spacy.py
  py ner_fine_tune_spacy.py --epochs 30 --batch-size 16
  py ner_fine_tune_spacy.py --eval-only   # évaluer un modèle existant
"""

import json
import random
import argparse
import time
from pathlib import Path
from datetime import datetime

# ─── Configuration ────────────────────────────────────────────────────────────
DATA_DIR   = Path("data")
MODELS_DIR = Path("models")
LOGS_DIR   = Path("logs")

# Labels NER du projet NouvelAir
LABELS = [
    "AIRCRAFT_REG",   # TS-INP, TS-INQ
    "ES_REF",         # ES001778
    "ATA_CHAPTER",    # 32-40-00
    "PART_NUMBER",    # P/N 123456
    "SERIAL_NUMBER",  # S/N ABC123, MSN 2158
    "DOC_REF",        # AD 2023-..., SB 737-...
    "DATE_AVIO",      # 01 JAN 2023
    "AIRLINE",        # NouvelAir
]

# Hyperparamètres (optimisés pour ce corpus)
DEFAULT_CONFIG = {
    "epochs":          30,
    "batch_size":      16,
    "dropout":         0.2,
    "learning_rate":   0.001,
    "eval_interval":   5,       # évaluer toutes les N epochs
    "patience":        10,      # early stopping
    "base_model":      "fr_core_news_md",
}


# ─── Chargement des données ───────────────────────────────────────────────────

def load_dataset(path: Path) -> list:
    """Charge le JSON généré par ner_auto_label.py."""
    if not path.exists():
        raise FileNotFoundError(
            f"Dataset introuvable : {path}\n"
            f"Lance d'abord : py ner_auto_label.py"
        )
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    print(f"   Chargé : {len(data)} exemples depuis {path}")
    return data


def json_to_spacy_format(examples: list, nlp):
    """Convertit le JSON en objets spaCy DocBin."""
    import spacy
    from spacy.tokens import DocBin
    from spacy.training import Example

    db = DocBin()
    skipped = 0
    for ex in examples:
        text     = ex["text"]
        entities = ex["entities"]
        doc      = nlp.make_doc(text)

        ents = []
        for start, end, label in entities:
            span = doc.char_span(start, end, label=label, alignment_mode="contract")
            if span is not None:
                ents.append(span)

        try:
            doc.ents = ents
            db.add(doc)
        except Exception:
            skipped += 1

    print(f"   Convertis : {len(examples) - skipped} docs OK, {skipped} ignorés (conflits)")
    return db


# ─── Évaluation NER ───────────────────────────────────────────────────────────

def evaluate_ner(nlp, eval_examples: list) -> dict:
    """Calcule Précision / Rappel / F1 par label."""
    from collections import defaultdict

    tp = defaultdict(int)
    fp = defaultdict(int)
    fn = defaultdict(int)

    for ex in eval_examples:
        text     = ex["text"]
        gold_ents = set((s, e, l) for s, e, l in ex["entities"])

        doc  = nlp(text)
        pred_ents = set((ent.start_char, ent.end_char, ent.label_) for ent in doc.ents)

        for ent in pred_ents:
            if ent in gold_ents:
                tp[ent[2]] += 1
            else:
                fp[ent[2]] += 1
        for ent in gold_ents:
            if ent not in pred_ents:
                fn[ent[2]] += 1

    scores = {}
    total_tp = total_fp = total_fn = 0

    for label in LABELS:
        p  = tp[label] / (tp[label] + fp[label]) if (tp[label] + fp[label]) > 0 else 0
        r  = tp[label] / (tp[label] + fn[label]) if (tp[label] + fn[label]) > 0 else 0
        f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0
        scores[label] = {"precision": p, "recall": r, "f1": f1,
                         "tp": tp[label], "fp": fp[label], "fn": fn[label]}
        total_tp += tp[label]
        total_fp += fp[label]
        total_fn += fn[label]

    # Macro F1
    macro_f1 = sum(s["f1"] for s in scores.values()) / len(LABELS)
    # Micro F1
    micro_p  = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0
    micro_r  = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0
    micro_f1 = 2 * micro_p * micro_r / (micro_p + micro_r) if (micro_p + micro_r) > 0 else 0

    scores["__macro_f1__"] = macro_f1
    scores["__micro_f1__"] = micro_f1
    return scores


def print_eval_table(scores: dict, epoch: int = None):
    """Affiche le tableau d'évaluation."""
    header = f"\n{'─'*65}"
    if epoch is not None:
        print(f"\n📊 Évaluation — Epoch {epoch}")
    print(header)
    print(f"{'Label':20s} {'Prec':>8} {'Recall':>8} {'F1':>8} {'TP':>5} {'FP':>5} {'FN':>5}")
    print(header)
    for label in LABELS:
        s = scores.get(label, {})
        if not s:
            continue
        print(f"{label:20s} {s['precision']:8.3f} {s['recall']:8.3f} {s['f1']:8.3f} "
              f"{s['tp']:5d} {s['fp']:5d} {s['fn']:5d}")
    print(header)
    print(f"{'Macro F1':20s} {scores['__macro_f1__']:>25.3f}")
    print(f"{'Micro F1':20s} {scores['__micro_f1__']:>25.3f}")


# ─── Entraînement ─────────────────────────────────────────────────────────────

def train(config: dict, eval_only: bool = False):
    try:
        import spacy
        from spacy.training import Example
    except ImportError:
        print("❌ spaCy non installé.")
        print("   pip install spacy --break-system-packages")
        print("   py -m spacy download fr_core_news_md")
        return

    MODELS_DIR.mkdir(exist_ok=True)
    LOGS_DIR.mkdir(exist_ok=True)

    model_path      = MODELS_DIR / "ner_nouvelair"
    best_model_path = MODELS_DIR / "ner_nouvelair_best"

    # ─── Mode évaluation uniquement ───────────────────────────────────────────
    if eval_only:
        if not model_path.exists():
            print(f"❌ Modèle introuvable : {model_path}")
            return
        print(f"📂 Chargement du modèle : {model_path}")
        nlp       = spacy.load(model_path)
        eval_data = load_dataset(DATA_DIR / "ner_eval_data.json")
        scores    = evaluate_ner(nlp, eval_data)
        print_eval_table(scores)
        return

    # ─── Chargement des données ───────────────────────────────────────────────
    print("\n📂 Chargement des données...")
    train_data = load_dataset(DATA_DIR / "ner_training_data.json")
    eval_data  = load_dataset(DATA_DIR / "ner_eval_data.json")

    # ─── Initialisation du modèle ─────────────────────────────────────────────
    print(f"\n🧠 Chargement du modèle de base : {config['base_model']}")
    try:
        nlp = spacy.load(config["base_model"])
    except OSError:
        print(f"❌ Modèle de base introuvable. Lance : py -m spacy download {config['base_model']}")
        return

    # Ajouter la pipe NER si elle n'existe pas, ou récupérer l'existante
    if "ner" not in nlp.pipe_names:
        ner = nlp.add_pipe("ner", last=True)
    else:
        ner = nlp.get_pipe("ner")

    # Ajouter les labels NouvelAir
    for label in LABELS:
        ner.add_label(label)

    print(f"   Labels NER : {LABELS}")

    # Désactiver les pipes non-NER pendant l'entraînement
    other_pipes = [pipe for pipe in nlp.pipe_names if pipe != "ner"]

    # ─── Boucle d'entraînement ────────────────────────────────────────────────
    optimizer = nlp.resume_training()
    optimizer.learn_rate = config["learning_rate"]

    best_f1   = 0.0
    patience  = 0
    log       = []

    print(f"\n🚀 Début de l'entraînement ({config['epochs']} epochs)...")
    print(f"   Batch size : {config['batch_size']}")
    print(f"   Dropout    : {config['dropout']}")
    print(f"   Train docs : {len(train_data)}")
    print(f"   Eval docs  : {len(eval_data)}")
    print(f"{'─'*50}")

    with nlp.disable_pipes(*other_pipes):
        for epoch in range(1, config["epochs"] + 1):
            t0 = time.time()
            random.shuffle(train_data)
            losses = {}

            # Mini-batches
            batch = []
            for ex in train_data:
                text     = ex["text"]
                entities = ex["entities"]
                doc      = nlp.make_doc(text)
                ents     = []
                for start, end, label in entities:
                    span = doc.char_span(start, end, label=label, alignment_mode="contract")
                    if span:
                        ents.append(span)
                doc.ents = ents
                example  = Example.from_dict(doc, {"entities": [(e.start_char, e.end_char, e.label_) for e in ents]})
                batch.append(example)

                if len(batch) >= config["batch_size"]:
                    nlp.update(batch, sgd=optimizer, drop=config["dropout"], losses=losses)
                    batch = []

            if batch:
                nlp.update(batch, sgd=optimizer, drop=config["dropout"], losses=losses)

            elapsed = time.time() - t0
            ner_loss = losses.get("ner", 0)
            print(f"Epoch {epoch:3d}/{config['epochs']} | Loss: {ner_loss:8.2f} | {elapsed:.1f}s", end="")

            # Évaluation périodique
            if epoch % config["eval_interval"] == 0:
                scores   = evaluate_ner(nlp, eval_data)
                macro_f1 = scores["__macro_f1__"]
                print(f" | F1 macro: {macro_f1:.3f}", end="")

                log.append({
                    "epoch":    epoch,
                    "loss":     ner_loss,
                    "macro_f1": macro_f1,
                    "scores":   {k: v for k, v in scores.items() if not k.startswith("__")},
                })

                if macro_f1 > best_f1:
                    best_f1 = macro_f1
                    nlp.to_disk(best_model_path)
                    print(f" ✅ (nouveau best !)", end="")
                    patience = 0
                else:
                    patience += 1
                    if patience >= config["patience"] // config["eval_interval"]:
                        print(f"\n\n⏹️  Early stopping (patience {config['patience']} epochs sans amélioration)")
                        break
            print()

    # Sauvegarde finale
    nlp.to_disk(model_path)
    print(f"\n💾 Modèle sauvegardé : {model_path}")
    print(f"💾 Meilleur modèle   : {best_model_path} (F1={best_f1:.3f})")

    # Log JSON
    log_path = LOGS_DIR / "ner_training_log.json"
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump({"config": config, "log": log, "best_f1": best_f1,
                   "trained_at": datetime.now().isoformat()}, f, indent=2)
    print(f"📊 Log sauvegardé   : {log_path}")

    # Évaluation finale sur le meilleur modèle
    print(f"\n🔁 Évaluation finale (meilleur modèle)...")
    best_nlp = spacy.load(best_model_path)
    final_scores = evaluate_ner(best_nlp, eval_data)
    print_eval_table(final_scores)

    # Test rapide
    print("\n🧪 Test rapide :")
    test_sentences = [
        "Work Order ES001778 pour l'aéronef TS-INQ ATA 32-40",
        "AD 2023-12-04 applicable au MSN 2158 P/N 1234567",
        "SB 737-28-1234 émis le 15 JAN 2023 pour TS-INP",
    ]
    for sent in test_sentences:
        doc = best_nlp(sent)
        print(f"\n   Texte : {sent}")
        if doc.ents:
            for ent in doc.ents:
                print(f"   → [{ent.label_:20s}] '{ent.text}'")
        else:
            print("   → Aucune entité détectée")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Fine-tuning NER NouvelAir")
    parser.add_argument("--epochs",     type=int,   default=DEFAULT_CONFIG["epochs"])
    parser.add_argument("--batch-size", type=int,   default=DEFAULT_CONFIG["batch_size"])
    parser.add_argument("--lr",         type=float, default=DEFAULT_CONFIG["learning_rate"])
    parser.add_argument("--dropout",    type=float, default=DEFAULT_CONFIG["dropout"])
    parser.add_argument("--base-model", type=str,   default=DEFAULT_CONFIG["base_model"])
    parser.add_argument("--eval-only",  action="store_true")
    args = parser.parse_args()

    config = {
        "epochs":        args.epochs,
        "batch_size":    args.batch_size,
        "learning_rate": args.lr,
        "dropout":       args.dropout,
        "base_model":    args.base_model,
        "eval_interval": DEFAULT_CONFIG["eval_interval"],
        "patience":      DEFAULT_CONFIG["patience"],
    }

    train(config, eval_only=args.eval_only)


if __name__ == "__main__":
    main()