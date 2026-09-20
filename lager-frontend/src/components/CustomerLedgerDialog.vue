<template>
  <v-dialog v-model="model" max-width="820" scrollable>
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
          @click="startRecording"
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
          <div class="d-flex align-center mb-4">
            <span class="text-subtitle-1 mr-2">Saldo:</span>
            <span class="text-h6" :class="balanceClass(balance)">{{ fmtEuro(balance) }}</span>
            <v-chip v-if="Number(balance) > 0" size="small" color="success" class="ml-3">
              Guthaben
            </v-chip>
            <v-chip v-else-if="Number(balance) < 0" size="small" color="error" class="ml-3">
              Offen
            </v-chip>
          </div>

          <v-alert v-if="saveError" type="error" density="compact" class="mb-4" closable
            @click:close="saveError = ''">
            {{ saveError }}
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
              Der Betrag erhöht den Saldo und steht als Guthaben zur Verfügung. Über
              „… verrechnen“ im Zahlungsdialog einer Rechnung kann er später zugeordnet werden.
            </div>
            <div class="d-flex justify-end mt-2">
              <v-btn size="small" variant="text" @click="recording = false">Abbrechen</v-btn>
              <v-btn size="small" color="primary" :loading="saving" :disabled="!canSave"
                @click="savePayment">Speichern</v-btn>
            </div>
          </v-card>

          <v-table v-if="entries.length" density="compact">
            <thead>
              <tr>
                <th class="text-no-wrap">Datum</th>
                <th>Art</th>
                <th>Beschreibung</th>
                <th class="text-right">Betrag</th>
                <th class="text-right">Saldo</th>
                <th>Benutzer</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="e in entries" :key="e.id">
                <td class="text-no-wrap">{{ fmtDate(e.entry_date) }}</td>
                <td>
                  <v-chip size="x-small" :color="typeColor(e)"
                    :prepend-icon="e.is_reversal ? 'mdi-file-undo' : undefined">
                    {{ typeLabel(e) }}
                  </v-chip>
                </td>
                <td class="text-caption">
                  <a
                    v-if="e.invoice"
                    href="#"
                    @click.prevent="openInvoice(e.invoice)"
                  >{{ e.description }}</a>
                  <template v-else>{{ e.description }}</template>
                </td>
                <td class="text-right" :class="balanceClass(e.amount)">{{ fmtEuro(e.amount) }}</td>
                <td class="text-right">{{ fmtEuro(e.running_balance) }}</td>
                <td class="text-caption">{{ e.actor || '—' }}</td>
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
    </v-card>
  </v-dialog>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api'
import NumberInput from './NumberInput.vue'
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
const balance = ref('0.00')

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

const canSave = computed(
  () => !!form.value.payment_date && Number(form.value.amount) > 0)

function startRecording() {
  form.value = {
    payment_date: new Date().toISOString().slice(0, 10),
    amount: null,
    method: 'transfer',
    note: '',
  }
  saveError.value = ''
  recording.value = true
}

async function savePayment() {
  if (!canSave.value) return
  saving.value = true
  saveError.value = ''
  try {
    // No invoice: the payment raises the balance and becomes available credit.
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
    balance.value = res.data.balance
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
  await loadLedger()
}, { immediate: true })

function openInvoice(id) {
  model.value = false
  router.push({ path: '/invoices', query: { openId: id } })
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
  return e.entry_type === 'reminder_fee' ? 'Storno Gebühr' : 'Storno'
}

function balanceClass(v) {
  const n = Number(v ?? 0)
  if (n < 0) return 'text-error'
  if (n > 0) return 'text-success'
  return ''
}

function fmtDate(d) {
  if (!d) return ''
  return new Date(d).toLocaleDateString('de-AT')
}

function fmtEuro(v) {
  return `${Number(v ?? 0).toLocaleString('de-AT', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} €`
}
</script>
