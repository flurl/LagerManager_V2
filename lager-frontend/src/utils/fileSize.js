// Human-readable file sizes for attachment lists and the send dialog.
//
// Uses binary steps (1 KB = 1024 B) because that is what the operating system
// shows next to the same file, and the locale's decimal separator so the value
// reads like every other number in the UI.

import { DEFAULT_LOCALE } from './number.js'

const UNITS = ['B', 'KB', 'MB', 'GB', 'TB']
const STEP = 1024

/**
 * Format a byte count, e.g. 1536 → '1,5 KB'.
 *
 * Bytes are shown without decimals; every larger unit with one. Invalid or
 * negative input formats as '0 B' rather than throwing — this only ever
 * decorates a label.
 */
export function formatBytes(bytes, locale = DEFAULT_LOCALE) {
  const value = Number(bytes)
  if (!Number.isFinite(value) || value <= 0) return '0 B'

  let size = value
  let unit = 0
  while (size >= STEP && unit < UNITS.length - 1) {
    size /= STEP
    unit += 1
  }

  const decimals = unit === 0 ? 0 : 1
  const formatted = size.toLocaleString(locale, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
    // '1023 B' reads better than '1 023 B'; grouping only helps once the
    // numbers can actually get large.
    useGrouping: unit > 0,
  })
  return `${formatted} ${UNITS[unit]}`
}

/** Sum the `size_bytes` of a list of attachments. */
export function totalBytes(attachments) {
  return (attachments || []).reduce((sum, a) => sum + (Number(a?.size_bytes) || 0), 0)
}
