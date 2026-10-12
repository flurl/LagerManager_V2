import assert from 'node:assert/strict'
import test, { describe } from 'node:test'

import {
  canCreateKind,
  canEditInTextForm,
  defaultMerge,
  defaultTextKind,
  deliveryChoices,
  deliveryLabel,
  hasDeliveryChoice,
  isIrreversible,
  textKinds,
} from '../src/utils/attachmentKinds.js'

// Shaped like GET /api/document-attachment-kinds/, in registry order.
const supplement = {
  kind: 'supplement', label: 'Ergänzung', requires_file: false,
  delivery_modes: ['merge', 'separate'],
  default_delivery: 'merge', editable: true, deletable: true,
  requires_issued_document: false,
}
const correction = {
  kind: 'correction', label: 'Berichtigungsnote', requires_file: false,
  delivery_modes: ['merge'],
  default_delivery: 'merge', editable: false, deletable: false,
  requires_issued_document: true,
}
const file = {
  kind: 'file', label: 'Datei', requires_file: true,
  delivery_modes: ['separate'],
  default_delivery: 'separate', editable: true, deletable: true,
  requires_issued_document: false,
}
const payments = {
  kind: 'payments', label: 'Zahlungsübersicht', requires_file: false,
  delivery_modes: ['merge'],
  default_delivery: 'merge', editable: false, deletable: false,
  requires_issued_document: true, creatable: false,
}
const kinds = [supplement, correction, payments, file]

describe('textKinds', () => {
  // The text form offers Ergänzung and Berichtigungsnote but not Datei (an upload),
  // in the backend registry's order, which is also the order of the kind toggle.
  test('keeps everything but uploads, in registry order', () => {
    assert.deepEqual(textKinds(kinds).map((k) => k.kind), ['supplement', 'correction'])
  })

  // The Zahlungsübersicht is created by the backend from the invoice's payments,
  // so the form must not offer it — the backend would refuse it anyway.
  test('leaves out kinds that users may not create', () => {
    assert.ok(!textKinds(kinds).some((k) => k.kind === 'payments'))
  })

  // Before the kinds request has answered the list is undefined: that must give an
  // empty form, not a crash.
  test('copes with a missing list', () => {
    assert.deepEqual(textKinds(undefined), [])
  })
})

describe('canCreateKind', () => {
  // A Berichtigungsnote needs an issued document: refused on a draft, allowed once
  // issued or later (e.g. paid). Mirrors the backend's 400 for drafts.
  test('issued-only kinds are refused on drafts', () => {
    assert.equal(canCreateKind(correction, 'draft'), false)
    assert.equal(canCreateKind(correction, 'issued'), true)
    assert.equal(canCreateKind(correction, 'paid'), true)
  })

  // Kinds without the issued-only rule (Ergänzung) are creatable on drafts too.
  test('other kinds are allowed everywhere', () => {
    assert.equal(canCreateKind(supplement, 'draft'), true)
    assert.equal(canCreateKind(supplement, 'issued'), true)
  })

  // Only an actual 'draft' blocks the kind; an empty or unknown status does not.
  // The backend still has the final word.
  test('an unknown document status is not treated as a draft', () => {
    assert.equal(canCreateKind(correction, ''), true)
  })

  // Without a kind (e.g. not loaded yet) nothing can be created.
  test('no kind, no creation', () => {
    assert.equal(canCreateKind(null, 'issued'), false)
  })
})

describe('defaultTextKind', () => {
  // The form starts on the first allowed text kind — the Ergänzung, on drafts and
  // issued documents alike.
  test('is the first text kind allowed on the document', () => {
    assert.equal(defaultTextKind(kinds, 'issued').kind, 'supplement')
    assert.equal(defaultTextKind(kinds, 'draft').kind, 'supplement')
  })

  // If the first kind isn't allowed here (a note on a draft) the next one is taken,
  // so the form never opens on a disabled kind.
  test('skips kinds the document does not allow', () => {
    assert.equal(defaultTextKind([correction, supplement], 'draft').kind, 'supplement')
  })

  // With no creatable text kind the form has no kind at all (null).
  test('is null when nothing may be created', () => {
    assert.equal(defaultTextKind([correction], 'draft'), null)
    assert.equal(defaultTextKind([], 'issued'), null)
  })
})

describe('isIrreversible', () => {
  // Either restriction alone makes creating the kind irreversible — which is what
  // triggers the warning and the confirmation prompt.
  test('a kind that cannot be edited or deleted is irreversible', () => {
    assert.equal(isIrreversible(correction), true)
    assert.equal(isIrreversible({ ...supplement, editable: false }), true)
    assert.equal(isIrreversible({ ...supplement, deletable: false }), true)
  })

  // An editable, deletable kind (or no kind) needs no warning or confirmation.
  test('an ordinary kind is not', () => {
    assert.equal(isIrreversible(supplement), false)
    assert.equal(isIrreversible(null), false)
  })
})

describe('defaultMerge', () => {
  // The merge switch starts where the kind's default_delivery says: on for a merge
  // default, off for a separate one.
  test('follows the kind default_delivery', () => {
    assert.equal(defaultMerge(supplement), true)
    assert.equal(defaultMerge(file), false)
    assert.equal(defaultMerge({ ...supplement, default_delivery: 'separate' }), false)
  })

  // No kind, no merge.
  test('is off without a kind', () => {
    assert.equal(defaultMerge(null), false)
  })
})

describe('canEditInTextForm', () => {
  // An existing Ergänzung gets the pencil and reopens in the text form.
  test('editable text kinds can be reopened', () => {
    assert.equal(canEditInTextForm({ kind: 'supplement', editable: true }, kinds), true)
  })

  // A Berichtigungsnote is not editable, so it gets no pencil.
  test('immutable kinds cannot', () => {
    assert.equal(canEditInTextForm({ kind: 'correction', editable: false }, kinds), false)
  })

  // A Datei is editable in principle but has no text form, so no pencil either.
  test('uploads are not edited through the text form', () => {
    assert.equal(canEditInTextForm({ kind: 'file', editable: true }, kinds), false)
  })

  // A kind the registry doesn't know (e.g. since removed) has no form to reopen.
  test('an unknown kind cannot be edited', () => {
    assert.equal(canEditInTextForm({ kind: 'mystery', editable: true }, kinds), false)
  })
})

describe('hasDeliveryChoice', () => {
  // Only the Ergänzung (merge or separate) gets a delivery switch: the note always
  // merges and the Datei is always separate.
  test('only a kind with several modes offers a choice', () => {
    assert.equal(hasDeliveryChoice(supplement), true)
    assert.equal(hasDeliveryChoice(correction), false)
    assert.equal(hasDeliveryChoice(file), false)
  })

  // The same check drives the table's delivery select, from each row's own
  // delivery_modes.
  test('works on an attachment row too', () => {
    assert.equal(hasDeliveryChoice({ id: 1, delivery_modes: ['merge'] }), false)
    assert.equal(hasDeliveryChoice({ id: 2, delivery_modes: ['merge', 'separate'] }), true)
  })

  // Missing data means no choice rather than an error.
  test('no modes, no choice', () => {
    assert.equal(hasDeliveryChoice({}), false)
    assert.equal(hasDeliveryChoice(null), false)
  })
})

describe('deliveryChoices', () => {
  // The select lists only the modes the kind allows, with display labels — a note
  // gets 'merge' alone, so 'separate' cannot even be picked.
  test('offers exactly the modes the kind allows, labelled', () => {
    assert.deepEqual(deliveryChoices(supplement), [
      { value: 'merge', title: 'Im Dokument-PDF' },
      { value: 'separate', title: 'Eigene Datei' },
    ])
    assert.deepEqual(deliveryChoices(correction), [{ value: 'merge', title: 'Im Dokument-PDF' }])
    assert.deepEqual(deliveryChoices(null), [])
  })
})

describe('deliveryLabel', () => {
  // Known modes get their German label; an unknown one shows as-is and a missing one
  // as '' rather than "undefined".
  test('names both modes and falls back to the raw value', () => {
    assert.equal(deliveryLabel('merge'), 'Im Dokument-PDF')
    assert.equal(deliveryLabel('separate'), 'Eigene Datei')
    assert.equal(deliveryLabel('carrier-pigeon'), 'carrier-pigeon')
    assert.equal(deliveryLabel(undefined), '')
  })
})
