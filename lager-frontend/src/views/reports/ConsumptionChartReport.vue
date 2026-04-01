<template>
  <div>
    <v-row class="mb-2" align="center">
      <v-col>
        <h2>Verbrauch (kumulativ)</h2>
      </v-col>
      <v-col cols="auto">
        <v-btn variant="text" @click="chartRef?.chart.resetZoom()">Zoom zurücksetzen</v-btn>
        <v-btn :loading="loading" @click="fetchData">Aktualisieren</v-btn>
      </v-col>
    </v-row>

    <v-row class="mb-2">
      <v-col>
        <v-autocomplete v-model="activeArticles" :items="allArticles" label="Artikel" multiple chips closable-chips clearable
          density="compact" hide-details>
          <template #prepend-item>
            <v-list-item title="Alle" @click="toggleAll">
              <template #prepend>
                <v-checkbox-btn :model-value="activeArticles.length === allArticles.length"
                  :indeterminate="activeArticles.length > 0 && activeArticles.length < allArticles.length" />
              </template>
            </v-list-item>
            <v-divider />
          </template>
        </v-autocomplete>
      </v-col>
    </v-row>
    <v-row>
      <v-col cols="12">
        <Line v-if="chartData" ref="chartRef" :data="chartData" :options="chartOptions" style="height: 450px" />
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
import zoomPlugin from 'chartjs-plugin-zoom'
import { usePeriodStore } from '../../stores/period'
import api from '../../api'

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend, zoomPlugin)

const periodStore = usePeriodStore()
const chartRef = ref(null)
const loading = ref(false)
const rawData = ref(null)
const activeArticles = ref([])

const allArticles = computed(() => (rawData.value?.datasets || []).map((d) => d.label))

function toggleAll() {
  activeArticles.value = activeArticles.value.length === allArticles.value.length ? [] : [...allArticles.value]
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
  plugins: {
    legend: { position: 'top' },
    zoom: {
      zoom: { wheel: { enabled: true }, pinch: { enabled: true }, mode: 'xy' },
      pan: { enabled: true, mode: 'xy' },
    },
  },
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
