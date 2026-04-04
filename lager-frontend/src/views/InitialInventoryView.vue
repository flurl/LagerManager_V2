<template>
  <div>
    <v-row class="mb-2" align="center">
      <v-col><h2>Initialer Stand</h2></v-col>
      <v-col cols="auto">
        <v-select
          v-model="locationId"
          :items="locations"
          item-title="name"
          item-value="id"
          label="Arbeitsplatz"
          hide-details
          clearable
          style="max-width: 200px"
        />
      </v-col>
      <v-col cols="auto">
        <v-btn color="secondary" :loading="initLoading" @click="initPeriod">Periode init.</v-btn>
        <v-btn class="ml-2" prepend-icon="mdi-download" @click="exportCsvAction">CSV</v-btn>
      </v-col>
    </v-row>

    <v-data-table
      :headers="headers"
      :items="items"
      :loading="loading"
      density="compact"
    >
      <template #item.quantity="{ item }">
        <NumberInput v-model="item.quantity" density="compact" hide-details style="width: 100px"
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
import NumberInput from '../components/NumberInput.vue'

const periodStore = usePeriodStore()
const { exportCsv } = useCsvExport()
const items = ref([])
const locations = ref([])
const locationId = ref(null)
const loading = ref(false)
const initLoading = ref(false)

const headers = [
  { title: 'Artikel', key: 'article_name' },
  { title: 'Arbeitsplatz', key: 'location_name' },
  { title: 'Menge', key: 'quantity' },
]

async function fetchItems() {
  if (!periodStore.currentPeriodId) return
  loading.value = true
  try {
    const res = await api.get('/initial-inventory/', {
      params: { period_id: periodStore.currentPeriodId, location_id: locationId.value || undefined },
    })
    items.value = res.data.results || res.data
  } finally {
    loading.value = false
  }
}

async function saveItem(item) {
  await api.patch(`/initial-inventory/${item.id}/`, { quantity: item.quantity })
}

async function initPeriod() {
  initLoading.value = true
  try {
    await api.post('/initial-inventory/init_period/', { period_id: periodStore.currentPeriodId })
    await fetchItems()
  } finally {
    initLoading.value = false
  }
}

function exportCsvAction() {
  exportCsv(['article_name', 'location_name', 'quantity'], items.value, 'initialer_stand.csv')
}

onMounted(async () => {
  const res = await api.get('/locations/')
  locations.value = res.data.results || res.data
  await fetchItems()
})

watch(() => periodStore.currentPeriodId, fetchItems)
watch(locationId, fetchItems)
</script>
