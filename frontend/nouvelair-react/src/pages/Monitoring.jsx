// pages/Monitoring.jsx
import { useState, useEffect } from 'react';
import { useApi, apiFetch, timeAgo } from '../hooks/useApi';
import { useToast } from '../contexts/ToastContext';
import { useAuth } from '../contexts/AuthContext';
import KPICard from '../components/ui/KPICard';

const AGENT_LIST = [
  { key: 'ocr',        name: 'OCR Agent v4' },
  { key: 'ner',        name: 'NER Agent'    },
  { key: 'classifier', name: 'Classifier'   },
  { key: 'embedding',  name: 'Embedding'    },
  { key: 'archive',    name: 'Archiveur'    },
  { key: 'monitoring', name: 'Monitoring'   },
];
const DOT_MAP   = { active: 'g p', ready: 'g', processing: 'pp', error: 'r', idle: 'b' };
const LABEL_MAP = { active: 'Actif', ready: 'Prêt', processing: 'Traitement...', error: 'Erreur', idle: 'Inactif' };

const SEV_COLOR = { critical: '#1d4ed8', warning: '#d97706', info: '#2563eb', success: '#059669' };
const SEV_BG    = { critical: '#dbeafe', warning: '#fef3c7', info: '#dbeafe', success: '#d1fae5' };
const SEV_ICON  = { critical: 'fa-radiation-alt', warning: 'fa-exclamation-triangle', info: 'fa-info-circle', success: 'fa-check-circle' };

const DOC_TYPES = [
  'WORK_ORDER', 'JOBCARD', 'DEFECT_REPORT', 'NCR', 'AD', 'SB',
  'ATL', 'AMM', 'CMM', 'IPC', 'SPECS', 'CERTIFICATE', 'RCT',
  'DB_CHART', 'OTHER',
];

const DOC_TYPES_DISPLAY = {
  'WORK_ORDER': 'Work Order', 'JOBCARD': 'Job Card',
  'DEFECT_REPORT': 'Defect Report', 'NCR': 'NCR',
  'AD': 'AD', 'SB': 'SB', 'ATL': 'ATL', 'AMM': 'AMM',
  'CMM': 'CMM', 'IPC': 'IPC', 'SPECS': 'Specs',
  'CERTIFICATE': 'Certificate', 'RCT': 'RCT',
  'DB_CHART': 'D&B Chart', 'OTHER': 'Other',
};

const CATEGORIES = [
  'Check A', 'Check C', 'Check D', 'AD', 'SB', 'AMM', 'CMM', 'IPC',
  'Specs', 'Certificates', 'Structural Repair', 'Engine File',
  'Job Card', 'ATL', 'Work Order', 'Divers',
];

const AIRCRAFT = ['TS-INP', 'TS-INQ', 'TS-INO', 'TS-ING', 'TS-INT'];
const REVIEW_PAGE_SIZE = 10;

export default function Monitoring() {
  const toast = useToast();
  const { session } = useAuth();
  const { data: statusData, refetch: refetchStatus } = useApi('/pipeline/status');
  const { data: kpiData }                            = useApi('/analytics/kpis');
  const { data: alertData, refetch: refetchAlerts }  = useApi('/pipeline/alerts?limit=50');

  // ── États alertes ──────────────────────────────────────────────────────────
  const [corrModal, setCorrModal]     = useState(null);
  const [corrForm,  setCorrForm]      = useState({});
  const [corrLoading, setCorrLoading] = useState(false);
  

  // ── États révision manuelle ────────────────────────────────────────────────
  const [reviewDocs, setReviewDocs]       = useState([]);
  const [reviewLoading, setReviewLoading] = useState(false);
  const [reviewModal, setReviewModal]     = useState(null);
  const [reviewForm, setReviewForm]       = useState({});
  const [reviewSaving, setReviewSaving]   = useState(false);
  const [reviewPage, setReviewPage]       = useState(0);
  const [reviewFilter, setReviewFilter]   = useState('');
  const [pendingDocs, setPendingDocs]     = useState([]);
  const [noAircraftDocs, setNoAircraftDocs] = useState([]);
  const [pendingLoading, setPendingLoading] = useState(false);
  const [noAircraftLoading, setNoAircraftLoading] = useState(false);

  const agents = statusData?.agents || {};
  const alerts = alertData || [];

  

  // ── Charger documents à réviser ────────────────────────────────────────────
  const fetchReviewDocs = async () => {
    setReviewLoading(true);
    try {
      const data = await apiFetch('/documents/?needs_review=true&size=500');
      setReviewDocs(data?.items || []);
    } catch {
      setReviewDocs([]);
    }
    setReviewLoading(false);
  };
  const fetchPendingDocs = async () => {
    setPendingLoading(true);
    try {
      const data = await apiFetch('/documents/?status=PENDING&size=500');
      setPendingDocs(data?.items || []);
    } catch { setPendingDocs([]); }
    setPendingLoading(false);
  };

  const fetchNoAircraftDocs = async () => {
    setNoAircraftLoading(true);
    try {
      const data = await apiFetch('/documents/?no_aircraft=true&size=500');
      setNoAircraftDocs(data?.items || []);
    } catch { setNoAircraftDocs([]); }
    setNoAircraftLoading(false);
  };
  useEffect(() => { fetchReviewDocs(); 
    fetchPendingDocs();
    fetchNoAircraftDocs();
  }, []);

  // ── Ouvrir modal révision ──────────────────────────────────────────────────
  const openReviewModal = (doc) => {
    setReviewForm({
      doc_type:             doc.doc_type             || 'OTHER',
      category:             doc.category             || '',
      ata_chapter:          doc.ata_chapter          || '',
      es_reference:         doc.es_reference         || '',
      aircraft_registration: doc.aircraft_registration || '',
    });
    setReviewModal(doc);
  };

  // ── Soumettre révision ─────────────────────────────────────────────────────
  const submitReview = async () => {
    if (!reviewModal) return;
    setReviewSaving(true);
    const patch = {
      doc_type:             reviewForm.doc_type,
      category:             reviewForm.category,
      ata_chapter:          reviewForm.ata_chapter  || null,
      es_reference:         reviewForm.es_reference || null,
      aircraft_registration: reviewForm.aircraft_registration || null,
      manually_corrected:   true,
      needs_review:         false,
    };
    const updated = await apiFetch(`/documents/${reviewModal.id}`, {
      method: 'PATCH',
      body: JSON.stringify(patch),
    });
    if (updated) {
      toast(`✅ Document #${reviewModal.id} corrigé`, 'ok');
      setReviewModal(null);
      setReviewDocs(prev => prev.filter(d => d.id !== reviewModal.id));
    } else {
      toast('Erreur lors de la correction', 'err');
    }
    setReviewSaving(false);
  };

  // ── Ouvrir modal correction alerte ────────────────────────────────────────
  const openCorrection = async (alert) => {
    if (!alert.document_id) {
      toast('Aucun document associé à cette alerte', 'warn');
      return;
    }
    const doc = await apiFetch(`/documents/${alert.document_id}`);
    if (!doc) { toast('Document introuvable', 'err'); return; }
    setCorrForm({
      aircraft_registration: doc.aircraft_registration || '',
      doc_type:              doc.doc_type              || '',
      category:              doc.category              || '',
      ata_chapter:           doc.ata_chapter           || '',
      es_reference:          doc.es_reference          || '',
      item_number:           doc.item_number           || '',
      comment:               '',
      resolve_action:        '',
    });
    setCorrModal({ alert, doc });
  };

  // ── Soumettre correction alerte ────────────────────────────────────────────
  const submitCorrection = async () => {
    if (!corrModal) return;
    if (!corrForm.resolve_action) {
      toast('Sélectionnez une action corrective', 'warn');
      return;
    }
    setCorrLoading(true);
    const patch = {
      aircraft_registration: corrForm.aircraft_registration || null,
      doc_type:              corrForm.doc_type              || null,
      category:              corrForm.category              || null,
      ata_chapter:           corrForm.ata_chapter           || null,
      es_reference:          corrForm.es_reference          || null,
      item_number:           corrForm.item_number           || null,
      manually_corrected:    true,
    };
    const updated = await apiFetch(`/documents/${corrModal.doc.id}`, {
      method: 'PATCH', body: JSON.stringify(patch),
    });
    if (!updated) {
      toast('Erreur lors de la correction du document', 'err');
      setCorrLoading(false);
      return;
    }
    await apiFetch(`/pipeline/alerts/${corrModal.alert.id}/resolve`, {
      method: 'POST',
      body: JSON.stringify({
        resolved_by:  session?.nom || 'Utilisateur',
        action_taken: corrForm.resolve_action,
        comment:      corrForm.comment || null,
      }),
    });
    toast(`Document #${corrModal.doc.id} corrigé et alerte résolue`, 'ok');
    setCorrLoading(false);
    setCorrModal(null);
    refetchAlerts();
  };

  // ── Filtrage documents à réviser ───────────────────────────────────────────
  const filteredDocs = reviewDocs.filter(d =>
    !reviewFilter ||
    d.filename?.toLowerCase().includes(reviewFilter.toLowerCase()) ||
    d.aircraft_registration?.toLowerCase().includes(reviewFilter.toLowerCase())
  );
  const pagedDocs = filteredDocs.slice(
    reviewPage * REVIEW_PAGE_SIZE,
    (reviewPage + 1) * REVIEW_PAGE_SIZE
  );

  

  return (
    <div className="page-enter">
      <div className="ph">
        <div className="ph-row">
          <div>
            <h2><i className="fas fa-shield-alt"></i>Monitoring Système</h2>
            <p>Supervision opérationnelle du pipeline IA · Santé des agents · Gestion des alertes MRO</p>
          </div>
          <button className="btn btn-out btn-sm" onClick={() => { refetchStatus(); refetchAlerts(); fetchReviewDocs(); fetchPendingDocs(); fetchNoAircraftDocs(); }}>
            <i className="fas fa-sync-alt"></i>Rafraîchir
          </button>
        </div>
      </div>

      {/* Santé des agents */}
      <div className="card" style={{ marginBottom: 18 }}>
        <div className="ch">
          <h3><i className="fas fa-heartbeat" style={{ color: 'var(--danger)' }}></i>Santé des Agents</h3>
          <span className="tag g">{AGENT_LIST.length} / {AGENT_LIST.length} opérationnels</span>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 10, padding: 16 }}>
          {AGENT_LIST.map(a => {
            const status = agents[a.key]?.status || 'ready';
            return (
              <div key={a.key} style={{
                display: 'flex', alignItems: 'center', gap: 10,
                padding: '12px 14px', borderRadius: 10,
                background: 'var(--bg2)', border: '1px solid var(--bdr)',
              }}>
                <div className={`sdot ${DOT_MAP[status] || 'g'}`}></div>
                <div>
                  <div style={{ fontSize: 12, fontWeight: 600 }}>{a.name}</div>
                  <div style={{ fontSize: 11, color: 'var(--tx3)' }}>{LABEL_MAP[status] || status}</div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <div className="g64">
        
      

        
      </div>

      {/* ── Documents à réviser ─────────────────────────────────────────────── */}
      <div className="card">
        <div className="ch">
          <h3>
            <i className="fas fa-exclamation-circle" style={{ color: '#d97706' }}></i>
            Documents à réviser
            {reviewDocs.length > 0 && (
              <span className="tag a" style={{ marginLeft: 8, fontSize: 11 }}>
                {reviewDocs.length}
              </span>
            )}
          </h3>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <input
              type="text"
              placeholder="Filtrer par nom ou avion..."
              value={reviewFilter}
              onChange={e => { setReviewFilter(e.target.value); setReviewPage(0); }}
              style={{
                padding: '5px 10px', borderRadius: 8, border: '1.5px solid var(--bdr)',
                fontSize: 12, background: 'var(--bg2)', color: 'var(--tx)', outline: 'none', width: 200
              }}
            />
            <button className="btn btn-out btn-sm" onClick={fetchReviewDocs}>
              <i className="fas fa-sync-alt"></i>
            </button>
          </div>
        </div>

        {reviewLoading ? (
          <div style={{ padding: 32, textAlign: 'center', color: 'var(--tx3)' }}>
            <i className="fas fa-spinner fa-spin" style={{ fontSize: 20, marginBottom: 8, display: 'block' }}></i>
            Chargement des documents...
          </div>
        ) : !filteredDocs.length ? (
          <div style={{ padding: 32, textAlign: 'center', color: 'var(--tx3)', fontSize: 13 }}>
            <i className="fas fa-check-circle" style={{ color: 'var(--acc)', fontSize: 28, display: 'block', marginBottom: 10 }}></i>
            {reviewFilter ? 'Aucun document trouvé' : 'Aucun document à réviser ✅'}
          </div>
        ) : (
          <>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                <thead>
                  <tr style={{ borderBottom: '2px solid var(--bdr)', background: 'var(--bg2)' }}>
                    {['#', 'Fichier', 'Avion', 'Type actuel', 'Catégorie', 'Conf. OCR', 'Conf. ML', 'Action'].map(h => (
                      <th key={h} style={{ padding: '10px 12px', textAlign: 'left', fontWeight: 700, color: 'var(--tx3)', fontSize: 11, textTransform: 'uppercase', whiteSpace: 'nowrap' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {pagedDocs.map(doc => (
                    <tr key={doc.id}
                      style={{ borderBottom: '1px solid var(--bdr)', cursor: 'pointer', transition: 'background .15s' }}
                      onMouseEnter={e => e.currentTarget.style.background = 'var(--bg2)'}
                      onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                    >
                      <td style={{ padding: '10px 12px', color: 'var(--tx3)', fontSize: 11 }}>#{doc.id}</td>
                      <td style={{ padding: '10px 12px', fontWeight: 500, maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        <i className="fas fa-file-pdf" style={{ color: '#dc2626', marginRight: 6, fontSize: 11 }}></i>
                        {doc.filename}
                      </td>
                      <td style={{ padding: '10px 12px' }}>
                        <span className="tag b" style={{ fontSize: 10 }}>{doc.aircraft_registration || '—'}</span>
                      </td>
                      <td style={{ padding: '10px 12px' }}>
                        <span className="tag a" style={{ fontSize: 10 }}>
                          {DOC_TYPES_DISPLAY[doc.doc_type] || doc.doc_type || 'OTHER'}
                        </span>
                      </td>
                      <td style={{ padding: '10px 12px', color: 'var(--tx2)', fontSize: 11 }}>{doc.category || '—'}</td>
                      <td style={{ padding: '10px 12px' }}>
                        <span style={{
                          fontWeight: 700, fontSize: 11,
                          color: doc.ocr_confidence > 70 ? '#059669' : doc.ocr_confidence > 40 ? '#d97706' : '#dc2626'
                        }}>
                          {doc.ocr_confidence != null ? doc.ocr_confidence.toFixed(0) + '%' : '—'}
                        </span>
                      </td>
                      <td style={{ padding: '10px 12px' }}>
                        <span style={{
                          fontWeight: 700, fontSize: 11,
                          color: doc.classifier_confidence > 0.7 ? '#059669' : doc.classifier_confidence > 0.4 ? '#d97706' : '#dc2626'
                        }}>
                          {doc.classifier_confidence != null ? (doc.classifier_confidence * 100).toFixed(0) + '%' : '—'}
                        </span>
                      </td>
                      <td style={{ padding: '10px 12px' }}>
                        <button
                          onClick={() => openReviewModal(doc)}
                          style={{
                            background: 'var(--nv)', color: '#fff', border: 'none',
                            borderRadius: 7, padding: '5px 14px', fontSize: 11,
                            cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 5,
                            fontWeight: 600, whiteSpace: 'nowrap'
                          }}
                        >
                          <i className="fas fa-edit"></i>Corriger
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            {filteredDocs.length > REVIEW_PAGE_SIZE && (
              <div style={{ padding: '10px 16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderTop: '1px solid var(--bdr)', fontSize: 12 }}>
                <span style={{ color: 'var(--tx3)' }}>
                  {reviewPage * REVIEW_PAGE_SIZE + 1}–{Math.min((reviewPage + 1) * REVIEW_PAGE_SIZE, filteredDocs.length)} sur {filteredDocs.length}
                </span>
                <div style={{ display: 'flex', gap: 6 }}>
                  <button className="btn btn-out btn-sm" onClick={() => setReviewPage(p => Math.max(0, p - 1))} disabled={reviewPage === 0}>
                    <i className="fas fa-chevron-left"></i>
                  </button>
                  <button className="btn btn-out btn-sm" onClick={() => setReviewPage(p => p + 1)} disabled={(reviewPage + 1) * REVIEW_PAGE_SIZE >= filteredDocs.length}>
                    <i className="fas fa-chevron-right"></i>
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </div>

      {/* Alertes actives */}
      <div className="card">
        <div className="ch">
          <h3>
            <i className="fas fa-exclamation-triangle" style={{ color: 'var(--warn)' }}></i>
            Alertes Actives
            {alerts.filter(a => !a.resolved).length > 0 && (
              <span className="tag r" style={{ marginLeft: 8, fontSize: 11 }}>
                {alerts.filter(a => !a.resolved).length}
              </span>
            )}
          </h3>
        </div>
        <div style={{ padding: 10 }}>
          {!alerts.length ? (
            <div style={{ padding: 24, textAlign: 'center', color: 'var(--tx3)', fontSize: 13 }}>
              <i className="fas fa-check-circle" style={{ color: 'var(--acc)', fontSize: 24, display: 'block', marginBottom: 8 }}></i>
              Aucune alerte active
            </div>
          ) : (
            alerts.map(a => (
              <div key={a.id} style={{
                display: 'flex', alignItems: 'flex-start', gap: 12,
                padding: '12px 14px', borderRadius: 10, marginBottom: 8,
                background: a.resolved ? 'var(--bg)' : SEV_BG[a.severity] || 'var(--bg)',
                border: `1px solid ${a.resolved ? 'var(--bdr)' : SEV_COLOR[a.severity] || 'var(--bdr)'}`,
                opacity: a.resolved ? 0.6 : 1,
                transition: 'opacity .2s',
              }}>
                <div style={{
                  width: 32, height: 32, borderRadius: 8, flexShrink: 0,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  background: a.resolved ? 'var(--bg2)' : SEV_COLOR[a.severity],
                  color: '#fff', fontSize: 14,
                }}>
                  <i className={`fas ${a.resolved ? 'fa-check' : SEV_ICON[a.severity] || 'fa-circle'}`}></i>
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 3 }}>
                    <span style={{ fontSize: 12, fontWeight: 700, color: a.resolved ? 'var(--tx3)' : 'var(--tx)' }}>
                      {a.title}
                    </span>
                    <span className={`tag ${a.severity === 'critical' ? 'r' : a.severity === 'warning' ? 'a' : 'b'}`} style={{ fontSize: 9 }}>
                      {a.severity?.toUpperCase()}
                    </span>
                    {a.document_id && (
                      <span className="tag gr" style={{ fontSize: 9 }}>Doc #{a.document_id}</span>
                    )}
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--tx2)', marginBottom: 4 }}>{a.message}</div>
                  <div style={{ fontSize: 11, color: 'var(--tx3)' }}>
                    {a.aircraft_registration && <span className="tag b" style={{ fontSize: 9, marginRight: 4 }}>{a.aircraft_registration}</span>}
                    {timeAgo(a.created_at)}
                    {a.resolved && a.resolved_by && ` · Résolu par ${a.resolved_by}`}
                  </div>
                </div>
                {!a.resolved ? (
                  <button className="btn btn-sm"
                    style={{ flexShrink: 0, background: 'var(--nv)', color: '#fff', border: 'none', borderRadius: 8, padding: '6px 14px', fontSize: 12, fontWeight: 600, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6 }}
                    onClick={() => openCorrection(a)}
                  >
                    <i className="fas fa-tools"></i>Corriger
                  </button>
                ) : (
                  <span style={{ fontSize: 11, color: 'var(--acc)', flexShrink: 0, display: 'flex', alignItems: 'center', gap: 4 }}>
                    <i className="fas fa-check-circle"></i> Résolu
                  </span>
                )}
              </div>
            ))
          )}
        </div>
      </div>

      {/* ── Modal Révision Manuelle ──────────────────────────────────────────── */}
      {reviewModal && (
        <div className="modal-overlay" onClick={() => setReviewModal(null)}>
          <div className="modal-box"
            style={{ width: '92%', maxWidth: 640, maxHeight: '90vh', display: 'flex', flexDirection: 'column' }}
            onClick={e => e.stopPropagation()}
          >
            {/* Header */}
            <div className="modal-hd" style={{ background: 'linear-gradient(135deg, #d97706 0%, #b45309 100%)' }}>
              <div>
                <h3 style={{ color: '#fff', margin: 0 }}>
                  <i className="fas fa-edit" style={{ marginRight: 8 }}></i>
                  Révision manuelle
                </h3>
                <div style={{ color: 'rgba(255,255,255,.7)', fontSize: 12, marginTop: 3 }}>
                  {reviewModal.filename} · Doc #{reviewModal.id}
                </div>
              </div>
              <button onClick={() => setReviewModal(null)}
                style={{ background: 'rgba(255,255,255,.15)', border: 'none', color: '#fff', width: 32, height: 32, borderRadius: 8, cursor: 'pointer', fontSize: 16 }}>
                ✕
              </button>
            </div>

            <div style={{ overflowY: 'auto', flex: 1, padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 14 }}>

              {/* Infos document */}
              <div style={{ background: 'var(--bg2)', borderRadius: 8, padding: 12, fontSize: 12, border: '1px solid var(--bdr)', display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8 }}>
                <div><span style={{ color: 'var(--tx3)', display: 'block', marginBottom: 2, fontSize: 10, textTransform: 'uppercase' }}>Avion</span><strong>{reviewModal.aircraft_registration || '—'}</strong></div>
                <div><span style={{ color: 'var(--tx3)', display: 'block', marginBottom: 2, fontSize: 10, textTransform: 'uppercase' }}>Type actuel</span><strong>{reviewModal.doc_type || '—'}</strong></div>
                <div><span style={{ color: 'var(--tx3)', display: 'block', marginBottom: 2, fontSize: 10, textTransform: 'uppercase' }}>Conf. OCR</span>
                  <strong style={{ color: reviewModal.ocr_confidence > 70 ? '#059669' : '#d97706' }}>
                    {reviewModal.ocr_confidence?.toFixed(0) || '—'}%
                  </strong>
                </div>
              </div>

              {/* Aperçu OCR */}
              {reviewModal.ocr_text && (
                <div>
                  <label style={{ fontSize: 11, fontWeight: 700, color: 'var(--tx3)', textTransform: 'uppercase', display: 'block', marginBottom: 6 }}>
                    <i className="fas fa-file-alt" style={{ marginRight: 5 }}></i>Aperçu OCR
                  </label>
                  <div style={{
                    background: 'var(--bg2)', borderRadius: 8, padding: 10,
                    fontSize: 11, color: 'var(--tx2)', maxHeight: 90, overflowY: 'auto',
                    fontFamily: 'monospace', border: '1px solid var(--bdr)', lineHeight: 1.5
                  }}>
                    {reviewModal.ocr_text.slice(0, 400)}…
                  </div>
                </div>
              )}

              {/* Avion */}
              <div>
                <label style={{ fontSize: 11, fontWeight: 700, color: 'var(--tx3)', textTransform: 'uppercase', display: 'block', marginBottom: 6 }}>
                  <i className="fas fa-plane" style={{ marginRight: 5, color: 'var(--nv)' }}></i>Immatriculation
                </label>
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                  {AIRCRAFT.map(reg => (
                    <button key={reg} onClick={() => setReviewForm(f => ({ ...f, aircraft_registration: reg }))}
                      style={{
                        padding: '5px 12px', borderRadius: 7, fontSize: 12, cursor: 'pointer', border: '1.5px solid',
                        borderColor: reviewForm.aircraft_registration === reg ? 'var(--nv)' : 'var(--bdr)',
                        background: reviewForm.aircraft_registration === reg ? 'var(--nv)' : 'var(--bg)',
                        color: reviewForm.aircraft_registration === reg ? '#fff' : 'var(--tx2)',
                        fontWeight: reviewForm.aircraft_registration === reg ? 700 : 400,
                      }}>
                      {reg}
                    </button>
                  ))}
                </div>
              </div>

              {/* Type document */}
              <div>
                <label style={{ fontSize: 11, fontWeight: 700, color: 'var(--tx3)', textTransform: 'uppercase', display: 'block', marginBottom: 6 }}>
                  <i className="fas fa-tag" style={{ marginRight: 5, color: 'var(--nv)' }}></i>Type de document
                </label>
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                  {DOC_TYPES.map(t => (
                    <button key={t} onClick={() => setReviewForm(f => ({ ...f, doc_type: t }))}
                      style={{
                        padding: '5px 12px', borderRadius: 7, fontSize: 12, cursor: 'pointer', border: '1.5px solid',
                        borderColor: reviewForm.doc_type === t ? 'var(--nv)' : 'var(--bdr)',
                        background: reviewForm.doc_type === t ? 'var(--sky)' : 'var(--bg)',
                        color: reviewForm.doc_type === t ? 'var(--nv)' : 'var(--tx2)',
                        fontWeight: reviewForm.doc_type === t ? 700 : 400,
                      }}>
                      {DOC_TYPES_DISPLAY[t] || t}
                    </button>
                  ))}
                </div>
              </div>

              {/* Catégorie */}
              <div>
                <label style={{ fontSize: 11, fontWeight: 700, color: 'var(--tx3)', textTransform: 'uppercase', display: 'block', marginBottom: 6 }}>
                  <i className="fas fa-folder-open" style={{ marginRight: 5, color: '#059669' }}></i>Catégorie
                </label>
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                  {CATEGORIES.map(c => (
                    <button key={c} onClick={() => setReviewForm(f => ({ ...f, category: c }))}
                      style={{
                        padding: '5px 12px', borderRadius: 7, fontSize: 12, cursor: 'pointer', border: '1.5px solid',
                        borderColor: reviewForm.category === c ? '#059669' : 'var(--bdr)',
                        background: reviewForm.category === c ? '#d1fae5' : 'var(--bg)',
                        color: reviewForm.category === c ? '#065f46' : 'var(--tx2)',
                        fontWeight: reviewForm.category === c ? 700 : 400,
                      }}>
                      {c}
                    </button>
                  ))}
                </div>
              </div>

              {/* ATA + ES ref */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                <div>
                  <label style={{ fontSize: 11, fontWeight: 700, color: 'var(--tx3)', display: 'block', marginBottom: 6, textTransform: 'uppercase' }}>Chapitre ATA</label>
                  <input type="text" value={reviewForm.ata_chapter}
                    onChange={e => setReviewForm(f => ({ ...f, ata_chapter: e.target.value }))}
                    placeholder="ex: 27, 32..."
                    style={{ width: '100%', padding: '8px 10px', borderRadius: 8, border: '1.5px solid var(--bdr)', fontSize: 13, boxSizing: 'border-box', background: 'var(--bg2)', color: 'var(--tx)', outline: 'none' }} />
                </div>
                <div>
                  <label style={{ fontSize: 11, fontWeight: 700, color: 'var(--tx3)', display: 'block', marginBottom: 6, textTransform: 'uppercase' }}>Référence ES</label>
                  <input type="text" value={reviewForm.es_reference}
                    onChange={e => setReviewForm(f => ({ ...f, es_reference: e.target.value }))}
                    placeholder="ex: ES001778"
                    style={{ width: '100%', padding: '8px 10px', borderRadius: 8, border: '1.5px solid var(--bdr)', fontSize: 13, boxSizing: 'border-box', background: 'var(--bg2)', color: 'var(--tx)', outline: 'none' }} />
                </div>
              </div>
            </div>

            {/* Footer */}
            <div style={{ padding: '12px 18px', borderTop: '1px solid var(--bdr)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'var(--bg2)' }}>
              <span style={{ fontSize: 12, color: 'var(--tx3)' }}>
                <i className="fas fa-user" style={{ marginRight: 5 }}></i>
                Par : <strong>{session?.nom || 'Utilisateur'}</strong>
              </span>
              <div style={{ display: 'flex', gap: 8 }}>
                <button className="btn btn-out btn-sm" onClick={() => setReviewModal(null)}>Annuler</button>
                <button onClick={submitReview} disabled={reviewSaving}
                  style={{
                    background: '#059669', color: '#fff', border: 'none',
                    borderRadius: 8, padding: '7px 20px', fontSize: 12,
                    fontWeight: 700, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6
                  }}>
                  <i className={`fas ${reviewSaving ? 'fa-spinner fa-spin' : 'fa-check'}`}></i>
                  {reviewSaving ? 'Enregistrement...' : 'Valider la correction'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── Modal Correction Documentaire (alertes) ──────────────────────────── */}
      {corrModal && (
        <div className="modal-overlay" onClick={() => setCorrModal(null)}>
          <div className="modal-box"
            style={{ width: '92%', maxWidth: 680, maxHeight: '90vh', display: 'flex', flexDirection: 'column' }}
            onClick={e => e.stopPropagation()}
          >
            <div className="modal-hd" style={{ background: 'linear-gradient(135deg, var(--nv) 0%, var(--nv2) 100%)' }}>
              <div>
                <h3 style={{ color: '#fff', margin: 0 }}>
                  <i className="fas fa-tools" style={{ marginRight: 8 }}></i>
                  Correction documentaire
                </h3>
                <div style={{ color: 'rgba(255,255,255,.7)', fontSize: 12, marginTop: 3 }}>
                  {corrModal.doc.filename} · Doc #{corrModal.doc.id}
                </div>
              </div>
              <button onClick={() => setCorrModal(null)}
                style={{ background: 'rgba(255,255,255,.15)', border: 'none', color: '#fff', width: 32, height: 32, borderRadius: 8, cursor: 'pointer', fontSize: 16 }}>
                ✕
              </button>
            </div>

            <div style={{ overflowY: 'auto', flex: 1 }}>
              <div style={{ margin: '16px 18px 0', padding: 12, borderRadius: 8, background: SEV_BG[corrModal.alert.severity], border: `1px solid ${SEV_COLOR[corrModal.alert.severity]}`, fontSize: 12, color: SEV_COLOR[corrModal.alert.severity] }}>
                <i className={`fas ${SEV_ICON[corrModal.alert.severity]} `} style={{ marginRight: 6 }}></i>
                <strong>Alerte #{corrModal.alert.id} :</strong> {corrModal.alert.title}
                <div style={{ marginTop: 4, color: 'var(--tx2)', fontWeight: 400 }}>{corrModal.alert.message}</div>
              </div>

              <div style={{ padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 14 }}>
                <div>
                  <label style={{ fontSize: 11, fontWeight: 700, color: 'var(--tx3)', textTransform: 'uppercase', letterSpacing: .5, display: 'block', marginBottom: 6 }}>
                    <i className="fas fa-plane" style={{ marginRight: 5, color: 'var(--nv)' }}></i>Immatriculation avion *
                  </label>
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                    {AIRCRAFT.map(reg => (
                      <button key={reg} onClick={() => setCorrForm(f => ({ ...f, aircraft_registration: reg }))}
                        style={{ padding: '6px 14px', borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: 'pointer', border: '2px solid', borderColor: corrForm.aircraft_registration === reg ? 'var(--nv)' : 'var(--bdr)', background: corrForm.aircraft_registration === reg ? 'var(--nv)' : 'var(--bg)', color: corrForm.aircraft_registration === reg ? '#fff' : 'var(--tx2)', transition: '.15s' }}>
                        {reg}
                      </button>
                    ))}
                    <input type="text" value={AIRCRAFT.includes(corrForm.aircraft_registration) ? '' : corrForm.aircraft_registration}
                      onChange={e => setCorrForm(f => ({ ...f, aircraft_registration: e.target.value.toUpperCase() }))}
                      placeholder="Autre (ex: TS-INX)"
                      style={{ flex: 1, minWidth: 120, padding: '6px 10px', borderRadius: 8, border: '1.5px solid var(--bdr)', fontSize: 13, color: 'var(--tx)', background: 'var(--bg2)', outline: 'none' }} />
                  </div>
                </div>

                <div>
                  <label style={{ fontSize: 11, fontWeight: 700, color: 'var(--tx3)', textTransform: 'uppercase', letterSpacing: .5, display: 'block', marginBottom: 6 }}>
                    <i className="fas fa-file-alt" style={{ marginRight: 5, color: 'var(--nv)' }}></i>Type de document
                  </label>
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                    {DOC_TYPES.map(t => (
                      <button key={t} onClick={() => setCorrForm(f => ({ ...f, doc_type: t }))}
                        style={{ padding: '5px 12px', borderRadius: 7, fontSize: 12, cursor: 'pointer', border: '1.5px solid', borderColor: corrForm.doc_type === t ? 'var(--nv)' : 'var(--bdr)', background: corrForm.doc_type === t ? 'var(--sky)' : 'var(--bg)', color: corrForm.doc_type === t ? 'var(--nv)' : 'var(--tx2)', fontWeight: corrForm.doc_type === t ? 700 : 400, transition: '.12s' }}>
                        {DOC_TYPES_DISPLAY[t] || t}
                      </button>
                    ))}
                  </div>
                </div>

                <div>
                  <label style={{ fontSize: 11, fontWeight: 700, color: 'var(--tx3)', textTransform: 'uppercase', letterSpacing: .5, display: 'block', marginBottom: 6 }}>
                    <i className="fas fa-folder-open" style={{ marginRight: 5, color: 'var(--nv)' }}></i>Catégorie
                  </label>
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                    {CATEGORIES.map(c => (
                      <button key={c} onClick={() => setCorrForm(f => ({ ...f, category: c }))}
                        style={{ padding: '5px 12px', borderRadius: 7, fontSize: 12, cursor: 'pointer', border: '1.5px solid', borderColor: corrForm.category === c ? '#059669' : 'var(--bdr)', background: corrForm.category === c ? '#d1fae5' : 'var(--bg)', color: corrForm.category === c ? '#065f46' : 'var(--tx2)', fontWeight: corrForm.category === c ? 700 : 400, transition: '.12s' }}>
                        {c}
                      </button>
                    ))}
                  </div>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                  <div>
                    <label style={{ fontSize: 11, fontWeight: 700, color: 'var(--tx3)', textTransform: 'uppercase', letterSpacing: .5, display: 'block', marginBottom: 6 }}>Chapitre ATA</label>
                    <input type="text" value={corrForm.ata_chapter} onChange={e => setCorrForm(f => ({ ...f, ata_chapter: e.target.value }))} placeholder="ex: 27, 32, 21..." style={{ width: '100%', padding: '8px 10px', borderRadius: 8, border: '1.5px solid var(--bdr)', fontSize: 13, color: 'var(--tx)', background: 'var(--bg2)', outline: 'none', boxSizing: 'border-box' }} />
                  </div>
                  <div>
                    <label style={{ fontSize: 11, fontWeight: 700, color: 'var(--tx3)', textTransform: 'uppercase', letterSpacing: .5, display: 'block', marginBottom: 6 }}>Référence ES</label>
                    <input type="text" value={corrForm.es_reference} onChange={e => setCorrForm(f => ({ ...f, es_reference: e.target.value }))} placeholder="ex: ES001778" style={{ width: '100%', padding: '8px 10px', borderRadius: 8, border: '1.5px solid var(--bdr)', fontSize: 13, color: 'var(--tx)', background: 'var(--bg2)', outline: 'none', boxSizing: 'border-box' }} />
                  </div>
                  <div style={{ gridColumn: '1 / -1' }}>
                    <label style={{ fontSize: 11, fontWeight: 700, color: 'var(--tx3)', textTransform: 'uppercase', letterSpacing: .5, display: 'block', marginBottom: 6 }}>Numéro d'item</label>
                    <input type="text" value={corrForm.item_number} onChange={e => setCorrForm(f => ({ ...f, item_number: e.target.value }))} placeholder="ex: 001, 002..." style={{ width: '100%', padding: '8px 10px', borderRadius: 8, border: '1.5px solid var(--bdr)', fontSize: 13, color: 'var(--tx)', background: 'var(--bg2)', outline: 'none', boxSizing: 'border-box' }} />
                  </div>
                </div>

                <div style={{ borderTop: '1px solid var(--bdr)', paddingTop: 14 }}>
                  <label style={{ fontSize: 11, fontWeight: 700, color: 'var(--tx3)', textTransform: 'uppercase', letterSpacing: .5, display: 'block', marginBottom: 8 }}>
                    <i className="fas fa-clipboard-check" style={{ marginRight: 5, color: '#d97706' }}></i>Action corrective *
                  </label>
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 10 }}>
                    {[
                      { v: 'verified',          l: '✓ Vérifié manuellement' },
                      { v: 'corrected',         l: '✏️ Classification corrigée' },
                      { v: 'reassigned',        l: '✈️ Réassigné à l\'avion' },
                      { v: 'duplicate_removed', l: '🗑 Doublon supprimé' },
                      { v: 'false_positive',    l: '🚫 Fausse alerte' },
                      { v: 'escalated',         l: '📤 Escaladé MRO' },
                    ].map(opt => (
                      <button key={opt.v} onClick={() => setCorrForm(f => ({ ...f, resolve_action: opt.v }))}
                        style={{ padding: '6px 12px', borderRadius: 8, fontSize: 12, cursor: 'pointer', border: '1.5px solid', borderColor: corrForm.resolve_action === opt.v ? '#d97706' : 'var(--bdr)', background: corrForm.resolve_action === opt.v ? '#fef3c7' : 'var(--bg)', color: corrForm.resolve_action === opt.v ? '#78350f' : 'var(--tx2)', fontWeight: corrForm.resolve_action === opt.v ? 700 : 400, transition: '.12s' }}>
                        {opt.l}
                      </button>
                    ))}
                  </div>
                  <textarea value={corrForm.comment} onChange={e => setCorrForm(f => ({ ...f, comment: e.target.value }))} rows={3}
                    placeholder="Commentaire libre..."
                    style={{ width: '100%', padding: 10, border: '1.5px solid var(--bdr)', borderRadius: 8, fontSize: 13, resize: 'none', outline: 'none', fontFamily: 'Barlow, sans-serif', color: 'var(--tx)', background: 'var(--bg2)', boxSizing: 'border-box' }} />
                </div>
              </div>
            </div>

            <div style={{ padding: '12px 18px', borderTop: '1px solid var(--bdr)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'var(--bg2)' }}>
              <span style={{ fontSize: 12, color: 'var(--tx3)' }}>
                <i className="fas fa-user" style={{ marginRight: 5 }}></i>
                Corrigé par : <strong>{session?.nom || 'Utilisateur'}</strong>
              </span>
              <div style={{ display: 'flex', gap: 8 }}>
                <button className="btn btn-out btn-sm" onClick={() => setCorrModal(null)}>Annuler</button>
                <button className="btn btn-blue btn-sm" onClick={submitCorrection} disabled={corrLoading} style={{ minWidth: 140 }}>
                  <i className={`fas ${corrLoading ? 'fa-spinner fa-spin' : 'fa-check'}`}></i>
                  {corrLoading ? 'Enregistrement...' : 'Valider la correction'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
      {/* Documents en attente */}
      <div className="card" style={{ marginBottom: 18 }}>
        <div className="ch">
          <h3><i className="fas fa-clock" style={{ color: '#d97706' }}></i>
            Documents en Attente
            {pendingDocs.length > 0 && <span className="tag a" style={{ marginLeft: 8, fontSize: 11 }}>{pendingDocs.length}</span>}
          </h3>
          <button className="btn btn-out btn-sm" onClick={fetchPendingDocs}>
            <i className="fas fa-sync-alt"></i>
          </button>
        </div>
        {pendingLoading ? (
          <div style={{ padding: 32, textAlign: 'center', color: 'var(--tx3)' }}>
            <i className="fas fa-spinner fa-spin"></i> Chargement...
          </div>
        ) : !pendingDocs.length ? (
          <div style={{ padding: 32, textAlign: 'center', color: 'var(--tx3)', fontSize: 13 }}>
            <i className="fas fa-check-circle" style={{ color: 'var(--acc)', fontSize: 28, display: 'block', marginBottom: 10 }}></i>
            Aucun document en attente ✅
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
              <thead>
                <tr style={{ borderBottom: '2px solid var(--bdr)', background: 'var(--bg2)' }}>
                  {['#', 'Fichier', 'Avion', 'Type', 'Date'].map(h => (
                    <th key={h} style={{ padding: '10px 12px', textAlign: 'left', fontWeight: 700, color: 'var(--tx3)', fontSize: 11, textTransform: 'uppercase' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {pendingDocs.map(doc => (
                  <tr key={doc.id} style={{ borderBottom: '1px solid var(--bdr)' }}>
                    <td style={{ padding: '10px 12px', color: 'var(--tx3)', fontSize: 11 }}>#{doc.id}</td>
                    <td style={{ padding: '10px 12px', fontWeight: 500, maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      <i className="fas fa-file-pdf" style={{ color: '#dc2626', marginRight: 6, fontSize: 11 }}></i>
                      {doc.filename}
                    </td>
                    <td style={{ padding: '10px 12px' }}>
                      <span className="tag b" style={{ fontSize: 10 }}>{doc.aircraft_registration || '—'}</span>
                    </td>
                    <td style={{ padding: '10px 12px' }}>
                      <span className="tag a" style={{ fontSize: 10 }}>{doc.doc_type || '—'}</span>
                    </td>
                    <td style={{ padding: '10px 12px', color: 'var(--tx3)', fontSize: 11 }}>
                      {doc.created_at ? doc.created_at.slice(0, 10) : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Documents sans immatriculation */}
      <div className="card">
        <div className="ch">
          <h3><i className="fas fa-plane-slash" style={{ color: 'var(--danger)' }}></i>
            Documents sans Immatriculation
            {noAircraftDocs.length > 0 && <span className="tag r" style={{ marginLeft: 8, fontSize: 11 }}>{noAircraftDocs.length}</span>}
          </h3>
          <button className="btn btn-out btn-sm" onClick={fetchNoAircraftDocs}>
            <i className="fas fa-sync-alt"></i>
          </button>
        </div>
        {noAircraftLoading ? (
          <div style={{ padding: 32, textAlign: 'center', color: 'var(--tx3)' }}>
            <i className="fas fa-spinner fa-spin"></i> Chargement...
          </div>
        ) : !noAircraftDocs.length ? (
          <div style={{ padding: 32, textAlign: 'center', color: 'var(--tx3)', fontSize: 13 }}>
            <i className="fas fa-check-circle" style={{ color: 'var(--acc)', fontSize: 28, display: 'block', marginBottom: 10 }}></i>
            Tous les documents ont une immatriculation ✅
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
              <thead>
                <tr style={{ borderBottom: '2px solid var(--bdr)', background: 'var(--bg2)' }}>
                  {['#', 'Fichier', 'Type', 'Catégorie', 'Date', 'Action'].map(h => (
                    <th key={h} style={{ padding: '10px 12px', textAlign: 'left', fontWeight: 700, color: 'var(--tx3)', fontSize: 11, textTransform: 'uppercase' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {noAircraftDocs.map(doc => (
                  <tr key={doc.id} style={{ borderBottom: '1px solid var(--bdr)' }}>
                    <td style={{ padding: '10px 12px', color: 'var(--tx3)', fontSize: 11 }}>#{doc.id}</td>
                    <td style={{ padding: '10px 12px', fontWeight: 500, maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      <i className="fas fa-file-pdf" style={{ color: '#dc2626', marginRight: 6, fontSize: 11 }}></i>
                      {doc.filename}
                    </td>
                    <td style={{ padding: '10px 12px' }}>
                      <span className="tag a" style={{ fontSize: 10 }}>{doc.doc_type || '—'}</span>
                    </td>
                    <td style={{ padding: '10px 12px', color: 'var(--tx2)', fontSize: 11 }}>{doc.category || '—'}</td>
                    <td style={{ padding: '10px 12px', color: 'var(--tx3)', fontSize: 11 }}>
                      {doc.created_at ? doc.created_at.slice(0, 10) : '—'}
                    </td>
                    <td style={{ padding: '10px 12px' }}>
                      <button
                        onClick={() => openReviewModal(doc)}
                        style={{
                          background: 'var(--nv)', color: '#fff', border: 'none',
                          borderRadius: 7, padding: '5px 14px', fontSize: 11,
                          cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 5,
                          fontWeight: 600, whiteSpace: 'nowrap'
                        }}
                      >
                        <i className="fas fa-edit"></i>Corriger
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}