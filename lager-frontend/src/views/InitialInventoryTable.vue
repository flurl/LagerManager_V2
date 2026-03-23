<template>
  <div>
    <v-row class="mb-2" align="center">
      <v-col><h2>Initialer Stand</h2></v-col>
      <v-col cols="auto">
        <v-select
          v-model="workplaceId"
          :items="workplaces"
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
        <v-text-field
          v-model.number="item.quantity"
          type="number"
          density="compact"
          hide-details
          style="width: 100px"
          @change="saveItem(item)"
        />
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
const workplaces = ref([])
const workplaceId = ref(null)
const loading = ref(false)
const initLoading = ref(false)

const headers = [
  { title: 'Artikel', key: 'article_name' },
  { title: 'Arbeitsplatz', key: 'workplace_name' },
  { title: 'Menge', key: 'quantity' },
]

async function fetchItems() {
  if (!periodStore.currentPeriodId) return
  loading.value = true
  try {
    const res = await api.get('/initial-inventory/', {
      params: { period_id: periodStore.currentPeriodId, workplace_id: workplaceId.value || undefined },
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
  exportCsv(['article_name', 'workplace_name', 'quantity'], items.value, 'initialer_stand.csv')
}

onMounted(async () => {
  const res = await api.get('/workplaces/')
  workplaces.value = res.data.results || res.data
  await fetchItems()
})

watch(() => periodStore.currentPeriodId, fetchItems)
watch(workplaceId, fetchItems)
</script>
