"""
Orchestrateur Pipeline IA
Coordonne : OCR → NER → Classifier → Embedding → Archive → Alertes

OPTIMISATIONS v2 :
  - process_batch() : traitement concurrent de N documents via asyncio.gather
    avec semaphore configurable (défaut: 3 docs en parallèle)
  - Les agents agents (NER, Classifier, Embedding) bénéficient du parallélisme
    inter-documents

v3 — Aircraft Resolver :
  - Après NER, si aircraft_registration est vide et es_reference est trouvée,
    on interroge la base pour trouver l'avion via les documents existants.
  - Fallback : cherche via le nom de fichier dans les docs existants.
  - Garantit que le système "apprend" de ses propres archives.
"""
import re
import time
import asyncio
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from backend.agents.ocr_agent import OCRAgent
from backend.agents.ner_agent import NERAgent
from backend.agents.classifier_agent import ClassifierAgent
from backend.agents.embedding_agent import EmbeddingAgent
from backend.agents.archive_agent import ArchiveAgent
from backend.agents.monitoring_agent import MonitoringAgent
from backend.agents.linked_wp_resolver import resolve_linked_wp_category
from backend.models.document import Document
from backend.schemas.document import (
    PipelineResult, DocumentStatusEnum, DocumentTypeEnum, ClassifierResult
)
from backend.core.processing_profiles import ProfileRegistry

# ── Mapping chemin → enum DocumentTypeEnum ───────────────────────────────────
PATH_TO_ENUM = {
    'job_card'      : 'Jobcard',
    'work_order'    : 'Work Order',
    'ncr'           : 'NCR',
    'atl'           : 'ATL',
    'ad'            : 'AD',
    'sb'            : 'SB',
    'rct'           : 'RCT',
    'certificate'   : 'Certificate',
    'defect_report' : 'Defect Report',
    'd_b_chart'     : 'D&B Chart',
    'amm'           : 'AMM',
    'cmm'           : 'CMM',
    'ipc'           : 'IPC',
    'specs'         : 'Specs',
}


async def _resolve_aircraft_from_db(
    db: AsyncSession,
    es_reference: str | None,
    filename: str,
) -> str | None:
    """
    Cherche l'immatriculation de l'avion dans la base de données
    en utilisant la référence ES ou le nom de fichier.

    Stratégie :
    1. Si es_reference connue → cherche les docs avec cette ES ref
    2. Sinon → cherche les docs avec un nom similaire
    3. Retourne l'immatriculation la plus fréquente trouvée
    """

    # ── Stratégie 1 : via référence ES ───────────────────────────────────────
    if es_reference:
        es_clean = es_reference.upper().strip()
        # Cherche avec ou sans le préfixe "ES"
        es_num = es_clean[2:] if es_clean.startswith('ES') else es_clean

        result = await db.execute(
            select(
                Document.aircraft_registration,
                func.count(Document.id).label('cnt')
            )
            .where(
                Document.aircraft_registration.isnot(None),
                Document.aircraft_registration != '',
                Document.es_reference.ilike(f'%{es_num}%'),
            )
            .group_by(Document.aircraft_registration)
            .order_by(func.count(Document.id).desc())
            .limit(1)
        )
        row = result.first()
        if row and row.aircraft_registration:
            logger.info(
                f"[Pipeline][AircraftResolver] "
                f"'{es_reference}' → '{row.aircraft_registration}' "
                f"({row.cnt} docs existants)"
            )
            return row.aircraft_registration

    # ── Stratégie 2 : via nom de fichier (extrait l'ES du nom) ───────────────
    m = re.search(r'(ES\d{4,8})', filename, re.IGNORECASE)
    if m:
        es_from_name = m.group(1).upper()
        es_num = es_from_name[2:]  # retire "ES"
        result = await db.execute(
            select(
                Document.aircraft_registration,
                func.count(Document.id).label('cnt')
            )
            .where(
                Document.aircraft_registration.isnot(None),
                Document.aircraft_registration != '',
                Document.es_reference.ilike(f'%{es_num}%'),
            )
            .group_by(Document.aircraft_registration)
            .order_by(func.count(Document.id).desc())
            .limit(1)
        )
        row = result.first()
        if row and row.aircraft_registration:
            logger.info(
                f"[Pipeline][AircraftResolver] "
                f"filename '{filename}' → ES '{es_from_name}' "
                f"→ '{row.aircraft_registration}' ({row.cnt} docs)"
            )
            return row.aircraft_registration

    logger.debug(
        f"[Pipeline][AircraftResolver] "
        f"Aucun avion trouvé pour ES='{es_reference}' / file='{filename}'"
    )
    return None


class PipelineOrchestrator:
    """
    Orchestre le pipeline complet de traitement d'un document.

    Pipeline single :
    1. OCR Agent       — Extraction de texte (pdfplumber + Tesseract)
    2. NER Agent       — Extraction d'entités (spaCy + Regex)
    2b. AircraftResolver — Lookup DB si avion non détecté
    3. Classifier      — Classification (TF-IDF + LR + règles chemin)
    3b. LinkedWP       — Résolution catégorie via Linked WP
    4. Embedding Agent — Vecteur 384d (MiniLM-L6-v2)
    5. Archive Agent   — Persistance PostgreSQL + SHA-256 dédup
    6. Monitoring      — Alertes + métriques
    """

    def __init__(self):
        self.ocr        = OCRAgent()
        self.ner        = NERAgent()
        self.classifier = ClassifierAgent()
        self.embedding  = EmbeddingAgent()
        self.archive    = ArchiveAgent()
        self.monitoring = MonitoringAgent()
        logger.info("[Pipeline] Orchestrateur initialisé — 6 agents prêts")

    async def process_document(
        self,
        db: AsyncSession,
        file_content: bytes,
        filename: str,
        original_path: str = "",
        file_size_kb: float = 0.0,
    ) -> PipelineResult:
        """Traite un document de bout en bout. Retourne un PipelineResult."""
        start = time.perf_counter()
        errors = []

        logger.info(f"[Pipeline] ► Démarrage: {filename}")

        # ── Étape 0 : Déduplication préventive ───────────────────────────────
        sha256 = self.archive.compute_hash(file_content)
        existing = await self.archive.check_duplicate(db, sha256)
        if existing:
            logger.warning(
                f"[Pipeline] Doublon détecté: {filename} == doc#{existing.id}"
            )
            return PipelineResult(
                document_id=existing.id,
                filename=filename,
                status=DocumentStatusEnum.DUPLICATE,
                is_duplicate=True,
                duplicate_of=existing.id,
                processing_time_s=round(time.perf_counter() - start, 3),
            )

        # ── Étape 0.5 : Profil de traitement ─────────────────────────────────
        doc_type, infer_conf = ProfileRegistry.infer_from_path(
            original_path or filename
        )
        profile = ProfileRegistry.get(doc_type)
        logger.info(
            f"[Pipeline] Profil détecté: '{profile.display_name}' "
            f"(conf={infer_conf:.0%}) ← {original_path or filename}"
        )

        # ── Étape 1 : OCR ─────────────────────────────────────────────────────
        logger.info(f"[Pipeline] [1/5] OCR: {filename}")
        try:
            ocr_result = await self.ocr.process(
                file_content, filename,
                doc_type=doc_type,
                profile=profile,
            )
        except Exception as e:
            logger.error(f"[Pipeline] OCR échoué: {e}")
            errors.append(f"OCR: {e}")
            ocr_result = None

        if not ocr_result or not ocr_result.text:
            logger.warning(
                f"[Pipeline] OCR texte vide pour {filename} → needs_review"
            )
            from backend.schemas.document import OCRResult
            ocr_result = OCRResult(
                text="", confidence=0.0, pages=0, engine="error",
                entities={}, needs_review=True, quality_score=0.0,
                validation_warnings=["OCR échoué — révision manuelle requise"],
            )

        # ── Étape 2 : NER ─────────────────────────────────────────────────────
        logger.info(f"[Pipeline] [2/5] NER: {filename}")
        try:
            ner_result = await self.ner.process(
                ocr_result.text, filename, profile=profile,
            )
            # Fallback 1 : inférer depuis le chemin
            if not ner_result.aircraft_registration and original_path:
                ner_result.aircraft_registration = \
                    self.ner.infer_aircraft_from_path(original_path)
            # Fallback 2 : regex sur le nom de fichier
            if not ner_result.aircraft_registration:
                m = re.search(r"(TS-IN[A-Z])", filename, re.IGNORECASE)
                if m:
                    ner_result.aircraft_registration = m.group(1).upper()
        except Exception as e:
            logger.error(f"[Pipeline] NER échoué: {e}")
            errors.append(f"NER: {e}")
            from backend.schemas.document import NERResult
            ner_result = NERResult()

        # ── Étape 2b : Aircraft Resolver (lookup base de données) ─────────────
        # Si après NER + fallbacks l'avion est toujours inconnu,
        # on interroge la base via la référence ES ou le nom de fichier.
        # Le système "apprend" de ses propres archives.
        if not ner_result.aircraft_registration:
            logger.info(
                f"[Pipeline] [2b] AircraftResolver: "
                f"avion non détecté pour '{filename}', "
                f"lookup DB via ES='{ner_result.es_reference}'..."
            )
            try:
                resolved = await _resolve_aircraft_from_db(
                    db,
                    es_reference=ner_result.es_reference,
                    filename=filename,
                )
                if resolved:
                    ner_result.aircraft_registration = resolved
                    logger.info(
                        f"[Pipeline] [2b] ✓ Avion résolu via DB: "
                        f"'{resolved}' pour '{filename}'"
                    )
                else:
                    logger.warning(
                        f"[Pipeline] [2b] ✗ Avion non résolu pour '{filename}'"
                    )
            except Exception as e:
                logger.warning(f"[Pipeline] AircraftResolver ignoré: {e}")

        # ── Étape 3 : Classification ──────────────────────────────────────────
        logger.info(f"[Pipeline] [3/5] Classification: {filename}")
        try:
            classifier_result = await self.classifier.process(
                ocr_result.text, filename, original_path, ner_result
            )

            if classifier_result.predicted_type.value != doc_type:
                logger.debug(
                    f"[Pipeline] Type divergent: "
                    f"path='{doc_type}' vs "
                    f"classifier='{classifier_result.predicted_type.value}'"
                )
                # Priorité au chemin si type connu et non 'unknown'
                if doc_type != 'unknown':
                    enum_value = PATH_TO_ENUM.get(doc_type.lower())
                    if enum_value:
                        try:
                            classifier_result.predicted_type = \
                                DocumentTypeEnum(enum_value)
                            classifier_result.predicted_category = enum_value
                            logger.debug(
                                f"[Pipeline] ✅ Correction chemin appliquée : "
                                f"'{enum_value}'"
                            )
                        except ValueError:
                            logger.debug(
                                f"[Pipeline] ⚠️ Type chemin '{enum_value}' "
                                f"non trouvé dans l'enum"
                            )

        except Exception as e:
            logger.error(f"[Pipeline] Classifier échoué: {e}")
            errors.append(f"Classifier: {e}")
            classifier_result = ClassifierResult(
                predicted_type=DocumentTypeEnum.OTHER,
                predicted_category="Other",
                confidence=0.5,
            )

        # ── Étape 3b : Résolution catégorie via Linked WP ────────────────────
        if classifier_result.predicted_type == DocumentTypeEnum.WORK_ORDER:
            try:
                resolved_category = await resolve_linked_wp_category(
                    db, ocr_result.text, filename=filename
                )
                if resolved_category:
                    old_cat = classifier_result.predicted_category
                    classifier_result.predicted_category = resolved_category
                    logger.info(
                        f"[Pipeline] [LinkedWP] {filename}: "
                        f"catégorie {old_cat!r} → {resolved_category!r}"
                    )
            except Exception as e:
                logger.warning(f"[Pipeline] LinkedWP resolver ignoré: {e}")

        # ── Étape 4 : Embedding ───────────────────────────────────────────────
        logger.info(f"[Pipeline] [4/5] Embedding: {filename}")
        embedding = None
        try:
            embedding = await self.embedding.embed_document(
                ocr_text=ocr_result.text,
                filename=filename,
                doc_type=classifier_result.predicted_type.value,
                category=classifier_result.predicted_category,
                aircraft=ner_result.aircraft_registration or "",
                es_ref=ner_result.es_reference or "",
                ata=ner_result.ata_chapter or "",
                sb_ad=ner_result.sb_ad_reference or "",
                semantic_prefix=profile.embedding.semantic_prefix,
            )
        except Exception as e:
            logger.warning(f"[Pipeline] Embedding ignoré: {e}")
            errors.append(f"Embedding: {e}")

        # ── Étape 5 : Archivage ───────────────────────────────────────────────
        logger.info(f"[Pipeline] [5/5] Archivage: {filename}")
        try:
            document, is_dup = await self.archive.archive(
                db=db,
                content=file_content,
                filename=filename,
                original_path=original_path,
                ocr=ocr_result,
                ner=ner_result,
                classification=classifier_result,
                embedding=embedding,
                file_size_kb=file_size_kb,
            )
            await db.commit()
        except Exception as e:
            logger.error(f"[Pipeline] Archivage échoué: {e}")
            errors.append(f"Archive: {e}")
            await db.rollback()
            return PipelineResult(
                document_id=0,
                filename=filename,
                status=DocumentStatusEnum.ERROR,
                ocr=ocr_result,
                ner=ner_result,
                classification=classifier_result,
                errors=errors,
                processing_time_s=round(time.perf_counter() - start, 3),
            )

        duration = round(time.perf_counter() - start, 3)
        self.monitoring.record_processing(
            success=len(errors) == 0, duration_s=duration
        )

        logger.info(
            f"[Pipeline] ✓ {filename} → doc#{document.id} "
            f"[{classifier_result.predicted_type.value}] "
            f"avion={ner_result.aircraft_registration or '?'} "
            f"conf={classifier_result.confidence:.0%} "
            f"ocr={ocr_result.confidence:.1f}% "
            f"t={duration}s"
        )

        return PipelineResult(
            document_id=document.id,
            filename=filename,
            status=DocumentStatusEnum.ARCHIVED,
            ocr=ocr_result,
            ner=ner_result,
            classification=classifier_result,
            embedding_generated=embedding is not None,
            is_duplicate=is_dup,
            processing_time_s=duration,
            errors=errors,
        )

    async def process_batch(
        self,
        db_factory,
        documents: list[dict],
        concurrency: int = 3,
    ) -> list[PipelineResult]:
        """
        Traite N documents en parallèle via asyncio.gather + semaphore.
        Chaque document obtient SA PROPRE session DB.
        """
        sem = asyncio.Semaphore(concurrency)
        logger.info(
            f"[Pipeline] Batch: {len(documents)} documents, "
            f"concurrence={concurrency}"
        )

        async def _process_one(doc: dict) -> PipelineResult:
            async with sem:
                async with db_factory() as db:
                    return await self.process_document(
                        db=db,
                        file_content=doc["content"],
                        filename=doc["filename"],
                        original_path=doc.get("path", ""),
                        file_size_kb=doc.get("size_kb", 0.0),
                    )

        results = await asyncio.gather(
            *[_process_one(doc) for doc in documents],
            return_exceptions=True,
        )

        final: list[PipelineResult] = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                logger.error(f"[Pipeline] Batch doc #{i} exception: {r}")
                final.append(PipelineResult(
                    document_id=0,
                    filename=documents[i].get("filename", f"doc_{i}"),
                    status=DocumentStatusEnum.ERROR,
                    errors=[str(r)],
                    processing_time_s=0.0,
                ))
            else:
                final.append(r)

        ok  = sum(1 for r in final if r.status == DocumentStatusEnum.ARCHIVED)
        dup = sum(1 for r in final if r.status == DocumentStatusEnum.DUPLICATE)
        err = sum(1 for r in final if r.status == DocumentStatusEnum.ERROR)
        logger.info(
            f"[Pipeline] Batch terminé: {ok} archivés, "
            f"{dup} doublons, {err} erreurs / {len(documents)} total"
        )
        return final


# ── Singleton global ──────────────────────────────────────────────────────────
_pipeline: PipelineOrchestrator | None = None


def get_pipeline() -> PipelineOrchestrator:
    global _pipeline
    if _pipeline is None:
        _pipeline = PipelineOrchestrator()
    return _pipeline