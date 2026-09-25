// Decisions the attachment dialog makes about attachment kinds.
//
// Every rule comes from the kind metadata the backend registry publishes at
// /api/document-attachment-kinds/, so a new kind shows up in the dialog with
// the right behaviour without a change here.

/** Kinds created through the text form, i.e. everything that is not an upload. */
export function textKinds(kinds) {
  return (kinds || []).filter((k) => !k.requires_file)
}

/** Whether a kind may be created on a document with the given status. */
export function canCreateKind(kind, docStatus) {
  if (!kind) return false
  return !(kind.requires_issued_document && docStatus === 'draft')
}

/** The kind the text form starts with: the first one allowed on this document. */
export function defaultTextKind(kinds, docStatus) {
  return textKinds(kinds).find((k) => canCreateKind(k, docStatus)) ?? null
}

/** Whether creating an attachment of this kind can never be taken back. */
export function isIrreversible(kind) {
  return !!kind && (!kind.editable || !kind.deletable)
}

const DELIVERY_LABELS = {
  merge: 'Im Dokument-PDF',
  separate: 'Eigene Datei',
}

/** Display name of a delivery mode. */
export function deliveryLabel(mode) {
  return DELIVERY_LABELS[mode] ?? mode ?? ''
}

/**
 * Whether the user picks the delivery mode. Works on a kind from the registry
 * and on an attachment row alike, since both carry `delivery_modes`. A single
 * mode is fixed: a Datei never merges, a Berichtigungsnote always does.
 */
export function hasDeliveryChoice(kindOrAttachment) {
  return (kindOrAttachment?.delivery_modes?.length ?? 0) > 1
}

/** The modes on offer, shaped for a v-select. */
export function deliveryChoices(kindOrAttachment) {
  return (kindOrAttachment?.delivery_modes ?? []).map((mode) => ({
    value: mode,
    title: deliveryLabel(mode),
  }))
}

/** Starting position of the "append to the document PDF" switch for a kind. */
export function defaultMerge(kind) {
  return kind?.default_delivery === 'merge'
}

/** Whether an existing attachment can be reopened in the text form. */
export function canEditInTextForm(item, kinds) {
  if (!item?.editable) return false
  const kind = (kinds || []).find((k) => k.kind === item.kind)
  return !!kind && !kind.requires_file
}
