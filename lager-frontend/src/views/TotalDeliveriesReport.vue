<template>
  <div>
    <ReportTable :headers="headers" :items="items" :loading="loading" title="Insgesamt gelieferte Artikel"
      csv-filename="gesamte_lieferungen.csv">
      <template #item.total_value="{ item }">{{ item.total_value.toFixed(2) }}</template>
      <template #item.avg_price="{ item }">{{ item.avg_price.toFixed(2) }}</template>
    </ReportTable>
  </div>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue'
import { usePeriodStore } from '../stores/period'
import api from '../api'
import ReportTable from '../components/ReportTable.vue'

const periodStore = usePeriodStore()
const items = ref([])
const loading = ref(false)

const headers = [
  { title: 'Datum', key: 'date' },
  { title: 'Artikel', key: 'article' },
  { title: 'Anzahl', key: 'quantity', align: 'end' },
  { title: 'Einheit', key: 'unit' },
  { title: 'Warenwert', key: 'total_value', align: 'end' },
  { title: 'Warenwert Durchschnitt', key: 'avg_price', align: 'end' },
]

async function fetchData() {
  if (!periodStore.currentPeriodId) return
  loading.value = true
  try {
    const res = await api.get('/reports/total-deliveries/', {
      params: { period_id: periodStore.currentPeriodId },
    })
    items.value = res.data.deliveries ?? res.data
  } finally {
    loading.value = false
  }
}

watch(() => periodStore.currentPeriodId, fetchData)
onMounted(fetchData)
</script>
