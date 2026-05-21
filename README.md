# Système d'Archivage Intelligent des Documents Aéronautiques
## NouvelAir MRO — Plateforme IA Documentaire

> Projet de Fin d'Études (PFE) — Master 2 Data Science  
> Faculté des Sciences de Monastir · Stage NouvelAir Tunisie  
> Directrice technique : ARFA Feriel

---

## Vue d'ensemble

Plateforme intelligente d'exploitation documentaire aéronautique combinant **pipeline IA modulaire**, **orchestration multi-agents**, **analyse sémantique vectorielle** et **ingestion documentaire automatisée** pour l'automatisation du cycle documentaire MRO.

**Contexte métier** : NouvelAir doit restituer deux aéronefs (TS-INP, TS-INQ) à leur bailleur avec une documentation technique complète. Le système transforme 3 545 PDFs non structurés en base de connaissances MRO interrogeable.

---

## Stack Technique

| Couche | Technologies |
|---|---|
| Backend API | FastAPI · Uvicorn · Python 3.11 |
| Base de données | PostgreSQL 15 (port 5434) · pgvector HNSW · pg_trgm |
| ORM | SQLAlchemy 2.0 async · asyncpg |
| OCR | pdfplumber · Tesseract 5 · OpenCV · EasyOCR |
| NER | Groq API (Llama 3.1 8B Instant) · spaCy · Regex |
| Classification | TF-IDF · Logistic Regression · ~15 classes |
| Embeddings | sentence-transformers all-MiniLM-L6-v2 (384d) |
| Recherche | pgvector cosine similarity · FTS PostgreSQL |
| Déduplication | SHA-256 |
| Frontend | React 18 · Vite · port 3000 |
| Analytics | Power BI (4 vues PostgreSQL) |

---

## Performances

| Métrique | Score |
|---|---|
| Accuracy classification | 91.2% |
| F1 Weighted classification | 90.7% |
| F1 Macro classification | 64.5% |
| F1 NER entity-level (seqeval) | 95% |
| Precision@5 recherche sémantique | 88% |
| Latence recherche (médiane) | < 300ms |
| Documents traités | 3 545 |
| Documents uniques (SHA-256) | 2 674 |
| Couverture embeddings | 100% |

---

## Architecture — Pipeline 6 Agents

```
PDF
 │
 ▼
[1] OCR Agent v5        pdfplumber → Tesseract (4 PSM) → EasyOCR fallback
 │                      Confiance < 60% → EasyOCR activé
 ▼
[2] NER Agent v6        Groq Llama 3.1 8B · 7 stratégies de priorité
 │                      Entités : REGISTRATION · ES_REF · DOC_TYPE · ATA · DATE
 │
[2b] Aircraft Resolver  Lookup DB si immatriculation non détectée
 │                      → cherche via es_reference dans les archives existantes
 ▼
[3] Classifier Agent    TF-IDF + Logistic Regression · class_weight=balanced
 │                      15 catégories · path-based rules override
 │
[3b] LinkedWP Resolver  Résolution catégorie via Work Package lié (RCT anchor)
 ▼
[4] Embedding Agent     all-MiniLM-L6-v2 · vecteur 384 dimensions
 ▼
[5] Archive Agent       PostgreSQL · SHA-256 dédup · copie vers ORGANISED/
 ▼
[6] Monitoring Agent    Alertes · KPIs · traçabilité
```

---

## Structure du Projet

```
système_darchivage_intelligent/
├── backend/
│   ├── main.py                    # Point d'entrée FastAPI
│   ├── config.py                  # Configuration (.env)
│   ├── database.py                # Connexion async PostgreSQL
│   ├── models/
│   │   ├── aircraft.py            # Modèle Aircraft (18 aéronefs)
│   │   ├── document.py            # Modèle Document (~4001 docs)
│   │   └── check.py               # Modèle AircraftCheck + Alert
│   ├── schemas/
│   │   ├── document.py            # Schémas Pydantic
│   │   └── search.py              # Schémas recherche
│   ├── agents/
│   │   ├── ocr_agent.py           # OCR v5 multi-moteur
│   │   ├── ner_agent.py           # NER v6 Groq + règles
│   │   ├── classifier_agent.py    # TF-IDF + LR
│   │   ├── embedding_agent.py     # MiniLM 384d
│   │   ├── archive_agent.py       # Archivage + ORGANISED/
│   │   ├── monitoring_agent.py    # Alertes + métriques
│   │   └── linked_wp_resolver.py  # Résolution Work Package
│   ├── api/
│   │   ├── documents_api.py       # CRUD + Upload + Pipeline
│   │   └── routes.py              # Search · Aircraft · Pipeline · Analytics
│   ├── core/
│   │   ├── pipeline.py            # Orchestrateur 6 agents
│   │   └── processing_profiles.py # Profils par type documentaire
│   └── services/
│       └── search_service.py      # Recherche hybride FTS + vectorielle
├── frontend/                      # React 18 + Vite
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Dashboard.jsx      # KPIs + analytics
│   │   │   ├── Documents.jsx      # Arbre 3 niveaux + PDFModal
│   │   │   ├── Search.jsx         # Recherche hybride + RAG
│   │   │   ├── Fleet.jsx          # Vue flotte 18 aéronefs + MSN
│   │   │   ├── Upload.jsx         # Upload + validation humaine
│   │   │   ├── Checks.jsx         # Checks A/C/D
│   │   │   ├── Pipeline.jsx       # Statut agents live
│   │   │   ├── PipelineDemo.jsx   # Simulation pipeline
│   │   │   ├── Monitoring.jsx     # Alertes MRO
│   │   │   └── Analytics.jsx      # Statistiques avancées
│   │   ├── components/
│   │   │   ├── Header.jsx
│   │   │   ├── Sidebar.jsx        # Navigation + ChecksAccordion
│   │   │   └── NewDocumentBanner.jsx
│   │   ├── contexts/
│   │   │   ├── AuthContext.jsx
│   │   │   └── ToastContext.jsx
│   │   └── hooks/
│   │       ├── useApi.js
│   │       └── useDocumentWatcher.js
│   └── package.json
├── models/
│   └── classifier_model.pkl       # Modèle TF-IDF + LR entraîné
├── scripts/
│   ├── init_db.sql                # Initialisation PostgreSQL
│   ├── retrain_classifier.py      # Réentraînement du classifieur
│   └── fix_missing_paths.py       # Correction chemins manquants
├── .env.example                   # Template variables d'environnement
├── requirements.txt               # Dépendances production
├── requirements-dev.txt           # Dépendances développement (+ torch)
└── install.bat                    # Script installation Windows
```

---

## Installation Rapide (Windows)

### Prérequis

- Python 3.11 — [python.org/downloads](https://python.org/downloads) (**cocher "Add to PATH"**)
- PostgreSQL 15 — [postgresql.org/download/windows](https://postgresql.org/download/windows) (port **5434**)
- Tesseract OCR — [github.com/UB-Mannheim/tesseract/wiki](https://github.com/UB-Mannheim/tesseract/wiki)
- Poppler — [github.com/oschwartz10612/poppler-windows](https://github.com/oschwartz10612/poppler-windows)

### Installation automatique

```batch
install.bat
```

### Installation manuelle

```powershell
# 1. Cloner le repo
git clone https://github.com/ARFAFeriel/syst-me_d-archivage_intelligent.git
cd syst-me_d-archivage_intelligent

# 2. Environnement virtuel
python -m venv venv
venv\Scripts\activate

# 3. Dépendances
pip install -r requirements.txt

# 4. Configuration
copy .env.example .env
# Éditer .env avec vos paramètres

# 5. Base de données
psql -U postgres -p 5434 -c "CREATE DATABASE nouv_db;"

# 6. Lancer le backend
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000

# 7. Lancer le frontend (développement)
cd frontend
npm install
npm run dev
```

---

## Configuration (.env)

```env
# Base de données
DATABASE_URL=postgresql+asyncpg://postgres:VOTRE_MOT_DE_PASSE@localhost:5434/nouv_db

# Chemins archives
ARCHIVE_ROOT_PATH=C:\chemin\vers\vos\archives\Aircraft
UPLOAD_PATH=C:\chemin\vers\uploads_temp

# API Groq (NER v6)
GROQ_API_KEY=votre_cle_groq

# Sécurité
SECRET_KEY=votre_secret_jwt
MAX_UPLOAD_SIZE_MB=100
```

---

## Types Documentaires (15 classes)

| Code | Libellé MRO |
|---|---|
| AD | Airworthiness Directive |
| SB | Service Bulletin |
| EAD | Emergency Airworthiness Directive |
| AMM | Aircraft Maintenance Manual |
| CMM | Component Maintenance Manual |
| IPC | Illustrated Parts Catalog |
| SPECS | Specifications techniques |
| WORK_ORDER | Work Order |
| JOBCARD | Job Card |
| RCT | Record of Completed Tasks |
| NCR | Non-Conformity Report |
| DEFECT_REPORT | Defect Report |
| D_B_CHART | D&B Chart |
| ATL | Aircraft Technical Log |
| CERTIFICATE | Certificat |

---

## Flotte NouvelAir (18 aéronefs)

| Immatriculation | MSN | Type |
|---|---|---|
| TS-INC | 1744 | A320-214 CEO |
| TS-IND | 5016 | A320-214 CEO |
| TS-INE | 5310 | A320-214 CEO |
| TS-INF | 5867 | A320-214 CEO |
| TS-ING | 5878 | A320-214 CEO |
| TS-INH | 5905 | A320-214 CEO |
| TS-INI | 6017 | A320-214 CEO |
| TS-INJ | 6084 | A320-214 CEO |
| TS-INK | 6133 | A320-214 CEO |
| TS-INL | 12280 | A320-251N NEO |
| TS-INM | 12308 | A320-251N NEO |
| TS-INN | 6254 | A320-214 CEO |
| TS-INO | 6285 | A320-214 CEO |
| TS-INP | 1597 | A320-214 CEO |
| TS-INQ | 6333 | A320-214 CEO |
| TS-INR | 6362 | A320-214 CEO |
| TS-INT | 6401 | A320-214 CEO |
| TS-INU | 6435 | A320-214 CEO |

---

## Endpoints API principaux

| Méthode | Endpoint | Description |
|---|---|---|
| POST | `/api/v1/documents/upload` | Upload + pipeline IA complet |
| GET | `/api/v1/documents/` | Liste paginée avec filtres |
| GET | `/api/v1/documents/{id}/file` | Servir le PDF |
| GET | `/api/v1/search/?q=...` | Recherche hybride FTS + vectorielle |
| POST | `/api/v1/search/rag` | Q&A documentaire (RAG) |
| GET | `/api/v1/aircraft/` | Liste flotte avec compteurs |
| GET | `/api/v1/analytics/kpis` | KPIs tableau de bord |
| GET | `/api/v1/analytics/archive-tree` | Arborescence documentaire |
| GET | `/api/v1/pipeline/status` | Statut des 6 agents |

Documentation interactive : `http://localhost:8000/docs`

---

## Conformité réglementaire

- **EASA Part-145** — traçabilité complète des opérations de maintenance
- **ATA iSpec 2200** — structure documentaire normalisée
- **ICAO** — formats d'immatriculation (TS-INP, TS-INQ...)
- **DGAC Tunisie** — conformité autorité nationale

---

## Perspectives d'évolution

- **RAG aéronautique** — chatbot maintenance via LangChain/LlamaIndex
- **Fine-tuning aviation** — embeddings spécialisés domaine MRO
- **Active learning** — amélioration continue du classifieur
- **Déploiement intranet** — serveur NouvelAir (Python + PostgreSQL)
- **Stockage distribué** — migration vers Cloudflare R2 / AWS S3 (>10GB)
- **Agents autonomes** — détection incohérences réglementaires AD

---

## Auteur

**ARFA Feriel** — Master 2 Data Science, Faculté des Sciences de Monastir  
Stage PFE — Direction Technique MRO, NouvelAir Tunisie  
Année universitaire 2025–2026
