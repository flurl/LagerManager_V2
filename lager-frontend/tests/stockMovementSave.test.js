import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { saveStockMovement } from '../src/utils/stockMovementSave.js'

// Records every request; POST /stock-movements/ creates movement 42.
function fakeApi() {
  const calls = []
  const record = (method) => async (url, body) => {
    calls.push([method, url, body])
    if (method === 'post' && url === '/stock-movements/') return { data: { id: 42 } }
    if (method === 'post') return { data: body }
    return { data: {} }
  }
  return { calls, post: record('post'), put: record('put'), patch: record('patch') }
}

const LINE = { article: 1, quantity: 2, unit_price: 3, tax_rate: 4, id: 9 }

describe('saveStockMovement', () => {
  // Regression: the dialog marked the movement as no longer new before linking,
  // so attachments uploaded to a new movement were never attached to it.
  it('links pending attachments to a newly created movement', async () => {
    const api = fakeApi()
    await saveStockMovement(api, {
      id: null, payload: {}, lines: [], pendingAttachments: [{ id: 7 }, { id: 8 }],
    })
    const patches = api.calls.filter(([m]) => m === 'patch')
    assert.deepEqual(patches, [
      ['patch', '/attachments/7/', { stock_movement: 42 }],
      ['patch', '/attachments/8/', { stock_movement: 42 }],
    ])
  })

  // A new movement is POSTed and reported at once, so a failing detail save
  // followed by a retry updates it instead of creating a second movement.
  it('creates a new movement and reports its id before saving the lines', async () => {
    const api = fakeApi()
    let createdId = null
    const result = await saveStockMovement(api, {
      id: null, payload: { comment: 'x' }, lines: [LINE], pendingAttachments: [],
      onCreated: (id) => { createdId = id },
    })
    assert.equal(createdId, 42)
    assert.equal(result.id, 42)
    assert.deepEqual(api.calls[0], ['post', '/stock-movements/', { comment: 'x' }])
  })

  // Existing movements are updated in place; only the line fields the backend
  // accepts are sent, in entry order.
  it('updates an existing movement and replaces its lines', async () => {
    const api = fakeApi()
    const result = await saveStockMovement(api, {
      id: 5, payload: { comment: 'y' }, lines: [LINE], pendingAttachments: [],
    })
    assert.deepEqual(api.calls, [
      ['put', '/stock-movements/5/', { comment: 'y' }],
      ['post', '/stock-movements/5/details/',
        [{ article: 1, quantity: 2, unit_price: 3, tax_rate: 4 }]],
    ])
    assert.equal(result.id, 5)
  })
})
