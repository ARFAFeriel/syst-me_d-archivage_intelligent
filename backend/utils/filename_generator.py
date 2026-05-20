"""
backend/utils/filename_generator.py
Génère un nom de fichier normalisé depuis les résultats NER + Classifier.

Format : {AVION}_{CATEGORIE}_{SOUS_CAT}_{REFERENCE}.pdf

Exemples :
  TS-INQ_Check_A_Work_Order_ES154313.pdf
  TS-INQ_AD_ES152173.pdf
  TS-INP_Structural_Repair_DB_Chart_R001.pdf
  TS-INQ_Check_A_Jobcard_0015.pdf
  TS-INQ_SB_SB22-1360.pdf
  TS-INQ_Certificates_Certificate_ES001019.pdf
"""
import re


# ── Mapping type document → nom court normalisé ───────────────────────────────
TYPE_LABEL = {
    "WORK_ORDER":     "Work_Order",
    "JOBCARD":        "Jobcard",
    "AD":             "AD",
    "SB":             "SB",
    "AMM":            "AMM",
    "CMM":            "CMM",
    "IPC":            "IPC",
    "SPECS":          "Specs",
    "CERTIFICATE":    "Certificate",
    "DEFECT_REPORT":  "Defect_Report",
    "NCR":            "NCR",
    "RCT":            "RCT",
    "ATL":            "ATL",
    "DB_CHART":       "DB_Chart",
    "OTHER":          "Doc",
}

# ── Mapping catégorie → nom normalisé ─────────────────────────────────────────
CAT_LABEL = {
    "Check A":          "Check_A",
    "Check C":          "Check_C",
    "Check D":          "Check_D",
    "AD":               "AD",
    "SB":               "SB",
    "AMM":              "AMM",
    "CMM":              "CMM",
    "IPC":              "IPC",
    "Specs":            "Specs",
    "Certificates":     "Certificates",
    "Structural Repair":"Structural_Repair",
    "Engine File":      "Engine_File",
    "Correspondence":   "Correspondence",
    "Weight & Balance": "Weight_Balance",
    "ATL":              "ATL",
}

# ── Référence principale selon le type de document ───────────────────────────
def _get_reference(doc_type: str, ner: dict) -> str:
    """Retourne la référence principale selon le type de document."""
    dt = (doc_type or "").upper()

    if dt in ("WORK_ORDER", "RCT"):
        # ES Reference est la référence principale
        return ner.get("es_reference") or ner.get("work_order_number") or ""

    if dt == "JOBCARD":
        # Item number ou ES reference
        return ner.get("item_number") or ner.get("es_reference") or ""

    if dt in ("AD", "SB"):
        # Référence AD/SB ou ES reference
        ref = ner.get("sb_ad_reference") or ner.get("es_reference") or ""
        # Nettoyer les caractères problématiques
        ref = re.sub(r"[/\\]", "-", ref)
        return ref

    if dt == "DB_CHART":
        # Référence depuis le nom original (R001, R0046...)
        ref = ner.get("sb_ad_reference") or ner.get("item_number") or ""
        return ref

    if dt == "CERTIFICATE":
        return ner.get("es_reference") or ner.get("serial_number") or ""

    if dt in ("AMM", "CMM", "IPC", "SPECS"):
        return ner.get("ata_chapter", "").replace("ATA ", "ATA") or ner.get("es_reference") or ""

    if dt == "DEFECT_REPORT":
        return ner.get("es_reference") or ner.get("item_number") or ""

    # Fallback
    return ner.get("es_reference") or ner.get("item_number") or ""


def _clean(s: str) -> str:
    """Nettoie une chaîne pour un nom de fichier valide."""
    if not s:
        return ""
    # Remplacer espaces et caractères spéciaux
    s = re.sub(r"[\s/\\:*?\"<>|]", "_", s.strip())
    # Supprimer les underscores multiples
    s = re.sub(r"_+", "_", s)
    return s.strip("_")


def generate_filename(
    aircraft: str,
    doc_type: str,
    category: str,
    ner: dict,
    original_filename: str = "",
) -> str:
    """
    Génère un nom de fichier normalisé.

    Args:
        aircraft: Immatriculation (ex: TS-INQ)
        doc_type: Type document enum (ex: WORK_ORDER)
        category: Catégorie (ex: Check A)
        ner: Dict des entités NER extraites
        original_filename: Nom original (fallback)

    Returns:
        Nom de fichier normalisé (sans extension)
    """
    parts = []

    # 1. Avion
    if aircraft:
        parts.append(_clean(aircraft.upper()))
    else:
        parts.append("UNKNOWN")

    # 2. Catégorie
    cat_norm = CAT_LABEL.get(category, _clean(category)) if category else ""
    if cat_norm:
        parts.append(cat_norm)

    # 3. Type document
    dt_upper = (doc_type or "").upper().split(".")[-1]
    type_norm = TYPE_LABEL.get(dt_upper, _clean(doc_type) if doc_type else "")
    if type_norm and type_norm != cat_norm:  # Éviter doublon si type == catégorie
        parts.append(type_norm)

    # 4. Référence principale
    ref = _get_reference(dt_upper, ner)
    ref_clean = _clean(ref)
    if ref_clean:
        parts.append(ref_clean)

    # Assembler
    name = "_".join(p for p in parts if p)

    # Fallback si trop vide
    if not name or len(name) < 5:
        base = re.sub(r"\.[^.]+$", "", original_filename)
        name = _clean(base) or "Document"

    return name + ".pdf"


def generate_filename_from_pipeline(pipeline_result: dict, original_filename: str = "") -> str:
    """
    Interface haut niveau depuis un résultat pipeline complet.

    Args:
        pipeline_result: Dict avec ner, classification, etc.
        original_filename: Nom original du fichier

    Returns:
        Nom de fichier suggéré
    """
    ner = pipeline_result.get("ner") or {}
    cls = pipeline_result.get("classification") or {}

    aircraft = ner.get("aircraft_registration", "")
    doc_type = cls.get("predicted_type", "")
    category = cls.get("predicted_category", "")

    # Récupérer aussi les infos LLM si disponibles
    raw = ner.get("raw_entities") or {}
    if raw.get("llm_doc_type") and not doc_type:
        doc_type = raw["llm_doc_type"][0] if isinstance(raw["llm_doc_type"], list) else raw["llm_doc_type"]
    if raw.get("llm_category") and not category:
        category = raw["llm_category"][0] if isinstance(raw["llm_category"], list) else raw["llm_category"]

    return generate_filename(aircraft, doc_type, category, ner, original_filename)