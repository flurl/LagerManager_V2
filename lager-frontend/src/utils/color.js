/**
 * Parses a CSS hex color string into its RGB components.
 * Returns null if the input is not a valid 6-digit hex color.
 * @param {string} hex
 * @returns {{ r: number, g: number, b: number } | null}
 */
export function hexToRgb(hex) {
  const clean = hex.replace('#', '')
  const r = parseInt(clean.slice(0, 2), 16)
  const g = parseInt(clean.slice(2, 4), 16)
  const b = parseInt(clean.slice(4, 6), 16)
  return isNaN(r) || isNaN(g) || isNaN(b) ? null : { r, g, b }
}

/**
 * Converts a hex color to an rgba() CSS string.
 * Falls back to transparent if the hex is invalid.
 * @param {string} hex
 * @param {number} alpha
 * @returns {string}
 */
export function hexToRgba(hex, alpha) {
  const rgb = hexToRgb(hex)
  if (!rgb) return `rgba(0, 0, 0, ${alpha})`
  return `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, ${alpha})`
}
