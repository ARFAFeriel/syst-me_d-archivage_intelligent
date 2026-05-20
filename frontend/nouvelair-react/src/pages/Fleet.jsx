// pages/Fleet.jsx
// Vue Flotte NouvelAir — filtres NEO/CEO, cards avions, arborescence documentaire
// + modal d'édition avion (changement de type NEO/CEO, MSN, bailleur...)
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useApi, apiFetch } from '../hooks/useApi';
import { useToast } from '../contexts/ToastContext';
import TreeView from '../components/ui/TreeView';

// ── Helpers ───────────────────────────────────────────────────────────────────
const TYPE_TAG = {
  NEO: { label: 'A320 NEO', cls: 'tag g', dot: '#059669' },
  CEO: { label: 'A320 CEO', cls: 'tag b', dot: 'var(--nv)' },
};

const ORIGIN_OPTIONS = [
  { value: 'ALL',        label: 'Toutes origines' },
  { value: 'BOCA',       label: 'BOCA (Légal)'    },
  { value: 'AIRBUS_LBT', label: 'Airbus LBT'      },
  { value: 'MRO',        label: 'MRO'             },
];

// ── Modal édition avion ───────────────────────────────────────────────────────
function EditAircraftModal({ aircraft, onClose, onSaved }) {
  const toast = useToast();
  const [form, setForm] = useState({
    aircraft_type: aircraft.aircraft_type || 'CEO',
    msn:           aircraft.msn || '',
    variant:       aircraft.variant || '',
    delivery_date: aircraft.delivery_date || '',
    lessor:        aircraft.lessor || '',
    notes:         aircraft.notes || '',
  });
  const [saving, setSaving] = useState(false);

  const isNeo = form.aircraft_type === 'NEO';

  const save = async () => {
    setSaving(true);
    const r = await apiFetch(`/aircraft/${aircraft.id}`, {
      method: 'PATCH',
      body: JSON.stringify(form),
    });
    setSaving(false);
    if (r) {
      toast(`${aircraft.registration} mis à jour`, 'ok');
      onSaved();
      onClose();
    } else {
      toast('Erreur lors de la mise à jour', 'err');
    }
  };

  return (
    <div
      className="modal-overlay"
      onClick={onClose}
    >
      <div
        className="modal-box"
        style={{ width: 520 }}
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="modal-hd">
          <h3>
            <i className="fas fa-plane-departure"></i>
            Modifier — {aircraft.registration}
          </h3>
          <button className="modal-close" onClick={onClose}>✕</button>
        </div>

        <div style={{ padding: 20 }}>
          {/* Type NEO / CEO */}
          <div className="fgrp">
            <label>Type d'avion</label>
            <div style={{ display: 'flex', gap: 10, marginTop: 4 }}>
              {['CEO', 'NEO'].map(t => (
                <button
                  key={t}
                  onClick={() => setForm(f => ({ ...f, aircraft_type: t }))}
                  style={{
                    flex: 1, padding: '10px 0', borderRadius: 8, fontWeight: 700,
                    fontSize: 14, cursor: 'pointer', transition: '.12s',
                    border: `2px solid ${form.aircraft_type === t
                      ? (t === 'NEO' ? '#059669' : 'var(--nv)')
                      : 'var(--bdr)'}`,
                    background: form.aircraft_type === t
                      ? (t === 'NEO' ? '#d1fae5' : 'var(--sky)')
                      : 'var(--sur)',
                    color: form.aircraft_type === t
                      ? (t === 'NEO' ? '#065f46' : 'var(--nv)')
                      : 'var(--tx3)',
                  }}
                >
                  {t === 'NEO' ? '✈ A320 NEO' : '✈ A320 CEO'}
                </button>
              ))}
            </div>
            <p style={{ fontSize: 11, color: 'var(--tx3)', marginTop: 6 }}>
              {isNeo
                ? 'NEO — arborescence BOCA + Standard List A–H (Airbus LBT)'
                : 'CEO — arborescence Certificats A + Maintenance B + Records C'}
            </p>
          </div>

          {/* MSN */}
          <div className="fgrp">
            <label>MSN (Manufacturing Serial Number)</label>
            <input
              value={form.msn}
              onChange={e => setForm(f => ({ ...f, msn: e.target.value }))}
              placeholder="ex: 12280"
            />
          </div>

          {/* Variant */}
          <div className="fgrp">
            <label>Variante</label>
            <select
              value={form.variant}
              onChange={e => setForm(f => ({ ...f, variant: e.target.value }))}
            >
              <option value="">— Sélectionner —</option>
              <option value="A320-251N">A320-251N (NEO CFM LEAP)</option>
              <option value="A320-271N">A320-271N (NEO PW1100G)</option>
              <option value="A320-200">A320-200 (CEO CFM56)</option>
              <option value="A320-214">A320-214 (CEO CFM56-5B4)</option>
              <option value="A320-232">A320-232 (CEO IAE V2527)</option>
            </select>
          </div>

          {/* Date de livraison — surtout utile pour NEO */}
          <div className="fgrp">
            <label>Date de livraison</label>
            <input
              type="date"
              value={form.delivery_date || ''}
              onChange={e => setForm(f => ({ ...f, delivery_date: e.target.value }))}
            />
          </div>

          {/* Bailleur */}
          <div className="fgrp">
            <label>Bailleur (Lessor)</label>
            <input
              value={form.lessor || ''}
              onChange={e => setForm(f => ({ ...f, lessor: e.target.value }))}
              placeholder="ex: BOC Aviation (BOCA)"
            />
          </div>

          {/* Notes */}
          <div className="fgrp">
            <label>Notes</label>
            <input
              value={form.notes || ''}
              onChange={e => setForm(f => ({ ...f, notes: e.target.value }))}
              placeholder="ex: Restitué — remplacé par MSN 99999"
            />
          </div>

          {/* Avertissement changement de type */}
          {form.aircraft_type !== aircraft.aircraft_type && (
            <div style={{
              background: '#fef3c7', border: '1px solid #fde68a',
              borderRadius: 8, padding: '10px 14px', marginBottom: 14,
              fontSize: 12, color: '#78350f',
            }}>
              <i className="fas fa-exclamation-triangle" style={{ marginRight: 7 }}></i>
              Le type passe de <strong>{aircraft.aircraft_type}</strong> à{' '}
              <strong>{form.aircraft_type}</strong> — l'arborescence documentaire
              dans Vue Flotte sera mise à jour immédiatement.
            </div>
          )}

          {/* Boutons */}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
            <button className="btn btn-out btn-sm" onClick={onClose}>
              Annuler
            </button>
            <button
              className="btn btn-blue btn-sm"
              onClick={save}
              disabled={saving}
            >
              <i className={`fas ${saving ? 'fa-spinner fa-spin' : 'fa-save'}`}></i>
              {saving ? 'Enregistrement...' : 'Enregistrer'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Composant carte avion ─────────────────────────────────────────────────────
function AircraftCard({ aircraft, selected, onClick, onEdit }) {
  const type     = aircraft.aircraft_type || 'CEO';
  const typeInfo = TYPE_TAG[type] || TYPE_TAG.CEO;
  const isNeo    = type === 'NEO';

  return (
    <div
      className="fc"
      onClick={onClick}
      style={{
        outline: selected ? '2.5px solid var(--nv)' : 'none',
        outlineOffset: 2,
        cursor: 'pointer',
      }}
    >
      {/* Header */}
      <div
        className="fc-hd"
        style={{
          background: isNeo
            ? 'linear-gradient(135deg, #065f46 0%, #059669 100%)'
            : 'linear-gradient(135deg, var(--nv) 0%, var(--nv2) 100%)',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <div>
            <div className="fc-reg">{aircraft.registration}</div>
            <div className="fc-mod">
              {aircraft.variant || (isNeo ? 'A320-251N' : 'A320-200')}
            </div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4 }}>
            <span style={{
              background: 'rgba(255,255,255,.2)', color: '#fff',
              fontSize: 9, fontWeight: 700, padding: '2px 7px',
              borderRadius: 10, letterSpacing: 1,
            }}>
              {type}
            </span>
            {/* Bouton éditer */}
            <button
              onClick={e => { e.stopPropagation(); onEdit(); }}
              style={{
                background: 'rgba(255,255,255,.15)', border: 'none',
                color: '#fff', fontSize: 10, padding: '2px 7px',
                borderRadius: 6, cursor: 'pointer',
                display: 'flex', alignItems: 'center', gap: 4,
              }}
              title="Modifier cet avion"
            >
              <i className="fas fa-edit"></i> Modifier
            </button>
          </div>
        </div>
      </div>

      {/* Body */}
      <div className="fc-bd">
        <div className="fsr">
          <span className="fsl">MSN</span>
          <span className="fsv">{aircraft.msn || '—'}</span>
        </div>
        <div className="fsr">
          <span className="fsl">Documents</span>
          <span className="fsv">{(aircraft.doc_count || 0).toLocaleString()}</span>
        </div>
        {aircraft.delivery_date && (
          <div className="fsr">
            <span className="fsl">Livraison</span>
            <span className="fsv" style={{ fontSize: 12 }}>
              {new Date(aircraft.delivery_date).toLocaleDateString('fr-FR', {
                month: 'short', year: 'numeric',
              })}
            </span>
          </div>
        )}
        {aircraft.lessor && (
          <div className="fsr">
            <span className="fsl">Bailleur</span>
            <span className="fsv" style={{ fontSize: 11 }}>
              {aircraft.lessor.replace(' (BOCA)', '')}
            </span>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="fc-ft">
        <span className={typeInfo.cls} style={{ fontSize: 10 }}>
          <i className={`fas ${isNeo ? 'fa-star' : 'fa-plane'}`}></i>
          {typeInfo.label}
        </span>
        {selected && (
          <span className="tag g" style={{ fontSize: 10, marginLeft: 'auto' }}>
            <i className="fas fa-eye"></i> Sélectionné
          </span>
        )}
      </div>
    </div>
  );
}

// ── Page principale ───────────────────────────────────────────────────────────
export default function Fleet() {
  const navigate = useNavigate();
  const toast    = useToast();
  const { data: aircraft, loading, error, refetch } = useApi('/aircraft/');

  const [typeFilter,   setTypeFilter]   = useState('ALL');
  const [originFilter, setOriginFilter] = useState('ALL');
  const [selected,     setSelected]     = useState(null);
  const [editAircraft, setEditAircraft] = useState(null);  // avion en cours d'édition

  const allAircraft = aircraft || [];
  const neoCount    = allAircraft.filter(a => a.aircraft_type === 'NEO').length;
  const ceoCount    = allAircraft.filter(a => a.aircraft_type === 'CEO').length;

  const filtered = allAircraft.filter(a =>
    typeFilter === 'ALL' || a.aircraft_type === typeFilter
  );

  const selectedAircraft = allAircraft.find(a => a.registration === selected);

  const tabs = [
    { key: 'ALL', label: 'Tous', count: allAircraft.length },
    { key: 'NEO', label: 'NEO',  count: neoCount           },
    { key: 'CEO', label: 'CEO',  count: ceoCount           },
  ];

  return (
    <div className="page-enter">
      {/* ── Header ── */}
      <div className="ph">
        <div className="ph-row">
          <div>
            <h2><i className="fas fa-plane"></i>Vue Flotte NouvelAir</h2>
            <p>
              {loading ? 'Chargement...'
                : `${allAircraft.length} aéronef(s) — ${neoCount} NEO actifs · ${ceoCount} CEO historiques`}
            </p>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn btn-out btn-sm" onClick={refetch}>
              <i className="fas fa-sync-alt"></i> Actualiser
            </button>
            <button className="btn btn-blue btn-sm" onClick={() => navigate('/documents')}>
              <i className="fas fa-folder-open"></i> Tous les documents
            </button>
          </div>
        </div>
      </div>

      {/* ── Filtres type ── */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 18, alignItems: 'center', flexWrap: 'wrap' }}>
        {tabs.map(t => (
          <button
            key={t.key}
            onClick={() => setTypeFilter(t.key)}
            style={{
              padding: '6px 14px', borderRadius: 20, fontSize: 12, fontWeight: 600,
              border: `1.5px solid ${typeFilter === t.key ? 'var(--nv)' : 'var(--bdr)'}`,
              background: typeFilter === t.key ? 'var(--sky)' : 'var(--sur)',
              color: typeFilter === t.key ? 'var(--nv)' : 'var(--tx2)',
              cursor: 'pointer', transition: '.12s',
            }}
          >
            {t.label}
            <span style={{
              marginLeft: 6,
              background: typeFilter === t.key ? 'var(--nv)' : 'var(--bdr)',
              color: typeFilter === t.key ? '#fff' : 'var(--tx3)',
              borderRadius: 10, padding: '1px 6px', fontSize: 10,
            }}>
              {t.count}
            </span>
          </button>
        ))}

        {selected && (
          <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 11, color: 'var(--tx3)' }}>Origine :</span>
            {ORIGIN_OPTIONS.map(o => (
              <button
                key={o.value}
                onClick={() => setOriginFilter(o.value)}
                style={{
                  padding: '4px 10px', borderRadius: 20, fontSize: 11, fontWeight: 500,
                  border: `1.5px solid ${originFilter === o.value ? 'var(--nv)' : 'var(--bdr)'}`,
                  background: originFilter === o.value ? 'var(--sky)' : 'var(--sur)',
                  color: originFilter === o.value ? 'var(--nv)' : 'var(--tx2)',
                  cursor: 'pointer', transition: '.12s',
                }}
              >
                {o.label}
              </button>
            ))}
          </div>
        )}
      </div>

      {error && (
        <div style={{ padding: 32, textAlign: 'center', color: 'var(--tx3)' }}>
          <i className="fas fa-exclamation-circle"></i> Backend non disponible
        </div>
      )}
      {loading && (
        <div style={{ padding: 32, textAlign: 'center', color: 'var(--tx3)' }}>
          <i className="fas fa-spinner fa-spin"></i> Chargement de la flotte...
        </div>
      )}

      {/* ── Contenu principal ── */}
      {!loading && !error && (
        <div style={{ display: 'flex', gap: 18, alignItems: 'flex-start' }}>

          {/* Grille cartes */}
          <div style={{
            flex: selected ? '0 0 auto' : '1',
            width: selected ? 320 : 'auto',
            display: selected ? 'flex' : 'grid',
            flexDirection: selected ? 'column' : undefined,
            gridTemplateColumns: selected ? undefined : 'repeat(3, 1fr)',
            gap: 14, transition: '.2s',
            maxHeight: selected ? 'calc(100vh - 200px)' : undefined,
            overflowY: selected ? 'auto' : undefined,
          }}>
            {filtered.map(a => (
              <AircraftCard
                key={a.registration}
                aircraft={a}
                selected={selected === a.registration}
                onClick={() => {
                  setSelected(sel => sel === a.registration ? null : a.registration);
                  setOriginFilter('ALL');
                }}
                onEdit={() => setEditAircraft(a)}
              />
            ))}
            {!filtered.length && (
              <div style={{ gridColumn: '1/-1', padding: 32, textAlign: 'center', color: 'var(--tx3)' }}>
                Aucun aéronef trouvé
              </div>
            )}
          </div>

          {/* Panneau arborescence */}
          {selected && selectedAircraft && (
            <div className="card" style={{ flex: 1, minWidth: 0 }}>
              <div className="ch" style={{ flexWrap: 'wrap', gap: 8 }}>
                <h3>
                  <i className="fas fa-sitemap"></i>
                  Arborescence — <span style={{ color: 'var(--acc)' }}>{selected}</span>
                  <span style={{ marginLeft: 6 }}>MSN {selectedAircraft.msn || '—'}</span>
                </h3>
                <div style={{ display: 'flex', gap: 6 }}>
                  <button
                    className="btn btn-out btn-sm"
                    onClick={() => setEditAircraft(selectedAircraft)}
                  >
                    <i className="fas fa-edit"></i> Modifier avion
                  </button>
                  <button
                    className="btn btn-blue btn-sm"
                    onClick={() => navigate('/documents', { state: { aircraft: selected } })}
                  >
                    <i className="fas fa-folder-open"></i> Documents
                  </button>
                  <button className="btn btn-out btn-sm" onClick={() => setSelected(null)}>
                    <i className="fas fa-times"></i>
                  </button>
                </div>
              </div>

              <div style={{
                display: 'flex', gap: 8, padding: '10px 18px',
                borderBottom: '1px solid var(--bdr)', flexWrap: 'wrap',
              }}>
                <span className={TYPE_TAG[selectedAircraft.aircraft_type || 'CEO'].cls} style={{ fontSize: 11 }}>
                  <i className="fas fa-plane"></i> {selectedAircraft.variant || 'A320-200'}
                </span>
                {selectedAircraft.aircraft_type === 'NEO' && (
                  <>
                    <span className="tag or" style={{ fontSize: 11 }}>
                      <i className="fas fa-briefcase"></i> BOCA
                    </span>
                    <span className="tag c" style={{ fontSize: 11 }}>
                      <i className="fas fa-plane-departure"></i> Airbus LBT
                    </span>
                  </>
                )}
                {selectedAircraft.aircraft_type === 'CEO' && (
                  <span className="tag b" style={{ fontSize: 11 }}>
                    <i className="fas fa-tools"></i> MRO Archives
                  </span>
                )}
                <span style={{ marginLeft: 'auto', fontSize: 11, color: 'var(--tx3)' }}>
                  {(selectedAircraft.doc_count || 0).toLocaleString()} documents
                </span>
              </div>

              <div className="cb" style={{ padding: '12px 14px', maxHeight: 500, overflowY: 'auto' }}>
                <TreeView
                  aircraftType={selectedAircraft.aircraft_type || 'CEO'}
                  originFilter={originFilter}
                />
              </div>

              <div style={{
                padding: '10px 16px', borderTop: '1px solid var(--bdr)',
                display: 'flex', gap: 8, flexWrap: 'wrap',
              }}>
                <button className="btn btn-out btn-xs"
                  onClick={() => navigate('/search', { state: { aircraft: selected } })}>
                  <i className="fas fa-search"></i> Recherche IA
                </button>
                <button className="btn btn-out btn-xs"
                  onClick={() => navigate('/checks', { state: { aircraft: selected } })}>
                  <i className="fas fa-clipboard-check"></i> Checks
                </button>
                {selectedAircraft.aircraft_type === 'NEO' && (
                  <button className="btn btn-out btn-xs" onClick={() => setOriginFilter('BOCA')}>
                    <i className="fas fa-briefcase"></i> BOCA only
                  </button>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Modal édition avion ── */}
      {editAircraft && (
        <EditAircraftModal
          aircraft={editAircraft}
          onClose={() => setEditAircraft(null)}
          onSaved={refetch}
        />
      )}
    </div>
  );
}