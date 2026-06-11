// PipelineDemo.jsx — Simulation interactive du pipeline 6 agents
import { useState, useRef } from 'react';
import { useApi } from '../hooks/useApi';

const STEPS = [
  {
    id: 1,
    icon: 'fa-eye',
    label: 'OCR Agent',
    subtitle: 'Tesseract + pdfplumber + OpenCV',
    color: '#0ea5e9',
    bg: 'rgba(14,165,233,.08)',
    border: 'rgba(14,165,233,.25)',
    duration: 1400,
    metric: 'conf. 87%',
    detail: {
      title: 'Extraction du texte',
      description: 'Pipeline en 10 étapes : correction OpenCV → multi-PSM Tesseract (PSM 6/4/11/3) → extraction tableaux via camelot et img2table → score qualité pondéré.',
      output: [
        { key: 'Texte extrait', value: 'WORK ORDER N° ES00217082 · Aircraft: TS-INP · ATA: 32...' },
        { key: 'Confiance OCR', value: '87.3%' },
        { key: 'Pages traitées', value: '1 (MAX_PAGES=1)' },
        { key: 'Moteur', value: 'Tesseract 5 UB-Mannheim' },
      ]
    }
  },
  {
    id: 2,
    icon: 'fa-tags',
    label: 'NER Agent',
    subtitle: 'Regex · spaCy · 25 patterns',
    color: '#8b5cf6',
    bg: 'rgba(139,92,246,.08)',
    border: 'rgba(139,92,246,.25)',
    duration: 420,
    metric: '6 entités',
    detail: {
      title: "Extraction d'entités nommées",
      description: "Patterns regex compilés à l'initialisation pour ~30% de gain. spaCy fr_core_news_sm complète pour les dates.",
      output: [
        { key: 'aircraft_registration', value: 'TS-INP' },
        { key: 'es_reference', value: 'ES00217082' },
        { key: 'linked_wp', value: 'ES001392 (depuis chemin)' },
        { key: 'ata_chapter', value: 'ATA 32' },
        { key: 'check_type', value: 'CHECK_C (RCT anchor)' },
        { key: 'document_date', value: '22/06/2021' },
      ]
    }
  },
  {
    id: 3,
    icon: 'fa-brain',
    label: 'Classifier Agent',
    subtitle: 'TF-IDF + SVM · C=5.0 · ngram(1,2)',
    color: '#f59e0b',
    bg: 'rgba(245,158,11,.08)',
    border: 'rgba(245,158,11,.25)',
    duration: 180,
    metric: 'conf. 94%',
    detail: {
      title: 'Classification du document',
      description: 'Texte OCR + filename + chemin combinés en vecteur TF-IDF. SVM entraîné sur corpus NouvelAir. Boost ×5 sur token du dossier parent. F1 macro 95.2%.',
      output: [
        { key: 'WORK_ORDER', value: '94.2% ✓' },
        { key: 'JOBCARD', value: '3.1%' },
        { key: 'DEFECT_REPORT', value: '1.4%' },
        { key: 'Décision', value: 'doc_type = WORK_ORDER' },
      ]
    }
  },
  {
    id: 4,
    icon: 'fa-vector-square',
    label: 'Embedding Agent',
    subtitle: 'all-MiniLM-L6-v2 · 384 dims',
    color: '#06b6d4',
    bg: 'rgba(6,182,212,.08)',
    border: 'rgba(6,182,212,.25)',
    duration: 850,
    metric: '384d vector',
    detail: {
      title: "Génération d'embedding sémantique",
      description: 'Encodage via sentence-transformers. Stocké dans pgvector avec index HNSW (m=16, ef_construction=64) pour recherche <300ms.',
      output: [
        { key: 'Modèle', value: 'sentence-transformers/all-MiniLM-L6-v2' },
        { key: 'Dimensions', value: '384' },
        { key: 'Index', value: 'HNSW · cosine similarity' },
        { key: 'Precision@5', value: '88%' },
      ]
    }
  },
  {
    id: 5,
    icon: 'fa-database',
    label: 'Archive Agent',
    subtitle: 'PostgreSQL 15 · SHA-256 · RCT anchor',
    color: '#10b981',
    bg: 'rgba(16,185,129,.08)',
    border: 'rgba(16,185,129,.25)',
    duration: 380,
    metric: 'archivé',
    detail: {
      title: 'Persistance et déduplication',
      description: 'Cache mémoire évite les requêtes DB répétées. RCT anchor : le RCT est la source de vérité du WP — backfill rétroactif.',
      output: [
        { key: 'SHA-256', value: 'a3f9b2... (unique)' },
        { key: 'aircraft_id', value: '1 → TS-INP' },
        { key: 'check_id', value: 'ES001392 · CHECK_C (RCT confirmé)' },
        { key: 'Statut', value: 'ARCHIVED' },
      ]
    }
  },
  {
    id: 6,
    icon: 'fa-chart-line',
    label: 'Monitoring Agent',
    subtitle: 'Alertes · KPIs · Power BI',
    color: '#6b7280',
    bg: 'rgba(107,114,128,.08)',
    border: 'rgba(107,114,128,.25)',
    duration: 130,
    metric: '0 alertes',
    detail: {
      title: 'Surveillance et reporting',
      description: '9 vues PostgreSQL alimentant Power BI sur 4 axes : Global, Fleet & Checks, AI Quality, Alerts & Monitoring.',
      output: [
        { key: 'Confiance OCR', value: '87.3% >= 60% OK' },
        { key: 'Confiance classifieur', value: '94.2% >= 50% OK' },
        { key: 'AD critique', value: 'Aucune détectée' },
        { key: 'Alertes générées', value: '0' },
      ]
    }
  }
];

const SAMPLE_DOCS = [
  { name: 'TS-INP_Check C_ES001392_WorkOrder_ES00217082.pdf', aircraft: 'TS-INP', check: 'CHECK_C', type: 'WORK_ORDER' },
  { name: 'TS-INQ_CHECK C_ES001440_RCT-ES001440.pdf', aircraft: 'TS-INQ', check: 'CHECK_C', type: 'RCT' },
  { name: 'TS-INP_Check A_ES001778_Jobcard_0043.pdf', aircraft: 'TS-INP', check: 'CHECK_A', type: 'JOBCARD' },
  { name: 'TS-INQ_Old doc_AD_AD DFPs_2011-0142.pdf', aircraft: 'TS-INQ', check: '-', type: 'AD' },
];

export default function PipelineDemo() {
  const [running, setRunning] = useState(false);
  const [completedSteps, setCompletedSteps] = useState([]);
  const [activeStep, setActiveStep] = useState(null);
  const [expandedStep, setExpandedStep] = useState(null);
  const [done, setDone] = useState(false);
  const [selectedDoc, setSelectedDoc] = useState(0);
  const [speed, setSpeed] = useState(1);
  const cancelRef = useRef(false);

  const { data: kpis }     = useApi('/analytics/kpis');
  const { data: pipeline } = useApi('/pipeline/status');

  const reset = () => {
    cancelRef.current = true;
    setRunning(false);
    setCompletedSteps([]);
    setActiveStep(null);
    setExpandedStep(null);
    setDone(false);
  };

  const run = async () => {
    cancelRef.current = false;
    setRunning(true);
    setCompletedSteps([]);
    setActiveStep(null);
    setExpandedStep(null);
    setDone(false);

    for (let i = 0; i < STEPS.length; i++) {
      if (cancelRef.current) break;
      setActiveStep(i);
      await new Promise(r => setTimeout(r, STEPS[i].duration / speed));
      if (cancelRef.current) break;
      setCompletedSteps(prev => [...prev, i]);
      setExpandedStep(i);
      setActiveStep(null);
      await new Promise(r => setTimeout(r, 800 / speed));
      setExpandedStep(null);
      await new Promise(r => setTimeout(r, 100 / speed));
    }

    if (!cancelRef.current) {
      setDone(true);
      setRunning(false);
    }
  };

  const doc = SAMPLE_DOCS[selectedDoc];
  const progress = completedSteps.length / STEPS.length * 100;

  const metrics = [
    { label: 'Documents archivés',  value: kpis?.total_documents?.toLocaleString() || '—',                                                                          color: 'var(--nv)'  },
    { label: 'F1 Macro Classifier', value: pipeline?.agents?.classifier?.confidence ? Math.round(pipeline.agents.classifier.confidence * 100) + '%' : '—',          color: '#f59e0b'    },
    { label: 'Texte extractible',   value: kpis?.text_extractible_pct ? kpis.text_extractible_pct + '%' : '—',                                                      color: '#8b5cf6'    },
    { label: 'Latence recherche',   value: '<300ms',                                                                                                                  color: '#06b6d4'    },
    { label: 'Couverture embedding',value: pipeline?.agents?.embedding?.confidence ? Math.round(pipeline.agents.embedding.confidence * 100) + '%' : '—',             color: '#10b981'    },
  ];

  return (
    <div className="page-enter" style={{ maxWidth: 960, margin: '0 auto', padding: '24px 20px' }}>

      {/* En-tête */}
      <div style={{ marginBottom: 24 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
          <i className="fas fa-play-circle" style={{ color: 'var(--nv)', fontSize: 20 }} />
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 600 }}>Simulation Pipeline</h1>
          <span style={{ fontSize: 11, padding: '2px 8px', background: 'rgba(0,82,204,.1)', color: 'var(--nv)', borderRadius: 4, fontWeight: 500 }}>6 agents</span>
        </div>
        <p style={{ margin: 0, fontSize: 14, color: 'var(--tx2)' }}>
          Traitement automatique d'un document MRO : de l'OCR à l'archivage PostgreSQL.
        </p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: 20, alignItems: 'start' }}>

        {/* Colonne gauche */}
        <div>
          {/* Sélecteur doc */}
          <div className="card" style={{ padding: 14, marginBottom: 14 }}>
            <div style={{ fontSize: 12, color: 'var(--tx3)', marginBottom: 8, fontWeight: 500 }}>Document simulé</div>
            {SAMPLE_DOCS.map((d, i) => (
              <div key={i}
                onClick={() => { if (!running) { reset(); setSelectedDoc(i); } }}
                style={{
                  padding: '7px 10px', borderRadius: 6, cursor: running ? 'default' : 'pointer',
                  background: selectedDoc === i ? 'var(--sky)' : 'transparent',
                  border: `0.5px solid ${selectedDoc === i ? 'var(--nv)' : 'transparent'}`,
                  fontSize: 12, color: 'var(--tx2)', marginBottom: 4,
                  display: 'flex', alignItems: 'center', gap: 8
                }}>
                <i className="fas fa-file-pdf" style={{ color: 'var(--danger)', fontSize: 11, flexShrink: 0 }} />
                <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{d.name}</span>
                <span className="tag" style={{ fontSize: 10, flexShrink: 0 }}>{d.type}</span>
              </div>
            ))}
          </div>

          {/* Barre progression */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
            <div style={{ flex: 1, height: 4, background: 'var(--bdr)', borderRadius: 2, overflow: 'hidden' }}>
              <div style={{ height: '100%', width: `${progress}%`, background: 'var(--nv)', borderRadius: 2, transition: 'width .4s ease' }} />
            </div>
            <span style={{ fontSize: 12, color: 'var(--tx3)', minWidth: 36 }}>{Math.round(progress)}%</span>
          </div>

          {/* Steps */}
          {STEPS.map((step, i) => {
            const isCompleted = completedSteps.includes(i);
            const isActive    = activeStep === i;
            const isExpanded  = expandedStep === i;
            const isLocked    = !isCompleted && !isActive && running;

            return (
              <div key={step.id}>
                <div
                  onClick={() => isCompleted && setExpandedStep(isExpanded ? null : i)}
                  style={{
                    background: isActive ? step.bg : 'var(--bg1)',
                    border: `0.5px solid ${isActive ? step.border : isCompleted ? 'var(--bdr2)' : 'var(--bdr)'}`,
                    borderRadius: 10, padding: '12px 14px',
                    cursor: isCompleted ? 'pointer' : 'default',
                    opacity: isLocked ? 0.4 : 1,
                    transition: 'all .2s',
                  }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <div style={{
                      width: 32, height: 32, borderRadius: '50%', flexShrink: 0,
                      background: isCompleted || isActive ? step.bg : 'var(--bg2)',
                      border: `0.5px solid ${isCompleted || isActive ? step.border : 'var(--bdr)'}`,
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                    }}>
                      {isCompleted
                        ? <i className="fas fa-check" style={{ color: step.color, fontSize: 12 }} />
                        : <i className={`fas ${step.icon}`} style={{ color: isActive ? step.color : 'var(--tx3)', fontSize: 12 }} />
                      }
                    </div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--tx1)' }}>
                        Étape {step.id} — <span style={{ color: isActive || isCompleted ? step.color : 'var(--tx2)' }}>{step.label}</span>
                        {isActive && <span style={{ fontSize: 11, color: step.color, marginLeft: 8 }}>en cours...</span>}
                      </div>
                      <div style={{ fontSize: 11, color: 'var(--tx3)', marginTop: 1 }}>{step.subtitle}</div>
                    </div>
                    {isCompleted && (
                      <span style={{ fontSize: 11, padding: '2px 8px', background: step.bg, color: step.color, borderRadius: 4, fontWeight: 500, flexShrink: 0 }}>
                        {step.metric}
                      </span>
                    )}
                    {isCompleted && (
                      <i className={`fas fa-chevron-${isExpanded ? 'up' : 'down'}`} style={{ fontSize: 10, color: 'var(--tx3)' }} />
                    )}
                  </div>

                  {isExpanded && isCompleted && (
                    <div style={{ marginTop: 12, paddingTop: 12, borderTop: '0.5px solid var(--bdr)' }}>
                      <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--tx2)', marginBottom: 4 }}>{step.detail.title}</div>
                      <div style={{ fontSize: 12, color: 'var(--tx3)', lineHeight: 1.6, marginBottom: 10 }}>{step.detail.description}</div>
                      {step.detail.output.map((o, j) => (
                        <div key={j} style={{ display: 'flex', gap: 8, fontSize: 12, marginBottom: 4 }}>
                          <span style={{ color: 'var(--tx3)', minWidth: 170, flexShrink: 0 }}>{o.key}</span>
                          <code style={{ fontSize: 11, background: 'var(--bg2)', padding: '1px 6px', borderRadius: 3, color: 'var(--tx1)' }}>{o.value}</code>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {i < STEPS.length - 1 && (
                  <div style={{ display: 'flex', justifyContent: 'center', height: 18, alignItems: 'center' }}>
                    <div style={{ width: 1, height: 18, background: isCompleted ? step.color : 'var(--bdr)', opacity: .5, transition: 'background .3s' }} />
                  </div>
                )}
              </div>
            );
          })}

          {/* Résultat */}
          {done && (
            <div style={{ marginTop: 16, padding: 16, background: 'rgba(16,185,129,.06)', border: '0.5px solid rgba(16,185,129,.3)', borderRadius: 10 }}>
              <div style={{ fontSize: 13, fontWeight: 500, color: '#10b981', marginBottom: 10 }}>
                <i className="fas fa-check-circle" style={{ marginRight: 6 }} />Document archivé avec succès
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8 }}>
                {[
                  { label: 'Type',       value: doc.type      },
                  { label: 'Avion',      value: doc.aircraft  },
                  { label: 'Check',      value: doc.check     },
                  { label: 'Confiance',  value: '94.2%'       },
                  { label: 'Embedding',  value: '384 dims'    },
                  { label: 'Statut',     value: 'ARCHIVED'    },
                ].map((m, i) => (
                  <div key={i} style={{ background: 'var(--bg1)', borderRadius: 6, padding: '7px 10px' }}>
                    <div style={{ fontSize: 11, color: 'var(--tx3)' }}>{m.label}</div>
                    <div style={{ fontSize: 12, fontWeight: 500 }}>{m.value}</div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Colonne droite */}
        <div style={{ position: 'sticky', top: 80 }}>

          {/* Contrôles */}
          <div className="card" style={{ padding: 16, marginBottom: 14 }}>
            <div style={{ fontSize: 12, color: 'var(--tx3)', fontWeight: 500, marginBottom: 12 }}>Contrôles</div>
            <button onClick={running ? reset : run} style={{
              width: '100%', padding: '10px 0', border: 'none', borderRadius: 8, cursor: 'pointer',
              fontWeight: 500, fontSize: 13, marginBottom: 12,
              background: running ? 'rgba(239,68,68,.12)' : 'var(--nv)',
              color: running ? '#ef4444' : '#fff'
            }}>
              <i className={`fas ${running ? 'fa-stop' : done ? 'fa-redo' : 'fa-play'}`} style={{ marginRight: 7 }} />
              {running ? 'Arrêter' : done ? 'Rejouer' : 'Démarrer'}
            </button>

            <div style={{ fontSize: 12, color: 'var(--tx3)', marginBottom: 6 }}>Vitesse</div>
            <div style={{ display: 'flex', gap: 6 }}>
              {[{ label: 'x1', val: 1 }, { label: 'x2', val: 2 }, { label: 'x5', val: 5 }].map(s => (
                <button key={s.val} onClick={() => setSpeed(s.val)} style={{
                  flex: 1, padding: '6px 0', borderRadius: 6,
                  border: '0.5px solid var(--bdr2)', cursor: 'pointer', fontSize: 12,
                  background: speed === s.val ? 'var(--nv)' : 'transparent',
                  color: speed === s.val ? '#fff' : 'var(--tx2)'
                }}>{s.label}</button>
              ))}
            </div>
          </div>

          {/* Métriques */}
          <div className="card" style={{ padding: 16, marginBottom: 14 }}>
            <div style={{ fontSize: 12, color: 'var(--tx3)', fontWeight: 500, marginBottom: 10 }}>Métriques système</div>
            {metrics.map((m, i) => (
              <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: i < metrics.length - 1 ? '0.5px solid var(--bdr)' : 'none' }}>
                <span style={{ fontSize: 12, color: 'var(--tx2)' }}>{m.label}</span>
                <span style={{ fontSize: 12, fontWeight: 500, color: m.color }}>{m.value}</span>
              </div>
            ))}
          </div>

          {/* Stack */}
          <div className="card" style={{ padding: 16 }}>
            <div style={{ fontSize: 12, color: 'var(--tx3)', fontWeight: 500, marginBottom: 10 }}>Stack technique</div>
            {[
              'FastAPI + PostgreSQL 15',
              'pgvector · HNSW',
              'Tesseract 5 + OpenCV 4.10',
              'sentence-transformers',
              'spaCy fr_core_news_sm',
              'TF-IDF + SVM (C=5.0)',
            ].map((t, i) => (
              <div key={i} style={{ fontSize: 11, fontFamily: 'monospace', color: 'var(--tx3)', padding: '3px 0' }}>
                <i className="fas fa-circle" style={{ fontSize: 4, marginRight: 7, verticalAlign: 'middle' }} />{t}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}