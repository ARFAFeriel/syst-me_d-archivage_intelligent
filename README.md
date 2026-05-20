# Système d'Archivage intelligent des Documents Aéronautiques
## NouvelAir MRO · Nouvelair 

---

## Stack Technique

| Couche | Technologies |
|---|---|
| Backend API | FastAPI · Uvicorn · Python 3.11+ |
| Base de données | PostgreSQL 15 (port 5434) · pgvector (HNSW m=16, ef=64) · pg_trgm |
| ORM | SQLAlchemy 2.0 async · asyncpg |
| OCR | pdfplumber · Tesseract OCR 5 (UB-Mannheim) · OpenCV 4.10.0 (`opencv-contrib-python-headless`) · pdf2image · Poppler |
| Extraction de tableaux | camelot 1.0.9 · img2table 1.4.2 |
| NER / Extraction | spaCy `fr_core_news_sm` · 25 patterns regex compilés |
| Classification | TF-IDF · Logistic Regression · 10 classes aéro |
| Embeddings | sentence-transformers `all-MiniLM-L6-v2` (384 dimensions) |
| Recherche | FTS PostgreSQL · pgvector cosine similarity (Precision@5 = 88 %) |
| Déduplication | SHA-256 |
| Frontend | HTML5 · CSS3 · Vanilla JS SPA  |
| Analytics | Microsoft Power BI (9 vues PostgreSQL) |

---

## Performances du Système

| Métrique | Score |
|---|---|
| F1-score Classification | 91 % |
| F1-score NER (immatriculation aéronef) | 95 % |
| Latence recherche sémantique | < 300 ms |
| Precision@5 recherche | 88 % |
| Couverture embeddings | 100 % (2 674 / 2 674) |
| Documents `needs_review` résiduels | 0 |
| Documents sans immatriculation | 0 |

---

## Structure du Projet

```
sys_archivage_intelligent/
├── backend/
│   ├── main.py                    # Point d'entrée FastAPI
│   ├── config.py                  # Configuration globale
│   ├── database.py                # Connexion async PostgreSQL
│   ├── models/
│   │   ├── __init__.py
│   │   ├── aircraft.py            # Modèle Aéronef
│   │   ├── document.py            # Modèle Document
│   │   ├── check.py               # Modèle Check A/C
│   │   └── alert.py               # Modèle Alerte
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── document.py            # Schémas Pydantic
│   │   └── search.py              # Schémas recherche
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── ocr_agent.py           # Agent OCR v4 (pipeline 10 étapes)
│   │   ├── ner_agent.py           # Agent NER (spaCy + 25 regex)
│   │   ├── classifier_agent.py    # Agent Classification (TF-IDF + LR)
│   │   ├── embedding_agent.py     # Agent Embeddings (MiniLM-L6-v2)
│   │   ├── archive_agent.py       # Agent Archivage (PostgreSQL)
│   │   ├── monitoring_agent.py    # Agent Monitoring & Alertes
│   │   └── tree_agent.py          # Agent Lecture Arborescence
│   ├── api/
│   │   ├── __init__.py
│   │   ├── documents.py           # Routes /documents
│   │   ├── search.py              # Routes /search
│   │   ├── aircraft.py            # Routes /aircraft
│   │   ├── pipeline.py            # Routes /pipeline
│   │   └── analytics.py          # Routes /analytics
│   ├── core/
│   │   ├── __init__.py
│   │   ├── pipeline.py            # Orchestrateur pipeline 6 agents
│   │   └── deduplication.py      # SHA-256 déduplication
│   └── services/
│       ├── __init__.py
│       └── search_service.py     # Service recherche hybride
├── frontend/
│   └── index.html                 # SPA complète (vanilla JS)
├── scripts/
│   ├── init_db.sql               # Initialisation PostgreSQL + extensions
│   ├── seed_db.py                # Données de test
│   ├── scan_archive.py           # Scanner arborescence locale
│   ├── reprocess_ocr.py          # Retraitement OCR ciblé (139 docs)
│   └── reprocess_ner.py          # Retraitement NER (correction immatriculations)
├── docs/
│   └── api.md                    # Documentation API
└── requirements.txt
```

---

## Types Documentaires Supportés (10 classes)

| Code | Libellé |

| AD | Airworthiness Directive |
| SB | Service Bulletin |
| AMM | Aircraft Maintenance Manual |
| CMM | Component Maintenance Manual |
| IPC | Illustrated Parts Catalog |
| MEL | Minimum Equipment List |
| Job Card | Carte de travail |
| Work Order | Ordre de travail |
| CRS | Certificate of Release to Service |
| COA | Certificate of Airworthiness |

---

## Pipeline de Traitement (6 agents)


Document PDF
     │
     ▼
[1] OCR Agent v4          ← OpenCV preprocessing · PSM 6/4/11/3 cascade
     │                       camelot + img2table (tableaux) · score qualité pondéré
     ▼
[2] NER Agent             ← Immatriculations TS-[A-Z]{3} · Part Numbers · S/N
     │                       Chapitres ATA · Références ES\d{6} · Dates
     ▼
[3] Classifier Agent      ← TF-IDF + Logistic Regression · 10 classes
     │
     ▼
[4] Embedding Agent       ← all-MiniLM-L6-v2 · 384d · HNSW pgvector
     │
     ▼
[5] Archive Agent         ← PostgreSQL 15 · déduplication SHA-256
     │
     ▼
[6] Monitoring Agent      ← Alertes · KPIs · Power BI (9 vues)
```

> **Note :** Pour les Job Cards, l'immatriculation est extraite à la page 3 (champ `FSN:`).
> `MAX_PAGES = 1` (première page) pour les autres types documentaires.

---

## Installation & Démarrage (Windows 10/11)

### 1. Prérequis

```powershell
# Python 3.11
winget install Python.Python.3.11

# PostgreSQL 15 (port personnalisé 5434)
winget install PostgreSQL.PostgreSQL

# Tesseract OCR 5 (UB-Mannheim)
# Télécharger depuis : https://github.com/UB-Mannheim/tesseract/wiki
# Installer avec packs de langue français + anglais

# Poppler (requis par pdf2image)
# Télécharger depuis : https://github.com/oschwartz10612/poppler-windows/releases
# Ajouter bin/ au PATH système
```

### 2. Base de données

```powershell
# Lancer psql (port 5434)
psql -U postgres -p 5434

# Créer la base
CREATE DATABASE nouv_db;
\c nouv_db
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;
\q

# Initialiser le schéma
psql -U postgres -p 5434 -d nouv_db -f scripts/init_db.sql
```

### 3. Environnement Python

```powershell
cd sys_archivage_intelligent
py -m venv venv
.\venv\Scripts\Activate.ps1

pip install -r requirements.txt
py -m spacy download fr_core_news_sm
```

### 4. Configuration `.env`

```powershell
copy .env.example .env
# Éditer les variables suivantes :
# DATABASE_URL = postgresql+asyncpg://postgres:<pwd>@localhost:5434/nouv_db
# ARCHIVE_PATH = C:\Users\ferie\Desktop\stage nvl\AviationArchive\Aircraft
# TESSERACT_PATH = C:\Program Files\Tesseract-OCR\tesseract.exe
# POPPLER_PATH = C:\poppler\bin
```

### 5. Démarrage

```powershell
# Backend
cd backend
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

# Frontend (ouvrir dans le navigateur)
py -m http.server 3000 --directory frontend
# → http://localhost:3000
```

### 6. Scanner l'arborescence locale

```powershell
# Simulation (aucune écriture en base)
py scripts/scan_archive.py --path "C:\Users\ferie\Desktop\stage nvl\AviationArchive\Aircraft" --dry-run

# Import réel (flag --import obligatoire)
py scripts/scan_archive.py --path "C:\Users\ferie\Desktop\stage nvl\AviationArchive\Aircraft" --import
```

### 7. Scripts de maintenance

```powershell
# Retraitement OCR ciblé
py scripts/reprocess_ocr.py

# Correction des immatriculations manquantes (NER)
py scripts/reprocess_ner.py
```

---

## API Endpoints Principaux

| Méthode | Endpoint | Description |
|---|---|---|
| POST | `/api/v1/documents/upload` | Upload + pipeline complet (6 agents) |
| GET | `/api/v1/documents/` | Lister documents (filtres multi-critères) |
| GET | `/api/v1/documents/{id}` | Détail document + texte OCR |
| PATCH | `/api/v1/documents/{id}` | Mise à jour métadonnées |
| GET | `/api/v1/search?q=...` | Recherche hybride (FTS + sémantique) |
| POST | `/api/v1/search/semantic` | Recherche sémantique pure (pgvector) |
| GET | `/api/v1/aircraft/` | Liste aéronefs (TS-INP · TS-INQ) |
| GET | `/api/v1/aircraft/{reg}/documents` | Documents par immatriculation |
| GET | `/api/v1/pipeline/status` | Statut des 6 agents |
| POST | `/api/v1/pipeline/scan` | Déclencher scan arborescence |
| POST | `/api/v1/pipeline/alerts/{id}/resolve` | Résoudre une alerte manuellement |
| GET | `/api/v1/analytics/stats` | Statistiques globales |
| GET | `/api/v1/analytics/kpis` | KPIs tableau de bord Power BI |

---

## Axes Reporting Power BI (9 vues PostgreSQL)

| Axe | Description |
|---|---|
| Global | Vue d'ensemble corpus · types · volumes |
| Fleet & Checks | Suivi checks par aéronef (TS-INP / TS-INQ) |
| AI Quality | Scores OCR · confiance classification · couverture embeddings |
| Alerts & Monitoring | Alertes actives · historique résolutions · KPIs pipeline |

---

## Auteur
**Feriel Arfa** — Master 2 Data Science · PFE NouvelAir 2025–2026
Faculté des Sciences de Monastir · Stage MRO NouvelAir