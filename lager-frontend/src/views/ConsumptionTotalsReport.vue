<template>
  <ReportTable :headers="headers" :items="items" :loading="loading" title="Gesamtverbrauch"
    csv-filename="gesamtverbrauch.csv">
    <template #item.total="{ item }">{{ item.total.toFixed(2) }}</template>
  </ReportTable>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { usePeriodStore } from '../stores/period'
import api from '../api'
import ReportTable from '../components/ReportTable.vue'

const periodStore = usePeriodStore()
const items = ref([])
const loading = ref(false)

const headers = [
  { title: 'Artikel', key: 'article' },
  { title: 'Gesamtmenge', key: 'total', align: 'end' },
]

async function fetchData() {
  if (!periodStore.currentPeriodId) return
  loading.value = true
  try {
    const res = await api.get('/reports/consumption-totals/', {
      params: { period_id: periodStore.currentPeriodId },
    })
    items.value = res.data
  } finally {
    loading.value = false
  }
}

watch(() => periodStore.currentPeriodId, fetchData)
onMounted(fetchData)
</script>
