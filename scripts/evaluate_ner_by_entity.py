"""
scripts/evaluate_ner_by_entity.py

Évalue les performances de l'agent NER (NERAgent) par type d'entité,
en comparant ses prédictions à la vérité terrain annotée manuellement
dans data/ner_eval_data.json.

Le fichier ground truth contient une liste de documents, chacun avec :
  - "text"     : le texte brut du document (issu de l'OCR)
  - "entities" : liste de spans [start, end, label] annotés manuellement
  - "meta"     : informations sur le document (filename, doc_type, etc.)

Pour chaque document, l'agent NER est exécuté sur le texte, et ses
prédictions sont comparées aux entités annotées, par type d'entité.

La comparaison se fait au niveau de la valeur textuelle extraite
(normalisée), et non au niveau du span exact en caractères, car
NERAgent ne renvoie pas de positions de caractères.

Usage :
    py scripts\\evaluate_ner_by_entity.py
    py scripts\\evaluate_ner_by_entity.py --limit 50    (test rapide sur 50 docs)
"""

import sys
import os
import json
import re
import asyncio
import argparse
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.agents.ner_agent import NERAgent

# Correspondance entre les labels du fichier ground truth et les champs
# retournés par NERResult.
# AIRLINE est exclu : aucun champ correspondant dans NERResult
# (l'agent n'extrait pas la compagnie aérienne comme champ structuré).
LABEL_TO_FIELD = {
    "ATA_CHAPTER": "ata_chapter",
    "DATE_AVIO": "document_date",
    "SERIAL_NUMBER": "serial_number",
    "DOC_REF": "sb_ad_reference",     # confirmé : AD/SB/CMM references
    "PART_NUMBER": "part_number",
    "AIRCRAFT_REG": "aircraft_registration",
    "ES_REF": "es_reference",
}


def normalize(value: str) -> str:
    """Normalise une valeur textuelle pour comparaison (casse, espaces)."""
    if value is None:
        return ""
    return re.sub(r"\s+", "", str(value).strip().upper())


def fuzzy_match(value_a: str, value_b: str) -> bool:
    """
    Comparaison souple : considère deux valeurs comme correspondantes
    si l'une contient l'autre (ex: 'ATA35' contient '35', '35-13-61'
    contient '35'), en plus du cas d'égalité stricte.
    """
    if not value_a or not value_b:
        return False
    a, b = normalize(value_a), normalize(value_b)
    if not a or not b:
        return False
    return a == b or a in b or b in a


def sets_match(gt_values: set, pred_values: set) -> bool:
    """Vérifie si au moins une paire (gt, pred) correspond, en mode souple."""
    for gt_val in gt_values:
        for pred_val in pred_values:
            if fuzzy_match(gt_val, pred_val):
                return True
    return False


def is_plausible_value(value: str, label: str) -> bool:
    """
    Filtre les valeurs ground truth manifestement aberrantes, issues
    d'erreurs de la regex de weak supervision (ex: 'Quantity' étiqueté
    SERIAL_NUMBER). Une valeur est jugée implausible si elle ne contient
    aucun chiffre, alors que toutes les entités évaluées ici désignent
    des codes alphanumériques ou des dates, jamais de simples mots
    entièrement composés de lettres.
    """
    if not value:
        return False
    return any(ch.isdigit() for ch in value)


def extract_ground_truth(doc: dict) -> dict:
    """
    Reconstruit, pour chaque label, l'ensemble des valeurs textuelles
    attendues à partir des spans [start, end, label] et du texte source.
    Les valeurs manifestement aberrantes (sans aucun chiffre) sont
    écartées avant comparaison.
    """
    text = doc["text"]
    gt = defaultdict(set)
    for start, end, label in doc["entities"]:
        value = text[start:end]
        if is_plausible_value(value, label):
            gt[label].add(normalize(value))
    return gt


def extract_predictions(ner_result, labels: list) -> dict:
    """
    Extrait, pour chaque label, la valeur prédite par l'agent NER
    (un seul champ par label dans NERResult, donc un seul élément
    par ensemble, sauf si le champ est multi-valeurs).
    """
    pred = defaultdict(set)
    for label in labels:
        field = LABEL_TO_FIELD.get(label)
        if not field:
            continue
        value = getattr(ner_result, field, None)
        if value:
            pred[label].add(normalize(value))
    return pred


async def main():
    parser = argparse.ArgumentParser(description="Évaluation de l'agent NER par type d'entité")
    parser.add_argument("--limit", type=int, default=None,
                         help="Limite le nombre de documents évalués (test rapide)")
    args = parser.parse_args()

    gt_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "ner_eval_data.json")
    with open(gt_path, encoding="utf-8") as f:
        dataset = json.load(f)

    if args.limit:
        dataset = dataset[:args.limit]

    print(f"[Init] {len(dataset)} documents annotés à évaluer.")
    agent = NERAgent()
    print("[Init] Agent NER prêt.\n")

    labels = sorted({label for doc in dataset for _, _, label in doc["entities"] if label != "AIRLINE"})

    # tp / fp / fn par label, au niveau document (présence/absence de la bonne valeur)
    stats = {label: {"tp": 0, "fn": 0} for label in labels}

    for i, doc in enumerate(dataset, 1):
        filename = doc.get("meta", {}).get("filename", f"doc_{i}")
        text = doc["text"]

        gt = extract_ground_truth(doc)

        try:
            result = await agent.process(text, filename=filename)
        except Exception as e:
            print(f"[{i}/{len(dataset)}] {filename} -> ERREUR agent: {e}")
            continue

        pred = extract_predictions(result, labels)

        for label in labels:
            gt_values = gt.get(label, set())

            if not gt_values:
                # Pas d'annotation pour ce label sur ce document : on ne peut
                # rien conclure (ni succès ni échec), on ignore ce cas.
                continue

            pred_values = pred.get(label, set())
            match = sets_match(gt_values, pred_values)

            if match:
                stats[label]["tp"] += 1
            else:
                stats[label]["fn"] += 1

        if i % 25 == 0:
            print(f"[{i}/{len(dataset)}] documents traités...")

    # Calcul du rappel uniquement par label (seule métrique fiable
    # étant donné que ner_eval_data.json est généré par weak supervision
    # à base de regex, et non par une annotation humaine exhaustive :
    # toute prédiction de l'agent absente de cette référence ne peut
    # pas être considérée à coup sûr comme une fausse extraction).
    report = {"date": datetime.now().isoformat(), "n_documents": len(dataset), "per_entity": {}}

    print("\n" + "=" * 70)
    print(f"{'Entité':<18} {'Rappel':>9} {'TP':>5} {'FN':>5} {'Support':>9}")
    print("-" * 70)

    recalls = []
    for label in labels:
        tp, fn = stats[label]["tp"], stats[label]["fn"]
        support = tp + fn
        recall = tp / support if support > 0 else 0.0
        recalls.append(recall)

        report["per_entity"][label] = {
            "recall": round(recall * 100, 2),
            "tp": tp, "fn": fn, "support": support,
        }

        print(f"{label:<18} {recall*100:>8.1f}% {tp:>5} {fn:>5} {support:>9}")

    recall_macro = sum(recalls) / len(recalls) if recalls else 0.0
    report["recall_macro"] = round(recall_macro * 100, 2)

    print("-" * 70)
    print(f"Rappel macro global : {recall_macro*100:.1f}%")
    print("=" * 70)
    print("\n[NOTE] Seul le rappel est calculé : la référence (ner_eval_data.json)")
    print("       est issue de règles regex (weak supervision), pas d'une")
    print("       annotation humaine exhaustive. La précision ne serait pas")
    print("       fiable, car une prédiction absente de cette référence")
    print("       peut être correcte sans y être simplement annotée.")

    out_path = os.path.join(os.path.dirname(__file__), "ner_evaluation_report.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n[OK] Rapport sauvegardé : {out_path}")


if __name__ == "__main__":
    asyncio.run(main())