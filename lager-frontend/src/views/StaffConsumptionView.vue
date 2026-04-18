<template>
  <div class="consumption-app">
    <!-- Header -->
    <div class="consumption-header">
      <div class="header-title">Personalverbrauch</div>
      <v-btn
        variant="outlined"
        size="small"
        :prepend-icon="showExport ? 'mdi-chevron-up' : 'mdi-export'"
        @click="showExport = !showExport"
      >
        Export
      </v-btn>
    </div>

    <!-- Export Panel -->
    <div v-if="showExport" class="export-panel">
      <!-- Login form if not authenticated -->
      <template v-if="!auth.isAuthenticated">
        <div class="export-login-title">Anmeldung erforderlich für Export</div>
        <v-form @submit.prevent="doLogin">
          <v-text-field
            v-model="loginForm.username"
            label="Benutzername"
            density="compact"
            variant="outlined"
            hide-details
            class="mb-2"
          />
          <v-text-field
            v-model="loginForm.password"
            label="Passwort"
            type="password"
            density="compact"
            variant="outlined"
            hide-details
            class="mb-2"
          />
          <v-alert v-if="loginError" type="error" density="compact" class="mb-2">{{ loginError }}</v-alert>
          <v-btn type="submit" color="primary" size="small" :loading="loginLoading">Anmelden</v-btn>
        </v-form>
      </template>

      <!-- Export actions when logged in -->
      <template v-else>
        <div class="export-actions">
          <v-btn size="small" variant="outlined" @click="showData">Anzeigen</v-btn>
          <v-btn size="small" variant="outlined" @click="downloadCsv">Download</v-btn>
          <v-btn size="small" variant="outlined" color="warning" @click="confirmDeleteOld = true">Alte Daten löschen</v-btn>
          <v-btn size="small" variant="outlined" color="primary" :loading="postLoading" @click="postToLm">Post to LM</v-btn>
          <v-btn size="small" variant="text" @click="auth.logout(); showExport = false">Abmelden</v-btn>
        </div>

        <!-- Show data table -->
        <div v-if="showTable && tableEntries.length > 0" class="data-table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>Datum</th>
                <th>Jahr-Monat</th>
                <th>Abteilung</th>
                <th>Artikel-ID</th>
                <th>Artikel</th>
                <th>Anzahl</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="e in tableEntries" :key="e.key">
                <td>{{ formatTs(e.timestamp) }}</td>
                <td>{{ e.yearMonth }}</td>
                <td>{{ e.departmentName }}</td>
                <td>{{ e.articleId }}</td>
                <td>{{ e.articleName }}</td>
                <td>{{ e.count }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-else-if="showTable" class="export-empty">Keine Daten vorhanden.</div>
      </template>
    </div>

    <!-- Department select -->
    <div class="department-select-wrap">
      <select v-model="selectedDepartment" class="department-select">
        <option value="" disabled>Abteilung wählen...</option>
        <option v-for="dept in departments" :key="dept.id" :value="dept">{{ dept.name }}</option>
      </select>
    </div>

    <!-- Article list -->
    <div v-if="selectedDepartment">
      <div v-if="loadingArticles" class="loading-hint">Lade Artikel...</div>

      <table v-else class="article-table">
        <tbody>
          <tr
            v-for="(article, idx) in articles"
            :key="article.article_id"
            :class="idx % 2 === 1 ? 'row-bisque' : ''"
          >
            <td class="article-name-cell">{{ article.article_name }}</td>
            <td class="count-cell">
              <input type="text" readonly :value="counts[article.article_id] ?? 0" class="count-input" />
            </td>
            <td class="btn-cell">
              <button class="pm-btn" @click="increment(article.article_id)">+</button>
            </td>
            <td class="btn-cell">
              <button class="pm-btn" @click="decrement(article.article_id)">-</button>
            </td>
            <td class="action-cell">
              <button class="save-btn" @click="saveConsumption()">
                Verbrauch übernehmen
              </button>
            </td>
          </tr>

          <!-- Free-text row -->
          <tr :class="articles.length % 2 === 1 ? 'row-bisque' : ''">
            <td class="article-name-cell">
              <input
                v-model="freeTextName"
                type="text"
                placeholder="Freie Eingabe"
                class="free-text-input"
              />
            </td>
            <td class="count-cell">
              <input type="text" readonly :value="freeTextCount" class="count-input" />
            </td>
            <td class="btn-cell">
              <button class="pm-btn" @click="freeTextCount++">+</button>
            </td>
            <td class="btn-cell">
              <button class="pm-btn" @click="freeTextCount = Math.max(0, freeTextCount - 1)">-</button>
            </td>
            <td class="action-cell">
              <button class="save-btn" @click="saveConsumption()">
                Verbrauch übernehmen
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Confirm save consumption -->
    <v-dialog v-model="confirmSave.show" max-width="420" persistent>
      <v-card>
        <v-card-title>Verbrauch übernehmen</v-card-title>
        <v-card-text>
          <div>Abteilung: <strong>{{ confirmSave.departmentName }}</strong></div>
          <div class="mt-2">Folgende Artikel werden gebucht:</div>
          <ul class="mt-1">
            <li v-for="item in confirmSave.items" :key="item.articleId">
              <strong>{{ item.articleName }}</strong> — {{ item.count }}×
            </li>
          </ul>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="confirmSave.show = false">Abbrechen</v-btn>
          <v-btn color="primary" @click="doSaveConfirmed">Übernehmen</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Confirm delete old data -->
    <v-dialog v-model="confirmDeleteOld" max-width="380">
      <v-card>
        <v-card-title>Alte Daten löschen</v-card-title>
        <v-card-text>Alle Daten älter als zwei Monate werden gelöscht. Bist du sicher?</v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="confirmDeleteOld = false">Abbrechen</v-btn>
          <v-btn color="warning" @click="deleteOldData">Löschen</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Snackbar -->
    <v-snackbar v-model="snackbar.show" :color="snackbar.color" :timeout="3000">
      {{ snackbar.message }}
    </v-snackbar>
  </div>
</template>

<script setup>
import { onMounted, ref, watch } from 'vue'
import api from '../api'
import { useAuthStore } from '../stores/auth'
import {
  deleteEntriesByKeys,
  deleteOldEntries,
  getAllEntries,
  saveConsumption as dbSave,
} from '../utils/staffConsumptionDb'

const auth = useAuthStore()

// --- State ---
const departments = ref([])
const selectedDepartment = ref('')
const articles = ref([])
const loadingArticles = ref(false)
const counts = ref({})

const freeTextName = ref('')
const freeTextCount = ref(0)

const showExport = ref(false)
const showTable = ref(false)
const tableEntries = ref([])
const postLoading = ref(false)
const confirmDeleteOld = ref(false)
const confirmSave = ref({ show: false, departmentName: '', items: [] })

const loginForm = ref({ username: '', password: '' })
const loginError = ref('')
const loginLoading = ref(false)

const snackbar = ref({ show: false, message: '', color: 'success' })

// --- Init ---
onMounted(async () => {
  await loadDepartments()
})

// --- Departments ---
async function loadDepartments() {
  const cached = localStorage.getItem('staffConsumption_departments')
  if (cached) {
    departments.value = JSON.parse(cached)
  }
  try {
    const res = await api.get('/staff-consumption/departments/')
    departments.value = res.data
    localStorage.setItem('staffConsumption_departments', JSON.stringify(res.data))
  } catch {
    // use cached if available
  }
}

// --- Department selection ---
async function loadArticles() {
  loadingArticles.value = true
  articles.value = []
  counts.value = {}

  const cacheKey = 'staffConsumption_articles'
  const cached = localStorage.getItem(cacheKey)
  if (cached) {
    articles.value = JSON.parse(cached)
  }

  try {
    const res = await api.get('/staff-consumption/articles/')
    articles.value = res.data
    localStorage.setItem(cacheKey, JSON.stringify(res.data))
  } catch {
    // use cached if available
  }
  loadingArticles.value = false
}

// Watch selectedDepartment
watch(selectedDepartment, (dept) => {
  if (dept) {
    loadArticles()
    counts.value = {}
    freeTextName.value = ''
    freeTextCount.value = 0
    showTable.value = false
  }
})

// --- Count controls ---
function increment(articleId) {
  counts.value[articleId] = (counts.value[articleId] ?? 0) + 1
}

function decrement(articleId) {
  counts.value[articleId] = Math.max(0, (counts.value[articleId] ?? 0) - 1)
}

// --- Save consumption ---
function collectNonZeroItems() {
  const items = []
  for (const article of articles.value) {
    const count = counts.value[article.article_id] ?? 0
    if (count > 0) {
      items.push({ articleId: String(article.article_id), articleName: article.article_name, count })
    }
  }
  if (freeTextName.value.trim() && freeTextCount.value > 0) {
    items.push({
      articleId: `free-text-${freeTextName.value.trim()}`,
      articleName: freeTextName.value.trim(),
      count: freeTextCount.value,
    })
  }
  return items
}

function saveConsumption() {
  const items = collectNonZeroItems()
  if (!items.length) {
    showSnackbar('Keine Artikel ausgewählt.', 'warning')
    return
  }
  confirmSave.value = { show: true, departmentName: selectedDepartment.value.name, items }
}

async function doSaveConfirmed() {
  confirmSave.value.show = false
  const { departmentName, items } = confirmSave.value
  const now = new Date()
  const base = {
    timestamp: Math.floor(now.getTime() / 1000),
    yearMonth: `${now.getFullYear()}-${now.getMonth() + 1}`,
    departmentName,
  }
  for (const item of items) {
    await dbSave({ ...base, articleId: item.articleId, articleName: item.articleName, count: item.count })
  }
  showSnackbar(`${items.length} Artikel gespeichert.`)
  // Reset so the next user must select a department again
  selectedDepartment.value = ''
  articles.value = []
  counts.value = {}
  freeTextName.value = ''
  freeTextCount.value = 0
}

// --- Export ---
async function showData() {
  tableEntries.value = await getAllEntries()
  showTable.value = true
}

async function downloadCsv() {
  const entries = await getAllEntries()
  if (!entries.length) {
    showSnackbar('Keine Daten vorhanden.', 'warning')
    return
  }
  const rows = entries.map((e) =>
    [e.timestamp, e.yearMonth, e.departmentName, e.articleId, e.articleName, e.count].join(';')
  )
  const blob = new Blob([rows.join('\n')], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'personalverbrauch.csv'
  a.click()
  URL.revokeObjectURL(url)
}

async function deleteOldData() {
  confirmDeleteOld.value = false
  const deleted = await deleteOldEntries()
  showSnackbar(`${deleted} alte Einträge gelöscht.`)
  if (showTable.value) await showData()
}

async function postToLm() {
  const entries = await getAllEntries()
  if (!entries.length) {
    showSnackbar('Keine Daten vorhanden.', 'warning')
    return
  }

  // Group entries by (yearMonth, departmentName, consumption_date bucket)
  // We POST each entry individually, grouped by the timestamp they were saved
  // Each IndexedDB entry has its own timestamp → treat each as a separate bulk call
  // Group by: departmentName + yearMonth + date (YYYY-MM-DD)
  /** @type {Map<string, { entries: typeof entries, representativeTs: number }>} */
  const groups = new Map()
  for (const e of entries) {
    const date = new Date(e.timestamp * 1000)
    const dateKey = date.toISOString().slice(0, 10)
    const key = `${e.departmentName}|${e.yearMonth}|${dateKey}`
    if (!groups.has(key)) {
      groups.set(key, { entries: [], representativeTs: e.timestamp })
    }
    groups.get(key).entries.push(e)
  }

  postLoading.value = true
  try {
    const allKeys = []
    for (const [, group] of groups) {
      const consumptionDate = new Date(group.representativeTs * 1000).toISOString()
      const payload = {
        consumption_date: consumptionDate,
        department_name: group.entries[0].departmentName,
        year_month: group.entries[0].yearMonth,
        entries: group.entries.map((e) => ({
          article_id: e.articleId,
          article_name: e.articleName,
          count: e.count,
        })),
      }
      await api.post('/staff-consumption/entries/bulk/', payload)
      allKeys.push(...group.entries.map((e) => e.key))
    }
    await deleteEntriesByKeys(allKeys)
    tableEntries.value = []
    showTable.value = false
    showSnackbar(`${entries.length} Einträge erfolgreich an LM übermittelt und lokal gelöscht.`)
  } catch (err) {
    showSnackbar('Fehler beim Übermitteln an LM. Bitte erneut versuchen.', 'error')
  } finally {
    postLoading.value = false
  }
}

// --- Auth ---
async function doLogin() {
  loginError.value = ''
  loginLoading.value = true
  try {
    await auth.login(loginForm.value.username, loginForm.value.password)
    loginForm.value = { username: '', password: '' }
  } catch {
    loginError.value = 'Anmeldung fehlgeschlagen.'
  } finally {
    loginLoading.value = false
  }
}

// --- Helpers ---
function showSnackbar(message, color = 'success') {
  snackbar.value = { show: true, message, color }
}

function formatTs(ts) {
  return new Date(ts * 1000).toLocaleString('de-AT')
}
</script>

<style scoped>
.consumption-app {
  max-width: 700px;
  margin: 0 auto;
  padding: 12px;
  font-family: sans-serif;
}

.consumption-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.header-title {
  font-size: 1.6rem;
  font-weight: bold;
}

.export-panel {
  background: #f5f5f5;
  border: 1px solid #ccc;
  border-radius: 4px;
  padding: 12px;
  margin-bottom: 16px;
}

.export-login-title {
  font-size: 0.9rem;
  margin-bottom: 8px;
  font-weight: 500;
}

.export-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}

.export-empty {
  color: #888;
  font-size: 0.9rem;
  margin-top: 8px;
}

.data-table-wrap {
  overflow-x: auto;
  margin-top: 8px;
}

.data-table {
  border-collapse: collapse;
  font-size: 0.8rem;
  width: 100%;
}

.data-table th,
.data-table td {
  border: 1px solid #ccc;
  padding: 4px 8px;
  text-align: left;
  white-space: nowrap;
}

.data-table th {
  background: #e0e0e0;
}

.department-select-wrap {
  margin-bottom: 16px;
}

.department-select {
  font-size: 1.2rem;
  padding: 6px 10px;
  border: 1px solid #aaa;
  border-radius: 4px;
  width: 240px;
  max-width: 100%;
}

.loading-hint {
  color: #888;
  padding: 8px 0;
}

.article-table {
  width: 100%;
  border-collapse: collapse;
}

.article-table tr {
  border-bottom: 1px solid #eee;
}

.row-bisque {
  background-color: #ffe4c4;
}

.article-name-cell {
  padding: 8px 6px;
  font-size: 1rem;
  min-width: 120px;
}

.count-cell {
  padding: 4px;
}

.count-input {
  width: 48px;
  text-align: center;
  border: 1px solid #bbb;
  padding: 4px;
  font-size: 1rem;
  background: #fff;
}

.btn-cell {
  padding: 4px 2px;
}

.pm-btn {
  width: 36px;
  height: 36px;
  font-size: 1.2rem;
  border: 1px solid #bbb;
  background: #f8f8f8;
  cursor: pointer;
  border-radius: 2px;
}

.pm-btn:active {
  background: #e0e0e0;
}

.action-cell {
  padding: 4px 6px;
}

.save-btn {
  font-size: 0.85rem;
  padding: 6px 10px;
  border: 1px solid #bbb;
  background: #f8f8f8;
  cursor: pointer;
  border-radius: 2px;
  white-space: nowrap;
}

.save-btn:active {
  background: #e0e0e0;
}

.free-text-input {
  width: 130px;
  border: 1px solid #bbb;
  padding: 4px 6px;
  font-size: 0.95rem;
  border-radius: 2px;
}
</style>
