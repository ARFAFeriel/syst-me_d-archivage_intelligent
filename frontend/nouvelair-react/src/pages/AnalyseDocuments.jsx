// pages/AnalyseDocuments.jsx
import { useState, useEffect, useCallback } from 'react';
import { apiFetch } from '../hooks/useApi';
import { useToast } from '../contexts/ToastContext';

// ─── Helpers ─────────────────────────────────────────────────────────────────

function Tag({ text, cls }) {
  return <span className={`tag ${cls}`}>{text}</span>;
}

const TYPE_CLS = {
  WORK_ORDER: 'b', JOBCARD: 'p', AD: 'r', SB: 'or',
  AMM: 'c', CMM: 'c', IPC: 'c', SPECS: 'gr',
  DEFECT_REPORT: 'a', NCR: 'a', RCT: 'g', ATL: 'b',
  CERTIFICATE: 'g', DB_CHART: 'p', OTHER: 'gr',
};

const TYPE_ICON = {
  WORK_ORDER: 'fa-file-alt', JOBCARD: 'fa-clipboard-list',
  AD: 'fa-exclamation-triangle', SB: 'fa-tools',
  AMM: 'fa-book', CMM: 'fa-book-open', IPC: 'fa-list-ol',
  SPECS: 'fa-file-contract', DEFECT_REPORT: 'fa-bug',
  NCR: 'fa-times-circle', RCT: 'fa-certificate',
  ATL: 'fa-plane-departure', CERTIFICATE: 'fa-award',
  DB_CHART: 'fa-chart-bar', OTHER: 'fa-file',
};

// Normalise "Work Order" -> "WORK_ORDER"
const normalizeType = (t) => (t || '').replace(/\s+/g, '_').toUpperCase();

// ─── ConfBar ──────────────────────────────────────────────────────────────────

function ConfBar({ value, width = 80 }) {
  const pct = Math.min(100, Math.max(0, Math.round(value || 0)));
  const color = pct >= 80 ? '#3B6D11' : pct >= 50 ? '#854F0B' : '#A32D2D';
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <div style={{
        height: 6, width, borderRadius: 99,
        background: 'var(--color-border-tertiary)', overflow: 'hidden', flexShrink: 0,
      }}>
        <div style={{ height: '100%', width: `${pct}%`, background: color, borderRadius: 99 }} />
      </div>
      <span style={{ fontSize: 13, fontWeight: 500, minWidth: 34 }}>{pct}%</span>
    </div>
  );
}

// ─── Stat card ────────────────────────────────────────────────────────────────

function StatCard({ icon, label, value, sub, color }) {
  return (
    <div style={{
      background: 'var(--color-background-secondary)',
      borderRadius: 10, padding: '14px 16px',
      display: 'flex', alignItems: 'center', gap: 14,
    }}>
      <div style={{
        width: 40, height: 40, borderRadius: 10,
        background: color + '22',
        display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
      }}>
        <i className={`fas ${icon}`} style={{ fontSize: 18, color }} />
      </div>
      <div>
        <p style={{ fontSize: 11, color: 'var(--color-text-tertiary)', marginBottom: 2 }}>{label}</p>
        <p style={{ fontSize: 22, fontWeight: 500, lineHeight: 1 }}>{value}</p>
        {sub && <p style={{ fontSize: 12, color: 'var(--color-text-secondary)', marginTop: 2 }}>{sub}</p>}
      </div>
    </div>
  );
}

// ─── Panel row ───────────────────────────────────────────────────────────────

function PanelRow({ icon, label, children }) {
  return (
    <div style={{
      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      padding: '7px 0', borderBottom: '0.5px solid var(--color-border-tertiary)', fontSize: 13,
    }}>
      <span style={{ color: 'var(--color-text-secondary)', display: 'flex', alignItems: 'center', gap: 6, minWidth: 150 }}>
        <i className={`fas ${icon}`} style={{ fontSize: 12, opacity: 0.7 }} />
        {label}
      </span>
      <span style={{ fontWeight: 500, textAlign: 'right' }}>{children}</span>
    </div>
  );
}

// ─── Classification Panel ─────────────────────────────────────────────────────

function ClassificationPanel({ doc, onClose }) {
  if (!doc) return null;
  const nType = normalizeType(doc.doc_type);
  const typeCls = TYPE_CLS[nType] || 'gr';
  const typeIcon = TYPE_ICON[nType] || 'fa-file';

  // classifier_confidence est entre 0 et 1 → multiplier par 100
  const classifPct = doc.classifier_confidence != null
    ? Math.round(doc.classifier_confidence * 100)
    : null;

  // ocr_confidence est déjà en 0-100
  const ocrPct = doc.ocr_confidence != null
    ? Math.round(doc.ocr_confidence)
    : null;

  return (
    <div style={{
      border: '0.5px solid var(--color-border-tertiary)',
      borderRadius: 12,
      background: 'var(--color-background-primary)',
      position: 'sticky', top: 16, alignSelf: 'start',
      overflow: 'hidden',
    }}>
      {/* Header */}
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        padding: '12px 14px', borderBottom: '0.5px solid var(--color-border-tertiary)',
        background: 'var(--color-background-secondary)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
          <i className={`fas ${typeIcon}`}
            style={{ fontSize: 14, color: 'var(--color-text-secondary)', flexShrink: 0 }} />
          <span style={{
            fontSize: 13, fontWeight: 500,
            whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
          }}>
            {doc.filename}
          </span>
        </div>
        <button onClick={onClose} style={{
          background: 'none', border: 'none', cursor: 'pointer',
          color: 'var(--color-text-tertiary)', fontSize: 16, lineHeight: 1,
          padding: '2px 6px', flexShrink: 0, marginLeft: 8,
        }} aria-label="Fermer">✕</button>
      </div>

      <div style={{ padding: '14px' }}>

        {/* Résultats de classification */}
        <p style={{
          fontSize: 11, fontWeight: 500, letterSpacing: '0.06em',
          color: 'var(--color-text-tertiary)', textTransform: 'uppercase', marginBottom: 8,
        }}>Résultats de classification</p>
        <div style={{ background: 'var(--color-background-secondary)', borderRadius: 8, padding: '4px 10px', marginBottom: 14 }}>
          <PanelRow icon="fa-tag" label="Type détecté">
            <Tag text={doc.doc_type || '—'} cls={typeCls} />
          </PanelRow>
          <PanelRow icon="fa-chart-bar" label="Confiance classifieur">
            {classifPct != null
              ? <ConfBar value={classifPct} width={80} />
              : <span style={{ color: 'var(--color-text-tertiary)' }}>—</span>}
          </PanelRow>
          <PanelRow icon="fa-eye" label="Confiance OCR">
            {ocrPct != null
              ? <ConfBar value={ocrPct} width={80} />
              : <span style={{ color: 'var(--color-text-tertiary)' }}>—</span>}
          </PanelRow>
          <PanelRow icon="fa-folder" label="Catégorie">
            {doc.category || '—'}
          </PanelRow>
          <PanelRow icon="fa-book" label="Chapitre ATA">
            {doc.ata_chapter || '—'}
          </PanelRow>
        </div>

        {/* Métadonnées */}
        <p style={{
          fontSize: 11, fontWeight: 500, letterSpacing: '0.06em',
          color: 'var(--color-text-tertiary)', textTransform: 'uppercase', marginBottom: 8,
        }}>Métadonnées</p>
        <div style={{ background: 'var(--color-background-secondary)', borderRadius: 8, padding: '4px 10px', marginBottom: 14 }}>
          <PanelRow icon="fa-plane" label="Avion">
            <span>
              {doc.aircraft_registration || '—'}
              {doc.msn && (
                <span style={{ fontWeight: 400, color: 'var(--color-text-secondary)', marginLeft: 6 }}>
                  MSN {doc.msn}
                </span>
              )}
            </span>
          </PanelRow>
          <PanelRow icon="fa-hashtag" label="Référence ES">
            {doc.es_reference || '—'}
          </PanelRow>
          <PanelRow icon="fa-exclamation-circle" label="Document critique">
            <Tag text={doc.is_critical ? 'Oui' : 'Non'} cls={doc.is_critical ? 'r' : 'g'} />
          </PanelRow>
          <PanelRow icon="fa-flag" label="Révision requise">
            <Tag text={doc.needs_review ? 'Oui' : 'Non'} cls={doc.needs_review ? 'or' : 'g'} />
          </PanelRow>
          <PanelRow icon="fa-archive" label="Statut">
            <Tag text={doc.status || '—'} cls={doc.status === 'archived' ? 'g' : 'b'} />
          </PanelRow>
        </div>

        {/* Actions */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <button className="btn btn-blue btn-sm" style={{ width: '100%', justifyContent: 'center' }}
            onClick={() => window.open(`http://localhost:8000/api/v1/documents/${doc.id}/file`, '_blank')}>
            <i className="fas fa-eye" /> Prévisualiser
          </button>
          <button className="btn btn-out btn-sm" style={{ width: '100%', justifyContent: 'center' }}
            onClick={() => window.open(`http://localhost:8000/api/v1/documents/${doc.id}/file?download=true`, '_blank')}>
            <i className="fas fa-download" /> Télécharger
          </button>
        </div>

      </div>
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

const PAGE_SIZE = 20;

export default function AnalyseDocuments() {
  const { toast } = useToast();

  const [stats, setStats]           = useState(null);
  const [statsLoading, setStatsLoading] = useState(true);
  const [docs, setDocs]             = useState([]);
  const [total, setTotal]           = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [page, setPage]             = useState(1);
  const [loading, setLoading]       = useState(false);
  const [filters, setFilters]       = useState({
    search: '', aircraft: '', type: '', needsReview: '',
  });
  const [selectedDoc, setSelectedDoc] = useState(null);

  // ── Load stats ──────────────────────────────────────────────────────────────
  useEffect(() => {
    const loadStats = async () => {
      setStatsLoading(true);
      const data = await apiFetch('/documents/classification-stats');
      if (data) setStats(data);
      setStatsLoading(false);
    };
    loadStats();
  }, []);

  // ── Load docs ───────────────────────────────────────────────────────────────
  const loadDocs = useCallback(async (p = 1) => {
    setLoading(true);
    let url = `/documents?page=${p}&size=${PAGE_SIZE}`;
    if (filters.search)      url += `&search=${encodeURIComponent(filters.search)}`;
    if (filters.aircraft)    url += `&aircraft=${encodeURIComponent(filters.aircraft)}`;
    if (filters.type)        url += `&doc_type=${encodeURIComponent(filters.type)}`;
    if (filters.needsReview) url += `&needs_review=true`;
    const data = await apiFetch(url);
    if (data) {
      setDocs(data.items || []);
      setTotal(data.total || 0);
      setTotalPages(data.pages || 1);
    }
    setLoading(false);
  }, [page, filters]);

  useEffect(() => { loadDocs(page); }, [page, filters]);

  const setFilter = (key, value) => {
    setFilters(f => ({ ...f, [key]: value }));
    setPage(1);
  };

  const clearFilters = () => {
    setFilters({ search: '', aircraft: '', type: '', needsReview: '' });
    setPage(1);
  };

  const hasFilters = Object.values(filters).some(Boolean);

  // ─── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className="page-content">

      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <h1 className="page-title">Analyse Documents</h1>
        <p style={{ fontSize: 13, color: 'var(--color-text-secondary)', marginTop: 3 }}>
          Résultats de classification IA · Confiance OCR · Qualité du corpus
        </p>
      </div>

      {/* Stats cards */}
      {statsLoading ? (
        <div style={{ textAlign: 'center', padding: 24, color: 'var(--color-text-secondary)' }}>
          <i className="fas fa-spinner fa-spin" /> Chargement des statistiques...
        </div>
      ) : stats ? (
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
          gap: 12, marginBottom: 24,
        }}>
          <StatCard icon="fa-copy" label="Total documents"
            value={(stats.total || 0).toLocaleString()} sub="corpus complet" color="#185FA5" />
          <StatCard icon="fa-check-circle" label="Bien classifiés"
            value={`${Math.round((stats.high_confidence || 0) / (stats.total || 1) * 100)}%`}
            sub={`${(stats.high_confidence || 0).toLocaleString()} docs ≥ 80%`} color="#3B6D11" />
          <StatCard icon="fa-exclamation-triangle" label="Révision requise"
            value={(stats.needs_review || 0).toLocaleString()} sub="OCR ou classif. faible" color="#854F0B" />
          <StatCard icon="fa-times-circle" label="Confiance faible"
            value={(stats.low_confidence || 0).toLocaleString()} sub="classif. < 50%" color="#A32D2D" />
          <StatCard icon="fa-eye" label="OCR moyen"
            value={`${Math.round(stats.avg_ocr || 0)}%`} sub="tous avions confondus" color="#534AB7" />
          <StatCard icon="fa-clone" label="Doublons"
            value={(stats.duplicates || 0).toLocaleString()} sub="sha256 identique" color="#888780" />
        </div>
      ) : null}

      {/* OCR par avion */}
      {stats?.ocr_by_aircraft && (
        <div style={{
          background: 'var(--color-background-secondary)',
          borderRadius: 10, padding: '14px 16px', marginBottom: 24,
        }}>
          <p style={{ fontSize: 13, fontWeight: 500, marginBottom: 12 }}>
            <i className="fas fa-plane" style={{ marginRight: 7, opacity: 0.6 }} />
            Confiance OCR par avion
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {stats.ocr_by_aircraft.map(ac => (
              <div key={ac.registration} style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <span style={{ fontSize: 13, fontWeight: 500, minWidth: 60 }}>{ac.registration}</span>
                <div style={{
                  flex: 1, height: 8, borderRadius: 99,
                  background: 'var(--color-border-tertiary)', overflow: 'hidden',
                }}>
                  <div style={{
                    height: '100%',
                    width: `${Math.round(ac.avg_ocr)}%`,
                    background: ac.avg_ocr >= 80 ? '#3B6D11' : ac.avg_ocr >= 50 ? '#854F0B' : '#A32D2D',
                    borderRadius: 99,
                  }} />
                </div>
                <span style={{ fontSize: 13, fontWeight: 500, minWidth: 40, textAlign: 'right' }}>
                  {Math.round(ac.avg_ocr)}%
                </span>
                <span style={{ fontSize: 12, color: 'var(--color-text-secondary)', minWidth: 80, textAlign: 'right' }}>
                  {ac.doc_count.toLocaleString()} docs
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Filters */}
      <div style={{
        display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 16,
        padding: '12px 14px',
        background: 'var(--color-background-secondary)',
        borderRadius: 10, border: '0.5px solid var(--color-border-tertiary)',
      }}>
        <input className="input-sm" placeholder="Rechercher (nom, ES...)"
          value={filters.search} onChange={e => setFilter('search', e.target.value)}
          style={{ flex: '1 1 180px', minWidth: 160 }} />
        <select className="input-sm" value={filters.aircraft}
          onChange={e => setFilter('aircraft', e.target.value)} style={{ minWidth: 120 }}>
          <option value="">Tous les avions</option>
          <option value="TS-INO">TS-INO</option>
          <option value="TS-INP">TS-INP</option>
          <option value="TS-INQ">TS-INQ</option>
        </select>
        <select className="input-sm" value={filters.type}
          onChange={e => setFilter('type', e.target.value)} style={{ minWidth: 140 }}>
          <option value="">Tous les types</option>
          {Object.keys(TYPE_CLS).map(t => (
            <option key={t} value={t}>{t.replace(/_/g, ' ')}</option>
          ))}
        </select>
        
        {hasFilters && (
          <button className="btn btn-out btn-sm" onClick={clearFilters}>
            <i className="fas fa-times" /> Effacer
          </button>
        )}
      </div>

      {/* Main layout */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: selectedDoc ? 'minmax(0,1fr) 320px' : 'minmax(0,1fr)',
        gap: 16, alignItems: 'start',
      }}>

        {/* Table */}
        <div>
          {loading ? (
            <div style={{ textAlign: 'center', padding: 40, color: 'var(--color-text-secondary)' }}>
              <i className="fas fa-spinner fa-spin" style={{ fontSize: 22, marginBottom: 10 }} />
              <p style={{ fontSize: 14 }}>Chargement...</p>
            </div>
          ) : docs.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 40, color: 'var(--color-text-secondary)' }}>
              <i className="fas fa-folder-open" style={{ fontSize: 32, marginBottom: 12, opacity: 0.4 }} />
              <p style={{ fontSize: 14 }}>Aucun document trouvé</p>
              {hasFilters && (
                <button className="btn btn-out btn-sm" onClick={clearFilters} style={{ marginTop: 12 }}>
                  Effacer les filtres
                </button>
              )}
            </div>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                <thead>
                  <tr style={{ borderBottom: '0.5px solid var(--color-border-tertiary)' }}>
                    {['Fichier', 'Type', 'Avion', 'Conf. classif.', 'Conf. OCR', 'Révision', 'Statut'].map(h => (
                      <th key={h} style={{
                        padding: '8px 10px', textAlign: 'left', fontWeight: 500,
                        color: 'var(--color-text-secondary)', whiteSpace: 'nowrap',
                      }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {docs.map(doc => {
                    const isSelected = selectedDoc?.id === doc.id;
                    const nType = normalizeType(doc.doc_type);
                    const classifPct = doc.classifier_confidence != null
                      ? Math.round(doc.classifier_confidence * 100)
                      : null;
                    const ocrPct = doc.ocr_confidence != null
                      ? Math.round(doc.ocr_confidence)
                      : null;
                    return (
                      <tr
                        key={doc.id}
                        onClick={() => setSelectedDoc(isSelected ? null : doc)}
                        style={{
                          borderBottom: '0.5px solid var(--color-border-tertiary)',
                          cursor: 'pointer',
                          background: isSelected ? 'var(--color-background-info)' : 'transparent',
                          transition: 'background .12s',
                        }}
                        onMouseEnter={e => { if (!isSelected) e.currentTarget.style.background = 'var(--color-background-secondary)'; }}
                        onMouseLeave={e => { if (!isSelected) e.currentTarget.style.background = 'transparent'; }}
                      >
                        <td style={{ padding: '8px 10px', maxWidth: 200 }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                            <i className={`fas ${TYPE_ICON[nType] || 'fa-file'}`}
                              style={{ fontSize: 13, color: 'var(--color-text-tertiary)', flexShrink: 0 }} />
                            <span style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 160 }}>
                              {doc.filename}
                            </span>
                          </div>
                        </td>
                        <td style={{ padding: '8px 10px', whiteSpace: 'nowrap' }}>
                          <Tag text={doc.doc_type || '—'} cls={TYPE_CLS[nType] || 'gr'} />
                        </td>
                        <td style={{ padding: '8px 10px', whiteSpace: 'nowrap' }}>
                          {doc.aircraft_registration || '—'}
                        </td>
                        <td style={{ padding: '8px 10px' }}>
                          {classifPct != null
                            ? <ConfBar value={classifPct} width={70} />
                            : <span style={{ color: 'var(--color-text-tertiary)' }}>—</span>}
                        </td>
                        <td style={{ padding: '8px 10px' }}>
                          {ocrPct != null
                            ? <ConfBar value={ocrPct} width={70} />
                            : <span style={{ color: 'var(--color-text-tertiary)' }}>—</span>}
                        </td>
                        <td style={{ padding: '8px 10px' }}>
                          {doc.needs_review
                            ? <Tag text="Oui" cls="or" />
                            : <Tag text="Non" cls="g" />}
                        </td>
                        <td style={{ padding: '8px 10px' }}>
                          <Tag
                            text={doc.status || '—'}
                            cls={doc.status === 'archived' ? 'g' : 'b'}
                          />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {/* Pagination */}
          {totalPages > 1 && (
            <div style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              padding: '12px 4px', marginTop: 8, fontSize: 13,
              color: 'var(--color-text-secondary)',
            }}>
              <span>Page {page} / {totalPages} — {total.toLocaleString()} documents</span>
              <div style={{ display: 'flex', gap: 6 }}>
                <button className="btn btn-out btn-sm" disabled={page <= 1}
                  onClick={() => setPage(p => Math.max(1, p - 1))}>
                  <i className="fas fa-chevron-left" />
                </button>
                <button className="btn btn-out btn-sm" disabled={page >= totalPages}
                  onClick={() => setPage(p => Math.min(totalPages, p + 1))}>
                  <i className="fas fa-chevron-right" />
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Panel */}
        {selectedDoc && (
          <ClassificationPanel doc={selectedDoc} onClose={() => setSelectedDoc(null)} />
        )}

      </div>
    </div>
  );
}