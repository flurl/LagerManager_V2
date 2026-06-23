<template>
  <v-dialog :model-value="modelValue" @update:model-value="emit('update:modelValue', $event)" max-width="640" persistent>
    <v-card>
      <v-card-title class="d-flex align-center pa-4">
        <v-icon class="mr-2">mdi-cash-register</v-icon>
        WZ Import
        <v-spacer />
        <v-btn icon @click="emit('update:modelValue', false)"><v-icon>mdi-close</v-icon></v-btn>
      </v-card-title>

      <v-card-text>
        <v-alert v-if="!periodStore.currentPeriodId" type="warning" class="mb-3">
          Keine Periode ausgewählt.
        </v-alert>

        <!-- Checkpoint dropdown -->
        <v-select
          v-model="selectedCheckpointId"
          :items="checkpoints"
          item-title="label"
          item-value="id"
          label="Kassaabschluss"
          density="compact"
          hide-details="auto"
          clearable
          :loading="loadingCheckpoints"
          :disabled="!periodStore.currentPeriodId"
          class="mb-4"
        />

        <!-- Tisch dropdown (only visible once a checkpoint is selected) -->
        <v-select
          v-if="selectedCheckpointId != null"
          v-model="selectedTischId"
          :items="tische"
          item-title="label"
          item-value="id"
          label="Tisch"
          density="compact"
          hide-details="auto"
          clearable
          :loading="loadingTische"
          class="mb-4"
        />

        <!-- Bondetail preview table -->
        <template v-if="bondetails.length">
          <div class="text-caption text-medium-emphasis mb-1">Positionen (gruppiert nach Artikel)</div>
          <v-table density="compact" class="mb-2">
            <thead>
              <tr>
                <th>Artikel</th>
                <th class="text-right">Menge</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in bondetails" :key="row.name">
                <td>{{ row.name }}</td>
                <td class="text-right">{{ row.quantity }}</td>
              </tr>
            </tbody>
          </v-table>
        </template>

        <v-alert v-if="selectedTischId != null && !loadingBondetails && bondetails.length === 0"
          type="info" density="compact" class="mt-2">
          Keine Positionen für diesen Tisch gefunden.
        </v-alert>

        <v-alert v-if="error" type="error" density="compact" class="mt-2">{{ error }}</v-alert>
      </v-card-text>

      <v-card-actions>
        <v-spacer />
        <v-btn @click="emit('update:modelValue', false)">Abbrechen</v-btn>
        <v-btn
          color="secondary"
          :disabled="!canImport"
          :loading="loadingBondetails"
          @click="doImportNotes"
        >
          In Anmerkungen
        </v-btn>
        <v-btn
          color="primary"
          :disabled="!canImport"
          :loading="loadingBondetails"
          @click="doImportLines"
        >
          Als Positionen
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import api from '../api'
import { usePeriodStore } from '../stores/period'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue', 'confirm'])

const periodStore = usePeriodStore()

const checkpoints = ref([])
const tische = ref([])
const bondetails = ref([])

const selectedCheckpointId = ref(null)
const selectedTischId = ref(null)

const loadingCheckpoints = ref(false)
const loadingTische = ref(false)
const loadingBondetails = ref(false)
const error = ref('')

const canImport = computed(() => bondetails.value.length > 0 && !loadingBondetails.value)

// Reset all state when dialog opens
watch(() => props.modelValue, (val) => {
  if (val) {
    checkpoints.value = []
    tische.value = []
    bondetails.value = []
    selectedCheckpointId.value = null
    selectedTischId.value = null
    error.value = ''
    if (periodStore.currentPeriodId) {
      loadCheckpoints()
    }
  }
})

async function loadCheckpoints() {
  if (!periodStore.currentPeriodId) return
  loadingCheckpoints.value = true
  error.value = ''
  try {
    const res = await api.get('/wz-import/checkpoints/', {
      params: { period_id: periodStore.currentPeriodId },
    })
    checkpoints.value = res.data
  } catch (e) {
    error.value = e.response?.data?.error ?? 'Fehler beim Laden der Kassaabschlüsse'
  } finally {
    loadingCheckpoints.value = false
  }
}

watch(selectedCheckpointId, async (id) => {
  selectedTischId.value = null
  tische.value = []
  bondetails.value = []
  if (!id) return
  loadingTische.value = true
  error.value = ''
  try {
    const res = await api.get('/wz-import/tische/', {
      params: { period_id: periodStore.currentPeriodId, checkpoint_id: id },
    })
    tische.value = res.data
  } catch (e) {
    error.value = e.response?.data?.error ?? 'Fehler beim Laden der Tische'
  } finally {
    loadingTische.value = false
  }
})

watch(selectedTischId, async (id) => {
  bondetails.value = []
  if (!id) return
  loadingBondetails.value = true
  error.value = ''
  try {
    const res = await api.get('/wz-import/bondetails/', {
      params: { period_id: periodStore.currentPeriodId, tisch_id: id },
    })
    bondetails.value = res.data
  } catch (e) {
    error.value = e.response?.data?.error ?? 'Fehler beim Laden der Positionen'
  } finally {
    loadingBondetails.value = false
  }
})

function doImportLines() {
  const lines = bondetails.value.map(row => ({
    billing_article: null,
    description: row.name,
    unit: '',
    quantity: row.quantity,
    unit_price: 0,
    tax_rate: null,  // parent will fill with default tax rate
  }))
  emit('confirm', { mode: 'lines', lines })
  emit('update:modelValue', false)
}

function doImportNotes() {
  const checkpoint = checkpoints.value.find(c => c.id === selectedCheckpointId.value)
  const tisch = tische.value.find(t => t.id === selectedTischId.value)
  const header = `Artikel vom ${checkpoint?.label ?? ''}  Tisch ${tisch?.label ?? ''}`

  const maxQtyLen = Math.max(...bondetails.value.map(r => String(r.quantity).length))
  const prefixWidth = maxQtyLen + 2  // digits + 'x' + min 1 space
  const lines = [
    header,
    ...bondetails.value.map(r => (String(r.quantity) + 'x').padEnd(prefixWidth) + r.name),
  ]
  emit('confirm', { mode: 'notes', text: lines.join('\n') })
  emit('update:modelValue', false)
}
</script>
