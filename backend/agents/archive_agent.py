"""
Agent Archive
Déduplication SHA-256, résolution aircraft/check, persistance PostgreSQL, alertes.

OPTIMISATIONS v2 :
  - Cache mémoire pour resolve_aircraft() : dict registration → Aircraft.id
  - Cache mémoire pour resolve_check() : dict es_reference → AircraftCheck.id
  - archive() ne refait plus le check_duplicate SHA256 (pipeline.py le fait déjà)
  - Méthode invalidate_cache() pour les tests et rechargements

v3 — RCT Anchor :
  - Quand un RCT est archivé → upsert aircraft_checks (confirmed_by_rct=TRUE)
    avec le linked_wp + check_type extraits par le NER agent
  - Backfill rétroactif : tous les documents déjà en DB avec le même es_reference
    héritent automatiquement du bon check_type et check_id
  - Pour les docs non-RCT : resolve_check() consulte d'abord les checks confirmés
    par RCT avant de créer un check inféré (moins fiable)

v4 — Organisation fichiers :
  - Après archivage, chaque document est copié dans ORGANISED/ avec nom normalisé
  - Format : {IMMAT}_{TYPE}_{REF}.pdf  ex: TS-INQ_WO_ES154313.pdf
  - Sans immatriculation → En_Attente/ + alerte générée
"""
import hashlib
import shutil
from pathlib import Path
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.models.aircraft import Aircraft
from backend.models.document import Document, DocumentStatus
from backend.models.check import AircraftCheck, Alert, AlertSeverity, AlertType, CheckType
from backend.schemas.document import OCRResult, NERResult, ClassifierResult
from backend.config import settings


# ─── Constantes organisation ──────────────────────────────────────────────────
_ORGANISED_ROOT = Path(settings.archive_root_path).parent / "ORGANISED"

_TYPE_SHORT = {
    "WORK_ORDER": "WO", "JOBCARD": "JC", "AD": "AD", "SB": "SB",
    "AMM": "AMM", "CMM": "CMM", "IPC": "IPC", "SPECS": "SPECS",
    "CERTIFICATE": "CERT", "DEFECT_REPORT": "DR", "RCT": "RCT",
    "NCR": "NCR", "ATL": "ATL",
}

_CATEGORY_FOLDER = {
    "check a": "Checks/Check_A", "check c": "Checks/Check_C",
    "check d": "Checks/Check_D", "ad": "Navigabilite/AD",
    "sb": "Navigabilite/SB", "amm": "Technique/AMM",
    "cmm": "Technique/CMM", "ipc": "Technique/IPC",
    "specs": "Technique/Specs", "certificates": "Certificates",
    "structural repair": "Structural Repair", "engine file": "Engine_File",
    "correspondence": "Correspondence", "weight & balance": "Weight_Balance",
    "atl": "ATL",
}

_TYPE_FOLDER = {
    "WORK_ORDER": "Work_Order", "JOBCARD": "Job_Card",
    "AD": "AD", "SB": "SB", "DEFECT_REPORT": "Defect_Report",
    "RCT": "RCT", "NCR": "NCR",
}

_CHECK_TYPE_MAP = {
    "CHECK_A": CheckType.CHECK_A, "CHECK_C": CheckType.CHECK_C,
    "CHECK_D": CheckType.CHECK_D, "CHECK A": CheckType.CHECK_A,
    "CHECK C": CheckType.CHECK_C, "CHECK D": CheckType.CHECK_D,
}


class ArchiveAgent:
    def __init__(self):
        self.name = "Archive Agent"
        self._aircraft_cache: dict[str, int] = {}
        self._check_cache: dict[str, int] = {}
        logger.info(f"[{self.name}] Initialisé (cache aircraft + check actifs)")

    def invalidate_cache(self):
        """Vide les caches (utile en tests ou après modification directe DB)."""
        self._aircraft_cache.clear()
        self._check_cache.clear()
        logger.debug(f"[{self.name}] Caches invalidés")

    def compute_hash(self, content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    async def check_duplicate(self, db: AsyncSession, sha256: str) -> Document | None:
        result = await db.execute(select(Document).where(Document.sha256_hash == sha256))
        return result.scalar_one_or_none()

    # ─── Organisation fichier ─────────────────────────────────────────────────
    def _organise_file(self, src_path: str, doc: Document) -> str | None:
        """
Retourne le chemin original sans copie physique.
        Format : {IMMAT}_{TYPE}_{REF}.pdf
        Retourne le nouveau chemin, ou None si la source est introuvable.
        """
        raw = (src_path or "").strip()
        src = Path(raw[4:] if raw.startswith("\\\\?\\") else raw)

        if not src.is_file():
            logger.warning(f"[{self.name}] _organise_file: source introuvable {src}")
            return None

        # Dossier destination
        reg = (doc.aircraft_registration or "").strip().upper()
        if not reg:
            dest_folder = _ORGANISED_ROOT / "En_Attente"
        else:
            cat_key  = (doc.category or "").strip().lower()
            cat_fold = _CATEGORY_FOLDER.get(cat_key) or cat_key.replace(' ', '_').replace('&', 'et').strip() or "Divers"
            dt_str   = str(doc.doc_type or "").split(".")[-1].upper()
            type_sub = _TYPE_FOLDER.get(dt_str, "")
            parts    = [_ORGANISED_ROOT, reg, cat_fold]
            if type_sub:
                parts.append(type_sub)
            dest_folder = Path(*parts)

        # Nom normalisé
        dt_str    = str(doc.doc_type or "").split(".")[-1].upper()
        short     = _TYPE_SHORT.get(dt_str, dt_str[:6])
        ref       = (
            doc.es_reference or doc.sb_ad_reference or
            doc.work_order_number or doc.item_number or str(doc.id)
        )
        ref       = ref.strip().replace(" ", "_").replace("/", "-").replace("\\", "-")
        ata       = f"_ATA{doc.ata_chapter}" if doc.ata_chapter else ""
        reg_part  = reg if reg else "UNKN"
        dest_name = f"{reg_part}_{short}_{ref}{ata}.pdf"
        dest_path = dest_folder / dest_name

        # Collision de nom → ajouter ID
        if dest_path.exists():
            try:
                if dest_path.resolve() == src.resolve():
                    return str(dest_path)  # déjà organisé
            except Exception:
                pass
            dest_name = f"{dest_path.stem}_{doc.id}.pdf"
            dest_path = dest_folder / dest_name

        logger.info(f"[{self.name}] Fichier référencé (pas de copie) → {src}")
        return str(src)

    async def resolve_aircraft(self, db: AsyncSession, registration: str) -> Aircraft | None:
        if not registration:
            return None
        reg_upper = registration.upper()
        if reg_upper in self._aircraft_cache:
            cached_id = self._aircraft_cache[reg_upper]
            result = await db.execute(select(Aircraft).where(Aircraft.id == cached_id))
            aircraft = result.scalar_one_or_none()
            if aircraft:
                return aircraft
            del self._aircraft_cache[reg_upper]
        result = await db.execute(select(Aircraft).where(Aircraft.registration == reg_upper))
        aircraft = result.scalar_one_or_none()
        if not aircraft:
            aircraft = Aircraft(
                registration=reg_upper, model="A320-214", airline="NouvelAir",
                archive_path=f"{settings.archive_root_path}\\{reg_upper}"
            )
            db.add(aircraft)
            await db.flush()
            logger.info(f"[{self.name}] Aéronef auto-créé: {reg_upper}")
        self._aircraft_cache[reg_upper] = aircraft.id
        return aircraft

    async def resolve_check(
        self, db: AsyncSession, es_ref: str, aircraft: Aircraft, doc_category: str
    ) -> AircraftCheck | None:
        if not es_ref:
            return None
        es_upper = es_ref.upper()
        if es_upper in self._check_cache:
            cached_id = self._check_cache[es_upper]
            result = await db.execute(select(AircraftCheck).where(AircraftCheck.id == cached_id))
            check = result.scalar_one_or_none()
            if check:
                return check
            del self._check_cache[es_upper]
        result = await db.execute(select(AircraftCheck).where(AircraftCheck.es_reference == es_upper))
        check = result.scalar_one_or_none()
        if not check and aircraft:
            check_type = CheckType.CHECK_A
            if doc_category and "C" in doc_category.upper():
                check_type = CheckType.CHECK_C
            check = AircraftCheck(
                es_reference=es_upper, check_type=check_type, aircraft_id=aircraft.id,
                description=f"Check {check_type} — {es_ref} (inféré)", confirmed_by_rct=False,
            )
            db.add(check)
            await db.flush()
            logger.info(f"[{self.name}] Check inféré créé: {es_upper} ({check_type})")
        if check:
            self._check_cache[es_upper] = check.id
        return check

    async def _process_rct_anchor(self, db: AsyncSession, doc: Document, ner: NERResult) -> None:
        linked_wp      = ner.linked_wp
        check_type_str = ner.check_type
        if not linked_wp or not check_type_str:
            logger.warning(f"[{self.name}] RCT {doc.filename} — linked_wp ou check_type manquant")
            return
        check_type_enum = _CHECK_TYPE_MAP.get(check_type_str.upper())
        if not check_type_enum:
            logger.warning(f"[{self.name}] check_type inconnu: {check_type_str}")
            return
        aircraft = await self.resolve_aircraft(db, ner.aircraft_registration)
        if not aircraft:
            logger.warning(f"[{self.name}] RCT anchor: aircraft introuvable ({ner.aircraft_registration})")
            return

        result = await db.execute(
            select(AircraftCheck).where(AircraftCheck.es_reference == linked_wp.upper())
        )
        existing_check = result.scalar_one_or_none()
        if existing_check:
            existing_check.check_type      = check_type_enum
            existing_check.aircraft_id     = aircraft.id
            existing_check.confirmed_by_rct = True
            existing_check.rct_document_id  = doc.id
            existing_check.description     = f"Confirmé par RCT — {doc.filename}"
            anchor_check = existing_check
            logger.info(f"[{self.name}] aircraft_checks mis à jour: {linked_wp} → {check_type_enum}")
        else:
            anchor_check = AircraftCheck(
                es_reference=linked_wp.upper(), check_type=check_type_enum,
                aircraft_id=aircraft.id, confirmed_by_rct=True,
                rct_document_id=doc.id, description=f"Confirmé par RCT — {doc.filename}",
            )
            db.add(anchor_check)
            logger.info(f"[{self.name}] aircraft_checks créé: {linked_wp} → {check_type_enum}")

        await db.flush()
        self._check_cache.pop(linked_wp.upper(), None)
        self._check_cache[linked_wp.upper()] = anchor_check.id

        # Backfill rétroactif
        result = await db.execute(
            select(Document).where(Document.es_reference == linked_wp.upper())
        )
        docs_to_update = result.scalars().all()
        category_label = check_type_str.replace("_", " ").title()
        updated_count  = 0
        for d in docs_to_update:
            if d.id == doc.id:
                continue
            changed = False
            if d.check_id != anchor_check.id:
                d.check_id = anchor_check.id
                changed = True
            if d.category != category_label:
                d.category = category_label
                changed = True
            if changed:
                updated_count += 1
        if updated_count:
            logger.info(f"[{self.name}] Backfill RCT: {updated_count} docs mis à jour")

    async def archive(
        self,
        db: AsyncSession,
        content: bytes,
        filename: str,
        original_path: str,
        ocr: OCRResult,
        ner: NERResult,
        classification: ClassifierResult,
        embedding: list[float] | None,
        file_size_kb: float = 0.0
    ) -> tuple[Document, bool]:
        """
        Persiste le document en base + copie organisée dans ORGANISED/.
        Retourne (document, is_duplicate).
        """
        sha256   = self.compute_hash(content)
        aircraft = await self.resolve_aircraft(db, ner.aircraft_registration)

        from backend.models.document import DocumentType
        is_rct          = (classification.predicted_type == DocumentType.RCT)
        es_ref_for_check = (ner.linked_wp if is_rct and ner.linked_wp else ner.es_reference)
        check = await self.resolve_check(db, es_ref_for_check, aircraft, classification.predicted_category)

        doc = Document(
            sha256_hash           = sha256,
            filename              = filename,
            original_path         = original_path,
            file_size_kb          = file_size_kb,
            doc_type              = classification.predicted_type,
            category              = classification.predicted_category,
            ata_chapter           = ner.ata_chapter,
            status                = DocumentStatus.PENDING,
            aircraft_registration = ner.aircraft_registration,
            es_reference          = ner.es_reference,
            item_number           = ner.item_number,
            part_number           = ner.part_number,
            serial_number         = ner.serial_number,
            work_order_number     = ner.work_order_number,
            sb_ad_reference       = ner.sb_ad_reference,
            extracted_entities    = ner.raw_entities,
            ocr_text              = ocr.text,
            ocr_confidence        = ocr.confidence,
            ocr_pages             = ocr.pages,
            ocr_engine            = ocr.engine,
            classifier_confidence = classification.confidence,
            classifier_scores     = classification.scores,
            embedding             = embedding,
            aircraft_id           = aircraft.id if aircraft else None,
            check_id              = check.id if check else None,
            archived_at           = None,
            is_critical           = self._is_critical_ad(ner, classification),
            needs_review          = ocr.confidence < 60.0 or classification.confidence < 0.5,
        )

        db.add(doc)
        await db.flush()

        # RCT anchor
        if is_rct:
            await self._process_rct_anchor(db, doc, ner)

        # Alertes qualité
        await self._generate_alerts(db, doc, ocr, classification)

        # ── Organisation fichier → ORGANISED/ ────────────────────────────────
        organised_path = self._organise_file(original_path, doc)
        if organised_path:
            doc.original_path = organised_path
        elif not ner.aircraft_registration:
            db.add(Alert(
                title                = f"Document sans immatriculation — {filename}",
                message              = (
                    f"'{filename}' n'a pas d'immatriculation reconnue. "
                    f"Placé dans En_Attente/. Vérification manuelle requise."
                ),
                severity             = AlertSeverity.WARNING,
                alert_type           = AlertType.OCR_LOW_CONFIDENCE,
                aircraft_registration= None,
                document_id          = doc.id,
            ))

        logger.info(f"[{self.name}] Document archivé: #{doc.id} {filename}")
        return doc, False

    def _is_critical_ad(self, ner: NERResult, classification: ClassifierResult) -> bool:
        from backend.models.document import DocumentType
        return (
            classification.predicted_type == DocumentType.AD
            and classification.confidence > 0.7
        )

    async def _generate_alerts(
        self, db: AsyncSession, doc: Document,
        ocr: OCRResult, classification: ClassifierResult
    ):
        alerts = []
       
        if 0 < ocr.confidence < 50.0:
            alerts.append(Alert(
                title                = f"OCR faible confiance — {doc.filename}",
                message              = f"Confiance OCR: {ocr.confidence:.1f}%. Vérification manuelle recommandée.",
                severity             = AlertSeverity.WARNING,
                alert_type           = AlertType.OCR_LOW_CONFIDENCE,
                aircraft_registration= doc.aircraft_registration,
                document_id          = doc.id,
            ))
        for alert in alerts:
            db.add(alert)
