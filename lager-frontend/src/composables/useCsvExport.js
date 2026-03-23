/**
 * Reusable CSV export composable.
 * Usage: const { exportCsv } = useCsvExport()
 *        exportCsv(headers, rows, 'filename.csv')
 */
export function useCsvExport() {
  function exportCsv(headers, rows, filename = 'export.csv') {
    const lines = [
      headers.join(';'),
      ...rows.map((row) =>
        headers.map((h) => {
          const val = row[h] ?? ''
          // Escape semicolons and newlines
          return typeof val === 'string' && (val.includes(';') || val.includes('\n'))
            ? `"${val.replace(/"/g, '""')}"`
            : val
        }).join(';')
      ),
    ]
    const blob = new Blob(['\uFEFF' + lines.join('\r\n')], {
      type: 'text/csv;charset=utf-8;',
    })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    link.click()
    URL.revokeObjectURL(url)
  }

  return { exportCsv }
}
