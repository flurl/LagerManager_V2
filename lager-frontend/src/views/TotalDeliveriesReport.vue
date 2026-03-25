<template>
  <div>
    <v-row class="mb-2" align="center">
      <v-col><h2>Gesamte Lieferungen</h2></v-col>
      <v-col cols="auto">
        <v-btn prepend-icon="mdi-download" @click="exportCsvAction">CSV</v-btn>
      </v-col>
    </v-row>

    <div v-for="(month, key) in byMonth" :key="key" class="mb-4">
      <v-card-title class="text-subtitle-1 font-weight-bold pa-2 bg-grey-lighten-4">
        {{ formatMonth(key) }}
        — Netto: {{ data.monthly_totals[key]?.net.toFixed(2) }} €
        / Brutto: {{ data.monthly_totals[key]?.gross.toFixed(2) }} €
      </v-card-title>
      <v-data-table
        :headers="headers"
        :items="month"
        density="compact"
        hide-default-footer
        :items-per-page="-1"
      >
        <template #item.date="{ item }">{{ item.date }}</template>
        <template #item.net="{ item }">{{ item.net.toFixed(2) }} €</template>
        <template #item.gross="{ item }">{{ item.gross.toFixed(2) }} €</template>
      </v-data-table>
    </div>

    <v-card v-if="data" class="pa-4 mt-2">
      <strong>Jahresgesamt — Netto: {{ data.grand_total_net?.toFixed(2) }} € / Brutto: {{ data.grand_total_gross?.toFixed(2) }} €</strong>
    </v-card>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { usePeriodStore } from '../stores/period'
import { useCsvExport } from '../composables/useCsvExport'
import api from '../api'

const periodStore = usePeriodStore()
const { exportCsv } = useCsvExport()
const data = ref(null)
const loading = ref(false)

const headers = [
  { title: 'Datum', key: 'date' },
  { title: 'Partner', key: 'partner' },
  { title: 'Kommentar', key: 'comment' },
  { title: 'Netto', key: 'net', align: 'end' },
  { title: 'Brutto', key: 'gross', align: 'end' },
]

const byMonth = computed(() => {
  if (!data.value) return {}
  const groups = {}
  for (const d of data.value.deliveries) {
    if (!groups[d.month]) groups[d.month] = []
    groups[d.month].push(d)
  }
  return groups
})

function formatMonth(key) {
  const [year, month] = key.split('-')
  return new Date(year, month - 1).toLocaleDateString('de-AT', { month: 'long', year: 'numeric' })
}

async function fetchData() {
  if (!periodStore.currentPeriodId) return
  loading.value = true
  try {
    const res = await api.get('/reports/total-deliveries/', {
      params: { period_id: periodStore.currentPeriodId },
    })
    data.value = res.data
  } finally {
    loading.value = false
  }
}

function exportCsvAction() {
  if (!data.value) return
  exportCsv(['date', 'partner', 'comment', 'net', 'gross'], data.value.deliveries, 'gesamte_lieferungen.csv')
}

watch(() => periodStore.currentPeriodId, fetchData)
onMounted(fetchData)
</script>
