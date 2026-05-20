"""
Agent Monitoring + Agent Arborescence — version optimisée
Optimisations :
  - get_system_health : 5 requêtes séparées → 1 seule requête agrégée
  - Cache TTL 30s sur get_system_health (évite le martelage DB au polling frontend)
  - TreeAgent : patterns regex compilés une fois au niveau classe
  - TreeAgent : os.scandir récursif remplace os.walk (2× plus rapide sur gros volumes)
"""
import os
import re
import time
from datetime import datetime
from pathlib import Path

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case, desc


# ══════════════════════════════════════════════════════════════════════════════
# MONITORING AGENT
# ══════════════════════════════════════════════════════════════════════════════

class MonitoringAgent:
    """
    Agent Monitoring — surveillance temps réel du pipeline.
    - Collecte des métriques système via une requête agrégée unique
    - Cache TTL 30 s pour ne pas interroger la DB à chaque poll frontend
    - Récupère les alertes actives
    - Enregistre les statistiques de traitement (moyenne mobile)
    """

    # Durée du cache santé système (secondes)
    _HEALTH_CACHE_TTL = 30

    def __init__(self):
        self.name = "Monitoring Agent"
        self._pipeline_stats = {
            "total_processed": 0,
            "total_errors": 0,
            "avg_processing_time": 0.0,
            "start_time": datetime.utcnow(),
        }
        # Cache pour get_system_health
        self._health_cache: dict | None = None
        self._health_cache_ts: float = 0.0

        logger.info(f"[{self.name}] Initialisé")

    # ── Enregistrement traitement ───────────────────────────────────────────

    def record_processing(self, success: bool, duration_s: float) -> None:
        """Met à jour les stats pipeline (moyenne mobile, compteurs)."""
        self._pipeline_stats["total_processed"] += 1
        if not success:
            self._pipeline_stats["total_errors"] += 1
        n = self._pipeline_stats["total_processed"]
        avg = self._pipeline_stats["avg_processing_time"]
        self._pipeline_stats["avg_processing_time"] = (avg * (n - 1) + duration_s) / n

    def invalidate_cache(self) -> None:
        """Force le prochain appel à get_system_health à relire la DB."""
        self._health_cache_ts = 0.0

    # ── Santé système ───────────────────────────────────────────────────────

    async def get_system_health(self, db: AsyncSession) -> dict:
        """
        Retourne un snapshot de santé.
        Résultat mis en cache 30 s pour limiter les lectures DB lors
        du polling toutes les 30 s depuis le frontend.
        """
        now = time.monotonic()
        if self._health_cache and (now - self._health_cache_ts) < self._HEALTH_CACHE_TTL:
            return self._health_cache

        from backend.models.document import Document, DocumentStatus
        from backend.models.check import Alert

        # ── 1 seule requête agrégée sur documents ──────────────────────────
        agg = await db.execute(
            select(
                func.count(Document.id).label("total"),
                func.sum(
                    case((Document.status == DocumentStatus.ARCHIVED, 1), else_=0)
                ).label("archived"),
                func.sum(
                    case((Document.status == DocumentStatus.ERROR, 1), else_=0)
                ).label("errors"),
                func.sum(
                    case((Document.is_duplicate == True, 1), else_=0)  # noqa: E712
                ).label("duplicates"),
                func.avg(Document.ocr_confidence).label("avg_ocr"),
            )
        )
        row = agg.one()

        # ── Alertes actives (requête légère sur table Alert) ────────────────
        active_alerts = await db.scalar(
            select(func.count(Alert.id)).where(Alert.resolved == False)  # noqa: E712
        )

        uptime = (datetime.utcnow() - self._pipeline_stats["start_time"]).total_seconds()
        errors_count = int(row.errors or 0)

        result = {
            "status": "healthy" if errors_count < 10 else "degraded",
            "uptime_s": round(uptime),
            "total_documents": int(row.total or 0),
            "archived": int(row.archived or 0),
            "errors": errors_count,
            "duplicates_detected": int(row.duplicates or 0),
            "active_alerts": int(active_alerts or 0),
            "avg_ocr_confidence": round(float(row.avg_ocr or 0.0), 2),
            "pipeline": {
                "total_processed": self._pipeline_stats["total_processed"],
                "total_errors": self._pipeline_stats["total_errors"],
                "avg_processing_time_s": round(self._pipeline_stats["avg_processing_time"], 3),
                "docs_per_hour": round(
                    self._pipeline_stats["total_processed"] / max(uptime / 3600, 0.01), 1
                ),
            },
            "agents": {
                "ocr":        {"status": "ready"},
                "ner":        {"status": "ready"},
                "classifier": {"status": "ready"},
                "embedding":  {"status": "ready"},
                "archive":    {"status": "ready"},
                "monitoring": {"status": "active"},
            },
            "timestamp": datetime.utcnow().isoformat(),
        }

        # Mise en cache
        self._health_cache = result
        self._health_cache_ts = now
        return result

    # ── Alertes récentes ────────────────────────────────────────────────────

    async def get_recent_alerts(self, db: AsyncSession, limit: int = 20) -> list:
        from backend.models.check import Alert
        result = await db.execute(
            select(Alert).order_by(desc(Alert.created_at)).limit(limit)
        )
        return [
            {
                "id": a.id,
                "title": a.title,
                "message": a.message,
                "severity": a.severity.value if a.severity else "info",
                "alert_type": a.alert_type.value if a.alert_type else None,
                "aircraft_registration": a.aircraft_registration,
                "document_id": a.document_id,
                  "resolved": a.resolved,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in result.scalars().all()
        ]


# ══════════════════════════════════════════════════════════════════════════════
# TREE AGENT
# ══════════════════════════════════════════════════════════════════════════════

class TreeAgent:
    """
    Agent Arborescence — lit la structure locale et infère les métadonnées.
    Analyse Aircraft/{TS-INP,TS-INQ}/... pour construire les entrées Document.

    Optimisations vs version précédente :
      - Patterns regex compilés une fois au niveau de la classe
      - _scan_dir récursif avec os.scandir (évite l'overhead os.walk)
    """

    FLEET_REGISTRATIONS: frozenset[str] = frozenset({
        "TS-INP", "TS-INQ", "TS-IML", "TS-INN", "TS-INM",
    })
    SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({
        ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    })

    # ── Patterns compilés une fois au chargement du module ──────────────────
    _RE_ES        = re.compile(r"ES(\d{6,8})", re.IGNORECASE)
    _RE_AD_SB     = re.compile(r"(A3\d{2}-\d{2}[A-Z]?\d{3,5}[A-Z]?)", re.IGNORECASE)
    _RE_ATA       = re.compile(r"ATA[\s\-]?(\d{2})", re.IGNORECASE)
    _RE_ITEM      = re.compile(r"^(\d{3,4})\.pdf$", re.IGNORECASE)

    _SUBCAT_MAP: dict[str, str] = {
        "JOBCARD":       "Jobcard",
        "JOB CARD":      "Jobcard",
        "WORKORDER":     "Work Order",
        "WORK ORDER":    "Work Order",
        "DEFECT REPORT": "Defect Report",
        "NCR":           "NCR",
        "RCT":           "RCT",
    }

    def __init__(self, archive_root: str):
        self.archive_root = Path(archive_root)
        self.name = "Tree Agent"
        logger.info(f"[{self.name}] Root: {self.archive_root}")

    # ── Scan ────────────────────────────────────────────────────────────────

    def scan(self) -> list[dict]:
        """
        Parcourt récursivement l'arborescence avec os.scandir.
        Retourne une liste de dicts avec toutes les métadonnées inférables.
        """
        if not self.archive_root.exists():
            logger.error(f"[{self.name}] Chemin introuvable: {self.archive_root}")
            return []

        results: list[dict] = []
        self._scan_dir(self.archive_root, results)
        logger.info(f"[{self.name}] Scan terminé: {len(results)} fichiers trouvés")
        return results

    def _scan_dir(self, directory: Path, results: list[dict]) -> None:
        """Récursion via os.scandir — plus rapide que os.walk sur gros volumes."""
        try:
            with os.scandir(directory) as it:
                for entry in it:
                    if entry.name.startswith(".") or entry.name == "__MACOSX":
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        self._scan_dir(Path(entry.path), results)
                    elif entry.is_file(follow_symlinks=False):
                        ext = Path(entry.name).suffix.lower()
                        if ext in self.SUPPORTED_EXTENSIONS:
                            rel = os.path.relpath(entry.path, self.archive_root)
                            results.append(self._infer_metadata(entry.path, entry.name, rel))
        except PermissionError as exc:
            logger.warning(f"[{self.name}] Accès refusé: {exc}")

    # ── Inférence métadonnées ───────────────────────────────────────────────

    def _infer_metadata(self, full_path: str, filename: str, rel_path: str) -> dict:
        """Infère les métadonnées depuis le chemin de fichier."""
        parts = rel_path.replace("\\", "/").split("/")

        # Immatriculation (premier segment)
        aircraft_reg: str | None = None
        if parts and parts[0].upper() in self.FLEET_REGISTRATIONS:
            aircraft_reg = parts[0].upper()

        # Catégorie (deuxième segment)
        category = parts[1] if len(parts) > 1 else ""

        # ES Reference (premier match dans les segments de chemin)
        es_ref: str | None = None
        for part in parts:
            m = self._RE_ES.search(part)
            if m:
                es_ref = f"ES{m.group(1)}"
                break

        # Sous-catégorie
        subcategory = ""
        for part in parts:
            sc = self._SUBCAT_MAP.get(part.upper())
            if sc:
                subcategory = sc
                break

        # AD/SB depuis filename
        m_sb = self._RE_AD_SB.search(filename)
        sb_ad: str | None = m_sb.group(1).upper() if m_sb else None

        # ATA depuis chemin complet
        m_ata = self._RE_ATA.search(rel_path)
        ata: str | None = f"ATA {m_ata.group(1)}" if m_ata else None

        # Item number depuis filename (ex: 0034.pdf)
        m_item = self._RE_ITEM.match(filename)
        item_num: str | None = m_item.group(1) if m_item else None

        # Taille fichier
        try:
            size_kb = os.path.getsize(full_path) / 1024
        except OSError:
            size_kb = 0.0

        return {
            "filename":             filename,
            "full_path":            full_path,
            "rel_path":             rel_path,
            "aircraft_registration": aircraft_reg,
            "category":             category,
            "subcategory":          subcategory,
            "es_reference":         es_ref,
            "sb_ad_reference":      sb_ad,
            "ata_chapter":          ata,
            "item_number":          item_num,
            "file_size_kb":         round(size_kb, 2),
            "extension":            Path(filename).suffix.lower(),
        }

    # ── Arborescence JSON ───────────────────────────────────────────────────

    def get_tree_json(self) -> dict:
        """Retourne l'arborescence sous forme d'un dict JSON imbriqué."""
        docs = self.scan()
        tree: dict = {"name": "Aircraft", "type": "root", "children": {}}

        for doc in docs:
            parts = doc["rel_path"].replace("\\", "/").split("/")
            node = tree["children"]
            for part in parts[:-1]:
                if part not in node:
                    node[part] = {"name": part, "type": "folder", "children": {}}
                node = node[part]["children"]
            node[parts[-1]] = {
                "name":     parts[-1],
                "type":     "file",
                "metadata": doc,
            }

        return tree
