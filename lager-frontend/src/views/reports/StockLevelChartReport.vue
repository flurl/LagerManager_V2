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

    <v-row v-if="hasHiddenArticles || hasNegativeArticles || hasCountedData" class="mb-2" align="center">
      <v-col v-if="hasHiddenArticles" cols="auto">
        <v-chip color="warning" size="small" prepend-icon="mdi-eye-off">
          {{ hiddenCount }} Artikel ausgeblendet
        </v-chip>
      </v-col>
      <v-col v-if="hasHiddenArticles" cols="auto">
        <v-checkbox v-model="showHidden" label="Ausgeblendete anzeigen" density="compact" hide-details />
      </v-col>
      <v-col v-if="hasNegativeArticles" cols="auto">
        <v-checkbox v-model="showNegativeOnly" label="Minusstände" density="compact" hide-details />
      </v-col>
      <v-col v-if="hasCountedData" cols="auto">
        <v-checkbox v-model="showCountDiff" label="Zählungen diff anzeigen" density="compact" hide-details />
      </v-col>
      <v-col v-if="hasCountedData" cols="auto">
        <v-checkbox v-model="onlyCountedDays" label="Nur Tage mit Zählung anzeigen" density="compact" hide-details />
      </v-col>
    </v-row>

    <v-row class="mb-2">
      <v-col>
        <v-autocomplete v-model="activeArticles" :items="allArticles" label="Artikel" multiple chips closable-chips
          clearable density="compact" hide-details>
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
import { useHiddenArticles } from '../../composables/useHiddenArticles'
import api from '../../api'

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend, zoomPlugin)

const periodStore = usePeriodStore()
const chartRef = ref(null)
const loading = ref(false)
const rawData = ref(null)
const activeArticles = ref([])

const { hasHiddenArticles, hiddenCount, showHidden, shouldInclude } = useHiddenArticles()

const showNegativeOnly = ref(false)
const showCountDiff = ref(false)
const onlyCountedDays = ref(false)

const articlesWithNegative = computed(() => {
  const result = new Set()
    ; (rawData.value?.datasets || []).forEach((d) => {
      if (d.data.some((v) => v < 0)) result.add(d.label)
    })
  return result
})

const hasNegativeArticles = computed(() => articlesWithNegative.value.size > 0)
const hasCountedData = computed(() => (rawData.value?.counted_datasets?.length ?? 0) > 0)

// Per-day flag: true if at least one article has a physical count that day.
// Same length as labels (never sliced), so the x/y scales — and any active
// zoom/pan — stay put when this filter is toggled; only the data points change.
const countedDayMask = computed(() => {
  const labels = rawData.value?.labels || []
  const countedDatasets = rawData.value?.counted_datasets || []
  return labels.map((_, i) => countedDatasets.some((d) => d.data[i] != null))
})

const COLORS = [
  '#1565C0', '#E53935', '#43A047', '#FB8C00', '#8E24AA',
  '#00ACC1', '#6D4C41', '#F06292', '#546E7A', '#26A69A',
]

// Shift a hex color towards lighter/darker to derive a related but distinct shade.
function shadeColor(hex, percent) {
  const num = parseInt(hex.slice(1), 16)
  const r = Math.min(255, Math.max(0, (num >> 16) + Math.round(2.55 * percent)))
  const g = Math.min(255, Math.max(0, ((num >> 8) & 0xff) + Math.round(2.55 * percent)))
  const b = Math.min(255, Math.max(0, (num & 0xff) + Math.round(2.55 * percent)))
  return `#${((r << 16) | (g << 8) | b).toString(16).padStart(6, '0')}`
}

const allArticles = computed(() =>
  (rawData.value?.datasets || [])
    .map((d) => d.label)
    .filter((label) => shouldInclude(label) && (!showNegativeOnly.value || articlesWithNegative.value.has(label)))
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

  const mask = onlyCountedDays.value ? countedDayMask.value : null
  const pick = (arr) => mask ? arr.map((v, i) => (mask[i] ? v : null)) : arr

  const stockDatasets = rawData.value.datasets
    .filter((d) => shouldInclude(d.label) && activeArticles.value.includes(d.label))
    .map((d) => {
      const data = pick(d.data)
      return {
        label: d.label,
        data,
        borderColor: colorMap.value[d.label],
        backgroundColor: 'transparent',
        tension: 0.1,
        spanGaps: true,
        pointRadius: data.map((v) => v < 0 ? 6 : 2),
        pointStyle: data.map((v) => v < 0 ? 'triangle' : 'circle'),
        pointBackgroundColor: data.map((v) => v < 0 ? '#E53935' : 'transparent'),
        pointBorderColor: data.map((v) => v < 0 ? '#E53935' : colorMap.value[d.label]),
      }
    })

  const countedDatasets = (rawData.value.counted_datasets || [])
    .filter((d) => {
      const articleName = d.label.replace('-gezaehlt', '')
      return shouldInclude(articleName) && activeArticles.value.includes(articleName)
    })
    .map((d) => {
      const articleName = d.label.replace('-gezaehlt', '')
      const countedColor = shadeColor(colorMap.value[articleName], +35)
      const stockDataset = rawData.value.datasets.find((s) => s.label === articleName)
      const countedData = pick(d.data)
      const stockData = pick(stockDataset?.data || [])
      const data = showCountDiff.value
        ? countedData.map((v, i) => (v != null && stockData[i] != null) ? v - stockData[i] : null)
        : countedData
      return {
        label: d.label,
        data,
        borderColor: countedColor,
        backgroundColor: countedColor,
        showLine: true,
        borderWidth: 1,
        spanGaps: true,
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
        label: (context) => {
          if (context.dataset.label.endsWith('-gezaehlt') && showCountDiff.value) {
            // Y-axis holds the diff while this mode is on — show the actual count instead
            const originalCount = rawData.value?.counted_datasets?.find((d) => d.label === context.dataset.label)?.data?.[context.dataIndex]
            const fmt = (v) => Number.isInteger(v) ? String(v) : v.toFixed(2)
            return `${context.dataset.label}: ${originalCount == null ? '-' : fmt(originalCount)}`
          }
          return `${context.dataset.label}: ${context.formattedValue}`
        },
        afterLabel: (context) => {
          if (context.dataset.label.endsWith('-gezaehlt')) {
            const articleName = context.dataset.label.replace('-gezaehlt', '')
            const stockDataset = rawData.value?.datasets?.find((d) => d.label === articleName)
            const stockValue = stockDataset?.data?.[context.dataIndex]
            const fmt = (v) => Number.isInteger(v) ? String(v) : v.toFixed(2)
            if (showCountDiff.value) {
              // Y-axis already holds the diff (count - stock) in this mode
              if (context.parsed.y == null) return []
              const diff = context.parsed.y
              const sign = diff >= 0 ? '+' : ''
              return [`  Diff: ${sign}${fmt(diff)}`]
            } else {
              // Y-axis is count — show the diff in the tooltip
              if (stockValue == null || context.parsed.y == null) return []
              const diff = context.parsed.y - stockValue
              const sign = diff >= 0 ? '+' : ''
              return [`  Diff: ${sign}${fmt(diff)}`]
            }
          }
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

watch(showNegativeOnly, () => {
  activeArticles.value = activeArticles.value.filter((a) => allArticles.value.includes(a))
})

watch(() => periodStore.currentPeriodId, fetchData)
onMounted(fetchData)
</script>
