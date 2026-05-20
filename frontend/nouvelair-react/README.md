# NouvelAir — Système d'Archivage Intelligent (React)

## Structure du projet

```
src/
├── contexts/
│   ├── AuthContext.jsx      ← Session utilisateur + droits
│   └── ToastContext.jsx     ← Notifications globales
├── hooks/
│   └── useApi.js            ← apiFetch() + hook useApi() + helpers
├── components/
│   ├── Header.jsx           ← Barre de navigation supérieure
│   ├── Sidebar.jsx          ← Menu latéral avec badges live
│   └── ui/
│       ├── KPICard.jsx      ← Carte KPI réutilisable
│       ├── AlertBadge.jsx   ← Alerte avec bouton résolution
│       └── DataTable.jsx    ← Tableau générique
├── pages/
│   ├── Login.jsx            ← Authentification
│   ├── Dashboard.jsx        ← Vue d'ensemble KPIs + graphiques
│   ├── Upload.jsx           ← Upload single + batch + révision
│   ├── Documents.jsx        ← Consultation + arborescence + filtres
│   ├── Search.jsx           ← Recherche hybride FTS+pgvector + RAG
│   ├── Fleet.jsx            ← Vue flotte par aéronef
│   ├── Checks.jsx           ← Checks maintenance par ES ref
│   ├── Pipeline.jsx         ← État des 6 agents IA
│   ├── Monitoring.jsx       ← Alertes + santé agents
│   ├── Analytics.jsx        ← Statistiques documentaires
│   └── Admin.jsx            ← Gestion utilisateurs + droits
├── styles/
│   ├── global.css           ← Variables CSS + composants
│   └── layout.css           ← Header, sidebar, main, KPI
└── App.jsx                  ← Routeur + guards de route
```

## Installation

```bash
npm install
npm run dev
```

Ouvre http://localhost:3000

## Prérequis

FastAPI doit tourner sur http://localhost:8000

## Comptes de test

- admin@nouvelair.com.tn / admin123
- technicien@nouvelair.com.tn / tech123
- consultant@nouvelair.com.tn / cons123

## Ce qui a été corrigé vs le vanilla JS

| Problème | Fix React |
|---|---|
| 1900 lignes dans un fichier | ~15 fichiers modulaires |
| `confirmArchive()` ne faisait rien | PATCH réel sur `/documents/{id}` |
| Icône microphone sans fonction | Supprimée |
| Power BI sans rapport réel | Remplacé par info d'intégration |
| `/aircraft/` retournait des faux positifs NER | Filtre VALID_AIRCRAFT = ['TS-INP','TS-INQ'] |
| loadTree charge 3000 docs côté client | Affiché depuis les docs déjà chargés |
