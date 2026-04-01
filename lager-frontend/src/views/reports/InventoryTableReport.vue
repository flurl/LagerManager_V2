<template>
  <div>
    <v-row class="mb-2" align="center">
      <v-col><h2>Inventur</h2></v-col>
      <v-col cols="auto">
        <v-btn prepend-icon="mdi-download" @click="exportCsvAction">CSV</v-btn>
      </v-col>
    </v-row>

    <v-data-table
      :headers="headers"
      :items="items"
      :loading="loading"
      density="compact"
    >
      <template #item.quantity="{ item }">{{ item.quantity.toFixed(3) }}</template>
      <template #item.purchase_price="{ item }">{{ item.purchase_price.toFixed(4) }} €</template>
      <template #item.total_value="{ item }">{{ item.total_value.toFixed(2) }} €</template>
      <template #body.append>
        <tr>
          <td colspan="3"><strong>Gesamt</strong></td>
          <td class="text-right"><strong>{{ grandTotal.toFixed(2) }} €</strong></td>
        </tr>
      </template>
    </v-data-table>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { usePeriodStore } from '../../stores/period'
import { useCsvExport } from '../../composables/useCsvExport'
import api from '../../api'

const periodStore = usePeriodStore()
const { exportCsv } = useCsvExport()
const items = ref([])
const loading = ref(false)

const headers = [
  { title: 'Artikel', key: 'article_name' },
  { title: 'Menge', key: 'quantity', align: 'end' },
  { title: 'EK-Preis', key: 'purchase_price', align: 'end' },
  { title: 'Gesamtwert', key: 'total_value', align: 'end' },
]

const grandTotal = computed(() =>
  items.value.reduce((s, i) => s + Number(i.total_value), 0)
)

async function fetchData() {
  if (!periodStore.currentPeriodId) return
  loading.value = true
  try {
    const res = await api.get('/reports/inventory/', {
      params: { period_id: periodStore.currentPeriodId },
    })
    items.value = res.data
  } finally {
    loading.value = false
  }
}

function exportCsvAction() {
  exportCsv(
    ['article_name', 'quantity', 'purchase_price', 'total_value'],
    items.value,
    'inventur.csv'
  )
}

watch(() => periodStore.currentPeriodId, fetchData)
onMounted(fetchData)
</script>
