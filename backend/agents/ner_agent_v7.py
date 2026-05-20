"""
ner_agent_v7.py  (remplace ner_agent_v6)
========================================
NER avec modèle spaCy fine-tuné NouvelAir (F1=0.922)
+ fallback regex pour les entités ratées.

CHANGEMENTS vs v6 :
  - Chargement du modèle custom models/ner_nouvelair_best
  - spaCy généraliste fr_core_news_md utilisé uniquement si custom absent
  - Résultats NER exportés comme features pour le classifieur (v7)
  - Même interface que v6 : extract_entities(text) → dict

INTÉGRATION dans pipeline.py :
  Remplacer l'import :
    from agents.ner_agent_v6 import extract_entities
  par :
    from agents.ner_agent_v7 import extract_entities
"""

import re
import os
from pathlib import Path
from functools import lru_cache

# ─── Chemins ─────────────────────────────────────────────────────────────────
from dotenv import load_dotenv; load_dotenv()
CUSTOM_MODEL_PATH = Path(__file__).parent.parent.parent / 'models' / 'ner_nouvelair_best'
FALLBACK_MODEL    = "fr_core_news_md"

# ─── Patterns regex (fallback pour entités manquées par le modèle) ────────────
REGEX_FALLBACK = {
    "aircraft_registration": re.compile(
        r'\b(TS-[A-Z]{3})\b'                          # TS-INQ standard
        r'|A/?C\s*[:\-]?\s*(TS-[A-Z]{3})'            # A/C: TS-INQ
        r'|A/?C\s*\n\s*(TS-[A-Z]{3})'                # A/C suivi de TS-INQ à la ligne
        r'|A/?C\s*\n[!\s]*(INP|INQ|INO)\b'           # A/C puis !INQ ou INQ seul
        r'|![A-Z]?(INP|INQ|INO)\b'                   # !NQ ou !INQ dans jobcard
        r'|FSN\s*[:\-]?\s*(TS-[A-Z]{3})',            # FSN: TS-INQ
        re.IGNORECASE
    ),
    "es_reference":  re.compile(r'\b(ES\s*\d{5,7})\b', re.IGNORECASE),
    "ata_chapter":   re.compile(
        r'\bATA\s*(\d{2}[-–]\d{2}(?:[-–]\d{2})?)\b' # ATA 27-10
        r'|\bATA\s*(\d{2})\b',                        # ATA 31
        re.IGNORECASE
    ),
    "part_number":   re.compile(r'\bP/?N[:\s#]?\s*([A-Z0-9][-A-Z0-9]{3,20})\b', re.IGNORECASE),
    "serial_number": re.compile(r'\b(?:S/?N|MSN)[:\s#]?\s*([A-Z0-9]{3,20})\b', re.IGNORECASE),
    "doc_ref":       re.compile(r'\b((?:AD|SB|AMM|CMM)\s+[\w][-\w]{3,25})\b', re.IGNORECASE),
}

# Mapping label spaCy → clé dict interne
LABEL_MAP = {
    "AIRCRAFT_REG":  "aircraft_registration",
    "ES_REF":        "es_reference",
    "ATA_CHAPTER":   "ata_chapter",
    "PART_NUMBER":   "part_number",
    "SERIAL_NUMBER": "serial_number",
    "DOC_REF":       "doc_ref",
    "DATE_AVIO":     "document_date",
    "AIRLINE":       "airline",
}


@lru_cache(maxsize=1)
def _load_nlp():
    """Chargement lazy du modèle NER (une seule fois en mémoire)."""
    import spacy
    if CUSTOM_MODEL_PATH.exists():
        nlp = spacy.load(CUSTOM_MODEL_PATH)
        print(f"[NER v7] Modèle custom chargé : {CUSTOM_MODEL_PATH}")
    else:
        nlp = spacy.load(FALLBACK_MODEL)
        print(f"[NER v7] ⚠️ Modèle custom absent, fallback : {FALLBACK_MODEL}")
    return nlp


def extract_entities(text: str, max_chars: int = 4800) -> dict:
    """
    Extrait les entités nommées du texte.

    Retourne un dict avec les clés :
      aircraft_registration, es_reference, ata_chapter,
      part_number, serial_number, doc_ref, document_date, airline

    Stratégie :
      1. Modèle spaCy fine-tuné (priorité)
      2. Regex fallback pour les entités non trouvées par le modèle
    """
    if not text or not text.strip():
        return _empty_entities()

    text_trunc = text[:max_chars]
    entities   = _empty_entities()

    # ── Étape 1 : modèle NER fine-tuné ────────────────────────────────────────
    try:
        nlp = _load_nlp()
        doc = nlp(text_trunc)
        for ent in doc.ents:
            key = LABEL_MAP.get(ent.label_)
            if key and not entities[key]:          # premier match gagne
                entities[key] = ent.text.strip()
    except Exception as e:
        print(f"[NER v7] Erreur modèle : {e}")

    # ── Étape 2 : regex fallback (uniquement si entité manquante) ─────────────
    for key, rx in REGEX_FALLBACK.items():
        if not entities.get(key):
            m = rx.search(text_trunc)
            if m:
                entities[key] = m.group(1).strip()

    # ── Post-traitement ───────────────────────────────────────────────────────
    # Reconstruire l'immatriculation complète si suffixe seul détecté
    reg = entities["aircraft_registration"]
    if reg:
        reg = reg.upper().strip()
        # Cas: "INQ", "INP", "INO" → "TS-INQ", "TS-INP", "TS-INO"
        if re.match(r'^IN[A-Z]$', reg):
            reg = f"TS-{reg}"
        # Cas: "NQ", "NP", "NO" → "TS-INQ", "TS-INP", "TS-INO"
        elif re.match(r'^N[A-Z]$', reg):
            reg = f"TS-I{reg}"
        entities["aircraft_registration"] = reg

    # Normaliser la référence ES
    if entities["es_reference"]:
        entities["es_reference"] = re.sub(r'\s', '', entities["es_reference"].upper())

    # Normaliser ATA — prendre le premier groupe capturé non nul
    ata = entities["ata_chapter"]
    if ata:
        entities["ata_chapter"] = ata.strip()

    # Normaliser la référence ES (majuscules, pas d'espace)
    if entities["es_reference"]:
        entities["es_reference"] = re.sub(r'\s', '', entities["es_reference"].upper())

    return entities


def extract_entities_all(text: str, max_chars: int = 4800) -> dict:
    """
    Variante qui retourne TOUTES les occurrences (pas uniquement la première).
    Utile pour les documents multi-avions ou multi-ES.

    Retourne un dict avec des listes :
      {"aircraft_registration": ["TS-INP", "TS-INQ"], "es_reference": ["ES001778"], ...}
    """
    if not text or not text.strip():
        return {k: [] for k in LABEL_MAP.values()}

    text_trunc = text[:max_chars]
    results    = {k: [] for k in LABEL_MAP.values()}
    seen       = {k: set() for k in LABEL_MAP.values()}

    try:
        nlp = _load_nlp()
        doc = nlp(text_trunc)
        for ent in doc.ents:
            key = LABEL_MAP.get(ent.label_)
            if key:
                val = ent.text.strip()
                if val not in seen[key]:
                    results[key].append(val)
                    seen[key].add(val)
    except Exception as e:
        print(f"[NER v7] Erreur modèle : {e}")

    # Regex fallback pour compléter
    for key, rx in REGEX_FALLBACK.items():
        for m in rx.finditer(text_trunc):
            val = m.group(1).strip()
            if val not in seen.get(key, set()):
                results[key].append(val)
                seen[key].add(val)

    return results


def entities_to_features(entities: dict) -> dict:
    """
    Convertit les entités en features binaires/catégorielles
    pour le classifieur augmenté.

    Ces 12 features booléennes sont concaténées au vecteur TF-IDF
    dans entity_augmented_classifier.py.
    """
    doc_ref = entities.get("doc_ref", "") or ""
    return {
        "has_aircraft_reg":   int(bool(entities.get("aircraft_registration"))),
        "has_es_ref":         int(bool(entities.get("es_reference"))),
        "has_ata_chapter":    int(bool(entities.get("ata_chapter"))),
        "has_part_number":    int(bool(entities.get("part_number"))),
        "has_serial_number":  int(bool(entities.get("serial_number"))),
        "has_doc_ref":        int(bool(entities.get("doc_ref"))),
        "has_date":           int(bool(entities.get("document_date"))),
        "has_airline":        int(bool(entities.get("airline"))),
        "is_ts_inp":          int("TS-INP" in (entities.get("aircraft_registration") or "")),
        "is_ts_inq":          int("TS-INQ" in (entities.get("aircraft_registration") or "")),
        "doc_ref_is_ad":      int(doc_ref.upper().startswith("AD")),
        "doc_ref_is_sb":      int(doc_ref.upper().startswith("SB")),
    }


def _empty_entities() -> dict:
    return {
        "aircraft_registration": None,
        "es_reference":          None,
        "ata_chapter":           None,
        "part_number":           None,
        "serial_number":         None,
        "doc_ref":               None,
        "document_date":         None,
        "airline":               None,
    }
