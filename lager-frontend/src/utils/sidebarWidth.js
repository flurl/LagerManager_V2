export const SIDEBAR_MIN_WIDTH = 320
export const SIDEBAR_DEFAULT_WIDTH = 520
// Share of the viewport the sidebar may take at most, so the main content stays usable.
export const SIDEBAR_MAX_SHARE = 0.8

/** Clamp a requested sidebar width to [SIDEBAR_MIN_WIDTH, SIDEBAR_MAX_SHARE × viewport]. */
export function clampSidebarWidth(width, viewportWidth) {
  const max = Math.max(SIDEBAR_MIN_WIDTH, Math.floor(viewportWidth * SIDEBAR_MAX_SHARE))
  const value = Number.isFinite(width) ? width : SIDEBAR_DEFAULT_WIDTH
  return Math.round(Math.min(max, Math.max(SIDEBAR_MIN_WIDTH, value)))
}
