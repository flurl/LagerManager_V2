<template>
  <div>
    <!-- Step 1: Location + Date Selection -->
    <div v-if="step === 1">
      <v-card class="mb-4" flat>
        <v-card-title class="text-h6 pb-0">Bestandszählung</v-card-title>
        <v-card-subtitle>Datum und Standort wählen</v-card-subtitle>
        <v-card-text>
          <v-text-field
            v-model="countDateInput"
            label="Datum"
            type="date"
            prepend-inner-icon="mdi-calendar"
            class="mb-4"
            hide-details
          />
        </v-card-text>
      </v-card>

      <v-progress-linear v-if="loadingLocations" indeterminate color="primary" class="mb-2" />

      <v-row dense>
        <v-col v-for="loc in locations" :key="loc.id" cols="6" sm="4">
          <v-btn
            block
            size="large"
            color="primary"
            variant="tonal"
            class="location-btn"
            @click="selectLocation(loc)"
          >
            <v-icon start>mdi-map-marker</v-icon>
            {{ loc.name }}
          </v-btn>
        </v-col>
      </v-row>
    </div>

    <!-- Step 2: Article Counting -->
    <div v-else-if="step === 2">
      <!-- Header bar -->
      <v-card flat class="mb-2 sticky-header" elevation="1">
        <v-card-text class="py-2 px-3">
          <div class="d-flex align-center justify-space-between mb-1">
            <div>
              <span class="text-subtitle-1 font-weight-bold">{{ selectedLocation.name }}</span>
              <span class="text-caption text-medium-emphasis ml-2">{{ countDateInput }}</span>
            </div>
            <v-chip v-if="!isOnline" color="warning" size="small" prepend-icon="mdi-wifi-off">Offline</v-chip>
          </div>
          <v-text-field
            v-model="search"
            placeholder="Suchen…"
            prepend-inner-icon="mdi-magnify"
            clearable
            hide-details
            density="compact"
            variant="outlined"
          />
        </v-card-text>
      </v-card>

      <v-progress-linear v-if="loadingArticles" indeterminate color="primary" class="mb-2" />

      <!-- Article list -->
      <v-list lines="one" class="pa-0 article-list">
        <template v-for="article in filteredArticles" :key="article.article_id">
          <v-list-item class="article-row px-3 py-1">
            <template #prepend>
              <div class="article-info">
                <div class="article-name">{{ article.article_name }}</div>
                <div class="article-id text-caption text-medium-emphasis">{{ article.article_id }}</div>
              </div>
            </template>
            <template #append>
              <div class="counter-controls">
                <v-btn
                  size="small"
                  variant="outlined"
                  color="error"
                  class="counter-btn"
                  @click="adjust(article.article_id, -packageStep(article))"
                >-{{ packageStep(article) }}</v-btn>
                <v-btn
                  size="small"
                  variant="outlined"
                  color="error"
                  class="counter-btn"
                  @click="adjust(article.article_id, -1)"
                >-1</v-btn>
                <div class="quantity-display">
                  <input
                    :value="getQty(article.article_id)"
                    type="number"
                    class="qty-input"
                    min="0"
                    @change="setQty(article.article_id, $event.target.value)"
                    @focus="$event.target.select()"
                  />
                </div>
                <v-btn
                  size="small"
                  variant="outlined"
                  color="success"
                  class="counter-btn"
                  @click="adjust(article.article_id, 1)"
                >+1</v-btn>
                <v-btn
                  size="small"
                  variant="outlined"
                  color="success"
                  class="counter-btn"
                  @click="adjust(article.article_id, packageStep(article))"
                >+{{ packageStep(article) }}</v-btn>
              </div>
            </template>
          </v-list-item>
          <v-divider />
        </template>
      </v-list>

      <!-- Bottom action bar -->
      <div class="bottom-bar">
        <v-btn variant="text" @click="goBack">
          <v-icon start>mdi-arrow-left</v-icon>
          Zurück
        </v-btn>
        <v-spacer />
        <v-btn
          color="primary"
          :loading="saving"
          prepend-icon="mdi-content-save"
          @click="save"
        >
          Speichern
        </v-btn>
      </div>
    </div>

    <!-- Snackbar -->
    <v-snackbar v-model="snackbar.show" :color="snackbar.color" :timeout="3000" location="top">
      {{ snackbar.message }}
    </v-snackbar>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import api from '../api'
import { usePeriodStore } from '../stores/period'

const periodStore = usePeriodStore()

// --- State ---
const step = ref(1)
const locations = ref([])
const loadingLocations = ref(false)
const loadingArticles = ref(false)
const saving = ref(false)
const search = ref('')
const isOnline = ref(navigator.onLine)

const today = new Date().toISOString().split('T')[0]
const countDateInput = ref(today)

const selectedLocation = ref(null)
const articles = ref([])
/** @type {import('vue').Ref<Record<string, number>>} */
const quantities = ref({})

const snackbar = reactive({ show: false, message: '', color: 'success' })

// --- Computed ---
const filteredArticles = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return articles.value
  return articles.value.filter(a => a.article_name.toLowerCase().includes(q) || a.article_id.toLowerCase().includes(q))
})

// --- Helpers ---
function getQty(articleId) {
  return quantities.value[articleId] ?? 0
}

function adjust(articleId, delta) {
  const current = getQty(articleId)
  quantities.value[articleId] = Math.max(0, current + delta)
}

function setQty(articleId, value) {
  const n = parseFloat(value)
  quantities.value[articleId] = isNaN(n) || n < 0 ? 0 : n
}

function packageStep(article) {
  const s = parseFloat(article.package_size)
  return isNaN(s) || s <= 0 ? 10 : s
}

function showSnack(message, color = 'success') {
  snackbar.message = message
  snackbar.color = color
  snackbar.show = true
}

// --- Navigation ---
async function selectLocation(loc) {
  selectedLocation.value = loc
  step.value = 2
  await loadArticles()
}

function goBack() {
  step.value = 1
  articles.value = []
  quantities.value = {}
  search.value = ''
}

// --- Data loading ---
async function loadLocations() {
  loadingLocations.value = true
  try {
    const res = await api.get('/locations/')
    locations.value = res.data.results ?? res.data
  } catch {
    showSnack('Standorte konnten nicht geladen werden.', 'error')
  } finally {
    loadingLocations.value = false
  }
}

async function loadArticles() {
  const periodId = periodStore.currentPeriodId
  if (!periodId) {
    showSnack('Keine Periode ausgewählt.', 'warning')
    return
  }
  loadingArticles.value = true
  try {
    const [articlesRes, entriesRes] = await Promise.allSettled([
      api.get('/stock-count/articles/', { params: { period_id: periodId, include_base: 'false' } }),
      api.get('/stock-count/entries/', {
        params: {
          period_id: periodId,
          location_id: selectedLocation.value.id,
          count_date: countDateInput.value,
        },
      }),
    ])

    if (articlesRes.status === 'fulfilled') {
      articles.value = articlesRes.value.data
    } else {
      showSnack('Artikel konnten nicht geladen werden.', 'error')
    }

    // Pre-fill existing counts for this location+date
    if (entriesRes.status === 'fulfilled') {
      for (const entry of entriesRes.value.data) {
        quantities.value[entry.article_id] = parseFloat(entry.quantity)
      }
    }
  } finally {
    loadingArticles.value = false
  }
}

// --- Saving ---
function buildPayload() {
  const periodId = periodStore.currentPeriodId
  const periodName = periodStore.currentPeriod?.name ?? ''
  const entries = Object.entries(quantities.value)
    .filter(([, qty]) => qty > 0)
    .map(([articleId, qty]) => {
      const article = articles.value.find(a => a.article_id === articleId)
      return {
        article_id: articleId,
        article_name: article?.article_name ?? articleId,
        quantity: qty,
      }
    })
  return {
    period_id: periodId,
    period_name: periodName,
    location_id: selectedLocation.value.id,
    location_name: selectedLocation.value.name,
    count_date: new Date(countDateInput.value + 'T12:00:00').toISOString(),
    entries,
  }
}

async function save() {
  const payload = buildPayload()
  if (!payload.entries.length) {
    showSnack('Keine Mengen erfasst.', 'warning')
    return
  }
  saving.value = true
  try {
    await api.post('/stock-count/entries/bulk/', payload)
    showSnack(`${payload.entries.length} Einträge gespeichert.`)
  } catch (err) {
    if (!navigator.onLine || err.code === 'ERR_NETWORK' || err.message === 'Network Error') {
      queuePendingSave(payload)
      showSnack('Offline gespeichert. Wird synchronisiert sobald online.', 'warning')
    } else {
      showSnack('Fehler beim Speichern.', 'error')
    }
  } finally {
    saving.value = false
  }
}

// --- Offline queue ---
const PENDING_KEY = 'stockcount_pending_saves'

function queuePendingSave(payload) {
  const existing = JSON.parse(localStorage.getItem(PENDING_KEY) || '[]')
  existing.push(payload)
  localStorage.setItem(PENDING_KEY, JSON.stringify(existing))
}

async function syncPending() {
  const raw = localStorage.getItem(PENDING_KEY)
  if (!raw) return
  const queue = JSON.parse(raw)
  if (!queue.length) return

  const remaining = []
  for (const payload of queue) {
    try {
      await api.post('/stock-count/entries/bulk/', payload)
    } catch (err) {
      if (err.response?.status === 401) {
        // JWT expired — keep in queue, user must re-login
        remaining.push(payload)
      }
      // Other errors: drop to avoid infinite retry of bad data
    }
  }

  if (remaining.length === 0) {
    localStorage.removeItem(PENDING_KEY)
    if (queue.length > remaining.length) {
      showSnack(`${queue.length - remaining.length} offline Einträge synchronisiert.`)
    }
  } else {
    localStorage.setItem(PENDING_KEY, JSON.stringify(remaining))
  }
}

function onOnline() {
  isOnline.value = true
  syncPending()
}

function onOffline() {
  isOnline.value = false
}

// --- Lifecycle ---
onMounted(async () => {
  window.addEventListener('online', onOnline)
  window.addEventListener('offline', onOffline)
  await loadLocations()
  syncPending()
})

onUnmounted(() => {
  window.removeEventListener('online', onOnline)
  window.removeEventListener('offline', onOffline)
})
</script>

<style scoped>
.sticky-header {
  position: sticky;
  top: 0;
  z-index: 10;
}

.location-btn {
  min-height: 64px;
  white-space: normal;
  margin-bottom: 8px;
}

.article-row {
  min-height: 56px;
}

.article-info {
  min-width: 0;
  max-width: 140px;
}

.article-name {
  font-size: 0.95rem;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.article-id {
  font-size: 0.7rem;
}

.counter-controls {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

.counter-btn {
  min-width: 42px !important;
  padding: 0 6px !important;
  font-weight: bold;
}

.quantity-display {
  display: flex;
  align-items: center;
  justify-content: center;
}

.qty-input {
  width: 52px;
  text-align: center;
  border: 1px solid rgba(0, 0, 0, 0.38);
  border-radius: 4px;
  padding: 4px 2px;
  font-size: 1rem;
  font-weight: 600;
  background: transparent;
  color: inherit;
}

.qty-input:focus {
  outline: none;
  border-color: rgb(var(--v-theme-primary));
  box-shadow: 0 0 0 1px rgb(var(--v-theme-primary));
}

.bottom-bar {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  display: flex;
  align-items: center;
  padding: 8px 16px;
  background: rgb(var(--v-theme-surface));
  border-top: 1px solid rgba(0, 0, 0, 0.12);
  z-index: 20;
}

.article-list {
  padding-bottom: 72px; /* space for bottom bar */
}
</style>
