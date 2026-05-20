// components/ui/DataTable.jsx
/**
 * Tableau générique réutilisable.
 * Props:
 *   columns: [{ key, label, render? }]
 *   rows: array of objects
 *   loading: bool
 *   emptyMsg: string
 */
export default function DataTable({ columns, rows, loading, emptyMsg = 'Aucune donnée' }) {
  return (
    <div className="tbl-wrap">
      <table className="tbl">
        <thead>
          <tr>
            {columns.map(c => (
              <th key={c.key}>{c.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {loading ? (
            <tr>
              <td colSpan={columns.length} style={{ textAlign: 'center', padding: 32, color: 'var(--tx3)' }}>
                <i className="fas fa-spinner fa-spin" style={{ marginRight: 8 }}></i>Chargement...
              </td>
            </tr>
          ) : !rows?.length ? (
            <tr>
              <td colSpan={columns.length} style={{ textAlign: 'center', padding: 32, color: 'var(--tx3)' }}>
                {emptyMsg}
              </td>
            </tr>
          ) : (
            rows.map((row, i) => (
              <tr key={row.id ?? i}>
                {columns.map(c => (
                  <td key={c.key}>
                    {c.render ? c.render(row[c.key], row) : (row[c.key] ?? '—')}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
