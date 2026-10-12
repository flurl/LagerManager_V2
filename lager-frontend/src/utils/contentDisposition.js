// The filename a server suggests in its Content-Disposition header.
//
// Used when saving a PDF that was fetched as a blob: the blob itself has no
// name, but the backend's document and attachment endpoints put one in the
// header (e.g. `inline; filename="rechnung_RE2601-001.pdf"`).

/** The suggested filename, or '' when the header carries none. */
export function filenameFromContentDisposition(header) {
  const match = /filename="([^"]+)"|filename=([^;\s]+)/i.exec(header || '')
  return match ? (match[1] ?? match[2]) : ''
}
