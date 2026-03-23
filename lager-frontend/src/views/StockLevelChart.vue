<template>
  <div>
    <v-row class="mb-2" align="center">
      <v-col><h2>Lagerstand Verlauf</h2></v-col>
      <v-col cols="auto">
        <v-btn :loading="loading" @click="fetchData">Aktualisieren</v-btn>
      </v-col>
    </v-row>

    <v-row>
      <v-col cols="3">
        <v-card height="600" class="overflow-y-auto">
          <v-card-title class="text-body-2">Artikel</v-card-title>
          <v-checkbox
            v-model="showAll"
            label="Alle"
            density="compact"
            hide-details
            class="px-4"
            @change="toggleAll"
          />
          <v-divider />
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
        <Line v-if="chartData" :data="chartData" :options="chartOptions" style="height: 500px" />
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
const showAll = ref(false)

const allArticles = computed(() =>
  (rawData.value?.datasets || [])
    .filter((d) => !d.label.endsWith('-gezaehlt'))
    .map((d) => d.label)
)

function toggleAll(val) {
  activeArticles.value = val ? [...allArticles.value] : []
}

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
  scales: { x: { ticks: { maxTicksLimit: 15 } } },
}

async function fetchData() {
  if (!periodStore.currentPeriodId) return
  loading.value = true
  try {
    const res = await api.get('/reports/stock-level/', {
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
