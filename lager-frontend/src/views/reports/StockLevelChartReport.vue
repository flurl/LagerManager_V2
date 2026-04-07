<template>
  <div>
    <v-row class="mb-2" align="center">
      <v-col>
        <h2>Lagerstand Verlauf</h2>
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
        <Line v-if="chartData" ref="chartRef" :data="chartData" :options="chartOptions" style="height: 500px" />
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

const COLORS = [
  '#1565C0', '#E53935', '#43A047', '#FB8C00', '#8E24AA',
  '#00ACC1', '#6D4C41', '#F06292', '#546E7A', '#26A69A',
]

const allArticles = computed(() =>
  (rawData.value?.datasets || [])
    .map((d) => d.label)
)

// Stable color map keyed by article name so colors don't shift when filtering
const colorMap = computed(() => {
  const map = {}
  allArticles.value.forEach((name, i) => { map[name] = COLORS[i % COLORS.length] })
  return map
})

function toggleAll() {
  activeArticles.value = activeArticles.value.length === allArticles.value.length ? [] : [...allArticles.value]
}

const chartData = computed(() => {
  if (!rawData.value) return null

  const stockDatasets = rawData.value.datasets
    .filter((d) => activeArticles.value.includes(d.label))
    .map((d) => ({
      label: d.label,
      data: d.data,
      borderColor: colorMap.value[d.label],
      backgroundColor: 'transparent',
      tension: 0.1,
      pointRadius: 2,
    }))

  const countedDatasets = (rawData.value.counted_datasets || [])
    .filter((d) => activeArticles.value.includes(d.label.replace('-gezaehlt', '')))
    .map((d) => {
      const articleName = d.label.replace('-gezaehlt', '')
      return {
        label: d.label,
        data: d.data,
        borderColor: colorMap.value[articleName],
        backgroundColor: colorMap.value[articleName],
        showLine: false,
        pointRadius: 6,
        pointStyle: 'rectRot',
      }
    })

  return { labels: rawData.value.labels, datasets: [...stockDatasets, ...countedDatasets] }
})

const chartOptions = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: {
      position: 'top',
      labels: { filter: (item) => !item.text.endsWith('-gezaehlt') },
    },
    tooltip: {
      callbacks: {
        afterLabel: (context) => {
          if (context.dataset.label.endsWith('-gezaehlt')) return []
          const movements = rawData.value?.movement_meta?.[context.label]?.[context.dataset.label]
          if (!movements?.length) return []
          return movements.map((m) => {
            const typeLabel = m.type === 'delivery' ? 'Lieferung' : 'Verbrauch'
            return `  ${typeLabel}: ${m.partner} (${m.quantity})`
          })
        },
      },
    },
    zoom: {
      zoom: { wheel: { enabled: true }, pinch: { enabled: true }, mode: 'xy' },
      pan: { enabled: true, mode: 'xy' },
    },
  },
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
