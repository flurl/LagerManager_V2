<template>
  <div>
    <v-row class="mb-2" align="center">
      <v-col>
        <v-btn-toggle v-model="isConsumption" mandatory>
          <v-btn :value="false">Lieferungen</v-btn>
          <v-btn :value="true">Verbräuche</v-btn>
        </v-btn-toggle>
      </v-col>
      <v-col cols="auto">
        <v-btn color="primary" prepend-icon="mdi-plus" @click="openNew">Neu</v-btn>
        <v-btn class="ml-2" prepend-icon="mdi-download" @click="exportCsvAction">CSV</v-btn>
      </v-col>
    </v-row>

    <v-data-table
      :headers="headers"
      :items="deliveries"
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
        <v-icon size="small" class="ml-1" color="error" @click.stop="deleteDelivery(item)">mdi-delete</v-icon>
      </template>
    </v-data-table>

    <!-- Delivery detail dialog -->
    <v-dialog v-model="dialog" max-width="900" persistent>
      <DeliveryDetailDialog
        :delivery="selectedDelivery"
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
import DeliveryDetailDialog from '../components/DeliveryDetailDialog.vue'

const periodStore = usePeriodStore()
const { exportCsv } = useCsvExport()

const deliveries = ref([])
const loading = ref(false)
const isConsumption = ref(false)
const dialog = ref(false)
const selectedDelivery = ref(null)

const headers = [
  { title: 'Datum', key: 'date' },
  { title: 'Lieferant', key: 'supplier_name' },
  { title: 'Kommentar', key: 'comment' },
  { title: 'Brutto', key: 'total_gross', align: 'end' },
  { title: '', key: 'actions', sortable: false, align: 'end' },
]

async function fetchDeliveries() {
  if (!periodStore.currentPeriodId) return
  loading.value = true
  try {
    const res = await api.get('/deliveries/', {
      params: {
        period_id: periodStore.currentPeriodId,
        is_consumption: isConsumption.value ? 1 : 0,
      },
    })
    deliveries.value = res.data.results || res.data
  } finally {
    loading.value = false
  }
}

function openNew() {
  selectedDelivery.value = null
  dialog.value = true
}

function openDetail(item) {
  selectedDelivery.value = item
  dialog.value = true
}

async function deleteDelivery(item) {
  if (!confirm(`Lieferung #${item.id} wirklich löschen?`)) return
  await api.delete(`/deliveries/${item.id}/`)
  await fetchDeliveries()
}

function onSaved() {
  dialog.value = false
  fetchDeliveries()
}

function exportCsvAction() {
  exportCsv(
    ['date', 'supplier_name', 'comment', 'total_gross'],
    deliveries.value,
    'lieferungen.csv'
  )
}

function formatDate(dt) {
  return dt ? new Date(dt).toLocaleDateString('de-AT') : ''
}

function formatCurrency(val) {
  return val != null ? Number(val).toFixed(2) + ' €' : ''
}

watch(() => periodStore.currentPeriodId, fetchDeliveries)
watch(isConsumption, fetchDeliveries)
onMounted(fetchDeliveries)
</script>
