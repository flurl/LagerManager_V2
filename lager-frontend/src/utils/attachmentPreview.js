// What "preview" means for one document attachment.
//
// An attachment that is merged into the document PDF has no meaningful preview
// of its own — what the recipient opens is the whole document with the extra
// pages in it, so that is what we show. Everything else is previewed on its
// own: rendered kinds through the API, uploaded files straight from /media.
// Anything a browser cannot display is offered as a download instead.

// Types a browser renders inside an <iframe> without a plugin.
const PREVIEWABLE_MIME = new Set([
  'application/pdf',
  'image/png',
  'image/jpeg',
  'image/gif',
  'image/webp',
  'image/bmp',
  'image/svg+xml',
])

export function isPreviewableMime(mime) {
  return PREVIEWABLE_MIME.has(String(mime || '').toLowerCase().trim())
}

/**
 * Path of the document PDF as it would be sent with `ids` selected.
 * Attachments that do not merge simply leave it unchanged.
 */
export function documentPreviewPath(apiPath, ids = []) {
  const params = new URLSearchParams()
  for (const id of ids) params.append('attachment_ids', String(id))
  const query = params.toString()
  return query ? `${apiPath}/send-pdf/?${query}` : `${apiPath}/send-pdf/`
}

/**
 * Decide how to preview one attachment.
 *
 * Returns one of:
 *   { mode: 'document', ids }  — the whole document PDF, this attachment included
 *   { mode: 'api', path }      — a PDF the API renders for this attachment
 *   { mode: 'url', url }       — an uploaded file the browser can display
 *   { mode: 'download', url }  — not previewable, offer the file for download
 *   null                       — nothing to show at all
 */
export function attachmentPreviewTarget(item, { selectedIds = [], apiPath = '' } = {}) {
  if (!item) return null

  if (item.effective_delivery === 'merge') {
    // Preview it as part of the document even when it is not ticked yet.
    return { mode: 'document', ids: [...new Set([...selectedIds, item.id])] }
  }
  if (item.renderable) {
    return { mode: 'api', path: `${apiPath}/attachments/${item.id}/pdf/` }
  }
  if (item.file_url) {
    return {
      mode: isPreviewableMime(item.mime_type) ? 'url' : 'download',
      url: item.file_url,
    }
  }
  return null
}
