#  Documentation API
## NouvelAir MRO · Intelligence Artificielle · Archivage Documentaire

Base URL: `http://localhost:8000/api/v1`
Documentation interactive: `http://localhost:8000/api/docs`

---

## Authentification
Actuellement en mode développement sans token JWT.
En production, ajouter `Authorization: Bearer <token>` dans les headers.

---

## Documents

### `POST /documents/upload`
Upload un document PDF et déclenche le pipeline complet.

**Body:** `multipart/form-data`
- `file` (required): fichier PDF/DOC/image

**Réponse:**
```json
{
  "message": "Document archivé avec succès",
  "document_id": 42,
  "pipeline_result": {
    "document_id": 42,
    "filename": "0034.pdf",
    "status": "archived",
    "ocr": {"text": "...", "confidence": 97.3, "pages": 2, "engine": "pdfplumber"},
    "ner": {
      "aircraft_registration": "TS-INP",
      "es_reference": "ES001778",
      "item_number": "0034",
      "ata_chapter": "ATA 27"
    },
    "classification": {
      "predicted_type": "Jobcard",
      "predicted_category": "Check A",
      "confidence": 0.93
    },
    "embedding_generated": true,
    "is_duplicate": false,
    "processing_time_s": 1.34
  }
}
```

### `POST /documents/upload/batch`
Upload multiple fichiers (max 50).

### `GET /documents/`
Liste les documents avec filtres.

**Query params:**
- `aircraft` — Immatriculation (TS-INP, TS-IML, TS-INQ)
- `doc_type` — Type (Work Order, Jobcard, AD, SB, ATL, Defect Report, NCR...)
- `category` — Catégorie (Check A, Check C, SB/AD, ATL, Specs...)
- `ata_chapter` — ATA Chapter (ATA 27, ATA 32...)
- `es_reference` — Référence ES (ES001778...)
- `page`, `size` — Pagination
- `sort` — Tri (created_at, doc_type...)

### `GET /documents/{id}`
Détail d'un document.

### `PATCH /documents/{id}`
Correction manuelle des métadonnées.

**Body:**
```json
{
  "doc_type": "Jobcard",
  "aircraft_registration": "TS-INP",
  "es_reference": "ES001778",
  "ata_chapter": "ATA 27",
  "manually_corrected": true
}
```

### `DELETE /documents/{id}`
Supprime un document.

### `GET /documents/{id}/ocr-text`
Retourne le texte OCR brut du document.

---

## Recherche

### `GET /search/?q=...`
Recherche hybride FTS + pgvector.

**Query params:**
- `q` (required) — Requête de recherche
- `aircraft` — Filtrer par avion
- `doc_type` — Filtrer par type
- `semantic` — Activer recherche sémantique (default: true)
- `fts` — Activer FTS (default: true)
- `limit`, `offset` — Pagination

**Réponse:**
```json
{
  "query": "Work Order ES001778 ATA 27",
  "results": [
    {
      "document": {"id": 42, "filename": "ES00272829.pdf", "...": "..."},
      "score": 0.92,
      "fts_score": 0.87,
      "semantic_score": 0.95,
      "matched_entities": ["Avion: TS-INP", "ES: ES001778"],
      "snippet": "...travaux effectués conformément AMM tâche 27-..."
    }
  ],
  "total": 7,
  "mode": "hybrid",
  "search_time_ms": 145.3,
  "extracted_entities": {"aircraft": "TS-INP", "es_reference": "ES001778"}
}
```

### `POST /search/rag`
Questions/Réponses sur les documents (RAG).

**Body:**
```json
{
  "question": "Quels Work Orders concernent l'ATA 27 du Check A ES001778 de TS-INP ?",
  "aircraft_registration": "TS-INP",
  "top_k": 5
}
```

---

## Aéronefs

### `GET /aircraft/`
Liste tous les aéronefs avec compteurs de documents.

### `GET /aircraft/{registration}/documents`
Documents d'un aéronef spécifique.

### `GET /aircraft/{registration}/checks`
Checks A/C d'un aéronef.

---

## Pipeline

### `GET /pipeline/status`
Santé du système et statut des 6 agents.

```json
{
  "status": "healthy",
  "uptime_s": 86400,
  "total_documents": 4821,
  "archived": 4650,
  "active_alerts": 3,
  "avg_ocr_confidence": 97.3,
  "pipeline": {
    "total_processed": 4821,
    "total_errors": 2,
    "avg_processing_time_s": 1.34,
    "docs_per_hour": 127
  },
  "agents": {
    "ocr_agent": "active",
    "ner_agent": "active",
    "classifier_agent": "active",
    "embedding_agent": "active",
    "archive_agent": "active",
    "monitoring_agent": "active"
  }
}
```

### `GET /pipeline/alerts`
Alertes actives.

### `POST /pipeline/alerts/{id}/resolve`
Résoudre une alerte.

### `POST /pipeline/scan`
Scanner l'arborescence locale et importer.

**Query params:**
- `path` — Chemin à scanner (défaut: config `ARCHIVE_ROOT_PATH`)
- `dry_run` — true = scan sans import (défaut: true)

### `GET /pipeline/tree`
Arborescence JSON de l'archive locale.

---

## Analytics

### `GET /analytics/kpis`
KPIs tableau de bord.

```json
{
  "total_documents": 4821,
  "archived": 4650,
  "avg_ocr_confidence": 97.3,
  "active_alerts": 3,
  "critical_ads": 12,
  "total_aircraft": 3,
  "archive_rate_pct": 96.5
}
```

### `GET /analytics/stats`
Distribution par type, catégorie, avion.

### `GET /analytics/powerbi-token`
Token Power BI Embedded (nécessite configuration Azure AD).

---

## Codes d'erreur

| Code | Description |
|------|-------------|
| 400  | Paramètre invalide ou fichier trop volumineux |
| 404  | Ressource introuvable |
| 422  | Erreur pipeline IA |
| 500  | Erreur serveur interne |

---

## Entités NER extraites automatiquement

| Entité | Pattern | Exemple |
|--------|---------|---------|
| aircraft_registration | `TS-IN[A-Z]` | TS-INP |
| es_reference | `ES\d{6,8}` | ES001778 |
| part_number | `P/N [A-Z0-9-]+` | 3538000-1 |
| serial_number | `S/N [A-Z0-9]+` | B867 |
| ata_chapter | `ATA \d{2}` | ATA 27 |
| work_order_number | `W/O \d+` | WO1234 |
| sb_ad_reference | `A3XX-\d{2}-\d{4}` | A320-27-1154 |
| item_number | `^\d{3,4}\.pdf$` | 0034 |
| document_date | `\d{2}/\d{2}/\d{4}` | 15/11/2024 |
