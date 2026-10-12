// The line in the send dialog that says what goes out with the document.
//
// It counts attachments, not pages: an embedded attachment may span several
// pages, and knowing how many would mean rendering each one when the dialog
// opens. It deliberately never names a kind, since embedded attachments can be
// Ergänzungen as well as Berichtigungsnoten.

/**
 * Caption for `mergedCount` attachments embedded into the document PDF and
 * `separateCount` sent as files of their own. A clause is left out when its
 * count is zero.
 */
export function attachmentCaption(mergedCount, separateCount) {
  let text = 'Das Dokument wird als PDF-Anhang beigefügt'
  if (mergedCount > 0) {
    text += mergedCount === 1
      ? ' – 1 Anhang wird als Seiten eingefügt'
      : ` – ${mergedCount} Anhänge werden als Seiten eingefügt`
  }
  text += '.'
  if (separateCount > 0) {
    text += separateCount === 1
      ? ' 1 zusätzliche Datei wird angehängt.'
      : ` ${separateCount} zusätzliche Dateien werden angehängt.`
  }
  return text
}
