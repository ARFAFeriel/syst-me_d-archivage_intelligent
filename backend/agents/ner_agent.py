"""
Agent NER v6 - LLM-powered (Groq/Llama 3.1) + Regex fallback
Extraction intelligente d'entites aeronautiques MRO
"""
import re
import json
import os
from typing import Optional
from loguru import logger
from backend.schemas.document import NERResult
from backend.core.processing_profiles import ProcessingProfile, NER_PATTERNS as PROFILE_NER_PATTERNS


# Prompt NER specialise MRO NouvelAir
NER_SYSTEM_PROMPT = """Tu es un expert en documentation MRO (Maintenance, Repair & Overhaul) aeronautique.
Tu travailles pour NouvelAir, une compagnie aerienne tunisienne operant des Airbus A320.

Les immatriculations de la flotte NouvelAir avec leurs MSN :
TS-INB (MSN 3312), TS-INC (MSN 1744), TS-IND (MSN 5016), TS-INE (MSN 5310),
TS-INF (MSN 5867), TS-ING (MSN 5878), TS-INH (MSN 4623), TS-INI (MSN 3508),
TS-INJ (MSN 13178), TS-INK (MSN 4564), TS-INL (MSN 12280), TS-INM (MSN 12308),
TS-INO (MSN 6285), TS-INP (MSN 1597), TS-INQ (MSN 2158), TS-INR (MSN 3487),
TS-INT (MSN 3798), TS-INU (MSN 3827).
Si tu vois un MSN dans le texte (ex: MSN 2158, 002158, S/N 2158), deduis l immatriculation correspondante.

IMPORTANT - Format des formulaires de maintenance NouvelAir :
Les tableaux utilisent le caractere "!" comme delimiteur de colonne.
Exemple : une ligne "!A/C" suivie de "!NQ" signifie que l avion est NQ = TS-INQ.
Exemple : "!A/C ... !NP" signifie TS-INP.
Ne confonds PAS "!" avec un caractere OCR degrade - c est un separateur de tableau.
Les suffixes valides apres "!" sont : NB, NC, ND, NE, NF, NG, NH, NI, NJ, NK, NL, NM, NN, NO, NP, NQ, NR, NT, NU.
Donc "!NQ" = TS-INQ, "!NP" = TS-INP, "!NO" = TS-INO, etc.

Ton role : extraire des entites structurees depuis du texte OCR de documents MRO.

Regles d extraction :
- aircraft_registration : immatriculation avion (format TS-XXX).
  Cherche sous "A/C", "IMMATRICULATION", "FSN:", "TAIL NUMBER".
  Cherche aussi le pattern "!NX" apres une ligne "!A/C" (format tableau NouvelAir).
  Deduis depuis MSN si present.
- es_reference : reference ES (format ES + 6-8 chiffres, ex: ES154313). Aussi sous "FSN:", "N TRAVAUX".
- ata_chapter : chapitre ATA (format ATA XX ou XX-XX, ex: ATA 27, 32-00).
- doc_type : type de document parmi [Work Order, Jobcard, AD, SB, AMM, CMM, Specs, Certificate, RCT, ATL, D&B Chart, Other].
- category : categorie parmi [Check A, Check C, Check D, AD, SB, AMM, CMM, IPC, Specs, Certificates, Structural Repair, Engine File, ATL, Correspondence, Weight & Balance].
- part_number : numero de piece (P/N ou PN).
- serial_number : numero de serie (S/N ou SN ou MSN).
- work_order_number : numero de work order (WO ou W/O).
- document_date : date du document (format DD/MM/YYYY ou YYYY-MM-DD).
- sb_ad_reference : reference SB ou AD (ex: A320-27-1234, AD 2023-01-02).

Reponds UNIQUEMENT avec un JSON valide, sans texte avant ou apres.
Si une entite n est pas trouvee, utilise null.
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

Texte OCR (premiere page) :
{ocr_text}

Extrais toutes les entites MRO presentes."""


# Patterns Regex (fallback)
PATTERNS = {
    "aircraft_registration": [
        r"\b(TS-IN[A-Z])\b",
        r"\b(TS-[A-Z]{3})\b",
        r"IMMATRICULATION[\s:.-]*\n?[^\n]{0,30}(TS-IN[A-Z])",
        r"A/?C[\s:.-]*\n[!\s]*(TS-IN[A-Z])\b",
        r"A/?C[\s:.-]*\n[!\s]*(IN[A-Z])\b",
        r"A/?C[\s:.-]*\n[!\s]*([A-Z]{2})\b",
        r"A/?C[\s:.-]+([A-Z]{2})\b",
        r"FSN[\s:.-]*\n?[^\n]{0,50}\(?(TS-IN[A-Z])\)?",
        r"(?:TAIL\s+NUMBER|FSN\s*:)[^\n]*\n[^\n]*(TS-IN[A-Z])",
        r"(?:AIRCRAFT|REG(?:ISTRATION)?)[\s:.-]+(TS-IN[A-Z])",
        # Format tableau NouvelAir : !NQ, !NP, !NO
        r"!A/?C[^\n]*\n![!\s]*(N[OPQRSTU])\b",
        r"^!(N[OPQRSTU])\b",
        r"![!\s]*(IN[A-Z])\b",
        r"!([NQ]{2}|NP|NO|NI|NH|NG|NF|NE|ND|NC|NB|NM|NL|NK|NJ|NN|NR|NT|NU)\b",
        r"[OoEe]{1,2}(NQ|NP|NO|NI|NM|NN|NR)\b",
        r"[t!|i][A/?C\s]*\n[t!|i\s]*(N[A-Z])\b",
        r"A/?C[^\n]*\n[^\n]{0,5}(N[OPQRSTU])\b",
        r"\b(N[OPQRSTU])\b(?=\s*\n|\s*!)",
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

# Table MSN -> Immatriculation NouvelAir
MSN_TO_REGISTRATION = {
    "3312":  "TS-INB",
    "1744":  "TS-INC",
    "5016":  "TS-IND",
    "5310":  "TS-INE",
    "5867":  "TS-INF",
    "5878":  "TS-ING",
    "4623":  "TS-INH",
    "3508":  "TS-INI",
    "13178": "TS-INJ",
    "4564":  "TS-INK",
    "12280": "TS-INL",
    "12308": "TS-INM",
    "6285":  "TS-INO",
    "1597":  "TS-INP",
    "2158":  "TS-INQ",
    "3487":  "TS-INR",
    "3798":  "TS-INT",
    "3827":  "TS-INU",
}

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

# Pattern specifique format tableau NouvelAir : !A/C\n!NQ
_RE_TABLEAU_AC = re.compile(
    r'!A/?C[^\n]*\n[^\n]{0,5}!(N[BCDEFINOPRTU])\b',
    re.IGNORECASE | re.MULTILINE
)


def _resolve_msn(text: str) -> Optional[str]:
    """
    Cherche un MSN dans le texte OCR et retourne l immatriculation correspondante.
    Gere les formats : MSN 2158, MSN: 002158, 002158 (NQ), S/N 2158, etc.
    """
    msn_patterns = [
        r"MSN[\s:.-]*0*(\d{3,5})\b",
        r"\b0{0,3}(\d{3,5})\s*\([Nn][A-Z]\)",
        r"S/?N[\s:.-]*MSN[\s:.-]*0*(\d{3,5})\b",
        r"\bMSN\s*[:\s]\s*0*(\d{3,5})\b",
    ]
    for pattern in msn_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            msn = match.group(1).lstrip("0") or "0"
            if msn in MSN_TO_REGISTRATION:
                reg = MSN_TO_REGISTRATION[msn]
                logger.info(f"[NER] MSN {msn} resolu -> {reg}")
                return reg
    return None


def _resolve_tableau_format(text: str) -> Optional[str]:
    """
    Detecte le format tableau NouvelAir : ligne !A/C suivie de !NX.
    Ex: "!A/C    P/N\n!NQ     980-6022-001" -> TS-INQ
    """
    m = _RE_TABLEAU_AC.search(text)
    if m:
        suffix = m.group(1).upper()
        candidate = f"TS-I{suffix}"
        if candidate in FLEET_REGISTRATIONS:
            logger.info(f"[NER] Format tableau NouvelAir detecte: !{suffix} -> {candidate}")
            return candidate
    # Pattern simplifie : ligne commencant par !NX apres A/C
    lines = text.split('\n')
    ac_found = False
    for line in lines:
        line_clean = line.strip()
        if re.search(r'!?A/?C\b', line_clean, re.IGNORECASE):
            ac_found = True
            continue
        if ac_found:
            m2 = re.match(r'^!(N[BCDEFINOPRTU])\b', line_clean, re.IGNORECASE)
            if m2:
                suffix = m2.group(1).upper()
                candidate = f"TS-I{suffix}"
                if candidate in FLEET_REGISTRATIONS:
                    logger.info(f"[NER] Format tableau ligne suivante: !{suffix} -> {candidate}")
                    return candidate
            ac_found = False
    return None


def _normalize_registration(val: str) -> Optional[str]:
    """
    Normalise une immatriculation partielle ou degradee en format complet TS-XXX.
    """
    val = val.upper().strip()
    if val in FLEET_REGISTRATIONS:
        return val
    if re.match(r'^N[A-Z]$', val):
        candidate = f"TS-I{val}"
        if candidate in FLEET_REGISTRATIONS:
            return candidate
    if re.match(r'^IN[A-Z]$', val):
        candidate = f"TS-{val}"
        if candidate in FLEET_REGISTRATIONS:
            return candidate
    if re.match(r'^[OoEe]{1,2}N[A-Z]$', val):
        candidate = f"TS-I{val[-2:]}"
        if candidate in FLEET_REGISTRATIONS:
            return candidate
    suffix = val[-2:] if len(val) >= 2 else ""
    if suffix in AC_SUFFIX_MAP:
        return AC_SUFFIX_MAP[suffix]
    return None


class NERAgent:
    """Agent NER v6 - LLM (Groq) + Regex fallback + MSN/tableau resolution."""

    def __init__(self):
        self.name = "NER Agent v6 (LLM)"
        self._nlp = None
        self._groq_client = None
        self._groq_available = None
        self._init_groq()
        logger.info(f"[{self.name}] Initialise")

    def _init_groq(self):
        try:
            from groq import Groq
            api_key = os.getenv("GROQ_API_KEY")
            if api_key:
                self._groq_client = Groq(api_key=api_key)
                self._groq_available = True
                logger.info(f"[{self.name}] Groq API initialisee (llama-3.1-8b-instant)")
            else:
                logger.warning(f"[{self.name}] GROQ_API_KEY non definie - mode regex uniquement")
                self._groq_available = False
        except ImportError:
            logger.warning(f"[{self.name}] groq non installe - mode regex uniquement")
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
            logger.info(f"[{self.name}] LLM extraction OK - confiance: {result.get('confidence', '?')}")
            return result
        except json.JSONDecodeError as e:
            logger.warning(f"[{self.name}] LLM JSON invalide: {e}")
            return None
        except Exception as e:
            logger.warning(f"[{self.name}] Groq erreur: {e} - fallback regex")
            self._groq_available = False
            return None

    def _extract_with_regex(self, text: str, filename: str) -> dict:
        """Extraction NER via regex (fallback)."""
        text_upper = text.upper()
        fn_upper   = filename.upper()
        extracted  = {}

        # Immatriculation - priorite 1 : filename
        reg = None
        for r in ACTIVE_REGISTRATIONS:
            if r in fn_upper:
                reg = r; break
        if not reg:
            for r in FLEET_REGISTRATIONS:
                if r in fn_upper:
                    reg = r; break

        # Immatriculation - priorite 2 : texte exact
        if not reg:
            for r in ACTIVE_REGISTRATIONS:
                if r in text_upper:
                    reg = r; break
        if not reg:
            for r in FLEET_REGISTRATIONS:
                if r in text_upper:
                    reg = r; break

        # Immatriculation - priorite 3 : format tableau NouvelAir !A/C\n!NQ
        if not reg:
            reg = _resolve_tableau_format(text)

        # Immatriculation - priorite 4 : resolution MSN
        if not reg:
            reg = _resolve_msn(text)
            if reg:
                logger.info(f"[{self.name}] Immatriculation resolue via MSN: {reg}")

        # Immatriculation - priorite 5 : OCR degrade
        if not reg:
            degraded_patterns = [
                r'\b[EtTiI!][N][OPQRSTU]\b',
                r'\b[OoEe]{1,2}N[OPQRSTU]\b',
                r'(?:A/?C|A\/C)[^\n]*\n[^\n]{0,10}(IN[A-Z])',
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

        # Immatriculation - priorite 6 : patterns compiles
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

        # Autres champs via regex
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

        # 1. Tentative LLM (Groq)
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

            # Si LLM n a pas trouve l immatriculation, essayer format tableau
            if not extracted.get("aircraft_registration"):
                reg_tableau = _resolve_tableau_format(text)
                if reg_tableau:
                    extracted["aircraft_registration"] = reg_tableau
                    raw_entities["aircraft_registration"] = [reg_tableau]
                    raw_entities["tableau_resolution"] = ["true"]
                    logger.info(f"[{self.name}] LLM: immatriculation resolue via tableau -> {reg_tableau}")

            # Si toujours pas trouve, essayer via MSN
            if not extracted.get("aircraft_registration"):
                reg_msn = _resolve_msn(text)
                if reg_msn:
                    extracted["aircraft_registration"] = reg_msn
                    raw_entities["aircraft_registration"] = [reg_msn]
                    raw_entities["msn_resolution"] = ["true"]
                    logger.info(f"[{self.name}] LLM: immatriculation resolue via MSN -> {reg_msn}")

            raw_entities["ner_method"] = ["LLM (Groq llama-3.1-8b-instant)"]
            logger.info(f"[{self.name}] Methode: LLM")
        else:
            # 2. Fallback Regex
            extracted = self._extract_with_regex(text, filename)
            raw_entities["ner_method"] = ["Regex fallback"]
            logger.info(f"[{self.name}] Methode: Regex fallback")

        # 3. Enrichissement depuis filename (toujours applique)
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

        # 4. Normalisation ATA
        if "ata_chapter" in extracted:
            ata_num = re.search(r"(\d{2})", extracted["ata_chapter"])
            if ata_num and ata_num.group(1) in ATA_MAP:
                raw_entities["ata_description"] = ATA_MAP[ata_num.group(1)]

        # 5. Extraction RCT anchor
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

        # 6. Normalisation finale immatriculation
        reg = extracted.get("aircraft_registration")
        if reg:
            normalized = _normalize_registration(reg)
            if normalized:
                extracted["aircraft_registration"] = normalized

        # 7. Dernier recours : tableau puis MSN si immatriculation toujours absente
        if not extracted.get("aircraft_registration"):
            reg_tableau = _resolve_tableau_format(text)
            if reg_tableau:
                extracted["aircraft_registration"] = reg_tableau
                raw_entities["aircraft_registration"] = [reg_tableau]
                raw_entities["tableau_resolution"] = ["true"]
                logger.info(f"[{self.name}] Dernier recours tableau -> {reg_tableau}")
            else:
                reg_msn = _resolve_msn(text)
                if reg_msn:
                    extracted["aircraft_registration"] = reg_msn
                    raw_entities["aircraft_registration"] = [reg_msn]
                    raw_entities["msn_resolution"] = ["true"]
                    logger.info(f"[{self.name}] Dernier recours MSN -> {reg_msn}")

        logger.info(
            f"[{self.name}] Entites: {list(extracted.keys())} | "
            f"Methode: {raw_entities.get('ner_method', ['?'])[0]}"
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