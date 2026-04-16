<template>
  <ReportTable :headers="headers" :items="items" :loading="loading" title="Gesamtverbrauch"
    csv-filename="gesamtverbrauch.csv">
    <template #controls>
      <v-row class="mb-2" align="center">
        <v-col cols="12" sm="auto">
          <v-btn-toggle v-model="revenueFilter" density="compact" variant="outlined" mandatory>
            <v-btn value="all">Alle</v-btn>
            <v-btn value="umsatz">Umsatz</v-btn>
            <v-btn value="aufwand">Aufwand</v-btn>
          </v-btn-toggle>
        </v-col>
        <v-col cols="12" sm="auto">
          <v-checkbox v-model="includeLmData" label="LM Daten einbeziehen" density="compact" hide-details />
        </v-col>
        <v-col cols="12" sm="auto">
          <v-checkbox v-model="showTableCode" label="Tischcode anzeigen" density="compact" hide-details />
        </v-col>
      </v-row>
    </template>
    <template #item.total="{ item }">{{ item.total.toFixed(3) }}</template>
    <template #item.purchase_price="{ item }">{{ item.purchase_price?.toFixed(4) ?? '—' }}</template>
    <template #item.total_value="{ item }">{{ item.total_value?.toFixed(2) ?? '—' }}</template>
    <template #item.warehouse_unit_multiplier="{ item }">{{ item.warehouse_unit_multiplier?.toFixed(4) ?? '—' }}</template>
  </ReportTable>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { usePeriodStore } from '../../stores/period'
import api from '../../api'
import ReportTable from '../../components/ReportTable.vue'

const periodStore = usePeriodStore()
const items = ref([])
const loading = ref(false)
const revenueFilter = ref('all')
const includeLmData = ref(true)
const showTableCode = ref(false)

const baseHeaders = [
  { title: 'Artikel', key: 'article' },
  { title: 'Gesamtmenge', key: 'total', align: 'end' },
  { title: 'EK-Preis', key: 'purchase_price', align: 'end' },
  { title: 'Warenwert', key: 'total_value', align: 'end' },
  { title: 'Einheit', key: 'warehouse_unit' },
  { title: 'Multiplikator', key: 'warehouse_unit_multiplier', align: 'end' },
]

const tableCodeHeader = { title: 'Tisch', key: 'table_code' }

const headers = computed(() =>
  showTableCode.value
    ? [baseHeaders[0], tableCodeHeader, ...baseHeaders.slice(1)]
    : baseHeaders
)

async function fetchData() {
  if (!periodStore.currentPeriodId) return
  loading.value = true
  try {
    const res = await api.get('/reports/consumption-totals/', {
      params: {
        period_id: periodStore.currentPeriodId,
        revenue_filter: revenueFilter.value,
        include_lm_data: includeLmData.value ? '1' : '0',
        show_table_code: showTableCode.value ? '1' : '0',
      },
    })
    items.value = res.data
  } finally {
    loading.value = false
  }
}

watch(() => periodStore.currentPeriodId, fetchData)
watch([revenueFilter, includeLmData, showTableCode], fetchData)
onMounted(fetchData)
</script>
