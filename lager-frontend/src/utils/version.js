/**
 * Compares the commit hash baked into the loaded frontend bundle with the one
 * the backend reports for its current HEAD.
 *
 * Both sides come from the same git repository, but they may abbreviate the
 * hash to different lengths (git widens the short hash as a repo grows), so a
 * prefix match counts as equal. Unknown/empty hashes never count as a mismatch
 * — that only means one side could not read git (e.g. no repo in the
 * container), which must not trigger a reload nag.
 *
 * @param {string | null | undefined} localHash hash built into this bundle
 * @param {string | null | undefined} remoteHash hash reported by /api/version/
 * @returns {boolean} true if the two hashes are known and differ
 */
export function isVersionMismatch(localHash, remoteHash) {
  const local = normalize(localHash)
  const remote = normalize(remoteHash)
  if (!local || !remote) return false
  return !local.startsWith(remote) && !remote.startsWith(local)
}

/**
 * @param {string | null | undefined} hash
 * @returns {string} the usable hash, or '' if it carries no information
 */
function normalize(hash) {
  const value = String(hash ?? '').trim().toLowerCase()
  if (!value || value === 'unknown') return ''
  return value
}
