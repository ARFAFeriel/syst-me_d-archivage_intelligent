"""
Agent NER v6 — LLM-powered (Groq/Llama 3.1) + Regex fallback
Extraction intelligente d'entités aéronautiques MRO
"""
import re
import json
import os
from typing import Optional
from loguru import logger
from backend.schemas.document import NERResult
from backend.core.processing_profiles import ProcessingProfile, NER_PATTERNS as PROFILE_NER_PATTERNS


# ── Prompt NER spécialisé MRO NouvelAir ──────────────────────────────────────
NER_SYSTEM_PROMPT = """Tu es un expert en documentation MRO (Maintenance, Repair & Overhaul) aéronautique.
Tu travailles pour NouvelAir, une compagnie aérienne tunisienne opérant des Airbus A320.
Les immatriculations de la flotte sont : TS-INP (MSN 2158) et TS-INQ (MSN 3012).

Ton rôle : extraire des entités structurées depuis du texte OCR de documents MRO.

Règles d'extraction :
- aircraft_registration : immatriculation avion (format TS-XXX). Cherche sous les mots "A/C", "IMMATRICULATION", "FSN:", "TAIL NUMBER". Priorité à TS-INP et TS-INQ.
- es_reference : référence ES (format ES + 6-8 chiffres, ex: ES154313). Aussi sous "FSN:", "N° TRAVAUX".
- ata_chapter : chapitre ATA (format ATA XX ou XX-XX, ex: ATA 27, 32-00).
- doc_type : type de document parmi [Work Order, Jobcard, AD, SB, AMM, CMM, Specs, Certificate, RCT, ATL, D&B Chart, Other].
- category : catégorie parmi [Check A, Check C, Check D, AD, SB, AMM, CMM, IPC, Specs, Certificates, Structural Repair, Engine File, ATL, Correspondence, Weight & Balance].
- part_number : numéro de pièce (P/N ou PN).
- serial_number : numéro de série (S/N ou SN ou MSN).
- work_order_number : numéro de work order (WO ou W/O).
- document_date : date du document (format DD/MM/YYYY ou YYYY-MM-DD).
- sb_ad_reference : référence SB ou AD (ex: A320-27-1234, AD 2023-01-02).

Réponds UNIQUEMENT avec un JSON valide, sans texte avant ou après.
Si une entité n'est pas trouvée, utilise null.
Format exact :
{
  "aircraft_registration": "TS-INQ",
  "es_reference": "ES154313",
  "ata_chapter": "ATA 27",
  "doc_type": "Work Order",
  "category": "Check A",
  "part_number": null,
  "serial_number": null,
  "work_order_number": null,
  "document_date": null,
  "sb_ad_reference": null,
  "confidence": 0.95
}"""

NER_USER_PROMPT = """Nom du fichier : {filename}

Texte OCR (première page) :
{ocr_text}

Extrais toutes les entités MRO présentes."""


# ── Patterns Regex (fallback) ─────────────────────────────────────────────────
PATTERNS = {
    "aircraft_registration": [
        # Format complet standard
        r"\b(TS-IN[A-Z])\b",
        r"\b(TS-[A-Z]{3})\b",
        # Après IMMATRICULATION
        r"IMMATRICULATION[\s:.-]*\n?[^\n]{0,30}(TS-IN[A-Z])",
        # Après A/C sur la même ligne ou ligne suivante
        r"A/?C[\s:.-]*\n[!\s]*(TS-IN[A-Z])\b",
        r"A/?C[\s:.-]*\n[!\s]*(IN[A-Z])\b",
        r"A/?C[\s:.-]*\n[!\s]*([A-Z]{2})\b",
        r"A/?C[\s:.-]+([A-Z]{2})\b",
        # FSN / TAIL
        r"FSN[\s:.-]*\n?[^\n]{0,50}\(?(TS-IN[A-Z])\)?",
        r"(?:TAIL\s+NUMBER|FSN\s*:)[^\n]*\n[^\n]*(TS-IN[A-Z])",
        r"(?:AIRCRAFT|REG(?:ISTRATION)?)[\s:.-]+(TS-IN[A-Z])",
        # Patterns OCR dégradé — caractères mal lus
        r"![!\s]*(IN[A-Z])\b",
        r"!([NQ]{2}|NP|NO|NI|NH|NG|NF|NE|ND|NC|NB|NM|NL|NK|NJ|NN|NR|NT|NU)\b",
        # "OENQ" → NQ, "OENp" → NP (O/E mal lus à la place de I)
        r"[OoEe]{1,2}(NQ|NP|NO|NI|NM|NN|NR)\b",
        # Lignes OCR dégradées type "tA/C" ou "!A/C"
        r"[t!|i][A/?C\s]*\n[t!|i\s]*(N[A-Z])\b",
        r"A/?C[^\n]*\n[^\n]{0,5}(N[OPQRSTU])\b",
        r"\b(N[OPQRSTU])\b(?=\s*\n|\s*!)",
        # INQ / INP seuls
        r"\b(IN[A-Z])\b",
    ],
    "es_reference": [
        r"\b(ES\s*\d{6,8})\b",
        r"WORK\s+ORDER\s+No[\s:.-]*(ES[\s]?\d{6,8})",
        r"\bES[\s-]?(\d{6,8})\b",
        r"FSN[\s:.-]+([A-Z]{0,2}\d{6,8})\b",
    ],
    "part_number": [
        r"P/?N[\s:.-]+([A-Z0-9][-A-Z0-9]{3,30})",
        r"PART\s+NO?\.?\s*:?\s*([A-Z0-9][-A-Z0-9]{3,30})",
    ],
    "serial_number": [
        r"S/?N[\s:.-]+([A-Z0-9][-A-Z0-9]{2,20})",
        r"MSN[\s:.-]+(\d{3,6})",
    ],
    "ata_chapter": [
        r"ATA[\s-]+(\d{2}[-\d]{0,5})",
        r"CHAPTER[\s:]+(\d{2}[-\d]{0,5})",
    ],
    "work_order_number": [
        r"WORK\s+ORDER[\s:.-]+([A-Z0-9-]{4,20})",
        r"W/?O[\s:.-]+([A-Z0-9-]{4,20})",
    ],
    "sb_ad_reference": [
        r"\b(A3[0-9]{2}-\d{2}-\d{3,5}[A-Z]?)\b",
        r"\b(AD[\s]?\d{4}-\d{2}-\d{2,4})\b",
    ],
    "item_number": [
        r"ITEM[\s:.-]+(\d{1,6})",
        r"CARD\s+NO?\.?[\s:.-]+(\d{1,6})",
    ],
    "document_date": [
        r"DATE[\s:.-]+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        r"(\d{1,2}[/-]\d{1,2}[/-]\d{4})",
        r"(\d{4}-\d{2}-\d{2})",
    ],
    "effectivity": [
        r"EFFECTIV(?:ITY|E)[\s:.-]+([A-Z0-9,\s-]{3,50})",
    ],
}

_FLAGS = re.IGNORECASE | re.MULTILINE
COMPILED_PATTERNS = {
    field: [re.compile(p, _FLAGS) for p in patterns]
    for field, patterns in PATTERNS.items()
}

FLEET_REGISTRATIONS = sorted([
    "TS-INB", "TS-INC", "TS-IND", "TS-INE", "TS-INF", "TS-ING",
    "TS-INH", "TS-INI", "TS-INJ", "TS-INK", "TS-INL", "TS-INM",
    "TS-INN", "TS-INO", "TS-INP", "TS-INQ", "TS-INR", "TS-INT", "TS-INU",
])
ACTIVE_REGISTRATIONS = ["TS-INP", "TS-INQ"]

AC_SUFFIX_MAP = {s: f"TS-I{s}" for s in [
    "NB","NC","ND","NE","NF","NG","NH","NI","NJ","NK",
    "NL","NM","NN","NO","NP","NQ","NR","NT","NU",
]}

ATA_MAP = {
    "05": "Time Limits", "21": "Air Conditioning", "22": "Auto Flight",
    "23": "Communications", "24": "Electrical Power", "25": "Equipment",
    "26": "Fire Protection", "27": "Flight Controls", "28": "Fuel",
    "29": "Hydraulic Power", "30": "Ice Protection", "31": "Instruments",
    "32": "Landing Gear", "33": "Lights", "34": "Navigation",
    "49": "APU", "51": "Structures", "52": "Doors", "53": "Fuselage",
    "71": "Power Plant", "72": "Engine", "79": "Oil",
}

_RE_ITEM_FILENAME = re.compile(r"^(\d{3,4})(?:\.pdf)?$", re.IGNORECASE)
_RE_ES_FILENAME   = re.compile(r"(ES\d{6,8})", re.IGNORECASE)
_RE_SB_FILENAME   = re.compile(r"(A3\d{2}-\d{2}-\d{3,5}[A-Z]?)", re.IGNORECASE)
_RE_ATA_FILENAME  = re.compile(r"ATA[\s-]?(\d{2})", re.IGNORECASE)
_RCT_FILENAME_RE  = re.compile(
    r"(TS-[A-Z]{3})_CHECK\s*([ABCD])_([A-Z]{0,2}\d{4,8})_RCT", re.IGNORECASE)
_RCT_WP_PATTERNS = [
    re.compile(r"WORK\s*PACKAGE\s*REF\s*[:\s]+([A-Z]{0,2}\d{4,8})", re.IGNORECASE),
    re.compile(r"W\.?P\.?\s*REF\s*[:\s]+([A-Z]{0,2}\d{4,8})", re.IGNORECASE),
]
_RCT_CHECK_PATTERNS = [
    re.compile(r'\bCHECK\s*([ABCD])\b', re.IGNORECASE),
    re.compile(r'\bVISITE\s*([ABCD])\b', re.IGNORECASE),
]


def _normalize_registration(val: str) -> Optional[str]:
    """
    Normalise une immatriculation partielle ou dégradée en format complet TS-XXX.
    Gère les cas OCR : "NQ" → "TS-INQ", "INQ" → "TS-INQ", "OENQ" → "TS-INQ"
    """
    val = val.upper().strip()
    # Déjà complet
    if val in FLEET_REGISTRATIONS:
        return val
    # Format "NQ", "NP" → "TS-INQ", "TS-INP"
    if re.match(r'^N[A-Z]$', val):
        candidate = f"TS-I{val}"
        if candidate in FLEET_REGISTRATIONS:
            return candidate
    # Format "INQ", "INP" → "TS-INQ", "TS-INP"
    if re.match(r'^IN[A-Z]$', val):
        candidate = f"TS-{val}"
        if candidate in FLEET_REGISTRATIONS:
            return candidate
    # Format dégradé OCR : "OENQ", "ENQ", "OeNQ" → "TS-INQ"
    if re.match(r'^[OoEe]{1,2}N[A-Z]$', val):
        candidate = f"TS-I{val[-2:]}"
        if candidate in FLEET_REGISTRATIONS:
            return candidate
    # Via AC_SUFFIX_MAP
    suffix = val[-2:] if len(val) >= 2 else ""
    if suffix in AC_SUFFIX_MAP:
        return AC_SUFFIX_MAP[suffix]
    return None


class NERAgent:
    """Agent NER v6 — LLM (Groq) + Regex fallback."""

    def __init__(self):
        self.name = "NER Agent v6 (LLM)"
        self._nlp = None
        self._groq_client = None
        self._groq_available = None
        self._init_groq()
        logger.info(f"[{self.name}] Initialisé")

    def _init_groq(self):
        try:
            from groq import Groq
            api_key = os.getenv("GROQ_API_KEY")
            if api_key:
                self._groq_client = Groq(api_key=api_key)
                self._groq_available = True
                logger.info(f"[{self.name}] Groq API initialisée (llama-3.1-8b-instant)")
            else:
                logger.warning(f"[{self.name}] GROQ_API_KEY non définie — mode regex uniquement")
                self._groq_available = False
        except ImportError:
            logger.warning(f"[{self.name}] groq non installé — mode regex uniquement")
            self._groq_available = False

    def _get_nlp(self):
        if self._nlp is None:
            try:
                import spacy
                from backend.config import settings
                custom = __import__('pathlib').Path('models/ner_nouvelair_best')
                self._nlp = spacy.load(str(custom)) if custom.exists() else spacy.load(settings.spacy_model)
            except Exception as e:
                logger.warning(f"[{self.name}] spaCy non disponible: {e}")
                self._nlp = False
        return self._nlp if self._nlp else None

    async def _extract_with_llm(self, text: str, filename: str) -> Optional[dict]:
        if not self._groq_available or not self._groq_client:
            return None
        try:
            ocr_excerpt = text[:2000].strip()
            prompt = NER_USER_PROMPT.format(filename=filename, ocr_text=ocr_excerpt)
            response = self._groq_client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {"role": "system", "content": NER_SYSTEM_PROMPT},
                    {"role": "user",   "content": prompt},
                ],
                max_tokens=400,
                temperature=0.1,
            )
            raw = response.choices[0].message.content.strip()
            raw = re.sub(r"```json|```", "", raw).strip()
            result = json.loads(raw)
            logger.info(f"[{self.name}] LLM extraction OK — confiance: {result.get('confidence', '?')}")
            return result
        except json.JSONDecodeError as e:
            logger.warning(f"[{self.name}] LLM JSON invalide: {e}")
            return None
        except Exception as e:
            logger.warning(f"[{self.name}] Groq erreur: {e} — fallback regex")
            self._groq_available = False
            return None

    def _extract_with_regex(self, text: str, filename: str) -> dict:
        """Extraction NER via regex (fallback)."""
        text_upper = text.upper()
        fn_upper   = filename.upper()
        extracted  = {}

        # ── Immatriculation — priorité 1 : filename ───────────────────────
        reg = None
        for r in ACTIVE_REGISTRATIONS:
            if r in fn_upper:
                reg = r; break
        if not reg:
            for r in FLEET_REGISTRATIONS:
                if r in fn_upper:
                    reg = r; break

        # ── Immatriculation — priorité 2 : texte exact ────────────────────
        if not reg:
            for r in ACTIVE_REGISTRATIONS:
                if r in text_upper:
                    reg = r; break
        if not reg:
            for r in FLEET_REGISTRATIONS:
                if r in text_upper:
                    reg = r; break

        # ── Immatriculation — priorité 3 : OCR dégradé ───────────────────
        if not reg:
            # Patterns OCR bruités : "ENQ", "OENQ", "tA/C\nINQ" etc.
            degraded_patterns = [
                r'\b[EtTiI!][N][OPQRSTU]\b',         # ENQ, tNQ, !NQ
                r'\b[OoEe]{1,2}N[OPQRSTU]\b',         # OENQ, ENP
                r'(?:A/?C|A\/C)[^\n]*\n[^\n]{0,10}(IN[A-Z])',  # A/C \n INQ
                r'(?:A/?C|A\/C)[^\n]*\n[^\n]{0,5}([NQ]{2}|NP|NO)\b',
            ]
            for dp in degraded_patterns:
                m = re.search(dp, text, re.IGNORECASE | re.MULTILINE)
                if m:
                    raw = m.group(0) if not m.lastindex else m.group(m.lastindex)
                    normalized = _normalize_registration(raw)
                    if normalized:
                        reg = normalized
                        break

        # ── Immatriculation — priorité 4 : patterns compilés ─────────────
        if not reg:
            for pattern in COMPILED_PATTERNS.get("aircraft_registration", []):
                matches = pattern.findall(text)
                if matches:
                    val = matches[0] if isinstance(matches[0], str) else matches[0][0]
                    normalized = _normalize_registration(val.strip())
                    if normalized:
                        reg = normalized
                        break

        if reg:
            extracted["aircraft_registration"] = reg

        # ── Autres champs via regex ───────────────────────────────────────
        for field, compiled_list in COMPILED_PATTERNS.items():
            if field == "aircraft_registration":
                continue
            for pattern in compiled_list:
                matches = pattern.findall(text_upper)
                if matches:
                    val = matches[0] if isinstance(matches[0], str) else matches[0][0]
                    extracted[field] = val.strip()
                    break

        return extracted

    async def process(self, text: str, filename: str = "",
                      profile: Optional[ProcessingProfile] = None) -> NERResult:
        if not text:
            return NERResult()

        logger.info(f"[{self.name}] Extraction NER: {filename}")
        raw_entities: dict = {}
        extracted: dict = {}

        # ── 1. Tentative LLM (Groq) ───────────────────────────────────────
        llm_result = await self._extract_with_llm(text, filename)

        if llm_result:
            field_map = {
                "aircraft_registration": "aircraft_registration",
                "es_reference":          "es_reference",
                "ata_chapter":           "ata_chapter",
                "part_number":           "part_number",
                "serial_number":         "serial_number",
                "work_order_number":     "work_order_number",
                "sb_ad_reference":       "sb_ad_reference",
                "document_date":         "document_date",
            }
            for llm_key, ner_key in field_map.items():
                val = llm_result.get(llm_key)
                if val and val != "null":
                    extracted[ner_key] = str(val).strip()
                    raw_entities[ner_key] = [str(val).strip()]

            if llm_result.get("category"):
                raw_entities["llm_category"] = [llm_result["category"]]
            if llm_result.get("doc_type"):
                raw_entities["llm_doc_type"] = [llm_result["doc_type"]]
            if llm_result.get("confidence"):
                raw_entities["llm_confidence"] = [str(llm_result["confidence"])]

            raw_entities["ner_method"] = ["LLM (Groq llama-3.1-8b-instant)"]
            logger.info(f"[{self.name}] Méthode: LLM")
        else:
            # ── 2. Fallback Regex ─────────────────────────────────────────
            extracted = self._extract_with_regex(text, filename)
            raw_entities["ner_method"] = ["Regex fallback"]
            logger.info(f"[{self.name}] Méthode: Regex fallback")

        # ── 3. Enrichissement depuis filename (toujours appliqué) ─────────
        if not extracted.get("es_reference"):
            m = _RE_ES_FILENAME.search(filename)
            if m:
                extracted["es_reference"] = m.group(1).upper()

        if not extracted.get("item_number"):
            m = _RE_ITEM_FILENAME.match(filename)
            if m:
                extracted["item_number"] = m.group(1)

        if not extracted.get("sb_ad_reference"):
            m = _RE_SB_FILENAME.search(filename)
            if m:
                extracted["sb_ad_reference"] = m.group(1).upper()

        if not extracted.get("ata_chapter"):
            m = _RE_ATA_FILENAME.search(filename)
            if m:
                extracted["ata_chapter"] = f"ATA {m.group(1)}"

        # ── 4. Normalisation ATA ──────────────────────────────────────────
        if "ata_chapter" in extracted:
            ata_num = re.search(r"(\d{2})", extracted["ata_chapter"])
            if ata_num and ata_num.group(1) in ATA_MAP:
                raw_entities["ata_description"] = ATA_MAP[ata_num.group(1)]

        # ── 5. Extraction RCT anchor ──────────────────────────────────────
        linked_wp: Optional[str] = None
        check_type: Optional[str] = None

        m = _RCT_FILENAME_RE.search(filename)
        if m:
            if not extracted.get("aircraft_registration"):
                normalized = _normalize_registration(m.group(1))
                extracted["aircraft_registration"] = normalized or m.group(1).upper()
            check_type = f"CHECK_{m.group(2).upper()}"
            linked_wp  = m.group(3).upper()

        if not linked_wp:
            for pat in _RCT_WP_PATTERNS:
                m = pat.search(text)
                if m:
                    linked_wp = m.group(1).upper()
                    break

        if not check_type:
            for pat in _RCT_CHECK_PATTERNS:
                m = pat.search(text)
                if m:
                    check_type = f"CHECK_{m.group(1).upper()}"
                    break

        if linked_wp:
            raw_entities["linked_wp"] = [linked_wp]
        if check_type:
            raw_entities["check_type"] = [check_type]

        # ── 6. Normalisation finale immatriculation ───────────────────────
        reg = extracted.get("aircraft_registration")
        if reg:
            normalized = _normalize_registration(reg)
            if normalized:
                extracted["aircraft_registration"] = normalized

        logger.info(
            f"[{self.name}] Entités: {list(extracted.keys())} | "
            f"Méthode: {raw_entities.get('ner_method', ['?'])[0]}"
        )

        return NERResult(
            aircraft_registration=extracted.get("aircraft_registration"),
            es_reference=extracted.get("es_reference"),
            item_number=extracted.get("item_number"),
            part_number=extracted.get("part_number"),
            serial_number=extracted.get("serial_number"),
            work_order_number=extracted.get("work_order_number"),
            sb_ad_reference=extracted.get("sb_ad_reference"),
            ata_chapter=extracted.get("ata_chapter"),
            document_date=extracted.get("document_date"),
            effectivity=extracted.get("effectivity"),
            raw_entities=raw_entities,
            linked_wp=linked_wp,
            check_type=check_type,
        )

    def infer_aircraft_from_path(self, file_path: str) -> Optional[str]:
        path_upper = file_path.upper().replace("\\", "/")
        for reg in ACTIVE_REGISTRATIONS + FLEET_REGISTRATIONS:
            if f"/{reg}/" in path_upper or reg in path_upper:
                return reg
        return None

    def infer_category_from_path(self, file_path: str) -> tuple[str, str]:
        parts = file_path.replace("\\", "/").split("/")
        category, subcategory = "", ""
        category_keywords = {
            "CHECK A": "Check A", "CHECK-A": "Check A",
            "CHECK C": "Check C", "CHECK-C": "Check C",
            "CHECK D": "Check D", "ATL": "ATL", "SB": "SB",
            "SERVICE BULLETIN": "SB", "AD": "AD", "AIRWORTHINESS": "AD",
            "SPECS": "Specs", "STRUCTURAL REPAIR": "Structural Repair",
            "WEIGHT": "Weight & Balance", "OLD DOC": "Delivery Package",
        }
        subcategory_keywords = {
            "JOBCARD": "Jobcard", "JOB CARD": "Jobcard",
            "WORKORDER": "Work Order", "WORK ORDER": "Work Order",
            "DEFECT REPORT": "Defect Report", "NCR": "NCR",
            "RCT": "RCT", "D&B": "D&B Chart",
        }
        for part in parts:
            pu = part.upper()
            for kw, cat in category_keywords.items():
                if kw in pu:
                    category = cat; break
            for kw, sub in subcategory_keywords.items():
                if kw in pu:
                    subcategory = sub; break
        return category, subcategory