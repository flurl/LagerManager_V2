import assert from 'node:assert/strict'
import test, { describe } from 'node:test'

import {
  attachmentPreviewTarget,
  documentPreviewPath,
  isPreviewableMime,
  mergedAttachmentIds,
} from '../src/utils/attachmentPreview.js'

const merged = { id: 1, effective_delivery: 'merge', renderable: true }
const ownPdf = { id: 2, effective_delivery: 'separate', renderable: true }
const uploadedPdf = {
  id: 3, effective_delivery: 'separate', renderable: false,
  mime_type: 'application/pdf', file_url: '/media/a/beleg.pdf',
}
const uploadedSheet = {
  id: 4, effective_delivery: 'separate', renderable: false,
  mime_type: 'application/vnd.ms-excel', file_url: '/media/a/liste.xls',
}

describe('isPreviewableMime', () => {
  test('accepts PDFs and common image types', () => {
    assert.equal(isPreviewableMime('application/pdf'), true)
    assert.equal(isPreviewableMime('image/png'), true)
    assert.equal(isPreviewableMime('IMAGE/JPEG'), true)
  })

  test('rejects everything else, including junk', () => {
    assert.equal(isPreviewableMime('application/vnd.ms-excel'), false)
    assert.equal(isPreviewableMime('text/plain'), false)
    assert.equal(isPreviewableMime(''), false)
    assert.equal(isPreviewableMime(null), false)
    assert.equal(isPreviewableMime(undefined), false)
  })
})

describe('documentPreviewPath', () => {
  test('lists every selected id as a repeated parameter', () => {
    assert.equal(
      documentPreviewPath('/invoices/5', [1, 2]),
      '/invoices/5/send-pdf/?attachment_ids=1&attachment_ids=2',
    )
  })

  test('drops the query string when nothing is selected', () => {
    assert.equal(documentPreviewPath('/invoices/5'), '/invoices/5/send-pdf/')
    assert.equal(documentPreviewPath('/invoices/5', []), '/invoices/5/send-pdf/')
  })
})

describe('attachmentPreviewTarget', () => {
  const opts = { apiPath: '/invoices/5', selectedIds: [2] }

  test('a merged attachment previews as the whole document', () => {
    assert.deepEqual(
      attachmentPreviewTarget(merged, opts),
      { mode: 'document', ids: [2, 1] },
    )
  })

  test('a merged attachment is included even when not ticked', () => {
    const target = attachmentPreviewTarget(merged, { ...opts, selectedIds: [] })
    assert.deepEqual(target.ids, [1])
  })

  test('a selected merged attachment is not listed twice', () => {
    const target = attachmentPreviewTarget(merged, { ...opts, selectedIds: [1, 2] })
    assert.deepEqual(target.ids, [1, 2])
  })

  test('a separately sent rendered attachment previews on its own', () => {
    assert.deepEqual(
      attachmentPreviewTarget(ownPdf, opts),
      { mode: 'api', path: '/invoices/5/attachments/2/pdf/' },
    )
  })

  test('an uploaded PDF previews straight from its URL', () => {
    assert.deepEqual(
      attachmentPreviewTarget(uploadedPdf, opts),
      { mode: 'url', url: '/media/a/beleg.pdf' },
    )
  })

  test('an undisplayable upload is offered as a download', () => {
    assert.deepEqual(
      attachmentPreviewTarget(uploadedSheet, opts),
      { mode: 'download', url: '/media/a/liste.xls' },
    )
  })

  test('returns null when there is nothing to show', () => {
    assert.equal(attachmentPreviewTarget(null, opts), null)
    assert.equal(
      attachmentPreviewTarget(
        { id: 9, effective_delivery: 'separate', renderable: false }, opts),
      null,
    )
  })
})

describe('mergedAttachmentIds', () => {
  // Only merged attachments are picked (10 and 12); the separately sent one (11)
  // never changes the document PDF, so it is left out.
  test('lists every attachment that ends up inside the document PDF', () => {
    const rows = [
      { id: 10, effective_delivery: 'merge' },   // Ergänzung
      { id: 11, effective_delivery: 'separate' },
      { id: 12, effective_delivery: 'merge' },   // Berichtigungsnote
    ]
    assert.deepEqual(mergedAttachmentIds(rows), [10, 12])
  })

  // No attachments, or none loaded yet: no ids, no crash.
  test('copes with nothing', () => {
    assert.deepEqual(mergedAttachmentIds([]), [])
    assert.deepEqual(mergedAttachmentIds(undefined), [])
  })

  // Regression (invoice PG260907-00007): in the attachments dialog, previewing the
  // Berichtigungsnote showed invoice + note (2 pages) while previewing the Ergänzung
  // showed all 3. With every merged id selected, both icons request the same [10, 12].
  test('makes every merged preview show the same whole document', () => {
    const rows = [
      { id: 10, effective_delivery: 'merge' },
      { id: 12, effective_delivery: 'merge' },
    ]
    const selectedIds = mergedAttachmentIds(rows)
    const ids = rows.map(
      (row) => attachmentPreviewTarget(row, { selectedIds, apiPath: '/invoices/27' }).ids,
    )
    assert.deepEqual(ids[0].slice().sort(), [10, 12])
    assert.deepEqual(ids[1].slice().sort(), [10, 12])
  })
})
