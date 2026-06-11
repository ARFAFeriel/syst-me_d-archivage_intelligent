// pages/Dashboard.jsx — NouvelAir MRO
import { useState } from 'react';
import * as XLSX from 'xlsx';
import { useApi } from '../hooks/useApi';

function useTooltip() {
  const [tip, setTip] = useState({ visible: false, text: '', x: 0, y: 0 });
  const show = (e, text) => setTip({ visible: true, text, x: e.clientX + 14, y: e.clientY - 36 });
  const move = (e) => setTip(t => t.visible ? { ...t, x: e.clientX + 14, y: e.clientY - 36 } : t);
  const hide = () => setTip(t => ({ ...t, visible: false }));
  const Tooltip = () => tip.visible ? (
    <div style={{
      position: 'fixed', left: tip.x, top: tip.y, zIndex: 900,
      background: '#1c2d45', color: '#d4e6f8',
      fontSize: 11, padding: '6px 10px', borderRadius: 6,
      pointerEvents: 'none', whiteSpace: 'nowrap',
      boxShadow: '0 4px 14px rgba(0,0,0,.3)',
    }}>{tip.text}</div>
  ) : null;
  return { show, move, hide, Tooltip };
}

function Gauge({ value, label, color = 'var(--nv)', size = 80 }) {
  const pct  = Math.min(100, Math.max(0, value || 0));
  const r    = (size / 2) - 8;
  const circ = 2 * Math.PI * r;
  const dash = (pct / 100) * circ;
  return (
    <div style={{ textAlign: 'center' }}>
      <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
        <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="var(--bg2)" strokeWidth={8} />
        <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={color} strokeWidth={8}
          strokeDasharray={`${dash} ${circ}`} strokeLinecap="round"
          style={{ transition: 'stroke-dasharray 1s ease' }} />
      </svg>
      <div style={{ marginTop: -size/2 - 4, fontSize: 14, fontWeight: 700, color }}>{pct.toFixed(1)}%</div>
      <div style={{ fontSize: 10, color: 'var(--tx3)', marginTop: size/2 - 8 }}>{label}</div>
    </div>
  );
}

function Bar({ label, value, max, color = 'var(--nv)', suffix = '', note }) {
  const tt = useTooltip();
  const pct = max > 0 ? Math.round(value / max * 100) : 0;
  return (
    <div className="aib">
      <tt.Tooltip />
      <div className="aib-h">
        <span style={{ fontSize: 12 }}
          onMouseEnter={note ? e => tt.show(e, note) : undefined}
          onMouseMove={note ? tt.move : undefined}
          onMouseLeave={note ? tt.hide : undefined}
        >{label}</span>
        <strong style={{ fontSize: 13 }}>{typeof value === 'number' ? value.toLocaleString() : value}{suffix}</strong>
      </div>
      <div className="bar-t">
        <div className="bar-f" style={{ width: `${pct}%`, background: color }} />
      </div>
    </div>
  );
}

function StatRow({ label, value, color, sub, border = true }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: '9px 0',
      borderBottom: border ? '1px solid var(--bdr)' : 'none',
    }}>
      <div>
        <div style={{ fontSize: 13, color: 'var(--tx)' }}>{label}</div>
        {sub && <div style={{ fontSize: 11, color: 'var(--tx3)', marginTop: 2 }}>{sub}</div>}
      </div>
      <span style={{ fontSize: 14, fontWeight: 700, color: color || 'var(--tx)', flexShrink: 0 }}>
        {typeof value === 'number' ? value.toLocaleString() : value}
      </span>
    </div>
  );
}

function CheckGroup({ type, checks }) {
  const [open, setOpen] = useState(false);
  const total = checks.reduce((s, c) => s + (c.total_documents || 0), 0);
  return (
    <div style={{ borderBottom: '1px solid var(--bdr)' }}>
      <div
        onClick={() => setOpen(o => !o)}
        style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '12px 16px', cursor: 'pointer',
          background: open ? 'var(--bg2)' : 'transparent',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <i className={`fas fa-chevron-${open ? 'down' : 'right'}`} style={{ fontSize: 11, color: 'var(--tx3)' }} />
          <span style={{ fontWeight: 600, fontSize: 13 }}>{type}</span>
          <span className="tag b" style={{ fontSize: 11 }}>{checks.length} checks</span>
        </div>
        <span style={{ fontSize: 12, color: 'var(--tx3)' }}>{total.toLocaleString()} docs</span>
      </div>
      {open && (
        <table className="tbl" style={{ margin: 0 }}>
          <thead>
            <tr>
              <th>Référence ES</th>
              <th>Avion</th>
              <th>Documents</th>
            </tr>
          </thead>
          <tbody>
            {checks.map(c => (
              <tr key={c.id}>
                <td><span className="tag b">{c.es_reference}</span></td>
                <td>{c.aircraft_registration}</td>
                <td><strong>{c.total_documents}</strong></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

export default function Dashboard() {
  const [activeTab, setActiveTab] = useState('overview');
  const chartTip = useTooltip();

  const { data: kpis,     loading: kLoading, refetch } = useApi('/analytics/kpis');
  const { data: stats }    = useApi('/analytics/stats');
  const { data: advanced } = useApi('/analytics/advanced');
  const { data: alerts }   = useApi('/pipeline/alerts?limit=5');
  const { data: pipeline } = useApi('/pipeline/status');
  const { data: checks }   = useApi('/aircraft/checks/all');

  const totalDocs    = kpis?.total_documents    || 0;
  const archived     = kpis?.archived           || 0;
  const avgOcr       = kpis?.avg_ocr_confidence || 0;
  const activeAlerts = kpis?.active_alerts      || 0;
  const criticalAds  = kpis?.critical_ads       || 0;
  const needsReview  = kpis?.needs_review       || 0;
  const archiveRate  = kpis?.archive_rate_pct   || 0;
  const qualityScore = advanced?.quality_score  || 0;

  const byAircraft = stats?.by_aircraft || [];
  const byType     = stats?.by_type     || [];
  const anomalies  = advanced?.anomalies || {};
  const coverage   = advanced?.coverage_by_aircraft || [];
  const ocrDist    = advanced?.ocr_distribution    || [];
  const monthly    = advanced?.monthly_evolution   || [];

  const nerConf = pipeline?.agents?.ner?.confidence        != null ? Math.round(pipeline.agents.ner.confidence * 100)        : null;
  const clsConf = pipeline?.agents?.classifier?.confidence != null ? Math.round(pipeline.agents.classifier.confidence * 100) : null;
  const embConf = pipeline?.agents?.embedding?.confidence  != null ? Math.round(pipeline.agents.embedding.confidence * 100)  : null;

  const maxByAircraft = Math.max(...byAircraft.map(a => a.count || 0), 1);
  const typeTotal     = byType.reduce((s, t) => s + (t.count || 0), 0) || 1;
  const maxMonthly    = Math.max(...monthly.map(m => m.count || 0), 1);
  const typeColors    = ['var(--nv)', 'var(--warn)', 'var(--acc)', '#7c3aed', '#0891b2', 'var(--danger)', '#059669', 'var(--tx3)'];
  const ocrColors     = { '90-100%': '#059669', '75-89%': 'var(--acc)', '50-74%': 'var(--warn)', '25-49%': '#f97316', '1-24%': 'var(--danger)', '0%': 'var(--tx3)' };

  const getMsn = (reg) => {
    const a = byAircraft.find(x => x.aircraft === reg);
    return a?.msn ? `MSN ${a.msn}` : 'Flotte NouvelAir';
  };

  const tabs = [
    { key: 'overview',    label: 'Vue Générale',    icon: 'fa-chart-bar'  },
    { key: 'quality',     label: 'Qualité Archive', icon: 'fa-shield-alt' },
    { key: 'restitution', label: 'Restitution',     icon: 'fa-plane'      },
  ];

  return (
    <div className="page-enter">
      <chartTip.Tooltip />

      {/* En-tête */}
      <div className="ph">
        <div className="ph-row">
          <div>
            <h2><i className="fas fa-chart-bar"></i>Tableau de Bord</h2>
            <p>Vue d'ensemble opérationnelle · KPIs archive · Qualité documentaire · Alertes MRO</p>
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            {needsReview > 0 && (
              <span className="tag a" style={{ fontSize: 11 }}>
                <i className="fas fa-clock"></i> {needsReview.toLocaleString()} à réviser
              </span>
            )}
            <button className="btn btn-out btn-sm" onClick={refetch}>
              <i className="fas fa-sync-alt"></i> Actualiser
            </button>
          </div>
        </div>
      </div>

      {/* 4 KPIs principaux */}
      <div className="kpig" style={{ marginBottom: 22 }}>
        {kLoading ? (
          <div style={{ gridColumn: '1/-1', padding: 24, textAlign: 'center', color: 'var(--tx3)' }}>
            <i className="fas fa-spinner fa-spin"></i> Chargement…
          </div>
        ) : kpis ? (
          <>
            <div className="kpi">
              <div className="kic b"><i className="fas fa-file-pdf"></i></div>
              <div style={{ flex: 1 }}>
                <div className="kval">{totalDocs.toLocaleString()}</div>
                <div className="klbl">Documents </div>
                <div className="kd up">
                  <i className="fas fa-check-circle"></i>
                  Taux archivage : {archiveRate}% · {archived.toLocaleString()} archivés · {(totalDocs - archived).toLocaleString()} en attente
                </div>
              </div>
            </div>


            <div className="kpi">
              <div className="kic b"><i className="fas fa-plane"></i></div>
              <div style={{ flex: 1 }}>
                <div className="kval">{kpis?.total_aircraft || 0}</div>
                <div className="klbl">Avions Gérés</div>
                <div className="kd up">
                  <i className="fas fa-info-circle"></i>
                  Flotte NouvelAir · Airbus A320
                </div>
              </div>
            </div>
            

            <div className="kpi">
              <div className="kic a"><i className="fas fa-plane-slash"></i></div>
              <div style={{ flex: 1 }}>
                <div className="kval">{(anomalies.sans_avion || 0).toLocaleString()}</div>
                <div className="klbl">Sans Immatriculation</div>
                <div className="kd dn">
                  <i className="fas fa-exclamation-circle"></i>
                  Documents non rattachés à un aéronef
                </div>
              </div>
            </div>

            <div className="kpi">
              <div className="kic b"><i className="fas fa-clock"></i></div>
              <div style={{ flex: 1 }}>
                <div className="kval" style={{ fontSize: 16 }}>
                  {kpis?.last_activity
                    ? new Date(kpis.last_activity).toLocaleDateString('fr-FR', {
                        day: '2-digit', month: 'short', year: 'numeric',
                        hour: '2-digit', minute: '2-digit'
                      })
                    : '—'}
                </div>
                <div className="klbl">Dernière Exécution Pipeline</div>
                <div className="kd up">
                  <i className="fas fa-info-circle"></i>
                  {pipeline?.status === 'idle' ? 'Pipeline en attente' : pipeline?.status || 'Statut inconnu'}
                </div>
              </div>
            </div>

            


            <div className="kpi">
              <div className="kic a"><i className="fas fa-exclamation-triangle"></i></div>
              <div style={{ flex: 1 }}>
                <div className="kval">{activeAlerts.toLocaleString()}</div>
                <div className="klbl">Alertes Actives</div>
                <div className="kd dn">
                  <i className="fas fa-exclamation-circle"></i>
                  {activeAlerts} OCR\_LOW\_CONFIDENCE · {needsReview.toLocaleString()} docs à réviser
                </div>
              </div>
            </div>
          </>
        ) : (
          <div style={{ gridColumn: '1/-1', padding: 24, textAlign: 'center', color: 'var(--tx3)' }}>
            <i className="fas fa-exclamation-circle"></i> Backend non disponible
          </div>
        )}
      </div>



      {/* Onglets */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 20, borderBottom: '2px solid var(--bdr)', paddingBottom: 0 }}>
        {tabs.map(t => (
          <button key={t.key} onClick={() => setActiveTab(t.key)} style={{
            padding: '8px 16px', border: 'none', cursor: 'pointer',
            fontSize: 13, fontWeight: 600, background: 'none',
            borderBottom: activeTab === t.key ? '2px solid var(--nv)' : '2px solid transparent',
            color: activeTab === t.key ? 'var(--nv)' : 'var(--tx3)',
            marginBottom: -2, transition: '.12s',
            display: 'flex', alignItems: 'center', gap: 7,
          }}>
            <i className={`fas ${t.icon}`}></i>{t.label}
          </button>
        ))}
      </div>

      {/* ══ ONGLET 1 — VUE GÉNÉRALE ══ */}
      {activeTab === 'overview' && (
        <>
          <div className="g64" style={{ marginBottom: 18 }}>

            {/* Documents par aéronef */}
            <div className="card">
              <div className="ch">
                <h3><i className="fas fa-chart-bar"></i>Documents par Aéronef</h3>
              </div>
              <div className="cb">
                <div className="chart-wrap">
                  <div className="chart-bars">
                    {byAircraft.map(a => (
                      <div key={a.aircraft} className="cbar b"
                        style={{ height: Math.round((a.count || 0) / maxByAircraft * 150) }}
                        onMouseEnter={e => chartTip.show(e, `${a.aircraft} — ${(a.count || 0).toLocaleString()} docs`)}
                        onMouseMove={chartTip.move}
                        onMouseLeave={chartTip.hide}
                      />
                    ))}
                    {!byAircraft.length && <div style={{ color: 'var(--tx3)', fontSize: 12, margin: 'auto' }}>Aucune donnée</div>}
                  </div>
                  <div className="chart-lbls">
                    {byAircraft.map(a => <span key={a.aircraft}>{a.aircraft}</span>)}
                  </div>
                </div>
              </div>
            </div>

            {/* Agents IA */}
            <div className="card">
              <div className="ch">
                <h3><i className="fas fa-brain" style={{ color: '#7c3aed' }}></i>Agents IA</h3>
              </div>
              <div className="cb">
                <Bar label="Texte extractible (PDF natif + OCR ≥ 60%)" value={kpis?.text_extractible_pct || 0} max={100} color="var(--acc)" suffix="%" note="% docs avec texte exploitable — PDFs natifs + scans de qualité suffisante" />
                <Bar label="NER — Extraction d'entités aéronautiques" value={nerConf ?? 0}  max={100} color="var(--nv)"  suffix="%" note="% docs avec immatriculation reconnue" />
                <Bar label="Classifier (TF-IDF + SVM)"                value={clsConf ?? 0}  max={100} color="#7c3aed"   suffix="%" note="Confiance moyenne de classification sur 12 classes" />
                <Bar label="Embeddings sémantiques (MiniLM-L6 384d)"  value={embConf ?? 100} max={100} color="var(--warn)" suffix="%" note="% docs avec vecteur stocké dans pgvector" />
                
              </div>
            </div>
          </div>

          <div className="g2">

            {/* Alertes actives */}
            <div className="card">
              <div className="ch">
                <h3><i className="fas fa-exclamation-triangle" style={{ color: 'var(--warn)' }}></i>Alertes Système</h3>
                <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                  <span className="tag a">{activeAlerts} actives</span>
                  <button
                    className="btn btn-out btn-sm"
                    onClick={async () => {
                      const res = await fetch(`http://localhost:8000/api/v1/documents/?needs_review=true&size=500`);
                      const data = await res.json();
                      const docs = data.items || [];
                      const rows = docs.map(d => ({
                        ID: d.id,
                        Fichier: d.filename || '',
                        Avion: d.aircraft_registration || '',
                        Type: d.doc_type || '',
                        Categorie: d.category || '',
                        'Ref.ES': d.es_reference || '',
                        ATA: d.ata_chapter || '',
                        'OCR%': d.ocr_confidence ? Math.round(d.ocr_confidence) : 0,
                        'Classifier%': d.classifier_confidence ? Math.round(d.classifier_confidence * 100) : 0,
                        Corrige: d.manually_corrected ? 'Oui' : 'Non',
                        Date: d.created_at ? d.created_at.slice(0, 10) : '',
                      }));
                      const ws = XLSX.utils.json_to_sheet(rows);
                      const wb = XLSX.utils.book_new();
                      XLSX.utils.book_append_sheet(wb, ws, 'A Réviser');
                      XLSX.writeFile(wb, `a_reviser_NouvelAir_${new Date().toISOString().slice(0,10)}.xlsx`);
                    }}
                  >
                    <i className="fas fa-file-excel"></i> Exporter à réviser
                  </button>
                </div>
              </div>
              <div className="cb" style={{ padding: 12 }}>
                {!alerts?.length ? (
                  <div style={{ padding: 16, textAlign: 'center', color: 'var(--tx3)', fontSize: 13 }}>
                    <i className="fas fa-check-circle" style={{ color: 'var(--acc)' }}></i> Aucune alerte active
                  </div>
                ) : (
                  <>
                    {/* Groupement par type */}
                    {[
                      {
                        type: 'ocr_low_confidence',
                        label: 'OCR faible confiance',
                        icon: 'fa-eye-slash',
                        color: 'var(--warn)',
                        count: alerts.filter(a => a.alert_type === 'ocr_low_confidence').length,
                        sample: alerts.find(a => a.alert_type === 'ocr_low_confidence'),
                      },
                      
                    ].filter(g => g.count > 0).map((g, i) => (
                      <div key={i} className="al w" style={{ marginBottom: 8, alignItems: 'center' }}>
                        <i className={`fas ${g.icon} al-ic`} style={{ color: g.color }} />
                        <div className="al-body" style={{ flex: 1, minWidth: 0 }}>
                          <p style={{ fontWeight: 600, color: g.color }}>{g.label}</p>
                          {g.sample && (
                            <span style={{
                              display: 'block', overflow: 'hidden',
                              textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                              fontSize: 11, color: 'var(--tx3)',
                            }}>
                              ex : {g.sample.title?.replace(/^.*— /, '') || g.sample.message}
                            </span>
                          )}
                        </div>
                        <span className="tag a" style={{ fontSize: 11, flexShrink: 0 }}>
                          {g.count === 5 ? `${activeAlerts > 5 ? activeAlerts : g.count}` : g.count}
                        </span>
                      </div>
                    ))}
                    <div style={{ textAlign: 'center', paddingTop: 8 }}>
                      <a href="/monitoring" style={{ fontSize: 12, color: 'var(--nv)', textDecoration: 'none' }}>
                        <i className="fas fa-arrow-right"></i> Voir toutes les alertes
                      </a>
                    </div>
                  </>
                )}
              </div>
            </div>

            {/* Distribution par type */}
            <div className="card">
              <div className="ch">
                <h3><i className="fas fa-layer-group"></i>Distribution par Type</h3>
                <span className="tag b">{byType.length} types</span>
              </div>
              <div className="cb">
                {byType.map((t, i) => {
                  const pct = Math.round((t.count || 0) / typeTotal * 100);
                  return (
                    <Bar
                      key={t.type}
                      label={t.type || '—'}
                      value={t.count || 0}
                      max={byType[0]?.count || 1}
                      color={typeColors[i % typeColors.length]}
                      note={`${pct}% du corpus · OCR moy: ${t.avg_ocr_confidence ? t.avg_ocr_confidence.toFixed(0) + '%' : 'N/A'}`}
                    />
                  );
                })}
              </div>
            </div>
          </div>
        </>
      )}

      {/* ══ ONGLET 2 — QUALITÉ ARCHIVE ══ */}
      {activeTab === 'quality' && (
        <>
          {/* Jauges */}
          <div className="card" style={{ marginBottom: 18 }}>
            <div className="ch">
              <h3><i className="fas fa-shield-alt" style={{ color: 'var(--acc)' }}></i>Score Qualité Globale</h3>
              <span className="tag g">Temps réel</span>
            </div>
            <div className="cb">
              <div style={{ display: 'flex', justifyContent: 'space-around', flexWrap: 'wrap', gap: 20, padding: '8px 0' }}>
                {[
                  { value: qualityScore, label: 'Score Global',   color: 'var(--nv)',   desc: 'OCR + Classifier + Anomalies' },
                  { value: kpis?.text_extractible_pct || 0, label: 'Texte Extractible', color: 'var(--acc)', desc: 'PDF natif + OCR ≥ 60%' },
                  { value: archiveRate,  label: 'Taux Archivage', color: 'var(--warn)', desc: '% docs traités et sauvegardés'},
                  { value: 100 - (anomalies.sans_avion || 0) / Math.max(totalDocs, 1) * 100, label: 'Docs avec Avion', color: '#0891b2', desc: 'Immatriculation reconnue' },
                  { value: clsConf ?? 0, label: 'Classifier',     color: '#7c3aed',     desc: 'Confiance TF-IDF + SVM'       },
                ].map((g, i) => (
                  <div key={i} style={{ textAlign: 'center' }}>
                    <Gauge value={g.value} label={g.label} color={g.color} size={90} />
                    <div style={{ fontSize: 11, color: 'var(--tx3)', maxWidth: 90, margin: '6px auto 0' }}>{g.desc}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="g2" style={{ marginBottom: 18 }}>

            {/* Distribution OCR */}
            <div className="card">
              <div className="ch">
                <h3><i className="fas fa-chart-pie" style={{ color: 'var(--acc)' }}></i>Distribution Qualité OCR</h3>
              </div>
              <div className="cb">
                <div className="al i" style={{ marginBottom: 14 }}>
                  <i className="fas fa-info-circle al-ic"></i>
                  <div className="al-body">
                    <span>Les PDFs numériques ont un score 0% — le texte est extrait directement par pdfplumber sans Tesseract.</span>
                  </div>
                </div>
                {[
                  { tranche: '90-100%', desc: 'Excellent — scan net ou PDF natif' },
                  { tranche: '75-89%',  desc: 'Bon — archivage fiable' },
                  { tranche: '50-74%',  desc: 'Moyen — retraitement possible' },
                  { tranche: '25-49%',  desc: 'Faible — révision recommandée' },
                  { tranche: '1-24%',   desc: 'Dégradé — retraitement nécessaire' },
                  { tranche: '0%',      desc: 'PDF natif — texte extrait directement' },
                ].map(row => {
                  const count = ocrDist.find(o => o.tranche === row.tranche)?.count || 0;
                  const max   = Math.max(...ocrDist.map(o => o.count || 0), 1);
                  return (
                    <Bar
                      key={row.tranche}
                      label={`${row.tranche} — ${row.desc}`}
                      value={count}
                      max={max}
                      color={ocrColors[row.tranche] || 'var(--tx3)'}
                      note={`${count.toLocaleString()} docs · ${Math.round(count / totalDocs * 100)}%`}
                    />
                  );
                })}
              </div>
            </div>

            {/* Anomalies — seulement les critiques */}
            <div className="card">
              <div className="ch">
                <h3><i className="fas fa-bug" style={{ color: 'var(--danger)' }}></i>Anomalies Documentaires</h3>
              </div>
              <div className="cb">
                <StatRow
                  label="Sans immatriculation"
                  value={anomalies.sans_avion || 0}
                  color={(anomalies.sans_avion || 0) > 0 ? 'var(--warn)' : 'var(--acc)'}
                  sub="Documents dont l'aéronef n'a pas été reconnu par le NER"
                />
                <StatRow
                  label="À réviser (OCR ou classifier faible)"
                  value={needsReview}
                  color={needsReview > 500 ? 'var(--warn)' : 'var(--acc)'}
                  sub="Confiance OCR < 60% ou classifier < 50%"
                  border={false}
                />
              </div>
            </div>
          </div>

          {/* Couverture par avion — SANS colonne Couverture % */}
          <div className="card">
            <div className="ch">
              <h3><i className="fas fa-plane"></i>Couverture Documentaire par Aéronef</h3>
            </div>
            <div className="tbl-wrap">
              <table className="tbl">
                <thead>
                  <tr>
                    <th>Immatriculation</th>
                    <th>MSN</th>
                    <th>Documents</th>
                    <th>Types couverts</th>
                    <th>OCR moyen</th>
                    <th>Corrections humaines</th>
                  </tr>
                </thead>
                <tbody>
                  {coverage.filter(r => r.total_docs > 0).map(r => (
                    <tr key={r.aircraft}>
                      <td><span className="tag b">{r.aircraft}</span></td>
                      <td><span style={{ fontSize: 12, color: 'var(--tx2)' }}>{r.msn || '—'}</span></td>
                      <td><strong>{r.total_docs.toLocaleString()}</strong></td>
                      <td>{r.nb_types} types</td>
                      <td>
                        <span style={{ fontWeight: 600, color: r.avg_ocr >= 75 ? '#059669' : r.avg_ocr >= 50 ? '#d97706' : 'var(--danger)' }}>
                          {r.avg_ocr}%
                        </span>
                      </td>
                      <td>{r.validated}</td>
                    </tr>
                  ))}
                  {!coverage.filter(r => r.total_docs > 0).length && (
                    <tr><td colSpan={6} style={{ textAlign: 'center', color: 'var(--tx3)', padding: 20 }}>Aucune donnée</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {/* ══ ONGLET 3 — RESTITUTION ══ */}
      {activeTab === 'restitution' && (
        <>
          {/* Bannière */}
          <div style={{
            background: 'linear-gradient(135deg, var(--nv) 0%, var(--nv2) 100%)',
            borderRadius: 'var(--rl)', padding: '18px 22px', marginBottom: 18,
            display: 'flex', alignItems: 'center', gap: 18, color: '#fff',
            boxShadow: 'var(--sh2)',
          }}>
            <i className="fas fa-plane-departure" style={{ fontSize: 36, opacity: .8 }}></i>
            <div>
              <div style={{ fontSize: 16, fontWeight: 700, fontFamily: "'Barlow Condensed', sans-serif", letterSpacing: .5 }}>
                Préparation au Dossier de Restitution
              </div>
              <div style={{ fontSize: 13, opacity: .75, marginTop: 4 }}>
                TS-INP ({getMsn('TS-INP')}) · TS-INQ ({getMsn('TS-INQ')}) · ~24 ans de service · Restitution au propriétaire EASA Part-145
              </div>
            </div>
          </div>

         

          {/* Statut par avion */}
          <div className="g3" style={{ marginBottom: 18 }}>
            {byAircraft.filter(a => ['TS-INP','TS-INQ','TS-INO'].includes(a.aircraft)).map(a => {
              const aircraftChecks = (checks || []).filter(c => c.aircraft_registration === a.aircraft);
              return (
                <div className="card" key={a.aircraft}>
                  <div className="ch">
                    <h3><i className="fas fa-plane"></i>{a.aircraft}</h3>
                    <span className="tag b">{a.msn ? `MSN ${a.msn}` : '—'}</span>
                  </div>
                  <div className="cb">
                    <StatRow label="Documents archivés" value={(a.count || 0).toLocaleString()} />
                    <StatRow label="Checks confirmés" value={aircraftChecks.length} />
                    <StatRow label="Types documentaires" value={coverage.find(r => r.aircraft === a.aircraft)?.nb_types || 0} border={false} />
                  </div>
                </div>
              );
            })}
          </div>

          {/* Checks confirmés — accordéon par type */}
          <div className="card" style={{ marginBottom: 18 }}>
            <div className="ch">
              <h3><i className="fas fa-clipboard-check"></i>Checks Confirmés</h3>
              <span className="tag g">{(checks || []).filter(c => ['TS-INP','TS-INQ','TS-INO'].includes(c.aircraft_registration)).length} checks</span>
            </div>
            <div className="cb" style={{ padding: 0 }}>
              {['Check A', 'Check C', 'Check D'].map(type => {
                const group = (checks || []).filter(c =>
                  ['TS-INP','TS-INQ','TS-INO'].includes(c.aircraft_registration) &&
                  c.check_type === type
                );
                if (!group.length) return null;
                return (
                  <CheckGroup key={type} type={type} checks={group} />
                );
              })}
            </div>
          </div>

          {/* Progression restitution */}
          <div className="card">
            <div className="ch">
              <h3><i className="fas fa-tasks" style={{ color: 'var(--acc)' }}></i>Progression Restitution</h3>
            </div>
            <div className="cb">
              {[
                { label: 'Documents archivés',        value: archived,                ok: archived > 0,               sub: `${archiveRate}% du corpus` },
                { label: 'Docs sans immatriculation', value: anomalies.sans_avion||0, ok: (anomalies.sans_avion||0)===0, sub: 'Tous rattachés à un aéronef' },
                { label: 'Documents à réviser',       value: needsReview,             ok: needsReview===0,             sub: 'Confiance OCR ou classifier faible' },
              ].map((item, i) => (
                <div key={i} className={`al ${item.ok ? 's' : 'w'}`} style={{ marginBottom: 8 }}>
                  <i className={`fas ${item.ok ? 'fa-check-circle' : 'fa-exclamation-triangle'} al-ic`}></i>
                  <div className="al-body" style={{ flex: 1 }}>
                    <p>{item.label}</p>
                    <span>{item.sub}</span>
                  </div>
                  <span className={`tag ${item.ok ? 'g' : 'a'}`} style={{ fontSize: 11 }}>
                    {typeof item.value === 'number' ? item.value.toLocaleString() : item.value}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </>
      )}

    </div>
  );
}