<template>
  <div>
    <v-row class="mb-2" align="center">
      <v-col><h2>Gezählter Stand – Übersicht</h2></v-col>
      <v-col cols="3">
        <v-text-field
          v-model="newDate"
          label="Neues Datum initialisieren"
          type="date"
          hide-details
          clearable
          density="compact"
        />
      </v-col>
      <v-col cols="auto">
        <v-btn color="secondary" :loading="initLoading" :disabled="!newDate" @click="initDate">Datum init.</v-btn>
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
          color="error"
          title="Alle Einträge dieses Tages löschen"
          @click.stop="openDeleteDialog(item)"
        >mdi-delete</v-icon>
      </template>
    </v-data-table>

    <!-- Delete confirmation dialog -->
    <v-dialog v-model="deleteDialog" max-width="400">
      <v-card>
        <v-card-title>Einträge löschen</v-card-title>
        <v-card-text>
          Alle <strong>{{ pendingDelete?.count }}</strong> Einträge vom
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
import { onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api'
import { usePeriodStore } from '../stores/period'

const router = useRouter()
const periodStore = usePeriodStore()

const items = ref([])
const loading = ref(false)
const initLoading = ref(false)
const newDate = ref('')
const snackbar = reactive({ show: false, message: '', color: 'success' })
const deleteDialog = ref(false)
const pendingDelete = ref(null)
const deleting = ref(false)

const headers = [
  { title: 'Datum', key: 'day' },
  { title: 'Einträge', key: 'count', align: 'end' },
  { title: '', key: 'actions', sortable: false, align: 'end' },
]

function formatDate(dateStr) {
  if (!dateStr) return ''
  const [y, m, d] = dateStr.split('-')
  return `${d}.${m}.${y}`
}

function showSnack(message, color = 'success') {
  snackbar.message = message
  snackbar.color = color
  snackbar.show = true
}

async function fetchItems() {
  if (!periodStore.currentPeriodId) return
  loading.value = true
  try {
    const res = await api.get('/physical-counts/dates/', {
      params: { period_id: periodStore.currentPeriodId },
    })
    items.value = res.data
  } catch {
    showSnack('Laden fehlgeschlagen.', 'error')
  } finally {
    loading.value = false
  }
}

function drillDown(item) {
  router.push({ path: '/physical-counts', query: { date: item.day } })
}

function openDeleteDialog(item) {
  pendingDelete.value = item
  deleteDialog.value = true
}

async function confirmDelete() {
  deleting.value = true
  try {
    const res = await api.delete('/physical-counts/by-day/', {
      params: { day: pendingDelete.value.day, period_id: periodStore.currentPeriodId },
    })
    deleteDialog.value = false
    showSnack(`${res.data.deleted} Einträge gelöscht.`)
    await fetchItems()
  } catch {
    showSnack('Fehler beim Löschen.', 'error')
  } finally {
    deleting.value = false
  }
}

async function initDate() {
  if (!newDate.value) return
  initLoading.value = true
  try {
    await api.post('/physical-counts/init_date/', {
      period_id: periodStore.currentPeriodId,
      date: newDate.value,
    })
    showSnack('Datum initialisiert.')
    newDate.value = ''
    await fetchItems()
  } catch {
    showSnack('Fehler beim Initialisieren.', 'error')
  } finally {
    initLoading.value = false
  }
}

watch(() => periodStore.currentPeriodId, fetchItems)
onMounted(fetchItems)
</script>
