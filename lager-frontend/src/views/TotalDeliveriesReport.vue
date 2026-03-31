<template>
  <div>
    <ReportTable
      :headers="headers"
      :items="items"
      :loading="loading"
      title="Gesamte Lieferungen"
      csv-filename="gesamte_lieferungen.csv"
    >
      <template #item.net="{ item }">{{ item.net.toFixed(2) }} €</template>
      <template #item.gross="{ item }">{{ item.gross.toFixed(2) }} €</template>
      <template #body.append>
        <tr>
          <td colspan="3"><strong>Jahresgesamt</strong></td>
          <td class="text-right"><strong>{{ grandTotalNet.toFixed(2) }} €</strong></td>
          <td class="text-right"><strong>{{ grandTotalGross.toFixed(2) }} €</strong></td>
        </tr>
      </template>
    </ReportTable>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { usePeriodStore } from '../stores/period'
import api from '../api'
import ReportTable from '../components/ReportTable.vue'

const periodStore = usePeriodStore()
const items = ref([])
const loading = ref(false)

const headers = [
  { title: 'Datum', key: 'date' },
  { title: 'Partner', key: 'partner' },
  { title: 'Kommentar', key: 'comment' },
  { title: 'Netto', key: 'net', align: 'end' },
  { title: 'Brutto', key: 'gross', align: 'end' },
]

const grandTotalNet = computed(() => items.value.reduce((s, i) => s + Number(i.net), 0))
const grandTotalGross = computed(() => items.value.reduce((s, i) => s + Number(i.gross), 0))

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
