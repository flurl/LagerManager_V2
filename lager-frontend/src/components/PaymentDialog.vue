<template>
  <v-dialog v-model="model" max-width="720" persistent scrollable>
    <v-card>
      <v-card-title class="d-flex align-center pa-4">
        <v-icon class="mr-2">mdi-cash-multiple</v-icon>
        Zahlungen
        <template v-if="info?.number"> — {{ info.number }}</template>
        <v-spacer />
        <v-btn icon variant="text" @click="model = false"><v-icon>mdi-close</v-icon></v-btn>
      </v-card-title>

      <v-card-text class="pa-4" style="overflow-y: auto">
        <div v-if="loading" class="text-center py-6">
          <v-progress-circular indeterminate />
        </div>

        <template v-else-if="info">
          <!-- Summary -->
          <v-table density="compact" class="mb-4 summary-table">
            <tbody>
              <tr>
                <td>Rechnungsbetrag (brutto)</td>
                <td class="text-right">{{ fmtEuro(info.gross_total) }}</td>
              </tr>
              <tr v-if="Number(info.reminder_fee_total) !== 0">
                <td>Mahngebühren</td>
                <td class="text-right">{{ fmtEuro(info.reminder_fee_total) }}</td>
              </tr>
              <tr v-if="Number(info.reminder_fee_total) !== 0">
                <td>Gesamtforderung</td>
                <td class="text-right">{{ fmtEuro(info.total_due) }}</td>
              </tr>
              <tr>
                <td>Bereits bezahlt</td>
                <td class="text-right">{{ fmtEuro(info.paid_amount) }}</td>
              </tr>
              <tr class="open-row">
                <td>Offener Betrag</td>
                <td class="text-right" :class="openAmount > 0 ? 'text-error' : 'text-success'">
                  {{ fmtEuro(info.open_amount) }}
                </td>
              </tr>
            </tbody>
          </v-table>

          <v-alert v-if="error" type="error" density="compact" class="mb-4" closable @click:close="error = ''">
            {{ error }}
          </v-alert>

          <!-- Credit that arrived after the invoice was issued -->
          <v-alert
            v-if="availableCredit > 0 && openAmount > 0"
            type="info"
            variant="tonal"
            density="compact"
            class="mb-4"
          >
            <div class="d-flex align-center flex-wrap ga-2">
              <span>
                Der Kunde hat ein Guthaben von {{ fmtEuro(availableCredit) }}.
              </span>
              <v-spacer />
              <v-btn
                size="small"
                color="info"
                variant="flat"
                :loading="applyingCredit"
                @click="applyCredit"
              >
                {{ fmtEuro(creditToApply) }} verrechnen
              </v-btn>
            </div>
          </v-alert>

          <!-- Existing payments -->
          <div class="text-subtitle-2 mb-2">Erfasste Zahlungen</div>
          <v-table v-if="info.payments.length" density="compact" class="mb-4">
            <thead>
              <tr>
                <th class="text-no-wrap">Datum</th>
                <th class="text-right">Betrag</th>
                <th>Art</th>
                <th>Notiz</th>
                <th class="text-right"></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="p in info.payments" :key="p.id">
                <td class="text-no-wrap">{{ fmtDate(p.payment_date) }}</td>
                <td class="text-right">{{ fmtEuro(p.amount) }}</td>
                <td>{{ p.method_display }}</td>
                <td class="text-caption">{{ p.note || '—' }}</td>
                <td class="text-right">
                  <v-tooltip text="Zahlung löschen">
                    <template #activator="{ props }">
                      <v-icon
                        v-bind="props"
                        size="small"
                        color="error"
                        :disabled="deletingId === p.id"
                        @click="remove(p)"
                      >mdi-delete</v-icon>
                    </template>
                  </v-tooltip>
                </td>
              </tr>
            </tbody>
          </v-table>
          <div v-else class="text-medium-emphasis text-caption mb-4">
            Noch keine Zahlungen erfasst.
          </div>

          <!-- New payment -->
          <template v-if="canAddPayment">
            <v-divider class="mb-3" />
            <div class="text-subtitle-2 mb-2">Zahlung erfassen</div>
            <v-row dense>
              <v-col cols="12" sm="4">
                <v-text-field v-model="form.payment_date" label="Datum *" type="date" density="compact" />
              </v-col>
              <v-col cols="12" sm="4">
                <NumberInput v-model="form.amount" label="Betrag *" density="compact" />
              </v-col>
              <v-col cols="12" sm="4">
                <v-select
                  v-model="form.method"
                  :items="methods"
                  item-title="title"
                  item-value="value"
                  label="Zahlungsart"
                  density="compact"
                />
              </v-col>
            </v-row>
            <v-row dense>
              <v-col cols="12">
                <v-text-field v-model="form.note" label="Notiz" density="compact" />
              </v-col>
            </v-row>
            <v-btn
              size="small"
              variant="text"
              prepend-icon="mdi-equal"
              :disabled="openAmount <= 0"
              @click="form.amount = openAmount"
            >
              Restbetrag übernehmen
            </v-btn>
          </template>
          <div v-else class="text-medium-emphasis text-caption">
            Für diese Rechnung können keine Zahlungen erfasst werden.
          </div>
        </template>
      </v-card-text>

      <v-card-actions class="pa-4">
        <v-spacer />
        <v-btn @click="model = false">Schließen</v-btn>
        <v-btn
          v-if="canAddPayment"
          color="primary"
          prepend-icon="mdi-cash-plus"
          :loading="saving"
          :disabled="!canSave"
          @click="save"
        >
          Zahlung speichern
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import api from '../api'
import NumberInput from './NumberInput.vue'
import { extractErrorMessage } from '../utils/errorMessage'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  invoiceId: { type: [Number, String], default: null },
})
const emit = defineEmits(['update:modelValue', 'changed'])

const model = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const methods = [
  { value: 'transfer', title: 'Überweisung' },
  { value: 'cash', title: 'Bar' },
  { value: 'card', title: 'Karte' },
  { value: 'other', title: 'Sonstiges' },
]

const loading = ref(false)
const saving = ref(false)
const applyingCredit = ref(false)
const availableCredit = ref(0)
const deletingId = ref(null)
const error = ref('')
const info = ref(null)
const form = ref({ payment_date: '', amount: null, method: 'transfer', note: '' })

const openAmount = computed(() => Number(info.value?.open_amount ?? 0))
const creditToApply = computed(
  () => Math.min(availableCredit.value, Math.max(openAmount.value, 0)))
// Drafts and cancelled invoices reject payments server-side; hide the form too.
const canAddPayment = computed(
  () => !!info.value && !['draft', 'cancelled'].includes(info.value.status),
)
const canSave = computed(
  () => !!form.value.payment_date && Number(form.value.amount) > 0,
)

watch(() => props.modelValue, async (open) => {
  if (!open || !props.invoiceId) return
  error.value = ''
  await load()
  resetForm()
}, { immediate: true })

async function load() {
  loading.value = true
  try {
    const res = await api.get(`/invoices/${props.invoiceId}/payment-info/`)
    info.value = res.data
    await loadCredit()
  } catch (err) {
    error.value = extractErrorMessage(err, 'Zahlungen konnten nicht geladen werden.')
  } finally {
    loading.value = false
  }
}

async function loadCredit() {
  availableCredit.value = 0
  if (!info.value?.customer) return
  try {
    const res = await api.get(`/customers/${info.value.customer}/balance/`)
    availableCredit.value = Number(res.data.available_credit ?? 0)
  } catch {
    // Not being able to read the balance must not break the payment list.
  }
}

async function applyCredit() {
  applyingCredit.value = true
  error.value = ''
  try {
    await api.post(`/invoices/${props.invoiceId}/apply-credit/`)
    await load()
    resetForm()
    emit('changed')
  } catch (err) {
    error.value = extractErrorMessage(err, 'Guthaben konnte nicht verrechnet werden.')
  } finally {
    applyingCredit.value = false
  }
}

function resetForm() {
  form.value = {
    payment_date: new Date().toISOString().slice(0, 10),
    amount: openAmount.value > 0 ? openAmount.value : null,
    method: 'transfer',
    note: '',
  }
}

async function save() {
  if (!canSave.value) return
  saving.value = true
  error.value = ''
  try {
    await api.post('/payments/', {
      customer: info.value.customer,
      invoice: info.value.invoice,
      payment_date: form.value.payment_date,
      amount: form.value.amount,
      method: form.value.method,
      note: form.value.note,
    })
    await load()
    resetForm()
    emit('changed')
  } catch (err) {
    error.value = extractErrorMessage(err, 'Zahlung konnte nicht gespeichert werden.')
  } finally {
    saving.value = false
  }
}

async function remove(payment) {
  if (!confirm(`Zahlung vom ${fmtDate(payment.payment_date)} über ${fmtEuro(payment.amount)} löschen?`)) return
  deletingId.value = payment.id
  error.value = ''
  try {
    await api.delete(`/payments/${payment.id}/`)
    await load()
    resetForm()
    emit('changed')
  } catch (err) {
    error.value = extractErrorMessage(err, 'Zahlung konnte nicht gelöscht werden.')
  } finally {
    deletingId.value = null
  }
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
.summary-table :deep(td) { border-bottom: none; }
.summary-table :deep(.open-row td) {
  font-weight: 700;
  font-size: 1rem;
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
</style>
