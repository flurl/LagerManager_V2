<template>
  <div>
    <v-row class="mb-2" align="center">
      <v-col>
        <v-btn-toggle v-model="movementType" mandatory>
          <v-btn value="delivery">Lieferungen</v-btn>
          <v-btn value="consumption">Verbräuche</v-btn>
        </v-btn-toggle>
      </v-col>
      <v-col cols="auto">
        <v-btn color="primary" prepend-icon="mdi-plus" @click="openNew">Neu</v-btn>
        <v-btn class="ml-2" prepend-icon="mdi-download" @click="exportCsvAction">CSV</v-btn>
      </v-col>
    </v-row>

    <v-data-table
      :headers="headers"
      :items="movements"
      :loading="loading"
      density="compact"
      @click:row="(_, { item }) => openDetail(item)"
    >
      <template #item.date="{ item }">
        {{ formatDate(item.date) }}
      </template>
      <template #item.total_gross="{ item }">
        {{ formatCurrency(item.total_gross) }}
      </template>
      <template #item.actions="{ item }">
        <v-icon size="small" @click.stop="openDetail(item)">mdi-pencil</v-icon>
        <v-icon size="small" class="ml-1" color="error" @click.stop="deleteMovement(item)">mdi-delete</v-icon>
      </template>
    </v-data-table>

    <v-dialog v-model="dialog" max-width="900" persistent>
      <StockMovementDialog
        :movement="selectedMovement"
        @saved="onSaved"
        @close="dialog = false"
      />
    </v-dialog>
  </div>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue'
import { usePeriodStore } from '../stores/period'
import { useCsvExport } from '../composables/useCsvExport'
import api from '../api'
import StockMovementDialog from '../components/StockMovementDialog.vue'

const periodStore = usePeriodStore()
const { exportCsv } = useCsvExport()

const movements = ref([])
const loading = ref(false)
const movementType = ref('delivery')
const dialog = ref(false)
const selectedMovement = ref(null)

const headers = [
  { title: 'Datum', key: 'date' },
  { title: 'Partner', key: 'partner_name' },
  { title: 'Kommentar', key: 'comment' },
  { title: 'Brutto', key: 'total_gross', align: 'end' },
  { title: '', key: 'actions', sortable: false, align: 'end' },
]

async function fetchMovements() {
  if (!periodStore.currentPeriodId) return
  loading.value = true
  try {
    const res = await api.get('/stock-movements/', {
      params: {
        period_id: periodStore.currentPeriodId,
        movement_type: movementType.value,
      },
    })
    movements.value = res.data.results || res.data
  } finally {
    loading.value = false
  }
}

function openNew() {
  selectedMovement.value = null
  dialog.value = true
}

function openDetail(item) {
  selectedMovement.value = item
  dialog.value = true
}

async function deleteMovement(item) {
  if (!confirm(`Lagerbewegung #${item.id} wirklich löschen?`)) return
  await api.delete(`/stock-movements/${item.id}/`)
  await fetchMovements()
}

function onSaved() {
  dialog.value = false
  fetchMovements()
}

function exportCsvAction() {
  exportCsv(
    ['date', 'partner_name', 'comment', 'total_gross'],
    movements.value,
    'lagerbewegungen.csv'
  )
}

function formatDate(dt) {
  return dt ? new Date(dt).toLocaleDateString('de-AT') : ''
}

function formatCurrency(val) {
  return val != null ? Number(val).toFixed(2) + ' €' : ''
}

watch(() => periodStore.currentPeriodId, fetchMovements)
watch(movementType, fetchMovements)
onMounted(fetchMovements)
</script>
