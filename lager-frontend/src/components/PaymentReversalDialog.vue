<template>
  <v-dialog v-model="model" max-width="480" persistent>
    <v-card>
      <v-card-title class="d-flex align-center pa-4">
        <v-icon class="mr-2">mdi-cash-remove</v-icon>
        Zahlung stornieren
      </v-card-title>

      <v-card-text class="pa-4 pt-0">
        <p v-if="payment" class="mb-4">
          Zahlung vom {{ fmtDate(payment.date) }} über <strong>{{ fmtEuro(payment.amount) }}</strong>
          <template v-if="payment.label"> ({{ payment.label }})</template>.
        </p>
        <p class="text-caption text-medium-emphasis mb-4">
          Die Zahlung bleibt im Kundenkonto stehen; eine „Zahlung Storno“ im Soll hebt sie auf.
          Was sie beglichen hat, ist danach wieder offen. Die richtige Zahlung kann anschließend
          neu erfasst werden.
        </p>

        <v-alert v-if="error" type="error" density="compact" class="mb-4">{{ error }}</v-alert>

        <v-textarea
          id="payment-reversal-reason"
          v-model="reason"
          label="Stornierungsgrund *"
          rows="2"
          auto-grow
          density="compact"
          autofocus
        />
        <v-text-field
          id="payment-reversal-date"
          v-model="date"
          label="Datum *"
          type="date"
          density="compact"
        />
      </v-card-text>

      <v-card-actions class="pa-4">
        <v-spacer />
        <v-btn :disabled="saving" @click="model = false">Abbrechen</v-btn>
        <v-btn color="error" variant="flat" :loading="saving" :disabled="!canSave" @click="save">
          Stornieren
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import api from '../api'
import { extractErrorMessage } from '../utils/errorMessage'

// payment: { id, amount, date, label } — amount as the money received (positive).
const props = defineProps({
  modelValue: { type: Boolean, default: false },
  payment: { type: Object, default: null },
})
const emit = defineEmits(['update:modelValue', 'reversed'])

const model = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const reason = ref('')
const date = ref('')
const saving = ref(false)
const error = ref('')

const canSave = computed(() => !!reason.value.trim() && !!date.value && !!props.payment)

watch(() => props.modelValue, (open) => {
  if (!open) return
  reason.value = ''
  date.value = new Date().toISOString().slice(0, 10)
  error.value = ''
})

async function save() {
  if (!canSave.value) return
  saving.value = true
  error.value = ''
  try {
    const res = await api.post(`/payments/${props.payment.id}/reverse/`, {
      reason: reason.value.trim(),
      date: date.value,
    })
    emit('reversed', res.data)
    model.value = false
  } catch (err) {
    error.value = extractErrorMessage(err, 'Zahlung konnte nicht storniert werden.')
  } finally {
    saving.value = false
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
