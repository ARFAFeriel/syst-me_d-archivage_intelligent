// ClassificationPanel.jsx
const barColor = (v) => {
  if (v >= 0.8) return '#639922'
  if (v >= 0.5) return '#BA7517'
  return '#E24B4A'
}

const docTypeBadge = {
  CRS:  { bg: '#E6F1FB', color: '#0C447C' },
  AD:   { bg: '#FCEBEB', color: '#791F1F' },
  SB:   { bg: '#EAF3DE', color: '#27500A' },
  AMM:  { bg: '#EEEDFE', color: '#3C3489' },
  DEFAULT: { bg: '#F1EFE8', color: '#444441' },
}

function Badge({ type, label }) {
  const s = docTypeBadge[type] || docTypeBadge.DEFAULT
  return (
    <span style={{
      background: s.bg, color: s.color,
      fontSize: 12, fontWeight: 500,
      padding: '3px 10px', borderRadius: 99
    }}>
      {label || type}
    </span>
  )
}

function ConfBar({ value }) {
  const pct = Math.round(value * 100)
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <div style={{
        height: 6, width: 80, borderRadius: 99,
        background: '#e5e5e5', overflow: 'hidden'
      }}>
        <div style={{
          height: '100%', width: `${pct}%`,
          background: barColor(value), borderRadius: 99
        }} />
      </div>
      <span style={{ fontSize: 13, fontWeight: 500, minWidth: 32 }}>
        {pct}%
      </span>
    </div>
  )
}

function Row({ label, children }) {
  return (
    <div style={{
      display: 'flex', justifyContent: 'space-between',
      alignItems: 'center', padding: '8px 0',
      borderBottom: '0.5px solid var(--color-border-tertiary)',
      fontSize: 13
    }}>
      <span style={{ color: 'var(--color-text-secondary)', minWidth: 140 }}>
        {label}
      </span>
      {children}
    </div>
  )
}

export default function ClassificationPanel({ doc }) {
  if (!doc) return null

  return (
    <div style={{ padding: 16 }}>

      {/* En-tête */}
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 14 }}>
        <p style={{ fontWeight: 500, fontSize: 14 }}>{doc.filename}</p>
        <Badge type={doc.doc_type} />
      </div>

      {/* Résultats de classification */}
      <p style={{ fontSize: 11, color: 'var(--color-text-tertiary)',
                  textTransform: 'uppercase', letterSpacing: '0.06em',
                  marginBottom: 8 }}>
        Résultats de classification
      </p>
      <div style={{ background: 'var(--color-background-secondary)',
                    borderRadius: 8, padding: 12, marginBottom: 14 }}>
        <Row label="Type détecté">
          <Badge type={doc.doc_type} />
        </Row>
        <Row label="Confiance classifieur">
          <ConfBar value={doc.class_confidence} />
        </Row>
        <Row label="Confiance OCR">
          <ConfBar value={doc.ocr_confidence} />
        </Row>
        <Row label="Catégorie">
          <span style={{ fontWeight: 500 }}>{doc.category}</span>
        </Row>
        <Row label="Chapitre ATA">
          <span style={{ fontWeight: 500 }}>{doc.ata_chapter}</span>
        </Row>
      </div>

      {/* Métadonnées */}
      <p style={{ fontSize: 11, color: 'var(--color-text-tertiary)',
                  textTransform: 'uppercase', letterSpacing: '0.06em',
                  marginBottom: 8 }}>
        Métadonnées
      </p>
      <div style={{ background: 'var(--color-background-secondary)',
                    borderRadius: 8, padding: 12 }}>
        <Row label="Avion">
          <span style={{ fontWeight: 500 }}>
            {doc.aircraft_registration}
            <span style={{ fontWeight: 400, color: 'var(--color-text-secondary)',
                           marginLeft: 6 }}>
              MSN {doc.msn}
            </span>
          </span>
        </Row>
        <Row label="Référence ES">
          <span style={{ fontWeight: 500 }}>{doc.es_reference}</span>
        </Row>
        <Row label="Critique">
          <Badge type={doc.is_critical ? 'AD' : 'SB'}
                 label={doc.is_critical ? 'Oui' : 'Non'} />
        </Row>
        <Row label="Révision requise">
          <Badge type={doc.needs_review ? 'AMM' : 'SB'}
                 label={doc.needs_review ? 'Oui' : 'Non'} />
        </Row>
      </div>

    </div>
  )
}