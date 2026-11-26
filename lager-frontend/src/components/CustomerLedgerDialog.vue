<template>
  <v-dialog v-model="model" max-width="1200" scrollable>
    <v-card>
      <v-card-title class="d-flex align-center pa-4">
        <v-icon class="mr-2">mdi-book-open-variant</v-icon>
        Kundenkonto
        <template v-if="customerLabel"> — {{ customerLabel }}</template>
        <v-spacer />
        <v-btn
          v-if="!recording"
          size="small"
          variant="tonal"
          prepend-icon="mdi-cash-plus"
          class="mr-2"
          @click="startRecording()"
        >
          Zahlung erfassen
        </v-btn>
        <v-btn icon variant="text" @click="model = false"><v-icon>mdi-close</v-icon></v-btn>
      </v-card-title>

      <v-card-text class="pa-4" style="overflow-y: auto">
        <div v-if="loading" class="text-center py-6">
          <v-progress-circular indeterminate />
        </div>

        <v-alert v-else-if="error" type="error" density="compact">{{ error }}</v-alert>

        <template v-else>
          <v-alert v-if="saveError" type="error" density="compact" class="mb-4" closable
            @click:close="saveError = ''">
            {{ saveError }}
          </v-alert>

          <!-- After a Storno: book the right payment.  A payment for an invoice
               belongs in that invoice's payment dialog, which settles it. -->
          <v-alert v-if="reversedNotice" type="info" variant="tonal" density="compact" class="mb-4"
            closable @click:close="reversedNotice = null">
            <div class="d-flex align-center flex-wrap ga-2">
              <span v-if="reversedNotice.invoiceNumber">
                Zahlung storniert. Die richtige Zahlung im Zahlungsdialog der Rechnung
                <a href="#" @click.prevent="openInvoice(reversedNotice.invoiceNumber)">
                  {{ reversedNotice.invoiceNumber }}</a> erfassen.
              </span>
              <template v-else>
                <span>Zahlung storniert.</span>
                <v-spacer />
                <v-btn size="small" color="info" variant="flat" @click="recordCorrection">
                  Richtige Zahlung erfassen
                </v-btn>
              </template>
            </div>
          </v-alert>

          <!-- Standalone payment: no invoice, so it simply becomes credit. -->
          <v-card v-if="recording" variant="tonal" class="pa-3 mb-4">
            <div class="text-subtitle-2 mb-2">Zahlung ohne Rechnungsbezug</div>
            <v-row dense>
              <v-col cols="12" sm="4">
                <v-text-field v-model="form.payment_date" label="Datum *" type="date" density="compact" />
              </v-col>
              <v-col cols="12" sm="4">
                <NumberInput v-model="form.amount" label="Betrag *" density="compact" />
              </v-col>
              <v-col cols="12" sm="4">
                <v-select v-model="form.method" :items="methods" item-title="title" item-value="value"
                  label="Zahlungsart" density="compact" />
              </v-col>
            </v-row>
            <v-row dense>
              <v-col cols="12">
                <v-text-field v-model="form.note" label="Notiz" density="compact" hide-details />
              </v-col>
            </v-row>
            <div class="text-caption text-medium-emphasis mt-2">
              Der Betrag wird im Haben gebucht und steht als Guthaben zur Verfügung. Über
              „… verrechnen“ im Zahlungsdialog einer Rechnung kann er später zugeordnet werden.
            </div>
            <div class="d-flex justify-end mt-2">
              <v-btn size="small" variant="text" @click="recording = false">Abbrechen</v-btn>
              <v-btn size="small" color="primary" :loading="saving" :disabled="!canSave"
                @click="savePayment">Speichern</v-btn>
            </div>
          </v-card>

          <v-table v-if="entries.length" density="compact" class="zebra-table ledger-table">
            <thead>
              <tr>
                <th class="text-no-wrap">Datum</th>
                <th>Art</th>
                <th style="min-width: 280px">Beschreibung</th>
                <th class="text-right">Soll</th>
                <th class="text-right">Haben</th>
                <th style="width: 1%"></th>
                <th class="text-right saldo-col">Saldo</th>
                <th class="text-disabled">Benutzer</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(e, i) in entries" :key="e.id"
                :class="{ 'current-row': i === entries.length - 1 }">
                <td class="text-no-wrap">{{ fmtDate(e.entry_date) }}</td>
                <td class="text-no-wrap">
                  <v-chip size="x-small" :color="typeColor(e)"
                    :prepend-icon="e.is_reversal ? 'mdi-file-undo' : undefined">
                    {{ typeLabel(e) }}
                  </v-chip>
                </td>
                <td class="text-caption">
                  <a v-if="linkTarget(e)" href="#" @click.prevent="openList(e)">
                    {{ e.description }}
                  </a>
                  <template v-else>{{ e.description }}</template>
                  <span v-if="e.method_display" class="text-medium-emphasis">
                    · {{ e.method_display }}</span>
                  <span v-if="e.note" class="text-medium-emphasis"> · {{ e.note }}</span>
                  <div v-if="e.is_reversed" class="text-deep-orange">storniert</div>
                  <div v-else-if="openLabel(e)" class="text-medium-emphasis">{{ openLabel(e) }}</div>
                </td>
                <td class="text-right text-no-wrap">
                  <template v-if="Number(e.amount) > 0">{{ fmtEuro(e.amount) }}</template>
                </td>
                <td class="text-right text-no-wrap">
                  <template v-if="Number(e.amount) < 0">{{ fmtEuro(-Number(e.amount)) }}</template>
                </td>
                <!-- Next to Haben: the action belongs to the payment amount. -->
                <td class="text-right text-no-wrap">
                  <v-tooltip v-if="e.entry_type === 'payment' && !e.is_reversed" text="Zahlung stornieren">
                    <template #activator="{ props: tip }">
                      <v-icon v-bind="tip" size="small" color="error" @click="startReversal(e)">
                        mdi-cash-remove
                      </v-icon>
                    </template>
                  </v-tooltip>
                </td>
                <td class="text-right text-no-wrap saldo-col" :class="balanceClass(e.running_balance)">
                  {{ fmtEuro(e.running_balance) }}
                  <!-- The last row's Saldo is the account's current balance. -->
                  <div v-if="i === entries.length - 1 && balanceState(e.running_balance)"
                    class="text-caption">
                    {{ balanceState(e.running_balance) }}
                  </div>
                </td>
                <!-- Audit information only: dimmed so it doesn't compete with the amounts. -->
                <td class="text-caption text-no-wrap text-disabled">{{ e.actor || '—' }}</td>
              </tr>
            </tbody>
          </v-table>
          <div v-else class="text-medium-emphasis text-caption">
            Noch keine Kontobewegungen.
          </div>
        </template>
      </v-card-text>

      <v-card-actions class="pa-4">
        <v-spacer />
        <v-btn @click="model = false">Schließen</v-btn>
      </v-card-actions>

      <PaymentReversalDialog v-model="reversalOpen" :payment="reversalPayment" @reversed="onReversed" />
    </v-card>
  </v-dialog>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api'
import NumberInput from './NumberInput.vue'
import PaymentReversalDialog from './PaymentReversalDialog.vue'
import { extractErrorMessage } from '../utils/errorMessage'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  customerId: { type: [Number, String], default: null },
  customerLabel: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue', 'changed'])

const router = useRouter()

const model = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const loading = ref(false)
const error = ref('')
const entries = ref([])

// Credit is never booked as a payment — it is applied from the invoice side.
const methods = [
  { value: 'transfer', title: 'Überweisung' },
  { value: 'cash', title: 'Bar' },
  { value: 'card', title: 'Karte' },
  { value: 'other', title: 'Sonstiges' },
]

const recording = ref(false)
const saving = ref(false)
const saveError = ref('')
const form = ref({ payment_date: '', amount: null, method: 'transfer', note: '' })

const reversalOpen = ref(false)
const reversalPayment = ref(null)
// The reversed payment, kept to offer booking the right one.
const reversedNotice = ref(null)

const canSave = computed(
  () => !!form.value.payment_date && Number(form.value.amount) > 0)

function startRecording(prefill = {}) {
  form.value = {
    payment_date: new Date().toISOString().slice(0, 10),
    amount: null,
    method: 'transfer',
    note: '',
    ...prefill,
  }
  saveError.value = ''
  recording.value = true
}

// Payments are never deleted: a Zahlung Storno cancels a wrong one.
function startReversal(e) {
  reversalPayment.value = {
    id: e.id,
    amount: -Number(e.amount),
    date: e.entry_date,
    label: e.description,
  }
  reversalOpen.value = true
}

async function onReversed() {
  const reversed = reversalPayment.value
  const entry = entries.value.find((x) => x.id === reversed.id)
  reversedNotice.value = {
    invoiceNumber: entry?.invoice_number || null,
    date: entry?.entry_date,
    method: entry?.method || 'transfer',
  }
  recording.value = false
  await loadLedger()
  emit('changed')
}

// Same date and method as the wrong payment; only the amount is left to enter.
function recordCorrection() {
  const n = reversedNotice.value
  reversedNotice.value = null
  startRecording({ payment_date: n.date, method: n.method })
}

function openInvoice(number) {
  model.value = false
  router.push({ path: '/invoices', query: { q: number } })
}

async function savePayment() {
  if (!canSave.value) return
  saving.value = true
  saveError.value = ''
  try {
    // No invoice: the payment is Haben, settles nothing yet and is credit.
    await api.post('/payments/', {
      customer: props.customerId,
      payment_date: form.value.payment_date,
      amount: form.value.amount,
      method: form.value.method,
      note: form.value.note,
    })
    recording.value = false
    await loadLedger()
    emit('changed')
  } catch (err) {
    saveError.value = extractErrorMessage(err, 'Zahlung konnte nicht gespeichert werden.')
  } finally {
    saving.value = false
  }
}

async function loadLedger() {
  loading.value = true
  error.value = ''
  try {
    const res = await api.get(`/customers/${props.customerId}/ledger/`)
    entries.value = res.data.entries || []
  } catch (err) {
    error.value = extractErrorMessage(err, 'Kundenkonto konnte nicht geladen werden.')
  } finally {
    loading.value = false
  }
}

watch(() => props.modelValue, async (open) => {
  if (!open || !props.customerId) return
  recording.value = false
  saveError.value = ''
  reversedNotice.value = null
  await loadLedger()
}, { immediate: true })

// Filters the matching list rather than opening the document: from an account
// overview you usually want to see the document in context — with its status,
// open amount and neighbouring documents — not jump straight into an editor.
// A reminder fee points at the Mahnung that charged it; everything else at the
// invoice.  Entries with no number (a standalone payment) are not links.
function linkTarget(e) {
  if (e.entry_type === 'reminder_fee' && e.reminder_number) {
    return { path: '/reminders', number: e.reminder_number }
  }
  if (e.invoice_number) {
    return { path: '/invoices', number: e.invoice_number }
  }
  return null
}

function openList(e) {
  const target = linkTarget(e)
  if (!target) return
  model.value = false
  router.push({ path: target.path, query: { q: target.number } })
}

const TYPE_COLORS = {
  invoice: 'error',
  reminder_fee: 'warning',
  payment: 'success',
  adjustment: 'info',
}

// A Storno reads as a plain "Rechnung" otherwise, right next to the invoice it
// cancels. deep-orange matches how the invoice list already flags one.
function typeColor(e) {
  return e.is_reversal ? 'deep-orange' : (TYPE_COLORS[e.entry_type] || 'default')
}

function typeLabel(e) {
  if (!e.is_reversal) return e.entry_type_display
  if (e.entry_type === 'payment_reversal') return e.entry_type_display // „Zahlung Storno“
  return e.entry_type === 'reminder_fee' ? 'Storno Gebühr' : 'Storno'
}

// Positive = Soll: the customer owes us.  Negative = credit.
function balanceState(v) {
  const n = Number(v ?? 0)
  if (n > 0) return 'offen'
  if (n < 0) return 'Guthaben'
  return ''
}

function balanceClass(v) {
  const n = Number(v ?? 0)
  if (n > 0) return 'text-error'
  if (n < 0) return 'text-success'
  return ''
}

// What of an entry is not yet settled (a charge) or not yet used (money in).
// Stornos are always settled against what they cancel, so they never show one.
function openLabel(e) {
  const open = Number(e.open_amount ?? 0)
  if (open <= 0 || e.is_reversal) return ''
  if (Number(e.amount) > 0) {
    return open === Number(e.amount) ? 'offen' : `davon offen: ${fmtEuro(open)}`
  }
  return `nicht zugeordnet: ${fmtEuro(open)}`
}

function fmtDate(d) {
  if (!d) return ''
  return new Date(d).toLocaleDateString('de-AT')
}

function fmtEuro(v) {
  return `${Number(v ?? 0).toLocaleString('de-AT', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} €`
}
</script>

<style scoped>
/* The running Saldo is what the account is about: set it apart from the
   Soll/Haben columns. */
.saldo-col {
  font-weight: 500;
  border-left: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
/* The last row's Saldo is the current balance.  Set on the cells and specific
   enough to beat the global zebra stripe; hover (!important) still wins. */
.ledger-table tbody tr.current-row:last-child td {
  background-color: rgba(var(--v-theme-on-surface), 0.12);
}
.current-row .saldo-col {
  font-weight: 700;
  font-size: 1.1rem;
}
</style>
