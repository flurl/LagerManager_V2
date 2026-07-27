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
      <v-col cols="auto">
        <v-checkbox v-model="onlyCountedDays" label="Nur Tage mit Zählung anzeigen" density="compact" hide-details />
      </v-col>
    </v-row>

    <v-expand-transition>
      <v-sheet v-if="showCountDiff && hasCountedData" class="mb-2 pl-4 py-2 border-s-md" color="transparent">
        <v-row align="center" dense>
          <v-col cols="auto">
            <v-checkbox v-model="showTrendLine" label="Ausgleichgerade" density="compact" hide-details />
          </v-col>
          <v-col cols="12" sm="4" md="3">
            <v-slider v-model="relSlopeThreshold" label="Rel. Steigung Grenzwert (%/Tag)" :disabled="!showTrendLine"
              min="0" max="50" step="1" thumb-label density="compact" hide-details />
          </v-col>
          <v-col cols="auto">
            <v-checkbox v-model="minMeanStockEnabled" label="Min. Stand" :disabled="!showTrendLine" density="compact"
              hide-details />
          </v-col>
          <v-col cols="auto" style="width: 5em">
            <v-text-field v-model.number="minMeanStock" label="Min St." :disabled="!showTrendLine || !minMeanStockEnabled"
              type="number" min="0" step="1" density="compact" hide-details />
          </v-col>
          <v-col cols="12" sm="4" md="3">
            <v-slider v-model="slopeThreshold" label="Steigung Grenzwert" :disabled="!showTrendLine" min="0" max="5"
              step="0.1" thumb-label density="compact" hide-details />
          </v-col>
          <v-col cols="12" sm="4" md="3">
            <v-slider v-model="r2Threshold" label="R² Grenzwert" :disabled="!showTrendLine" min="0" max="1" step="0.01"
              thumb-label density="compact" hide-details />
          </v-col>
        </v-row>
      </v-sheet>
    </v-expand-transition>

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
import { toFont } from 'chart.js/helpers'
import zoomPlugin from 'chartjs-plugin-zoom'
import { usePeriodStore } from '../../stores/period'
import { useHiddenArticles } from '../../composables/useHiddenArticles'
import api from '../../api'

// Chart.js's horizontal (top) legend only reserves single-line height per item —
// unlike the vertical legend, it ignores multi-line array `text` — so the
// Ausgleichgerade legend's second line gets clipped by the plot area. Patch each
// chart's legend.fit() to add the missing height for the tallest multi-line item.
const legendMultilineFix = {
  id: 'legendMultilineFix',
  afterInit(chart) {
    const legend = chart.legend
    if (!legend) return
    const originalFit = legend.fit.bind(legend)
    legend.fit = function () {
      originalFit()
      const maxLines = this.legendItems.reduce(
        (max, item) => Math.max(max, Array.isArray(item.text) ? item.text.length : 1), 1)
      if (maxLines > 1) {
        this.height += (maxLines - 1) * toFont(this.options.labels.font).lineHeight
      }
    }
  },
}

ChartJS.register(
  CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend, zoomPlugin, legendMultilineFix,
)

const periodStore = usePeriodStore()
const chartRef = ref(null)
const loading = ref(false)
const rawData = ref(null)
const activeArticles = ref([])

const { hasHiddenArticles, hiddenCount, showHidden, shouldInclude } = useHiddenArticles()

const showNegativeOnly = ref(false)
const showCountDiff = ref(false)
const showTrendLine = ref(false)
const r2Threshold = ref(1)
const slopeThreshold = ref(0)
const relSlopeThreshold = ref(0)
const minMeanStockEnabled = ref(true)
const minMeanStock = ref(5)
const onlyCountedDays = ref(false)

watch(showCountDiff, (enabled) => {
  if (!enabled) showTrendLine.value = false
})

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

const TREND_SUFFIX = '-ausgleichsgerade'

// Ordinary least squares fit (y = slope*x + intercept) over non-null points,
// plus R² (coefficient of determination) as a goodness-of-fit measure.
function leastSquaresFit(points) {
  const n = points.length
  if (n < 2) return null
  let sumX = 0, sumY = 0, sumXY = 0, sumXX = 0
  for (const { x, y } of points) {
    sumX += x
    sumY += y
    sumXY += x * y
    sumXX += x * x
  }
  const denom = n * sumXX - sumX * sumX
  if (denom === 0) return null
  const slope = (n * sumXY - sumX * sumY) / denom
  const intercept = (sumY - slope * sumX) / n

  const meanY = sumY / n
  let ssRes = 0, ssTot = 0
  for (const { x, y } of points) {
    const yHat = slope * x + intercept
    ssRes += (y - yHat) ** 2
    ssTot += (y - meanY) ** 2
  }
  const r2 = ssTot === 0 ? 1 : 1 - ssRes / ssTot

  return { slope, intercept, r2 }
}

function average(values) {
  return values.length ? values.reduce((sum, v) => sum + v, 0) / values.length : 0
}

// Best-fit slope/R² of the count-vs-stock trend line per article, plus the
// average stock level and slope relative to it (%/day) — normalizing the
// slope this way keeps a small loss on a rarely-stocked article and a large
// loss on a heavily-stocked one comparable, independent of the current
// article selection so it can be used to filter the selectable article list.
const articleFitMap = computed(() => {
  const map = {}
  if (!rawData.value) return map;
  (rawData.value.counted_datasets || []).forEach((d) => {
    const articleName = d.label.replace('-gezaehlt', '')
    const stockDataset = rawData.value.datasets.find((s) => s.label === articleName)
    if (!stockDataset) return
    const points = d.data
      .map((v, i) => {
        const stockValue = stockDataset.data[i]
        return { x: i, y: (v != null && stockValue != null) ? v - stockValue : null }
      })
      .filter((p) => p.y != null)
    const fit = leastSquaresFit(points)
    if (!fit) return
    const meanStock = average(stockDataset.data.filter((v) => v != null))
    const relSlopePercent = meanStock ? (fit.slope / meanStock) * 100 : null
    map[articleName] = { ...fit, meanStock, relSlopePercent }
  })
  return map
})

const allArticles = computed(() =>
  (rawData.value?.datasets || [])
    .map((d) => d.label)
    .filter((label) => shouldInclude(label)
      && (!showNegativeOnly.value || articlesWithNegative.value.has(label))
      && (!showTrendLine.value || articleFitMap.value[label]?.r2 <= r2Threshold.value)
      && (!showTrendLine.value || Math.abs(articleFitMap.value[label]?.slope) >= slopeThreshold.value)
      && (!showTrendLine.value || Math.abs(articleFitMap.value[label]?.relSlopePercent) >= relSlopeThreshold.value)
      && (!showTrendLine.value || !minMeanStockEnabled.value || articleFitMap.value[label]?.meanStock >= minMeanStock.value))
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

  const trendDatasets = []
  if (showCountDiff.value && showTrendLine.value) {
    countedDatasets.forEach((d) => {
      const articleName = d.label.replace('-gezaehlt', '')
      const fit = articleFitMap.value[articleName]
      if (!fit) return
      trendDatasets.push({
        label: `${articleName}${TREND_SUFFIX}`,
        data: rawData.value.labels.map((_, i) => fit.slope * i + fit.intercept),
        borderColor: colorMap.value[articleName],
        backgroundColor: 'transparent',
        borderWidth: 1.5,
        borderDash: [6, 4],
        pointRadius: 0,
        r2: fit.r2,
        slope: fit.slope,
        meanStock: fit.meanStock,
        relSlopePercent: fit.relSlopePercent,
      })
    })
  }

  return { labels: rawData.value.labels, datasets: [...stockDatasets, ...countedDatasets, ...trendDatasets] }
})

const chartOptions = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: {
      position: 'top',
      labels: {
        filter: (item) => !(Array.isArray(item.text) ? item.text.join(' ') : item.text).endsWith('-gezaehlt'),
        generateLabels: (chart) => {
          const items = ChartJS.defaults.plugins.legend.labels.generateLabels(chart)
          items.forEach((item) => {
            const dataset = chart.data.datasets[item.datasetIndex]
            if (dataset?.label?.endsWith(TREND_SUFFIX) && dataset.r2 != null) {
              const articleName = dataset.label.replace(TREND_SUFFIX, '')
              const relSlope = dataset.relSlopePercent != null ? `${dataset.relSlopePercent.toFixed(1)}%/Tag` : '–'
              item.text = [
                `${articleName} Ausgleichgerade`,
                `(R²=${dataset.r2.toFixed(2)}, Ø-Bestand=${dataset.meanStock.toFixed(1)}, Steigung=${dataset.slope.toFixed(2)}, rel.=${relSlope})`,
              ]
            }
          })
          return items
        },
      },
    },
    tooltip: {
      callbacks: {
        label: (context) => {
          if (context.dataset.label.endsWith(TREND_SUFFIX)) {
            const articleName = context.dataset.label.replace(TREND_SUFFIX, '')
            return `${articleName} (Ausgleichgerade): ${context.formattedValue}`
          }
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

watch(
  [showNegativeOnly, showTrendLine, r2Threshold, slopeThreshold, relSlopeThreshold, minMeanStockEnabled, minMeanStock],
  () => {
    activeArticles.value = activeArticles.value.filter((a) => allArticles.value.includes(a))
  },
)

watch(() => periodStore.currentPeriodId, fetchData)
onMounted(fetchData)
</script>
