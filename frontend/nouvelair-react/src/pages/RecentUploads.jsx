// pages/RecentUploads.jsx
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useApi } from '../hooks/useApi';

const TYPE_COLORS = {
  WORK_ORDER: '#003087', JOBCARD: '#059669', DEFECT_REPORT: '#f59e0b',
  AD: '#1d4ed8', CERTIFICATE: '#7c3aed', SB: '#0891b2', ATL: '#64748b',
  SPECS: '#0d9488', NCR: '#2563eb', RCT: '#10b981', CMM: '#8b5cf6',
  AMM: '#6366f1', IPC: '#ec4899',
};

function timeAgo(iso) {
  if (!iso) return '—';
  const d = (Date.now() - new Date(iso)) / 1000;
  if (d < 60)    return 'À l\'instant';
  if (d < 3600)  return `Il y a ${Math.round(d / 60)} min`;
  if (d < 86400) return `Il y a ${Math.round(d / 3600)} h`;
  if (d < 604800) return `Il y a ${Math.round(d / 86400)} j`;
  return new Date(iso).toLocaleDateString('fr-FR', { day: '2-digit', month: 'short', year: 'numeric' });
}

function formatDateTime(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('fr-FR', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

export default function RecentUploads() {
  const navigate = useNavigate();
  const [limit, setLimit] = useState(20);
  const [filterAircraft, setFilterAircraft] = useState('');
  const [filterType, setFilterType] = useState('');
  const [filterPeriod, setFilterPeriod] = useState('');

  const { data: docs, loading, refetch } = useApi(`/documents/?page=1&size=${limit}&sort=created_at_desc`);
  const { data: aircraftList } = useApi('/aircraft/');
  const { data: stats } = useApi('/analytics/stats');

  const allDocs = docs?.items || docs || [];
  const docTypes = stats?.by_type?.map(t => t.type) || [];
  const activeAircraft = (aircraftList || []);

  // Filtres côté frontend
  const filtered = allDocs.filter(d => {
    if (filterAircraft && d.aircraft_registration !== filterAircraft) return false;
    if (filterType && d.doc_type !== filterType) return false;
    if (filterPeriod) {
      const ms = Date.now() - new Date(d.created_at || d.archived_at);
      if (filterPeriod === 'today'  && ms > 86400000)    return false;
      if (filterPeriod === 'week'   && ms > 604800000)   return false;
      if (filterPeriod === 'month'  && ms > 2592000000)  return false;
    }
    return true;
  });

  // Grouper par jour
  const grouped = {};
  filtered.forEach(d => {
    const date = d.created_at || d.archived_at;
    const day = date ? new Date(date).toLocaleDateString('fr-FR', { weekday: 'long', day: '2-digit', month: 'long', year: 'numeric' }) : 'Date inconnue';
    if (!grouped[day]) grouped[day] = [];
    grouped[day].push(d);
  });

  const ocrColor = (v) => {
    if (!v) return 'var(--tx3)';
    if (v >= 85) return '#059669';
    if (v >= 70) return '#d97706';
    return '#1d4ed8';
  };

  return (
    <div className="page-enter">
      <div className="ph">
        <div className="ph-row">
          <div>
            <h2><i className="fas fa-history"></i>Documents Uploadés</h2>
            <p>Historique des documents archivés · Triés par date d'upload décroissante</p>
          </div>
          <button className="btn btn-out btn-sm" onClick={refetch}>
            <i className="fas fa-sync-alt"></i>Actualiser
          </button>
        </div>
      </div>

      {/* ── Filtres ── */}
      <div style={{
        display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center',
        marginBottom: 18, padding: '12px 16px',
        background: 'var(--sur)', borderRadius: 10, border: '1px solid var(--bdr)',
      }}>
        <i className="fas fa-filter" style={{ color: 'var(--tx3)', fontSize: 12 }}></i>

        {/* Avion */}
        <select value={filterAircraft} onChange={e => setFilterAircraft(e.target.value)}
          style={{ padding: '6px 10px', border: '1.5px solid var(--bdr)', borderRadius: 8, fontSize: 12, background: 'var(--bg2)', color: 'var(--tx)', cursor: 'pointer' }}>
          <option value="">Tous les avions</option>
          {activeAircraft.map(a => (
            <option key={a.registration} value={a.registration}>{a.registration}</option>
          ))}
        </select>

        {/* Type */}
        <select value={filterType} onChange={e => setFilterType(e.target.value)}
          style={{ padding: '6px 10px', border: '1.5px solid var(--bdr)', borderRadius: 8, fontSize: 12, background: 'var(--bg2)', color: 'var(--tx)', cursor: 'pointer' }}>
          <option value="">Tous les types</option>
          {docTypes.map(t => <option key={t} value={t}>{t}</option>)}
        </select>

        {/* Période */}
        <select value={filterPeriod} onChange={e => setFilterPeriod(e.target.value)}
          style={{ padding: '6px 10px', border: '1.5px solid var(--bdr)', borderRadius: 8, fontSize: 12, background: 'var(--bg2)', color: 'var(--tx)', cursor: 'pointer' }}>
          <option value="">Toutes les périodes</option>
          <option value="today">Aujourd'hui</option>
          <option value="week">Cette semaine</option>
          <option value="month">Ce mois</option>
        </select>

        {/* Nombre de résultats */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginLeft: 'auto' }}>
          <span style={{ fontSize: 11, color: 'var(--tx3)' }}>Afficher</span>
          <select value={limit} onChange={e => setLimit(Number(e.target.value))}
            style={{ padding: '6px 10px', border: '1.5px solid var(--bdr)', borderRadius: 8, fontSize: 12, background: 'var(--bg2)', color: 'var(--tx)', cursor: 'pointer' }}>
            {[10, 20, 50, 100, 200].map(n => (
              <option key={n} value={n}>{n} documents</option>
            ))}
          </select>
        </div>

        {/* Résumé */}
        <span style={{ fontSize: 11, color: 'var(--tx3)', marginLeft: 8 }}>
          {filtered.length} document{filtered.length > 1 ? 's' : ''}
          {(filterAircraft || filterType || filterPeriod) && ' (filtré)'}
        </span>

        {/* Reset filtres */}
        {(filterAircraft || filterType || filterPeriod) && (
          <button className="btn btn-out btn-sm"
            onClick={() => { setFilterAircraft(''); setFilterType(''); setFilterPeriod(''); }}
            style={{ fontSize: 11 }}>
            <i className="fas fa-times"></i>Réinitialiser
          </button>
        )}
      </div>

      {/* ── Contenu ── */}
      {loading ? (
        <div style={{ padding: 40, textAlign: 'center', color: 'var(--tx3)' }}>
          <i className="fas fa-spinner fa-spin" style={{ fontSize: 24, display: 'block', marginBottom: 12 }}></i>
          Chargement de l'historique...
        </div>
      ) : !filtered.length ? (
        <div style={{ padding: 40, textAlign: 'center', color: 'var(--tx3)' }}>
          <i className="fas fa-inbox" style={{ fontSize: 32, display: 'block', marginBottom: 12, opacity: .3 }}></i>
          Aucun document trouvé
        </div>
      ) : (
        /* Timeline groupée par jour */
        Object.entries(grouped).map(([day, dayDocs]) => (
          <div key={day} style={{ marginBottom: 24 }}>
            {/* En-tête du jour */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
              <div style={{
                padding: '4px 12px', background: 'var(--nv)', color: '#fff',
                borderRadius: 20, fontSize: 11, fontWeight: 600, whiteSpace: 'nowrap',
              }}>
                {day}
              </div>
              <div style={{ flex: 1, height: 1, background: 'var(--bdr)' }}></div>
              <span style={{ fontSize: 11, color: 'var(--tx3)', whiteSpace: 'nowrap' }}>
                {dayDocs.length} document{dayDocs.length > 1 ? 's' : ''}
              </span>
            </div>

            {/* Documents du jour */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {dayDocs.map((doc, i) => {
                const typeColor = TYPE_COLORS[doc.doc_type] || 'var(--tx3)';
                const date = doc.created_at || doc.archived_at;
                return (
                  <div key={doc.id || i} style={{
                    display: 'flex', alignItems: 'center', gap: 14,
                    padding: '12px 16px', background: 'var(--sur)',
                    borderRadius: 10, border: '1px solid var(--bdr)',
                    transition: 'border-color .15s, box-shadow .15s',
                    cursor: 'default',
                  }}
                    onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--nv2)'; e.currentTarget.style.boxShadow = '0 2px 8px rgba(0,48,135,.08)'; }}
                    onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--bdr)'; e.currentTarget.style.boxShadow = 'none'; }}
                  >
                    {/* Icône type */}
                    <div style={{
                      width: 36, height: 36, borderRadius: 8, flexShrink: 0,
                      background: `${typeColor}18`, display: 'flex',
                      alignItems: 'center', justifyContent: 'center',
                    }}>
                      <i className="fas fa-file-pdf" style={{ color: typeColor, fontSize: 15 }}></i>
                    </div>

                    {/* Infos principales */}
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--tx)', marginBottom: 3, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {doc.filename}
                      </div>
                      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
                        {doc.aircraft_registration && (
                          <span className="tag b" style={{ fontSize: 9 }}>{doc.aircraft_registration}</span>
                        )}
                        {doc.doc_type && (
                          <span style={{ fontSize: 9, padding: '1px 7px', borderRadius: 10, background: `${typeColor}18`, color: typeColor, fontWeight: 600 }}>
                            {doc.doc_type}
                          </span>
                        )}
                        {doc.es_reference && (
                          <span style={{ fontSize: 10, color: 'var(--tx3)' }}>ES: {doc.es_reference}</span>
                        )}
                        {doc.ata_chapter && (
                          <span style={{ fontSize: 10, color: 'var(--tx3)' }}>ATA {doc.ata_chapter}</span>
                        )}
                      </div>
                    </div>

                    {/* OCR */}
                    <div style={{ textAlign: 'center', flexShrink: 0, width: 60 }}>
                      <div style={{ fontSize: 13, fontWeight: 700, color: ocrColor(doc.ocr_confidence) }}>
                        {doc.ocr_confidence ? doc.ocr_confidence.toFixed(0) + '%' : '—'}
                      </div>
                      <div style={{ fontSize: 9, color: 'var(--tx3)', textTransform: 'uppercase', letterSpacing: '.3px' }}>OCR</div>
                    </div>

                    {/* Heure + timeAgo */}
                    <div style={{ textAlign: 'right', flexShrink: 0, minWidth: 110 }}>
                      <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--tx2)' }}>
                        {date ? new Date(date).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' }) : '—'}
                      </div>
                      <div style={{ fontSize: 10, color: 'var(--tx3)', marginTop: 2 }}>{timeAgo(date)}</div>
                    </div>

                    {/* Bouton accès direct */}
                    <button
                      className="btn btn-out btn-sm"
                      style={{ flexShrink: 0, fontSize: 11 }}
                      onClick={() => navigate('/search', { state: { query: doc.filename } })}
                      title="Rechercher ce document"
                    >
                      <i className="fas fa-arrow-right"></i>
                    </button>
                  </div>
                );
              })}
            </div>
          </div>
        ))
      )}
    </div>
  );
}