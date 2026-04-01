<template>
  <div>
    <v-row class="mb-2" align="center">
      <v-col><h2>Gezählter Stand</h2></v-col>
      <v-col cols="3">
        <v-text-field
          v-model="filterDate"
          label="Datum"
          type="date"
          hide-details
          clearable
        />
      </v-col>
      <v-col cols="auto">
        <v-btn color="secondary" :loading="initLoading" @click="initDate">Datum init.</v-btn>
      </v-col>
    </v-row>

    <v-data-table
      :headers="headers"
      :items="items"
      :loading="loading"
      density="compact"
    >
      <template #item.date="{ item }">{{ formatDate(item.date) }}</template>
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
import api from '../api'
import NumberInput from '../components/NumberInput.vue'

const periodStore = usePeriodStore()
const items = ref([])
const filterDate = ref('')
const loading = ref(false)
const initLoading = ref(false)

const headers = [
  { title: 'Datum', key: 'date' },
  { title: 'Artikel', key: 'article_name' },
  { title: 'Menge', key: 'quantity' },
]

async function fetchItems() {
  if (!periodStore.currentPeriodId) return
  loading.value = true
  try {
    const res = await api.get('/physical-counts/', {
      params: {
        period_id: periodStore.currentPeriodId,
        date: filterDate.value || undefined,
      },
    })
    items.value = res.data.results || res.data
  } finally {
    loading.value = false
  }
}

async function saveItem(item) {
  await api.patch(`/physical-counts/${item.id}/`, { quantity: item.quantity })
}

async function initDate() {
  if (!filterDate.value) return
  initLoading.value = true
  try {
    await api.post('/physical-counts/init_date/', {
      period_id: periodStore.currentPeriodId,
      date: filterDate.value,
    })
    await fetchItems()
  } finally {
    initLoading.value = false
  }
}

function formatDate(dt) {
  return dt ? new Date(dt).toLocaleDateString('de-AT') : ''
}

watch(() => periodStore.currentPeriodId, fetchItems)
watch(filterDate, fetchItems)
onMounted(fetchItems)
</script>
