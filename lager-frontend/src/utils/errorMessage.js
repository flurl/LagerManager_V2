// Extracts a human-readable message from an Axios/DRF error.
// Handles plain strings, `{ detail: "..." }`, field-error dicts
// (`{ field: ["msg"] }`) and nested list-serializer errors
// (`[{}, { field: ["msg"] }]`) as returned for bulk line payloads.
function flatten(data) {
  if (data == null) return ''
  if (typeof data === 'string') return data
  if (Array.isArray(data)) {
    return data.map(flatten).filter(Boolean).join(' | ')
  }
  if (typeof data === 'object') {
    if (typeof data.detail === 'string') return data.detail
    return Object.entries(data)
      .map(([key, val]) => {
        const inner = flatten(val)
        return inner ? `${key}: ${inner}` : ''
      })
      .filter(Boolean)
      .join(' | ')
  }
  return String(data)
}

export function extractErrorMessage(err, fallback = 'Unbekannter Fehler') {
  const data = err?.response?.data
  const fromData = data != null ? flatten(data) : ''
  return fromData || err?.message || fallback
}
