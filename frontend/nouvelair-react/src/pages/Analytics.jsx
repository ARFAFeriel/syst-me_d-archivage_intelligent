// pages/Analytics.jsx
import { useApi, apiFetch } from '../hooks/useApi';
import { useToast } from '../contexts/ToastContext';

export default function Analytics() {
  const toast = useToast();
  const { data: kpis }  = useApi('/analytics/kpis');
  const { data: stats } = useApi('/analytics/stats');

  const archRate = kpis?.archive_rate_pct    || 0;
  const ocrRate  = kpis?.avg_ocr_confidence  || 0;

  const byType = stats?.by_type || [];
  const total  = byType.reduce((s, t) => s + (t.count || 0), 0) || 1;

  // ── Export CSV ──────────────────────────────────────────────────
  const exportCSV = async () => {
    const data = await apiFetch('/documents/?page=1&size=5000');
    if (!data?.items) { toast("Impossible d'exporter", 'err'); return; }
    const headers = ['ID', 'Fichier', 'Avion', 'Type', 'Catégorie', 'Réf.ES', 'ATA', 'Confiance OCR', 'Date'];
    const rows = data.items.map(d => [
      d.id, `"${d.filename}"`, d.aircraft_registration || '', d.doc_type || '',
      d.category || '', d.es_reference || '', d.ata_chapter || '',
      d.ocr_confidence ? d.ocr_confidence.toFixed(1) + '%' : '',
      d.created_at ? d.created_at.split('T')[0] : '',
    ]);
    const csv  = [headers, ...rows].map(r => r.join(',')).join('\n');
    const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8' });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href = url;
    a.download = `analytics_${new Date().toISOString().split('T')[0]}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    toast(`${data.items.length} documents exportés`, 'ok');
  };

  // ── Action recommandée selon confiance OCR ──────────────────────
  const getAction = (conf) => {
    if (!conf) return { label: '—', color: 'var(--tx3)' };
    if (conf >= 85) return { label: 'Archive fiable', color: '#059669' };
    if (conf >= 70) return { label: 'Acceptable', color: '#d97706' };
    return { label: 'Retraitement recommandé', color: '#1d4ed8' };
  };

  return (
    <div className="page-enter">
      <div className="ph">
        <h2><i className="fas fa-chart-line"></i>Analytics</h2>
        <p>Analyse de la qualité documentaire · Performance OCR · Distribution par type</p>
      </div>

      <div  style={{ marginBottom: 18 }}>
        

        {/* ── Power BI ── */}
        <div className="card">
          <div className="ch">
            <h3><i className="fas fa-chart-pie"></i>Rapports Power BI</h3>
          </div>
          <div style={{ padding: 0 }}>
            <iframe
              src="/Projet_PFE.pdf"
              width="100%"
              height="800px"
              style={{ border: 'none', borderRadius: '0 0 16px 16px' }}
            />
          </div>
        </div>
      </div>

      {/* ── Tableau stats par type ── */}
      <div className="card">
        <div className="ch">
          <h3><i className="fas fa-table"></i>Statistiques par Type de Document</h3>

        </div>
        <div className="tbl-wrap">
          <table className="tbl">
            <thead>
              <tr>
                <th>Type Document</th>
                <th>Nombre</th>
                <th title="Nombre de docs de ce type / total corpus × 100">% Total</th>
                <th title="Moyenne de ocr_confidence en DB pour ce type">Confiance OCR moy.</th>
                <th>Action recommandée</th>
              </tr>
            </thead>
            <tbody>
              {byType.length ? byType.map(t => {
                const pct    = ((t.count || 0) / total * 100).toFixed(1);
                const conf   = t.avg_ocr_confidence;
                const confCls = conf >= 85 ? 'h' : conf >= 70 ? 'm' : 'l';
                const action  = getAction(conf);
                return (
                  <tr key={t.type}>
                    <td style={{ fontWeight: 500 }}>{t.type || '—'}</td>
                    <td>{(t.count || 0).toLocaleString()}</td>
                    <td><span className="tag b">{pct}%</span></td>
                    <td>
                      <span className={`conf ${confCls}`}>
                        ● {conf ? conf.toFixed(1) + '%' : '—'}
                      </span>
                    </td>
                    <td>
                      <span style={{ fontSize: 11, fontWeight: 600, color: action.color }}>
                        {action.label}
                      </span>
                    </td>
                  </tr>
                );
              }) : (
                <tr>
                  <td colSpan={5} style={{ textAlign: 'center', padding: 32, color: 'var(--tx3)' }}>
                    {stats === null ? 'Backend non disponible' : <i className="fas fa-spinner fa-spin"></i>}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        {/* Note explicative */}
        <div style={{ padding: '10px 18px', fontSize: 11, color: 'var(--tx3)', borderTop: '1px solid var(--bdr)' }}>
          <i className="fas fa-info-circle" style={{ marginRight: 5 }}></i>
          <strong>Confiance OCR</strong> : moyenne calculée en DB (AVG ocr_confidence) par type.
          &nbsp;·&nbsp; <strong style={{ color: '#059669' }}>≥ 85%</strong> = fiable &nbsp;·&nbsp;
          <strong style={{ color: '#d97706' }}>70–84%</strong> = acceptable &nbsp;·&nbsp;
          <strong style={{ color: '#1d4ed8' }}>{'< 70%'}</strong> = retraitement recommandé
        </div>
      </div>
    </div>
  );
}