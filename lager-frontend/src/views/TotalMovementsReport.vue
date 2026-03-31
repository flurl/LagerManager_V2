<template>
  <div>
    <ReportTable :headers="headers" :items="items" :loading="loading" :title="title"
      :csv-filename="csvFilename">
      <template #controls>
        <v-row class="mb-2" align="center">
          <v-col cols="12" sm="auto">
            <v-btn-toggle v-model="movementType" density="compact" variant="outlined" mandatory>
              <v-btn value="delivery">Lieferungen</v-btn>
              <v-btn value="consumption">Verbrauch</v-btn>
            </v-btn-toggle>
          </v-col>
          <v-col cols="12" sm="auto">
            <v-btn-toggle v-model="dateGrouping" density="compact" variant="outlined" mandatory>
              <v-btn value="">Periode</v-btn>
              <v-btn value="year">Jahr</v-btn>
              <v-btn value="year_month">Jahr/Monat</v-btn>
            </v-btn-toggle>
          </v-col>
          <v-col cols="12" sm="auto">
            <v-checkbox v-model="groupByPartner" label="Nach Lieferant gruppieren" density="compact" hide-details />
          </v-col>
        </v-row>
      </template>
      <template #item.total_value="{ item }">{{ item.total_value.toFixed(2) }}</template>
      <template #item.avg_price="{ item }">{{ item.avg_price.toFixed(2) }}</template>
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
const movementType = ref('delivery')
const dateGrouping = ref('')
const groupByPartner = ref(false)

const title = computed(() =>
  movementType.value === 'delivery' ? 'Insgesamt gelieferte Artikel' : 'Insgesamt verbrauchte Artikel'
)

const csvFilename = computed(() =>
  movementType.value === 'delivery' ? 'gesamte_lieferungen.csv' : 'gesamter_verbrauch.csv'
)

const baseHeaders = [
  { title: 'Datum', key: 'date' },
  { title: 'Artikel', key: 'article' },
  { title: 'Anzahl', key: 'quantity', align: 'end' },
  { title: 'Einheit', key: 'unit' },
  { title: 'Warenwert', key: 'total_value', align: 'end' },
  { title: 'Warenwert Durchschnitt', key: 'avg_price', align: 'end' },
]

const partnerHeader = { title: 'Lieferant', key: 'partner' }

const headers = computed(() =>
  groupByPartner.value
    ? [...baseHeaders.slice(0, 2), partnerHeader, ...baseHeaders.slice(2)]
    : baseHeaders
)

async function fetchData() {
  if (!periodStore.currentPeriodId) return
  loading.value = true
  try {
    const params = { period_id: periodStore.currentPeriodId, movement_type: movementType.value }
    if (dateGrouping.value) params.date_grouping = dateGrouping.value
    if (groupByPartner.value) params.group_by_partner = '1'
    const res = await api.get('/reports/total-movements/', { params })
    items.value = res.data.movements ?? res.data
  } finally {
    loading.value = false
  }
}

watch(() => periodStore.currentPeriodId, fetchData)
watch([movementType, dateGrouping, groupByPartner], fetchData)
onMounted(fetchData)
</script>
