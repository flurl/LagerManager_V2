<template>
  <ReportTable :headers="headers" :items="items" :loading="loading" title="Unter Mindestbestand"
    csv-filename="unter-mindestbestand.csv">
    <template #item.stock="{ item }">{{ item.stock.toFixed(3) }}</template>
    <template #item.minimum_inventory="{ item }">{{ item.minimum_inventory }}</template>
    <template #item.shortage="{ item }">{{ item.shortage.toFixed(3) }}</template>
    <template #item.purchase_price="{ item }">{{ item.purchase_price?.toFixed(4) ?? '—' }}</template>
    <template #item.total_value="{ item }">{{ item.total_value?.toFixed(2) ?? '—' }}</template>
    <template #item.warehouse_unit="{ item }">{{ item.warehouse_unit ?? '—' }}</template>
  </ReportTable>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { usePeriodStore } from '../../stores/period'
import api from '../../api'
import ReportTable from '../../components/ReportTable.vue'

const periodStore = usePeriodStore()
const items = ref([])
const loading = ref(false)

const headers = [
  { title: 'Artikel', key: 'article' },
  { title: 'Bestand', key: 'stock', align: 'end' },
  { title: 'Mindestbestand', key: 'minimum_inventory', align: 'end' },
  { title: 'Fehlmenge', key: 'shortage', align: 'end' },
  { title: 'EK-Preis', key: 'purchase_price', align: 'end' },
  { title: 'Warenwert', key: 'total_value', align: 'end' },
  { title: 'Einheit', key: 'warehouse_unit' },
]

async function fetchData() {
  if (!periodStore.currentPeriodId) return
  loading.value = true
  try {
    const res = await api.get('/reports/below-minimum-stock/', {
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
