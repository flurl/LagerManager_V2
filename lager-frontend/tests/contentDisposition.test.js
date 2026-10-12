import assert from 'node:assert/strict'
import test, { describe } from 'node:test'

import { filenameFromContentDisposition } from '../src/utils/contentDisposition.js'

describe('filenameFromContentDisposition', () => {
  // The shape the document PDF endpoints send (send-pdf is "inline" so the
  // browser shows it): the quoted filename is returned without the quotes.
  test('reads a quoted filename', () => {
    assert.equal(
      filenameFromContentDisposition('inline; filename="rechnung_RE2601-001.pdf"'),
      'rechnung_RE2601-001.pdf',
    )
  })

  // The disposition type does not matter — attachment PDFs use "attachment".
  test('works for attachment dispositions too', () => {
    assert.equal(
      filenameFromContentDisposition('attachment; filename="berichtigungsnote_RE1_2.pdf"'),
      'berichtigungsnote_RE1_2.pdf',
    )
  })

  // Unquoted values are legal HTTP as well and must not be lost.
  test('reads an unquoted filename', () => {
    assert.equal(filenameFromContentDisposition('inline; filename=beleg.pdf'), 'beleg.pdf')
  })

  // No header, or a header without a filename: '' so the caller falls back to
  // its own default name instead of saving a file called "undefined".
  test('returns an empty string when there is no filename', () => {
    assert.equal(filenameFromContentDisposition(undefined), '')
    assert.equal(filenameFromContentDisposition(''), '')
    assert.equal(filenameFromContentDisposition('inline'), '')
  })
})
