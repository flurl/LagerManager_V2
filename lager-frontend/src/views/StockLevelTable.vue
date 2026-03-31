<template>
  <div>
    <v-row class="mb-2" align="center">
      <v-col>
        <h2>Periode Start-Stand</h2>
      </v-col>
      <v-col cols="auto">
        <v-btn color="secondary" :loading="initLoading" @click="initPeriod">Periode initialisieren</v-btn>
        <v-btn class="ml-2" prepend-icon="mdi-download" @click="exportCsvAction">CSV</v-btn>
      </v-col>
    </v-row>

    <v-data-table :headers="headers" :items="items" :loading="loading" density="compact">
      <template #item.quantity="{ item }">
        <v-text-field v-model.number="item.quantity" type="number" density="compact" hide-details style="width: 100px"
          @change="saveItem(item)" />
      </template>
    </v-data-table>
  </div>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue'
import { usePeriodStore } from '../stores/period'
import { useCsvExport } from '../composables/useCsvExport'
import api from '../api'

const periodStore = usePeriodStore()
const { exportCsv } = useCsvExport()
const items = ref([])
const loading = ref(false)
const initLoading = ref(false)

const headers = [
  { title: 'Artikel', key: 'article_name' },
  { title: 'Menge', key: 'quantity' },
  { title: 'Geändert', key: 'updated_at' },
]

async function fetchItems() {
  if (!periodStore.currentPeriodId) return
  loading.value = true
  try {
    const res = await api.get('/stock-levels/', { params: { period_id: periodStore.currentPeriodId } })
    items.value = res.data.results || res.data
  } finally {
    loading.value = false
  }
}

async function saveItem(item) {
  await api.patch(`/stock-levels/${item.id}/`, { quantity: item.quantity })
}

async function initPeriod() {
  initLoading.value = true
  try {
    await api.post('/stock-levels/init_period/', { period_id: periodStore.currentPeriodId })
    await fetchItems()
  } finally {
    initLoading.value = false
  }
}

function exportCsvAction() {
  exportCsv(['article_name', 'quantity'], items.value, 'lagerstand.csv')
}

watch(() => periodStore.currentPeriodId, fetchItems)
onMounted(fetchItems)
</script>
