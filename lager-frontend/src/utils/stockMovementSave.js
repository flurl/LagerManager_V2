/**
 * Save a stock movement with its detail lines and pending attachments.
 *
 * Attachments uploaded while a movement is still new have no movement yet; they
 * are linked here once the movement exists.  Linking is keyed on there being
 * pending attachments, not on the movement being new: the movement stops being
 * new the moment it is created, so a check on "new" after creating it never
 * fires — which left every such attachment unlinked.
 *
 * @param {object} api  axios-like client
 * @param {object} args
 * @param {number|null} args.id  movement id, null for a new movement
 * @param {object} args.payload  movement fields to POST/PUT
 * @param {object[]} args.lines  detail lines, in entry order
 * @param {object[]} args.pendingAttachments  attachments still to link
 * @param {(id: number) => void} [args.onCreated]  called as soon as a new
 *   movement exists, so a failure further on doesn't create it a second time
 * @returns {Promise<{ id: number, details: object[] }>}
 */
export async function saveStockMovement(api, { id, payload, lines, pendingAttachments, onCreated }) {
  let movementId = id
  if (movementId) {
    await api.put(`/stock-movements/${movementId}/`, payload)
  } else {
    const res = await api.post('/stock-movements/', payload)
    movementId = res.data.id
    onCreated?.(movementId)
  }

  // Replace all detail lines in one atomic backend request, preserving entry order
  const linesPayload = lines.map((l) => ({
    article: l.article,
    quantity: l.quantity,
    unit_price: l.unit_price,
    tax_rate: l.tax_rate,
  }))
  const detailsRes = await api.post(`/stock-movements/${movementId}/details/`, linesPayload)

  await Promise.all(
    pendingAttachments.map((a) =>
      api.patch(`/attachments/${a.id}/`, { stock_movement: movementId })
    )
  )

  return { id: movementId, details: detailsRes.data }
}
