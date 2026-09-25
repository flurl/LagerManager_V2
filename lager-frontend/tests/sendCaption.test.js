import assert from 'node:assert/strict'
import test, { describe } from 'node:test'

import { attachmentCaption } from '../src/utils/sendCaption.js'

describe('attachmentCaption', () => {
  // With nothing selected only the document goes out — no mention of
  // attachments at all.
  test('the bare document', () => {
    assert.equal(attachmentCaption(0, 0), 'Das Dokument wird als PDF-Anhang beigefügt.')
  })

  // One embedded attachment uses the singular ("1 Anhang wird …").
  test('one embedded attachment', () => {
    assert.equal(
      attachmentCaption(1, 0),
      'Das Dokument wird als PDF-Anhang beigefügt – 1 Anhang wird als Seiten eingefügt.',
    )
  })

  // Several of both kinds: both clauses, plural forms, each sentence closed.
  test('embedded attachments and separate files', () => {
    assert.equal(
      attachmentCaption(2, 3),
      'Das Dokument wird als PDF-Anhang beigefügt – 2 Anhänge werden als Seiten '
        + 'eingefügt. 3 zusätzliche Dateien werden angehängt.',
    )
  })

  // Only separate files: the embedding clause is left out rather than
  // reading "0 Anhänge werden eingefügt".
  test('only separate files', () => {
    assert.equal(
      attachmentCaption(0, 2),
      'Das Dokument wird als PDF-Anhang beigefügt. 2 zusätzliche Dateien werden angehängt.',
    )
  })

  // One separate file uses the singular ("1 zusätzliche Datei wird …").
  test('a single separate file', () => {
    assert.equal(
      attachmentCaption(1, 1),
      'Das Dokument wird als PDF-Anhang beigefügt – 1 Anhang wird als Seiten eingefügt. '
        + '1 zusätzliche Datei wird angehängt.',
    )
  })

  // Regression: the old caption labelled every embedded attachment an
  // "Ergänzung", so an embedded Berichtigungsnote was miscounted as one.
  // The caption must not name a kind at all.
  test('never names an attachment kind', () => {
    for (const [merged, separate] of [[1, 0], [2, 1], [0, 3]]) {
      const text = attachmentCaption(merged, separate)
      assert.doesNotMatch(text, /Ergänzung|Berichtigung/)
    }
  })
})
