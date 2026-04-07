<template>
  <div>
    <v-row class="mb-2" align="center">
      <v-col><h2>Zählergebnisse</h2></v-col>
      <v-col cols="auto">
        <v-btn color="primary" prepend-icon="mdi-plus" @click="openNew">Neu</v-btn>
      </v-col>
    </v-row>

    <!-- Filters -->
    <v-row dense class="mb-3">
      <v-col cols="12" sm="4">
        <v-select
          v-model="filterLocationId"
          :items="locations"
          item-title="name"
          item-value="id"
          label="Standort"
          clearable
          hide-details
          density="compact"
          @update:model-value="fetchItems"
        />
      </v-col>
      <v-col cols="12" sm="3">
        <v-text-field
          v-model="filterDate"
          label="Datum"
          type="date"
          clearable
          hide-details
          density="compact"
          @update:model-value="fetchItems"
        />
      </v-col>
    </v-row>

    <v-data-table
      :headers="headers"
      :items="items"
      :loading="loading"
      :items-per-page="100"
      density="compact"
    >
      <template #item.count_date="{ item }">
        {{ formatDate(item.count_date) }}
      </template>
      <template #item.quantity="{ item }">
        <span v-if="item.package_count > 0 || item.unit_count > 0">
          {{ item.package_count }}&nbsp;#&nbsp;+&nbsp;{{ item.unit_count }}&nbsp;=&nbsp;{{ item.quantity }}
        </span>
        <span v-else>{{ item.quantity }}</span>
      </template>
      <template #item.actions="{ item }">
        <v-icon size="small" @click="openEdit(item)">mdi-pencil</v-icon>
        <v-icon size="small" class="ml-1" color="error" @click="deleteItem(item)">mdi-delete</v-icon>
        <v-icon size="small" class="ml-1" color="primary" @click="openImportDialog(item)">mdi-import</v-icon>
      </template>
    </v-data-table>

    <v-dialog v-model="dialog" max-width="480">
      <v-card>
        <v-card-title>{{ form.id ? 'Eintrag bearbeiten' : 'Neuer Eintrag' }}</v-card-title>
        <v-card-text>
          <v-text-field v-model="form.count_date" label="Zähldatum" type="datetime-local" class="mb-2" />
          <v-select
            v-model="selectedLocation"
            :items="locations"
            item-title="name"
            item-value="id"
            label="Standort"
            return-object
            class="mb-2"
            @update:model-value="onLocationChange"
          />
          <v-text-field v-model="form.article_id" label="Artikel-ID" class="mb-2" />
          <v-text-field v-model="form.article_name" label="Artikelname" class="mb-2" />
          <v-row dense>
            <v-col cols="4">
              <v-text-field v-model.number="form.package_count" label="Pakete" type="number" min="0" step="1" hide-details />
            </v-col>
            <v-col cols="4">
              <v-text-field v-model.number="form.units_per_package" label="Stk/Paket" type="number" min="0" step="1" hide-details />
            </v-col>
            <v-col cols="4">
              <v-text-field v-model.number="form.unit_count" label="Einzeln" type="number" min="0" step="1" hide-details />
            </v-col>
          </v-row>
          <v-text-field
            :model-value="form.package_count * form.units_per_package + form.unit_count"
            label="Menge (gesamt)"
            readonly
            class="mt-2"
            hide-details
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="dialog = false">Abbrechen</v-btn>
          <v-btn color="primary" :loading="saving" @click="save">Speichern</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Import dialog -->
    <v-dialog v-model="importDialog" max-width="400">
      <v-card>
        <v-card-title>In Gezählten Stand importieren</v-card-title>
        <v-card-text>
          <p class="mb-1"><strong>{{ importItem?.article_name }}</strong></p>
          <p class="text-caption text-medium-emphasis">{{ formatDate(importItem?.count_date) }}</p>
          <p class="mt-3">Was soll importiert werden?</p>
        </v-card-text>
        <v-card-actions class="flex-column align-stretch pa-3" style="gap: 8px">
          <v-btn color="primary" variant="tonal" block :loading="importing" @click="doImport('single')">
            Nur diesen Eintrag
          </v-btn>
          <v-btn color="primary" variant="tonal" block :loading="importing" @click="doImport('batch')">
            Gesamte Zählung ({{ batchCount }} Einträge)
          </v-btn>
          <v-btn variant="text" block @click="importDialog = false">Abbrechen</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Conflict confirmation dialog -->
    <v-dialog v-model="conflictDialog" max-width="400">
      <v-card>
        <v-card-title>Bereits vorhanden</v-card-title>
        <v-card-text>
          Es existieren bereits <strong>{{ conflictInfo?.existing_count }}</strong> Einträge für
          den <strong>{{ conflictInfo?.date }}</strong> in der Bestandszählung.
          Sollen diese überschrieben werden?
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="conflictDialog = false">Abbrechen</v-btn>
          <v-btn color="warning" :loading="importing" @click="forceImport">Überschreiben</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-snackbar v-model="snackbar.show" :color="snackbar.color" :timeout="3000" location="top">
      {{ snackbar.message }}
    </v-snackbar>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import api from '../api'

const items = ref([])
const locations = ref([])
const loading = ref(false)
const saving = ref(false)
const dialog = ref(false)
const filterLocationId = ref(null)
const filterDate = ref(null)
const selectedLocation = ref(null)
const snackbar = reactive({ show: false, message: '', color: 'success' })

// Import state
const importDialog = ref(false)
const conflictDialog = ref(false)
const importItem = ref(null)
const importMode = ref(null)
const importing = ref(false)
const conflictInfo = ref(null)

const batchCount = computed(() => {
  if (!importItem.value) return 0
  return items.value.filter(i => i.count_date === importItem.value.count_date).length
})

const form = ref({
  id: null,
  count_date: '',
  article_id: '',
  article_name: '',
  location_id: null,
  location_name: '',
  package_count: 0,
  units_per_package: 0,
  unit_count: 0,
})

const headers = [
  { title: 'Datum', key: 'count_date' },
  { title: 'Standort', key: 'location_name' },
  { title: 'Artikel-ID', key: 'article_id' },
  { title: 'Artikel', key: 'article_name' },
  { title: 'Menge', key: 'quantity', align: 'end' },
  { title: '', key: 'actions', sortable: false, align: 'end' },
]

function formatDate(dt) {
  if (!dt) return ''
  return new Date(dt).toLocaleString('de-AT', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
  })
}

function showSnack(message, color = 'success') {
  snackbar.message = message
  snackbar.color = color
  snackbar.show = true
}

async function fetchLocations() {
  try {
    const res = await api.get('/locations/')
    locations.value = res.data.results ?? res.data
  } catch {
    showSnack('Standorte konnten nicht geladen werden.', 'error')
  }
}

async function fetchItems() {
  loading.value = true
  try {
    const params = {}
    if (filterLocationId.value) params.location_id = filterLocationId.value
    if (filterDate.value) params.count_date = filterDate.value
    const res = await api.get('/stock-count/entries/', { params })
    items.value = res.data.results ?? res.data
  } catch {
    showSnack('Laden fehlgeschlagen.', 'error')
  } finally {
    loading.value = false
  }
}

function toDatetimeLocal(isoString) {
  if (!isoString) return ''
  // Convert ISO datetime to datetime-local input format (YYYY-MM-DDTHH:mm)
  return isoString.substring(0, 16)
}

function openNew() {
  form.value = {
    id: null,
    count_date: toDatetimeLocal(new Date().toISOString()),
    article_id: '',
    article_name: '',
    location_id: null,
    location_name: '',
    package_count: 0,
    units_per_package: 0,
    unit_count: 0,
  }
  selectedLocation.value = null
  dialog.value = true
}

function openEdit(item) {
  form.value = {
    ...item,
    count_date: toDatetimeLocal(item.count_date),
  }
  selectedLocation.value = locations.value.find(l => l.id === item.location_id) ?? null
  dialog.value = true
}

function onLocationChange(loc) {
  if (loc) {
    form.value.location_id = loc.id
    form.value.location_name = loc.name
  }
}

async function save() {
  saving.value = true
  try {
    const payload = {
      count_date: new Date(form.value.count_date).toISOString(),
      article_id: form.value.article_id,
      article_name: form.value.article_name,
      location_id: form.value.location_id,
      location_name: form.value.location_name,
      package_count: form.value.package_count ?? 0,
      units_per_package: form.value.units_per_package ?? 0,
      unit_count: form.value.unit_count ?? 0,
    }
    if (form.value.id) {
      await api.put(`/stock-count/entries/${form.value.id}/`, payload)
    } else {
      await api.post('/stock-count/entries/', payload)
    }
    dialog.value = false
    showSnack('Gespeichert.')
    await fetchItems()
  } catch (err) {
    const detail = err.response?.data
    showSnack(typeof detail === 'string' ? detail : 'Fehler beim Speichern.', 'error')
  } finally {
    saving.value = false
  }
}

async function deleteItem(item) {
  if (!confirm(`Eintrag "${item.article_name}" @ ${item.location_name} wirklich löschen?`)) return
  try {
    await api.delete(`/stock-count/entries/${item.id}/`)
    showSnack('Gelöscht.')
    await fetchItems()
  } catch {
    showSnack('Fehler beim Löschen.', 'error')
  }
}

function openImportDialog(item) {
  importItem.value = item
  importDialog.value = true
}

function collectEntryIds(mode) {
  if (mode === 'single') return [importItem.value.id]
  return items.value
    .filter(i => i.count_date === importItem.value.count_date)
    .map(i => i.id)
}

async function doImport(mode) {
  importDialog.value = false
  importMode.value = mode
  importing.value = true
  try {
    const res = await api.post('/stock-count/entries/import/', { entry_ids: collectEntryIds(mode) })
    let msg = `${res.data.created} erstellt, ${res.data.updated} aktualisiert.`
    if (res.data.not_found?.length) msg += ` ${res.data.not_found.length} Artikel nicht gefunden.`
    showSnack(msg)
  } catch (err) {
    if (err.response?.status === 409) {
      conflictInfo.value = err.response.data
      conflictDialog.value = true
      return
    }
    showSnack('Import fehlgeschlagen.', 'error')
  } finally {
    importing.value = false
  }
}

async function forceImport() {
  conflictDialog.value = false
  importing.value = true
  try {
    const res = await api.post('/stock-count/entries/import/', {
      entry_ids: collectEntryIds(importMode.value),
      force: true,
    })
    let msg = `${res.data.created} erstellt, ${res.data.updated} aktualisiert.`
    if (res.data.not_found?.length) msg += ` ${res.data.not_found.length} Artikel nicht gefunden.`
    showSnack(msg)
  } catch {
    showSnack('Import fehlgeschlagen.', 'error')
  } finally {
    importing.value = false
  }
}

onMounted(async () => {
  await fetchLocations()
  await fetchItems()
})
</script>
