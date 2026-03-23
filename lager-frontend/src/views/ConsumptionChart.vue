<template>
  <div>
    <v-row class="mb-2" align="center">
      <v-col><h2>Verbrauch (kumulativ)</h2></v-col>
      <v-col cols="auto">
        <v-btn :loading="loading" @click="fetchData">Aktualisieren</v-btn>
      </v-col>
    </v-row>

    <v-row>
      <v-col cols="3">
        <v-card height="500" class="overflow-y-auto">
          <v-card-title class="text-body-2">Artikel</v-card-title>
          <div v-for="article in allArticles" :key="article" class="px-4">
            <v-checkbox
              v-model="activeArticles"
              :label="article"
              :value="article"
              density="compact"
              hide-details
            />
          </div>
        </v-card>
      </v-col>
      <v-col cols="9">
        <Line v-if="chartData" :data="chartData" :options="chartOptions" style="height: 450px" />
        <v-progress-circular v-else-if="loading" indeterminate />
      </v-col>
    </v-row>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { Line } from 'vue-chartjs'
import {
  Chart as ChartJS, CategoryScale, LinearScale, PointElement, LineElement,
  Title, Tooltip, Legend,
} from 'chart.js'
import { usePeriodStore } from '../stores/period'
import api from '../api'

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend)

const periodStore = usePeriodStore()
const loading = ref(false)
const rawData = ref(null)
const activeArticles = ref([])

const allArticles = computed(() => (rawData.value?.datasets || []).map((d) => d.label))

const COLORS = [
  '#1565C0', '#E53935', '#43A047', '#FB8C00', '#8E24AA',
  '#00ACC1', '#6D4C41', '#F06292', '#546E7A', '#26A69A',
]

const chartData = computed(() => {
  if (!rawData.value) return null
  const datasets = rawData.value.datasets
    .filter((d) => activeArticles.value.includes(d.label))
    .map((d, i) => ({
      label: d.label,
      data: d.data,
      borderColor: COLORS[i % COLORS.length],
      backgroundColor: 'transparent',
      tension: 0.1,
      pointRadius: 2,
    }))
  return { labels: rawData.value.labels, datasets }
})

const chartOptions = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: { legend: { position: 'top' } },
}

async function fetchData() {
  if (!periodStore.currentPeriodId) return
  loading.value = true
  try {
    const res = await api.get('/reports/consumption/', {
      params: { period_id: periodStore.currentPeriodId },
    })
    rawData.value = res.data
  } finally {
    loading.value = false
  }
}

watch(() => periodStore.currentPeriodId, fetchData)
onMounted(fetchData)
</script>
