"""
processing_profiles.py
======================
Système de Profils de Traitement Adaptatif par Type Documentaire
NouvelAir — Système d'Archivage Intelligent

CONCEPT :
---------
Chaque type de document MRO a un layout différent → il faut un profil
de traitement spécifique qui configure :
  1. Le prétraitement OCR (OpenCV : contraste, deskew, zone crop...)
  2. La configuration Tesseract (PSM, langue, whitelist)
  3. Les entités NER à extraire (patterns actifs)
  4. Les champs obligatoires (validation post-extraction)
  5. Les zones prioritaires pour les embeddings sémantiques
  6. Les métadonnées à inférer depuis le path de fichier

Ce module est le CERVEAU du pipeline adaptatif.
Il est utilisé par les agents OCR, NER, et Embedding.
"""

from dataclasses import dataclass, field
from typing import Optional
import re


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 1 — STRUCTURES DE DONNÉES
# ═══════════════════════════════════════════════════════════════════════════
# On définit des dataclasses (structures de données légères Python) pour
# représenter les différentes parties d'un profil.
# Un dataclass est comme une classe normale, mais Python génère
# automatiquement __init__, __repr__, __eq__ → moins de code, plus lisible.

@dataclass
class OCRProfile:
    """
    Paramètres de prétraitement OpenCV et configuration Tesseract.

    PSM (Page Segmentation Mode) — valeurs clés Tesseract :
      3  = Fully automatic page segmentation (défaut) → documents flux libre
      4  = Assume a single column of text              → bulletins, AMM
      6  = Assume a single uniform block of text       → tableaux simples
     11  = Sparse text, find as much as possible       → formulaires
     12  = Sparse text with OSD                        → docs désordonnés
    """
    # Tesseract
    psm: int = 3                          # Mode de segmentation page
    lang: str = "eng"                     # Langue OCR (eng = anglais technique)
    dpi: int = 300                        # Résolution cible en DPI

    # Prétraitement OpenCV
    deskew: bool = True                   # Correction d'inclinaison
    denoise: bool = False                 # Filtre de débruitage (lent, activer si scan bruité)
    contrast_enhance: bool = False        # CLAHE (Contrast Limited Adaptive Histogram)
    binarize: bool = True                 # Seuillage adaptatif Otsu
    remove_borders: bool = False          # Suppression des bordures de page

    # Zones d'intérêt (ROI = Region Of Interest)
    # Format : [(x%, y%, w%, h%)] — coordonnées en % de la page
    # None = traiter toute la page
    roi_zones: Optional[list] = None      # Zones à cropper avant OCR

    # Page prioritaire pour l'extraction des entités clés
    # Ex : pour Job Card, le FSN est en page 3 → priorité à page 3
    priority_page: Optional[int] = None  # 0-indexed. None = toutes les pages


@dataclass
class NERProfile:
    """
    Configuration du NER (Named Entity Recognition) adaptatif.

    Le principe : on n'active QUE les patterns pertinents pour ce type.
    Un SB n'a pas de FSN, un Job Card n'a pas de SB number → évite les
    faux positifs et accélère le traitement.
    """
    # Entités à extraire (clés = noms d'entités, valeurs = patterns regex)
    # Chaque type de document active un sous-ensemble de ces entités
    active_entities: list = field(default_factory=list)

    # Champ qui identifie UNIQUEMENT ce type de document
    # Sert au classifier comme signal fort
    discriminant_field: Optional[str] = None

    # Page où chercher les entités principales (optimisation)
    # None = chercher dans tout le document
    entity_search_pages: Optional[list] = None  # ex: [0, 2] = pages 1 et 3

    # ── Early stopping ────────────────────────────────────────────────────────
    # Liste minimale d'entités à trouver pour arrêter la lecture des pages.
    # Si toutes ces entités sont trouvées sur la page courante → on s'arrête.
    # Si None → lire toutes les pages jusqu'à priority_page du profil OCR.
    #
    # Logique pipeline :
    #   Page 1 → OCR → check entités → toutes trouvées ? stop : page 2 → ...
    #
    # Exemples :
    #   Job Card  → ["AIRCRAFT_REG", "ATA_CHAPTER"]  # FSN en p3 si pas trouvé en p1
    #   Work Order → ["WORK_ORDER", "AIRCRAFT_REG"]   # tout en p1 normalement
    #   SB        → ["SB_NUMBER", "ATA_CHAPTER"]      # header p1 suffit
    required_for_stop: Optional[list] = None


@dataclass
class ValidationProfile:
    """
    Règles de validation post-extraction NER.

    Après l'extraction, on vérifie que les champs critiques sont présents.
    Si un champ requis est manquant → le document passe en révision manuelle.
    """
    required_fields: list = field(default_factory=list)   # Champs obligatoires
    optional_fields: list = field(default_factory=list)   # Champs souhaitables
    format_checks: dict = field(default_factory=dict)     # Regex de validation format


@dataclass
class EmbeddingProfile:
    """
    Configure quelle partie du texte est utilisée pour générer l'embedding.

    L'embedding est le vecteur sémantique stocké dans pgvector.
    Il ne faut PAS embedder tout le texte brut → trop de bruit.
    On sélectionne les sections les plus informatives.
    """
    # Sections du texte à prioriser pour l'embedding
    # Ces sections sont concaténées pour former le "résumé métier"
    priority_sections: list = field(default_factory=list)

    # Longueur max du texte source pour l'embedding (en caractères)
    # all-MiniLM-L6-v2 a une fenêtre de 256 tokens ≈ ~1000 chars
    max_chars: int = 1000

    # Préfixe ajouté au texte pour guider la sémantique
    # Technique issue des travaux sur les "instruction embeddings"
    semantic_prefix: str = ""


@dataclass
class PathInferenceProfile:
    """
    Règles pour inférer le type et les métadonnées depuis le path de fichier.
    C'est l'Approche B (Metadata-First) — aucun OCR n'est nécessaire pour
    déterminer le type documentaire.

    Exemple de path NouvelAir :
    AviationArchive/Aircraft/TS-INP/Check_A/Job_Cards/ES001778_task_32-40.pdf
    → type = "job_card", aircraft = "TS-INP", check = "Check_A"
    """
    # Mots-clés dans le path qui identifient ce type (insensible à la casse)
    path_keywords: list = field(default_factory=list)

    # Pattern regex appliqué au nom de fichier seul pour détecter le type
    # Ex : r'^ES\d{5,8}' détecte les Work Orders nommés ES150929.pdf
    # Si le pattern matche → score += 1.0 (signal fort)
    filename_regex: Optional[str] = None

    # Pattern regex pour extraire des métadonnées du nom de fichier
    filename_patterns: dict = field(default_factory=dict)  # {champ: regex}

    # Confiance de l'inférence (0.0 → 1.0)
    inference_confidence: float = 0.9


@dataclass
class ProcessingProfile:
    """
    PROFIL COMPLET DE TRAITEMENT pour un type documentaire.

    C'est l'objet central de l'architecture adaptative.
    Il regroupe tous les sous-profils et est retourné par le ProfileRegistry.

    Usage dans le pipeline :
        profile = ProfileRegistry.get("job_card")
        profile.ocr.psm          → 6
        profile.ner.active_entities → ["CHECK_ID", "AIRCRAFT_REG", ...]
        profile.validation.required_fields → ["check_id", "aircraft_reg"]
    """
    document_type: str               # Identifiant du type (ex: "job_card")
    display_name: str                # Nom lisible (ex: "Job Card")
    description: str                 # Description courte pour les logs/UI

    ocr: OCRProfile = field(default_factory=OCRProfile)
    ner: NERProfile = field(default_factory=NERProfile)
    validation: ValidationProfile = field(default_factory=ValidationProfile)
    embedding: EmbeddingProfile = field(default_factory=EmbeddingProfile)
    path_inference: PathInferenceProfile = field(default_factory=PathInferenceProfile)

    # Catégorie parente dans la taxonomie documentaire NouvelAir
    category: str = "unknown"
    subcategory: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 2 — PATTERNS NER GLOBAUX
# ═══════════════════════════════════════════════════════════════════════════
# On définit ici TOUS les patterns regex possibles.
# Chaque profil ne sélectionne que ceux qui lui sont pertinents.
# Centraliser les patterns ici évite la duplication et facilite la maintenance.

NER_PATTERNS = {

    # ── Identification aéronef ────────────────────────────────────────────
    "AIRCRAFT_REG": re.compile(
        r'\bTS-I[A-Z]{2}\b',
        re.IGNORECASE
    ),
    # Explication : TS- = préfixe Tunisie, I = Nouvelair, puis 2 lettres
    # Ex : TS-INP, TS-INQ → nos deux avions réels

    "MSN": re.compile(
        r'(?:MSN|M\.S\.N\.?)[:\s#]*(\d{3,5})',
        re.IGNORECASE
    ),
    # Explication : MSN suivi d'un numéro de 3 à 5 chiffres
    # Ex : MSN: 2158, MSN 3012

    # ── Références de maintenance ─────────────────────────────────────────
    "CHECK_ID": re.compile(
        r'\b(ES\d{6})\b'
    ),
    # Explication : format NouvelAir — ES + exactement 6 chiffres
    # Ex : ES001778 (Check A TS-INP), ES001392 (Check C TS-INQ)

    "CHECK_TYPE": re.compile(
        r'(?:Check|CHECK|Visite)\s+([ABC]|Line|Heavy|OASN)',
        re.IGNORECASE
    ),
    # Ex : Check A, Check C, Heavy Maintenance

    "WORK_ORDER": re.compile(
        r'(?:W\.?O\.?|Work\s*Order)[:\s#]*([A-Z0-9\-]{4,15})',
        re.IGNORECASE
    ),

    "FSN": re.compile(
        r'(?:FSN|F\.S\.N\.?)[:\s#]*([A-Z0-9\-]{5,20})',
        re.IGNORECASE
    ),
    # FSN = Field Service Number — identifiant unique d'une tâche Job Card
    # CRITIQUE : trouvé en page 3 du Job Card selon notre analyse

    # ── Références techniques ─────────────────────────────────────────────
    "ATA_CHAPTER": re.compile(
        r'\b(\d{2}-\d{2}(?:-\d{2})?)\b'
    ),
    # Format ATA : XX-XX ou XX-XX-XX
    # Ex : 32-40-00 = Landing Gear / Retraction System

    "PART_NUMBER": re.compile(
        r'(?:P/?N|Part\s*N(?:o|umber)?\.?)[:\s#]*([A-Z0-9][\w\-]{3,20})',
        re.IGNORECASE
    ),
    # Ex : P/N: 114760-001-01

    "SERIAL_NUMBER": re.compile(
        r'(?:S/?N|Serial\s*N(?:o|umber)?\.?)[:\s#]*([A-Z0-9][\w\-]{3,20})',
        re.IGNORECASE
    ),
    # Ex : S/N: JF4892

    # ── Service Bulletins / ADs ───────────────────────────────────────────
    "SB_NUMBER": re.compile(
        r'(?:SB|S\.B\.)[:\s]*([A-Z0-9]{2,10}-\d{2}-\d{3,4}(?:-\d+)?)',
        re.IGNORECASE
    ),
    # Ex : SB A320-27-1208

    "REVISION": re.compile(
        r'(?:Rev(?:ision)?\.?|Rév\.?)[:\s]*(\d+|[A-Z])',
        re.IGNORECASE
    ),
    # Ex : Rev.3, Revision B

    "EFFECTIVITY": re.compile(
        r'(?:Effectiv(?:ity|ité)|Applicabilit[yé])[:\s]*([^\n]{5,60})',
        re.IGNORECASE
    ),
    # Ex : Effectivity: MSN 2158 and subsequent

    # ── Dates et délais ───────────────────────────────────────────────────
    "DATE": re.compile(
        r'\b(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4}|\d{4}-\d{2}-\d{2})\b'
    ),

    "COMPLIANCE_DATE": re.compile(
        r'(?:Compliance|Due\s*Date|Date\s*limite)[:\s]*([^\n]{5,40})',
        re.IGNORECASE
    ),

    # ── Heures / cycles (FH/FC) ───────────────────────────────────────────
    "FLIGHT_HOURS": re.compile(
        r'(?:FH|Flight\s*Hours?|Heures?\s*de\s*Vol)[:\s]*(\d+(?:\.\d+)?)',
        re.IGNORECASE
    ),

    "FLIGHT_CYCLES": re.compile(
        r'(?:FC|Flight\s*Cycles?|Cycles?)[:\s]*(\d+)',
        re.IGNORECASE
    ),
}


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 3 — DÉFINITION DES PROFILS PAR TYPE
# ═══════════════════════════════════════════════════════════════════════════

def _make_job_card_profile() -> ProcessingProfile:
    """
    JOB CARD — Carte de travail de maintenance
    ──────────────────────────────────────────
    Layout : Tableau structuré sur plusieurs pages.
             Le FSN (identifiant de tâche) se trouve TOUJOURS en page 3.
             L'immatriculation de l'avion est dans le header ET en page 3.
    Données réelles : ES001778 (Check A), ES001440 — TS-INP / MSN 2158

    Choix OCR :
    - PSM 6 : "single uniform block" → adapté aux tableaux structurés
    - deskew=True : les scans de job cards sont souvent légèrement inclinés
    - denoise=True : les formulaires papier ont souvent du bruit de fond
    - priority_page=2 : index 0 → page 3 est index 2, contient FSN + A/C Reg
    """
    return ProcessingProfile(
        document_type="job_card",
        display_name="Job Card",
        description="Carte de travail maintenance — tâches spécifiques par ATA chapter",
        category="Maintenance",
        subcategory="Job Cards",

        ocr=OCRProfile(
            psm=6,
            lang="eng",
            dpi=300,
            deskew=True,
            denoise=True,
            contrast_enhance=False,
            binarize=True,
            priority_page=2,           # Page 3 (0-indexed) = FSN + A/C Reg
            roi_zones=None             # Traiter toute la page (FSN peut varier en position)
        ),

        ner=NERProfile(
            active_entities=[
                "FSN",           # CRITIQUE — identifiant unique tâche, page 3
                "AIRCRAFT_REG",  # TS-INP ou TS-INQ
                "MSN",           # 2158 ou 3012
                "CHECK_ID",      # ES001778, ES001440...
                "CHECK_TYPE",    # Check A, Check C
                "ATA_CHAPTER",   # 32-40-00, 29-10-00...
                "PART_NUMBER",   # Pièces requises pour la tâche
                "SERIAL_NUMBER", # S/N des composants remplacés
                "FLIGHT_HOURS",  # FH au moment de la tâche
                "FLIGHT_CYCLES", # FC au moment de la tâche
                "DATE",
            ],
            discriminant_field="FSN",
            entity_search_pages=[0, 1, 2],
            # Early stopping : FSN est en p3 → on lit jusqu'à le trouver
            # Si FSN + AIRCRAFT_REG + ATA trouvés dès p1 → stop immédiat
            required_for_stop=["FSN", "AIRCRAFT_REG", "ATA_CHAPTER"]
        ),

        validation=ValidationProfile(
            required_fields=["fsn", "aircraft_reg", "ata_chapter"],
            optional_fields=["check_id", "part_number", "flight_hours", "flight_cycles"],
            format_checks={
                "aircraft_reg": r"^TS-I[A-Z]{2}$",
                "ata_chapter":  r"^\d{2}-\d{2}(-\d{2})?$",
            }
        ),

        embedding=EmbeddingProfile(
            priority_sections=["task_description", "ata_chapter", "aircraft_reg", "fsn"],
            max_chars=800,
            semantic_prefix="Job Card maintenance task: "
        ),

        path_inference=PathInferenceProfile(
            path_keywords=["job_card", "job card", "jobcard", "jc", "task_card"],
            # Job Cards sont souvent nommés avec un numéro court : 0034.pdf, 034.pdf
            # ou avec ATA dans le nom : ES001778_task_32-40.pdf
            filename_regex=r'^(\d{3,4}\.pdf$|.*task.*)',
            filename_patterns={
                "check_id": r'(ES\d{6})',
                "ata_chapter": r'(\d{2}-\d{2}(?:-\d{2})?)',
            },
            inference_confidence=0.95
        )
    )


def _make_work_order_profile() -> ProcessingProfile:
    """
    WORK ORDER — Ordre de travail global
    ─────────────────────────────────────
    Layout : Formulaire séquentiel linéaire (pas de tableaux complexes).
             Le WO# est en header. Sections : Description, Personnel, Durée.
    Données réelles : ES001392 (Check C TS-INQ / MSN 3012)

    Choix OCR :
    - PSM 3 : auto → adapté aux formulaires séquentiels
    - denoise=False : Work Orders sont souvent des impressions propres
    - priority_page=0 : tout est sur la première page (header + résumé)
    """
    return ProcessingProfile(
        document_type="work_order",
        display_name="Work Order",
        description="Ordre de travail global — regroupe plusieurs Job Cards",
        category="Maintenance",
        subcategory="Work Orders",

        ocr=OCRProfile(
            psm=3,
            lang="eng",
            dpi=300,
            deskew=True,
            denoise=False,
            contrast_enhance=False,
            binarize=True,
            priority_page=0,
        ),

        ner=NERProfile(
            active_entities=[
                "WORK_ORDER",    # WO# principal
                "CHECK_ID",      # Référence check associé (ES001392)
                "CHECK_TYPE",    # Check C
                "AIRCRAFT_REG",  # TS-INQ
                "MSN",           # 3012
                "DATE",          # Date d'ouverture / clôture
                "FLIGHT_HOURS",
                "FLIGHT_CYCLES",
            ],
            discriminant_field="WORK_ORDER",
            entity_search_pages=[0],
            # Work Order : tout est en page 1 → si WO# + A/C trouvés dès p1, stop
            required_for_stop=["WORK_ORDER", "AIRCRAFT_REG"]
        ),

        validation=ValidationProfile(
            required_fields=["work_order", "aircraft_reg"],
            optional_fields=["check_id", "check_type", "date"],
            format_checks={
                "aircraft_reg": r"^TS-I[A-Z]{2}$",
            }
        ),

        embedding=EmbeddingProfile(
            priority_sections=["work_description", "aircraft_reg", "check_type"],
            max_chars=700,
            semantic_prefix="Work order maintenance: "
        ),

        path_inference=PathInferenceProfile(
            path_keywords=["work_order", "work order", "wo", "ordre_travail"],
            # Détecte les fichiers nommés ESxxxxxx.pdf ou WO-ESxxxxxx.pdf
            # Format NouvelAir réel : ES150929.pdf, WO-ES001229.pdf
            filename_regex=r'^(wo[-_]?)?es\d{5,8}',
            filename_patterns={
                "check_id": r'(ES\d{6})',
            },
            inference_confidence=0.92
        )
    )


def _make_service_bulletin_profile() -> ProcessingProfile:
    """
    SERVICE BULLETIN (SB) — Bulletin de service constructeur
    ──────────────────────────────────────────────────────────
    Layout : Header EASA standardisé (SB#, Rev, Effectivité, Dates) suivi
             de chapitres techniques numérotés. Format très standardisé.
    Données réelles : SB Airbus A320-27-1208 Rev.3, Effectivité MSN 2158+

    Choix OCR :
    - PSM 4 : "single column" → adapté aux SB avec sections verticales
    - contrast_enhance=True : les SB sont souvent scannés depuis microfiches
    - priority_page=0 : header page 1 contient SB#, Rev, Effectivité
    """
    return ProcessingProfile(
        document_type="service_bulletin",
        display_name="Service Bulletin",
        description="Bulletin de service Airbus — modifications et inspections recommandées",
        category="Technical",
        subcategory="Service Bulletins",

        ocr=OCRProfile(
            psm=4,
            lang="eng",
            dpi=300,
            deskew=True,
            denoise=False,
            contrast_enhance=True,     # SB souvent scannés avec faible contraste
            binarize=True,
            priority_page=0,           # Header page 1 : SB#, Rev, Effectivité
        ),

        ner=NERProfile(
            active_entities=[
                "SB_NUMBER",       # A320-27-1208
                "REVISION",        # Rev.3
                "EFFECTIVITY",     # MSN 2158 and subsequent
                "MSN",             # MSN concernés
                "COMPLIANCE_DATE", # Date limite de conformité
                "ATA_CHAPTER",     # Chapitre ATA concerné
                "PART_NUMBER",     # Pièces concernées
                "DATE",
            ],
            discriminant_field="SB_NUMBER",
            entity_search_pages=[0, 1],
            # SB : header p1 suffit si SB# + ATA trouvés
            required_for_stop=["SB_NUMBER", "ATA_CHAPTER"]
        ),

        validation=ValidationProfile(
            required_fields=["sb_number", "revision"],
            optional_fields=["effectivity", "compliance_date", "ata_chapter"],
            format_checks={
                "sb_number": r'^[A-Z]\d{3}-\d{2}-\d{3,4}',
            }
        ),

        embedding=EmbeddingProfile(
            priority_sections=["sb_number", "effectivity", "description", "compliance_date"],
            max_chars=900,
            semantic_prefix="Service bulletin airworthiness: "
        ),

        path_inference=PathInferenceProfile(
            path_keywords=["sb", "service_bulletin", "service bulletin", "bulletin"],
            filename_patterns={
                "sb_number": r'([A-Z]\d{3}-\d{2}-\d{3,4})',
                "revision":  r'[Rr]ev?\.?(\d+)',
            },
            inference_confidence=0.93
        )
    )


def _make_amm_profile() -> ProcessingProfile:
    """
    AMM — Aircraft Maintenance Manual
    ───────────────────────────────────
    Layout : Chapitres ATA hiérarchiques. Très long, nombreuses pages.
             Structure : ATA XX-XX-XX → Sections → Steps numérotés → Figures.
             Contient des WARNINGS et CAUTIONS en boîtes distinctes.

    Choix OCR :
    - PSM 3 : auto → adapté aux documents longs multi-colonnes
    - remove_borders=True : les AMM ont des cadres de page à supprimer
    - priority_page=None : l'information est dispersée dans tout le manuel
    """
    return ProcessingProfile(
        document_type="amm",
        display_name="Aircraft Maintenance Manual (AMM)",
        description="Manuel de maintenance aéronef — procédures détaillées par chapitre ATA",
        category="Technical",
        subcategory="Manuals",

        ocr=OCRProfile(
            psm=3,
            lang="eng",
            dpi=300,
            deskew=True,
            denoise=False,
            contrast_enhance=False,
            binarize=True,
            remove_borders=True,       # Supprimer les cadres de page AMM
            priority_page=None,        # Tout le manuel est pertinent
        ),

        ner=NERProfile(
            active_entities=[
                "ATA_CHAPTER",   # Chapitre de référence
                "PART_NUMBER",   # Pièces mentionnées dans les procédures
                "SERIAL_NUMBER",
                "AIRCRAFT_REG",  # Si l'AMM est spécifique à un avion
                "REVISION",      # Révision du manuel
                "DATE",
            ],
            discriminant_field="ATA_CHAPTER",
            entity_search_pages=None,
            # AMM : ATA en p1 suffit pour classifier
            required_for_stop=["ATA_CHAPTER", "REVISION"]
        ),

        validation=ValidationProfile(
            required_fields=["ata_chapter"],
            optional_fields=["revision", "part_number"],
            format_checks={
                "ata_chapter": r"^\d{2}-\d{2}(-\d{2})?$",
            }
        ),

        embedding=EmbeddingProfile(
            priority_sections=["chapter_title", "procedure_summary", "ata_chapter"],
            max_chars=1000,
            semantic_prefix="Aircraft maintenance manual procedure: "
        ),

        path_inference=PathInferenceProfile(
            path_keywords=["amm", "aircraft_maintenance", "maintenance_manual"],
            filename_patterns={
                "ata_chapter": r'(\d{2}-\d{2}(?:-\d{2})?)',
                "revision":    r'[Rr]ev?\.?(\d+)',
            },
            inference_confidence=0.90
        )
    )


def _make_delivery_package_profile() -> ProcessingProfile:
    """
    DELIVERY PACKAGE — Documents de livraison aéronef
    ──────────────────────────────────────────────────
    Layout : Variable. Ensemble de documents liés à la livraison de l'avion.
             Identifié par le dossier "Old doc" dans l'arborescence NouvelAir.
             Contient : certificats, weight & balance, configuration initiale.
    Données réelles : 1 758 documents dans le dossier Old doc

    Choix OCR :
    - PSM 3 : auto → layout variable, laisser Tesseract décider
    - dpi=400 : haute résolution car ces docs sont souvent très anciens
    - contrast_enhance=True : documents anciens = faible contraste
    """
    return ProcessingProfile(
        document_type="delivery_package",
        display_name="Delivery Package",
        description="Documents de livraison aéronef — certificats et configuration initiale",
        category="Delivery",
        subcategory="Delivery Package",

        ocr=OCRProfile(
            psm=3,
            lang="eng",
            dpi=400,               # Haute résolution pour vieux documents
            deskew=True,
            denoise=True,          # Documents anciens = bruit
            contrast_enhance=True, # Documents anciens = faible contraste
            binarize=True,
            priority_page=0,
        ),

        ner=NERProfile(
            active_entities=[
                "MSN",           # Numéro de série de l'avion livré
                "AIRCRAFT_REG",  # Immatriculation à la livraison
                "DATE",          # Date de livraison
                "PART_NUMBER",
                "CHECK_TYPE",
            ],
            discriminant_field=None,    # Pas de champ discriminant fort
            entity_search_pages=[0]
        ),

        validation=ValidationProfile(
            required_fields=["msn"],    # Seul le MSN est vraiment requis
            optional_fields=["aircraft_reg", "date"],
        ),

        embedding=EmbeddingProfile(
            priority_sections=["document_title", "msn", "aircraft_reg", "date"],
            max_chars=600,
            semantic_prefix="Aircraft delivery document: "
        ),

        path_inference=PathInferenceProfile(
            path_keywords=["old_doc", "old doc", "delivery", "livraison", "delivery_package"],
            filename_patterns={
                "msn": r'(\d{3,5})',
            },
            inference_confidence=0.88    # Moins sûr car layout variable
        )
    )


def _make_cmm_profile() -> ProcessingProfile:
    """
    CMM / IPC — Component Maintenance Manual / Illustrated Parts Catalog
    ─────────────────────────────────────────────────────────────────────
    Layout : Catalogues illustrés avec tableaux de pièces (P/N, Fig, Item, Qty).
             Format très dense en numéros de pièce.

    Choix OCR :
    - PSM 6 : "single block" → adapté aux tableaux denses de P/N
    - dpi=400 : les IPC ont des petits caractères (P/N, quantités)
    - contrast_enhance=True : tableaux denses = faible contraste
    """
    return ProcessingProfile(
        document_type="cmm_ipc",
        display_name="CMM / IPC",
        description="Component Maintenance Manual / Illustrated Parts Catalog",
        category="Technical",
        subcategory="Manuals",

        ocr=OCRProfile(
            psm=6,
            lang="eng",
            dpi=400,               # P/N en petits caractères
            deskew=True,
            denoise=False,
            contrast_enhance=True, # Tableaux denses
            binarize=True,
            priority_page=None,
        ),

        ner=NERProfile(
            active_entities=[
                "PART_NUMBER",   # P/N = entité principale des IPC
                "SERIAL_NUMBER", # S/N des composants
                "ATA_CHAPTER",   # Chapitre ATA du composant
                "REVISION",
            ],
            discriminant_field="PART_NUMBER",
            entity_search_pages=None
        ),

        validation=ValidationProfile(
            required_fields=["part_number"],
            optional_fields=["ata_chapter", "revision"],
        ),

        embedding=EmbeddingProfile(
            priority_sections=["component_name", "part_number", "ata_chapter"],
            max_chars=700,
            semantic_prefix="Component maintenance catalog: "
        ),

        path_inference=PathInferenceProfile(
            path_keywords=["cmm", "ipc", "illustrated_parts", "component_maintenance"],
            filename_patterns={
                "ata_chapter": r'(\d{2}-\d{2}(?:-\d{2})?)',
            },
            inference_confidence=0.91
        )
    )


def _make_mel_profile() -> ProcessingProfile:
    """
    MEL — Minimum Equipment List
    ─────────────────────────────
    Layout : Liste structurée par ATA chapter, avec conditions d'opération
             sous équipement dégradé. Format réglementaire DGAC/EASA.
    """
    return ProcessingProfile(
        document_type="mel",
        display_name="MEL (Minimum Equipment List)",
        description="Liste des équipements minimum — conditions d'opération dégradée",
        category="Technical",
        subcategory="Regulatory",

        ocr=OCRProfile(
            psm=4,
            lang="eng",
            dpi=300,
            deskew=True,
            contrast_enhance=False,
            binarize=True,
        ),

        ner=NERProfile(
            active_entities=[
                "ATA_CHAPTER",
                "AIRCRAFT_REG",
                "REVISION",
                "DATE",
                "COMPLIANCE_DATE",
            ],
            discriminant_field="ATA_CHAPTER",
        ),

        validation=ValidationProfile(
            required_fields=["ata_chapter"],
            optional_fields=["revision", "date"],
        ),

        embedding=EmbeddingProfile(
            priority_sections=["item_description", "ata_chapter", "dispatch_conditions"],
            max_chars=800,
            semantic_prefix="Minimum equipment list item: "
        ),

        path_inference=PathInferenceProfile(
            path_keywords=["mel", "minimum_equipment", "liste_equipement"],
            inference_confidence=0.94
        )
    )


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 4 — PROFILEREGISTRY (POINT D'ENTRÉE PRINCIPAL)
# ═══════════════════════════════════════════════════════════════════════════
# Le ProfileRegistry est un singleton (une seule instance dans toute
# l'application) qui centralise tous les profils et expose deux méthodes :
#   - get(document_type) → retourne le profil
#   - infer_from_path(path) → devine le type depuis le chemin de fichier

class ProfileRegistry:
    """
    Registre central des profils de traitement documentaire.

    Pattern Singleton + Factory : une seule instance, accès global via
    ProfileRegistry.get() et ProfileRegistry.infer_from_path().

    Utilisation dans les agents :
        from processing_profiles import ProfileRegistry

        # Dans OCRAgent :
        profile = ProfileRegistry.get(document_type)
        deskew = profile.ocr.deskew

        # Dans NERAgent :
        active = profile.ner.active_entities
        patterns = {k: NER_PATTERNS[k] for k in active}

        # Depuis un path :
        doc_type, confidence = ProfileRegistry.infer_from_path(file_path)
        profile = ProfileRegistry.get(doc_type)
    """

    # Dictionnaire interne : document_type → ProcessingProfile
    _profiles: dict[str, ProcessingProfile] = {}
    _initialized: bool = False

    @classmethod
    def _initialize(cls):
        """Construit le registre au premier accès (lazy initialization)."""
        if cls._initialized:
            return

        profiles = [
            _make_job_card_profile(),
            _make_work_order_profile(),
            _make_service_bulletin_profile(),
            _make_amm_profile(),
            _make_delivery_package_profile(),
            _make_cmm_profile(),
            _make_mel_profile(),
        ]

        for p in profiles:
            cls._profiles[p.document_type] = p

        cls._initialized = True

    @classmethod
    def get(cls, document_type: str) -> ProcessingProfile:
        """
        Retourne le profil pour un type documentaire donné.
        Si le type n'est pas reconnu, retourne un profil générique.

        Args:
            document_type: identifiant du type (ex: "job_card", "service_bulletin")

        Returns:
            ProcessingProfile correspondant

        Exemple:
            profile = ProfileRegistry.get("job_card")
            print(profile.ocr.psm)          # → 6
            print(profile.ocr.priority_page) # → 2 (page 3, 0-indexed)
        """
        cls._initialize()
        profile = cls._profiles.get(document_type)
        if profile is None:
            print(f"[ProfileRegistry] ⚠️  Type '{document_type}' inconnu → profil générique")
            return cls._get_generic_profile(document_type)
        return profile

    @classmethod
    def infer_from_path(cls, file_path: str) -> tuple[str, float]:
        """
        Inférence du type documentaire depuis le chemin de fichier.
        C'est l'Approche B (Metadata-First) du pipeline adaptatif.

        Algorithme :
          1. Normaliser le path (minuscules, slashes)
          2. Extraire le nom de fichier seul
          3. Pour chaque profil :
             a. Compter les mots-clés présents dans le path
             b. Vérifier si filename_regex matche le nom de fichier (signal fort)
          4. Retourner le type avec le score le plus élevé

        Args:
            file_path: chemin absolu ou relatif du fichier PDF

        Returns:
            (document_type, confidence) — ex: ("work_order", 0.92)

        Exemples (données réelles NouvelAir) :
            "AviationArchive/TS-INP/Check_A/Job_Cards/ES001778.pdf"
            → ("job_card", 0.95)

            "ES150929.pdf"  ← nommé ESxxxxxx → Work Order
            → ("work_order", 0.92)

            "WO-ES001229.pdf"  ← préfixe WO
            → ("work_order", 0.92)
        """
        cls._initialize()
        path_lower = file_path.lower().replace("\\", "/")

        # Extraire le nom de fichier seul (sans le dossier)
        filename_only = path_lower.split("/")[-1]

        best_type = "unknown"
        best_score = 0.0

        for doc_type, profile in cls._profiles.items():
            score = 0.0

            # ── Signal 1 : mots-clés dans le path complet ─────────────────
            kw_hits = sum(
                1 for kw in profile.path_inference.path_keywords
                if kw.lower() in path_lower
            )
            if kw_hits > 0 and profile.path_inference.path_keywords:
                score += (kw_hits / len(profile.path_inference.path_keywords)) \
                         * profile.path_inference.inference_confidence

            # ── Signal 2 : filename_regex sur le nom de fichier seul ───────
            # Signal fort et prioritaire — si le regex matche, on booste le score
            if profile.path_inference.filename_regex:
                if re.search(
                    profile.path_inference.filename_regex,
                    filename_only,
                    re.IGNORECASE
                ):
                    # Boost : le regex filename est plus fiable que les mots-clés
                    score += profile.path_inference.inference_confidence

            if score > best_score:
                best_score = score
                best_type = doc_type

        return best_type, round(min(best_score, 1.0), 3)

    @classmethod
    def list_types(cls) -> list[str]:
        """Retourne la liste de tous les types documentaires enregistrés."""
        cls._initialize()
        return list(cls._profiles.keys())

    @classmethod
    def _get_generic_profile(cls, document_type: str) -> ProcessingProfile:
        """Profil générique de fallback pour les types non reconnus."""
        return ProcessingProfile(
            document_type=document_type,
            display_name=f"Document ({document_type})",
            description="Profil générique — type non reconnu",
            category="Unknown",
            ocr=OCRProfile(psm=3, deskew=True),
            ner=NERProfile(active_entities=["AIRCRAFT_REG", "MSN", "DATE", "ATA_CHAPTER"]),
            validation=ValidationProfile(required_fields=[]),
        )


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 5 — DÉMONSTRATION (données réelles NouvelAir)
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 70)
    print("  ProfileRegistry — Démonstration avec données réelles NouvelAir")
    print("=" * 70)

    # ── Test 1 : Accès direct à un profil ──────────────────────────────────
    print("\n📋 PROFIL Job Card :")
    profile = ProfileRegistry.get("job_card")
    print(f"  Nom           : {profile.display_name}")
    print(f"  OCR PSM       : {profile.ocr.psm} (6 = single block, adapté tableaux)")
    print(f"  OCR page prio : page {profile.ocr.priority_page + 1} (FSN + A/C Reg)")
    print(f"  NER entités   : {profile.ner.active_entities}")
    print(f"  Champs requis : {profile.validation.required_fields}")
    print(f"  Discriminant  : {profile.ner.discriminant_field}")

    # ── Test 2 : Inférence depuis paths réels NouvelAir ────────────────────
    print("\n🔍 INFÉRENCE depuis paths réels :")
    test_paths = [
        "AviationArchive/Aircraft/TS-INP/Check_A/Job_Cards/ES001778_task_32-40.pdf",
        "AviationArchive/Aircraft/TS-INQ/Check_C/Work_Orders/ES001392.pdf",
        "AviationArchive/Aircraft/TS-INP/Technical/Service_Bulletin/A320-27-1208_Rev3.pdf",
        "AviationArchive/Aircraft/TS-INP/Old_doc/delivery_cert_MSN2158.pdf",
        "AviationArchive/Manuals/AMM/A320_AMM_32-40-00.pdf",
    ]

    for path in test_paths:
        doc_type, confidence = ProfileRegistry.infer_from_path(path)
        p = ProfileRegistry.get(doc_type)
        print(f"  ✅ {doc_type:<22} (conf: {confidence:.2f}) ← {path.split('/')[-1]}")

    # ── Test 3 : Extraction NER simulée sur Job Card ES001778 ──────────────
    print("\n🧠 NER SIMULÉ — Job Card ES001778 (TS-INP / MSN 2158) :")
    sample_text = """
    AIRCRAFT REGISTRATION: TS-INP    MSN: 2158
    FSN: ES001778-A       CHECK: Check A
    ATA CHAPTER: 32-40-00  P/N: 114760-001-01  S/N: JF4892
    FLIGHT HOURS: 14523.5  FLIGHT CYCLES: 8921
    DATE: 15/03/2026
    """

    profile = ProfileRegistry.get("job_card")
    print(f"  Entités actives : {len(profile.ner.active_entities)} patterns activés")
    print()

    for entity_name in profile.ner.active_entities:
        if entity_name in NER_PATTERNS:
            pattern = NER_PATTERNS[entity_name]
            matches = pattern.findall(sample_text)
            if matches:
                print(f"  {entity_name:<18} → {matches}")

    # ── Test 4 : Liste tous les types ──────────────────────────────────────
    print(f"\n📚 Types documentaires enregistrés : {ProfileRegistry.list_types()}")
    print("\n" + "=" * 70)