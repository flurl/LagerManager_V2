<template>
  <div>
    <v-row class="mb-2" align="center">
      <v-col><h2>Bestandszählung – Übersicht</h2></v-col>
      <v-col cols="auto" class="d-flex gap-2">
        <v-btn color="secondary" prepend-icon="mdi-archive-arrow-down" @click="openInitDialog">+Init. Stand</v-btn>
        <v-btn color="primary" prepend-icon="mdi-plus" @click="$router.push('/stock-count-entries')">Alle Einträge</v-btn>
      </v-col>
    </v-row>

    <v-data-table
      :headers="headers"
      :items="items"
      :loading="loading"
      :items-per-page="100"
      density="compact"
      :row-props="() => ({ style: 'cursor: pointer' })"
      @click:row="(_, { item }) => drillDown(item)"
    >
      <template #item.day="{ item }">
        {{ formatDate(item.day) }}
      </template>
      <template #item.actions="{ item }">
        <v-icon
          size="small"
          color="primary"
          :title="`Tagesakkumuliert importieren (${item.day})`"
          @click.stop="openImportConfirm(item)"
        >mdi-import</v-icon>
        <v-icon
          size="small"
          class="ml-1"
          color="error"
          title="Alle Einträge dieses Tages/Standorts löschen"
          @click.stop="openDeleteDialog(item)"
        >mdi-delete</v-icon>
      </template>
    </v-data-table>

    <!-- Init from initial inventory dialog -->
    <v-dialog v-model="initDialog" max-width="420">
      <v-card>
        <v-card-title>Init. Stand importieren</v-card-title>
        <v-card-text>
          <v-select
            v-model="initLocationIds"
            :items="locations"
            item-title="name"
            item-value="id"
            label="Standorte"
            multiple
            chips
            closable-chips
            class="mb-3"
          />
          <v-text-field
            v-model="initDate"
            label="Datum"
            type="date"
            hide-details
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="initDialog = false">Abbrechen</v-btn>
          <v-btn
            color="primary"
            :loading="initLoading"
            :disabled="!initLocationIds.length || !initDate"
            @click="doInitFromInventory"
          >
            Importieren
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Import confirmation dialog -->
    <v-dialog v-model="importConfirmDialog" max-width="400">
      <v-card>
        <v-card-title>Tagesakkumuliert importieren</v-card-title>
        <v-card-text>
          Alle Zähleinträge vom <strong>{{ pendingImportItem ? formatDate(pendingImportItem.day) : '' }}</strong>
          (alle Standorte) in den Gezählten Stand importieren?
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="importConfirmDialog = false">Abbrechen</v-btn>
          <v-btn color="primary" :loading="importing" @click="doConfirmedImport">Importieren</v-btn>
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
          <v-alert
            v-if="conflictInfo?.warnings?.length"
            type="warning"
            variant="tonal"
            class="mt-3"
            density="compact"
          >
            <div v-for="w in conflictInfo.warnings" :key="w">{{ w }}</div>
          </v-alert>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="conflictDialog = false">Abbrechen</v-btn>
          <v-btn color="warning" :loading="importing" @click="forceImport">Überschreiben</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Delete confirmation dialog -->
    <v-dialog v-model="deleteDialog" max-width="400">
      <v-card>
        <v-card-title>Einträge löschen</v-card-title>
        <v-card-text>
          Alle <strong>{{ pendingDelete?.count }}</strong> Einträge für
          <strong>{{ pendingDelete?.location_name }}</strong> am
          <strong>{{ pendingDelete ? formatDate(pendingDelete.day) : '' }}</strong>
          wirklich löschen?
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="deleteDialog = false">Abbrechen</v-btn>
          <v-btn color="error" :loading="deleting" @click="confirmDelete">Löschen</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-snackbar v-model="snackbar.show" :color="snackbar.color" :timeout="3000" location="top">
      {{ snackbar.message }}
    </v-snackbar>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api'
import { usePeriodStore } from '../stores/period'
import { useStockCountImport } from '../composables/useStockCountImport'

const router = useRouter()
const periodStore = usePeriodStore()

const items = ref([])
const locations = ref([])
const loading = ref(false)

// Import confirm state
const importConfirmDialog = ref(false)
const pendingImportItem = ref(null)

// Delete state
const deleteDialog = ref(false)
const pendingDelete = ref(null)
const deleting = ref(false)

// Init from initial inventory state
const initDialog = ref(false)
const initLocationIds = ref([])
const initDate = ref(new Date().toISOString().substring(0, 10))
const initLoading = ref(false)

const { importing, conflictDialog, conflictInfo, snackbar, importCumulative, forceImport } =
  useStockCountImport(fetchItems)

const headers = [
  { title: 'Datum', key: 'day' },
  { title: 'Standort', key: 'location_name' },
  { title: 'Einträge', key: 'count', align: 'end' },
  { title: '', key: 'actions', sortable: false, align: 'end' },
]

function formatDate(dateStr) {
  if (!dateStr) return ''
  const [y, m, d] = dateStr.split('-')
  return `${d}.${m}.${y}`
}

async function fetchItems() {
  loading.value = true
  try {
    const res = await api.get('/stock-count/entries/dates/')
    items.value = res.data
  } catch {
    snackbar.message = 'Laden fehlgeschlagen.'
    snackbar.color = 'error'
    snackbar.show = true
  } finally {
    loading.value = false
  }
}

async function fetchLocations() {
  try {
    const res = await api.get('/locations/')
    locations.value = res.data.results ?? res.data
  } catch {
    // non-critical, init dialog just won't have options
  }
}

function drillDown(item) {
  router.push({ path: '/stock-count-entries', query: { date: item.day, location_id: item.location_id } })
}

function openImportConfirm(item) {
  pendingImportItem.value = item
  importConfirmDialog.value = true
}

async function doConfirmedImport() {
  importConfirmDialog.value = false
  await importCumulative(pendingImportItem.value.day)
}

function openDeleteDialog(item) {
  pendingDelete.value = item
  deleteDialog.value = true
}

async function confirmDelete() {
  deleting.value = true
  try {
    const res = await api.delete('/stock-count/entries/by-day/', {
      params: { day: pendingDelete.value.day, location_id: pendingDelete.value.location_id },
    })
    deleteDialog.value = false
    snackbar.message = `${res.data.deleted} Einträge gelöscht.`
    snackbar.color = 'success'
    snackbar.show = true
    await fetchItems()
  } catch {
    snackbar.message = 'Fehler beim Löschen.'
    snackbar.color = 'error'
    snackbar.show = true
  } finally {
    deleting.value = false
  }
}

function openInitDialog() {
  initLocationIds.value = []
  initDate.value = new Date().toISOString().substring(0, 10)
  initDialog.value = true
}

async function doInitFromInventory() {
  if (!initLocationIds.value.length || !initDate.value) return
  initLoading.value = true
  try {
    const res = await api.post('/stock-count/entries/from-initial-inventory/', {
      location_ids: initLocationIds.value,
      count_date: `${initDate.value}T12:00:00`,
      period_id: periodStore.currentPeriodId,
    })
    initDialog.value = false
    snackbar.message = `${res.data.created} erstellt, ${res.data.updated} aktualisiert.`
    snackbar.color = 'success'
    snackbar.show = true
    await fetchItems()
  } catch (err) {
    const detail = err.response?.data
    snackbar.message = typeof detail === 'string' ? detail : 'Fehler beim Importieren.'
    snackbar.color = 'error'
    snackbar.show = true
  } finally {
    initLoading.value = false
  }
}

onMounted(async () => {
  await Promise.all([fetchItems(), fetchLocations()])
})
</script>
