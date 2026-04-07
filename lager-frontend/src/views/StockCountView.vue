<template>
  <div>
    <!-- Step 1: Location Selection -->
    <div v-if="step === 1">
      <v-card class="mb-4" flat>
        <v-card-title class="text-h6 pb-0">Bestandszählung</v-card-title>
        <v-card-subtitle>Standort wählen</v-card-subtitle>
      </v-card>

      <v-progress-linear v-if="loadingLocations" indeterminate color="primary" class="mb-2" />

      <v-row dense>
        <v-col v-for="loc in locations" :key="loc.id" cols="6" sm="4">
          <v-btn block size="large" color="primary" variant="tonal" class="location-btn" @click="selectLocation(loc)">
            <v-icon start>mdi-map-marker</v-icon>
            {{ loc.name }}
          </v-btn>
        </v-col>
      </v-row>
    </div>

    <!-- Step 2: Article Counting -->
    <div v-else-if="step === 2">
      <!-- Header bar -->
      <v-card ref="headerRef" flat class="sticky-header" elevation="1">
        <v-card-text class="py-2 px-3">
          <div class="d-flex align-center justify-space-between mb-1">
            <span class="text-subtitle-1 font-weight-bold">{{ selectedLocation.name }}</span>
            <div class="d-flex align-center" style="gap: 8px">
              <span class="text-caption font-weight-medium">{{ countedCount }} / {{ articles.length }} gezählt</span>
              <v-chip v-if="!isOnline" color="warning" size="small" prepend-icon="mdi-wifi-off">Offline</v-chip>
            </div>
          </div>
        </v-card-text>
      </v-card>

      <v-progress-linear v-if="loadingArticles" indeterminate color="primary" />

      <!-- Article sections -->
      <div class="article-list-wrap">
        <template v-for="letter in groupedLetters" :key="letter">
          <div :id="`section-${letter}`" class="letter-header">{{ letter }}</div>
          <v-card v-for="article in articlesByLetter[letter]" :key="article.article_id" class="article-card mx-2 mb-2"
            elevation="1" rounded="lg">
            <!-- Name + formula row -->
            <div class="pa-3 pb-1 d-flex justify-space-between align-start">
              <div class="article-info-block">
                <div class="article-name-text">{{ article.article_name }}</div>
                <div class="text-caption text-medium-emphasis">
                  ID: {{ article.article_id }} &bull; Größe: {{ packageStep(article) }}
                </div>
              </div>
              <div class="formula-block">
                <!-- No sessions yet: show zeroed formula -->
                <template v-if="getSessionsForArticle(article.article_id).length === 0">
                  <div class="formula-line">
                    <span class="f-pkg">0</span><span class="f-hash">&nbsp;#&nbsp;</span><span
                      class="f-op">+&nbsp;</span><span class="f-unit">0</span><span
                      class="f-op">&nbsp;=&nbsp;</span><span class="f-total">0</span>
                  </div>
                </template>
                <!-- Sessions exist -->
                <template v-else>
                  <div v-for="(sess, idx) in getSessionsForArticle(article.article_id)" :key="idx" class="formula-line"
                    :class="{ 'formula-underline': idx === getSessionsForArticle(article.article_id).length - 1 && getSessionsForArticle(article.article_id).length > 1 }">
                    <span class="f-pkg">{{ sess.pkgCount }}</span><span class="f-hash">&nbsp;#&nbsp;</span><span
                      class="f-op">+&nbsp;</span><span class="f-unit">{{ sess.unitCount }}</span><span
                      class="f-op">&nbsp;=&nbsp;</span><span class="f-total">{{ sess.pkgCount * packageStep(article) +
                      sess.unitCount }}</span>
                  </div>
                  <!-- Sum line when multiple sessions -->
                  <div v-if="getSessionsForArticle(article.article_id).length > 1"
                    class="formula-line formula-sum-line">
                    <span class="f-pkg">{{ totalPkgCount(article.article_id) }}</span><span
                      class="f-hash">&nbsp;#&nbsp;</span><span class="f-op">+&nbsp;</span><span class="f-unit">{{
                        totalUnitCount(article.article_id) }}</span><span class="f-op">&nbsp;=&nbsp;</span><span
                      class="f-total">{{ getTotal(article.article_id, article) }}</span>
                  </div>
                </template>
              </div>
            </div>
            <!-- Count buttons -->
            <div class="btn-row pa-2 pt-1">
              <v-btn class="count-btn" color="success" variant="tonal" rounded="lg"
                @click="adjustUnit(article.article_id, 1)">+1</v-btn>
              <v-btn class="count-btn" color="error" variant="tonal" rounded="lg"
                @click="adjustUnit(article.article_id, -1)">-1</v-btn>
              <v-btn class="count-btn" color="success" variant="tonal" rounded="lg"
                @click="adjustPkg(article.article_id, 1)">+{{
                  packageStep(article) }}</v-btn>
              <v-btn class="count-btn" color="warning" variant="tonal" rounded="lg"
                @click="adjustPkg(article.article_id, -1)">-{{
                  packageStep(article) }}</v-btn>
            </div>
          </v-card>
        </template>
        <!-- bottom bar spacer -->
        <div style="height: 72px" />
      </div>

      <!-- Alphabet sidebar -->
      <div class="alpha-sidebar">
        <div v-for="letter in alphabet" :key="letter" class="alpha-letter"
          :class="letterHasArticles(letter) ? 'alpha-active' : 'alpha-inactive'" @click="scrollToLetter(letter)">{{
          letter }}
        </div>
      </div>

      <!-- Bottom action bar -->
      <div class="bottom-bar">
        <v-btn variant="text" @click="goBack">
          <v-icon start>mdi-arrow-left</v-icon>
          Abbrechen
        </v-btn>
        <v-spacer />
        <v-btn color="primary" :loading="saving" prepend-icon="mdi-content-save" @click="save">
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

// --- State ---
const step = ref(1)
const locations = ref([])
const loadingLocations = ref(false)
const loadingArticles = ref(false)
const saving = ref(false)
const isOnline = ref(navigator.onLine)
const headerRef = ref(null)

const selectedLocation = ref(null)
const articles = ref([])

/**
 * Per-article counting sessions.
 * Each session: { pkgCount: number, unitCount: number }
 * A new session is started when the user switches to a different article and comes back.
 */
const articleSessions = ref({})
const lastTouchedId = ref(null)

const snackbar = reactive({ show: false, message: '', color: 'success' })

// --- Alphabet ---
const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'.split('')

// --- Computed ---
const articlesByLetter = computed(() => {
  const groups = {}
  for (const article of articles.value) {
    const first = (article.article_name[0] ?? '').toUpperCase()
    const key = /[A-Z]/.test(first) ? first : '#'
    if (!groups[key]) groups[key] = []
    groups[key].push(article)
  }
  return groups
})

const groupedLetters = computed(() => Object.keys(articlesByLetter.value).sort())

const countedCount = computed(() =>
  articles.value.filter(a => getTotal(a.article_id, a) > 0).length,
)

// --- Helpers ---
function packageStep(article) {
  const s = parseFloat(article.package_size)
  return isNaN(s) || s <= 0 ? 10 : s
}

function getSessionsForArticle(articleId) {
  return articleSessions.value[articleId] ?? []
}

function getTotal(articleId, article) {
  return getSessionsForArticle(articleId).reduce(
    (sum, s) => sum + s.pkgCount * packageStep(article) + s.unitCount,
    0,
  )
}

function totalPkgCount(articleId) {
  return getSessionsForArticle(articleId).reduce((sum, s) => sum + s.pkgCount, 0)
}

function totalUnitCount(articleId) {
  return getSessionsForArticle(articleId).reduce((sum, s) => sum + s.unitCount, 0)
}

function letterHasArticles(letter) {
  return !!articlesByLetter.value[letter]?.length
}

function showSnack(message, color = 'success') {
  snackbar.message = message
  snackbar.color = color
  snackbar.show = true
}

// --- Session management ---
function touchArticle(articleId) {
  if (!articleSessions.value[articleId]) {
    articleSessions.value[articleId] = []
  }
  // Start a new session if this is a different article than the last touched one
  if (lastTouchedId.value !== articleId || articleSessions.value[articleId].length === 0) {
    articleSessions.value[articleId].push({ pkgCount: 0, unitCount: 0 })
    lastTouchedId.value = articleId
  }
}

function currentSession(articleId) {
  const sessions = articleSessions.value[articleId]
  return sessions[sessions.length - 1]
}

function adjustUnit(articleId, delta) {
  touchArticle(articleId)
  const sess = currentSession(articleId)
  sess.unitCount = Math.max(0, sess.unitCount + delta)
}

function adjustPkg(articleId, delta) {
  touchArticle(articleId)
  const sess = currentSession(articleId)
  sess.pkgCount = Math.max(0, sess.pkgCount + delta)
}

// --- Alphabet navigation ---
function scrollToLetter(letter) {
  if (!letterHasArticles(letter)) return
  const el = document.getElementById(`section-${letter}`)
  if (!el) return
  const headerEl = headerRef.value?.$el ?? headerRef.value
  const headerHeight = headerEl?.offsetHeight ?? 72
  const y = el.getBoundingClientRect().top + window.scrollY - headerHeight
  window.scrollTo({ top: y, behavior: 'smooth' })
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
  articleSessions.value = {}
  lastTouchedId.value = null
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
  loadingArticles.value = true
  try {
    const today = new Date().toISOString().split('T')[0]
    const periodRes = await api.get('/periods/by-date/', { params: { date: today } })
    const periodId = periodRes.data.id

    const articlesRes = await api.get('/stock-count/articles/', {
      params: { period_id: periodId, include_base: 'false' },
    })
    articles.value = articlesRes.data
  } catch (err) {
    if (err.response?.status === 404) {
      showSnack('Keine Periode für das gewählte Datum gefunden.', 'warning')
    } else {
      showSnack('Laden fehlgeschlagen.', 'error')
    }
  } finally {
    loadingArticles.value = false
  }
}

// --- Saving ---
function buildPayload() {
  const entries = articles.value
    .map(article => {
      const total = getTotal(article.article_id, article)
      if (total <= 0) return null
      return {
        article_id: article.article_id,
        article_name: article.article_name,
        package_count: totalPkgCount(article.article_id),
        units_per_package: packageStep(article),
        unit_count: totalUnitCount(article.article_id),
      }
    })
    .filter(Boolean)
  return {
    location_id: selectedLocation.value.id,
    location_name: selectedLocation.value.name,
    count_date: new Date().toISOString(),
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
    goBack()
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
  document.body.style.overscrollBehaviorY = 'none'
  window.addEventListener('online', onOnline)
  window.addEventListener('offline', onOffline)
  await loadLocations()
  syncPending()
})

onUnmounted(() => {
  document.body.style.overscrollBehaviorY = ''
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

/* Article list */
.article-list-wrap {
  padding-right: 44px;
  /* room for alpha sidebar */
}

.letter-header {
  font-size: 0.85rem;
  font-weight: 700;
  padding: 6px 16px 2px;
  color: rgba(0, 0, 0, 0.55);
  letter-spacing: 0.05em;
}

.article-card {
  border: 1px solid rgba(0, 0, 0, 0.08);
}

.article-info-block {
  min-width: 0;
  flex: 1;
  margin-right: 12px;
}

.article-name-text {
  font-size: 0.95rem;
  font-weight: 600;
  line-height: 1.3;
}

/* Formula */
.formula-block {
  text-align: right;
  flex-shrink: 0;
}

.formula-line {
  font-size: 1.05rem;
  font-weight: 700;
  line-height: 1.5;
  white-space: nowrap;
}

/* Underline on the last per-session row (before the sum) */
.formula-underline {
  border-bottom: 2px solid rgba(0, 0, 0, 0.2);
  padding-bottom: 1px;
  margin-bottom: 2px;
}

.formula-sum-line {
  /* same style as regular lines; underline on the preceding row provides visual separation */
}

.f-pkg {
  color: #3949ab;
}

/* indigo */
.f-hash {
  color: #e53935;
}

/* red */
.f-op {
  color: #5e35b1;
}

/* deep-purple */
.f-unit {
  color: #2e7d32;
}

/* green */
.f-total {
  color: #3949ab;
}

/* indigo */

/* Count buttons */
.btn-row {
  display: flex;
  gap: 6px;
}

.count-btn {
  flex: 1;
  font-size: 1.2rem !important;
  font-weight: 700 !important;
  height: 56px !important;
}

/* Alphabet sidebar */
.alpha-sidebar {
  position: fixed;
  right: 0;
  top: 0;
  bottom: 56px;
  width: 40px;
  display: flex;
  flex-direction: column;
  align-items: center;
  z-index: 30;
  /* above sticky header and bottom bar */
  overflow-y: auto;
  background: rgb(var(--v-theme-surface));
  border-left: 1px solid rgba(0, 0, 0, 0.08);
  scrollbar-width: none;
  -ms-overflow-style: none;
  pointer-events: auto;
}

.alpha-sidebar::-webkit-scrollbar {
  display: none;
}

.alpha-letter {
  font-size: 0.85rem;
  font-weight: 700;
  width: 100%;
  min-height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  user-select: none;
  flex-shrink: 0;
}

.alpha-active {
  color: rgb(var(--v-theme-primary));
}

.alpha-inactive {
  color: rgba(0, 0, 0, 0.2);
  cursor: default;
  pointer-events: none;
}

/* Bottom bar */
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
</style>
