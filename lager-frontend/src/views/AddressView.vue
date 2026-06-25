<template>
  <div>
    <v-row class="mb-2" align="center">
      <v-col><h2>Adressen</h2></v-col>
      <v-col cols="auto" class="d-flex gap-2">
        <v-btn variant="tonal" prepend-icon="mdi-sync" :loading="syncing" @click="syncWz">WZ synchronisieren</v-btn>
        <v-btn color="primary" prepend-icon="mdi-plus" @click="openNew">Neu</v-btn>
      </v-col>
    </v-row>

    <v-text-field v-model="search" label="Suche" prepend-inner-icon="mdi-magnify" clearable
      density="compact" class="mb-3" style="max-width: 360px" @update:model-value="onSearch" />

    <v-data-table :headers="headers" :items="items" :loading="loading" density="compact"
      :row-props="() => ({ style: 'cursor: pointer' })" @click:row="(_, { item }) => openEdit(item)">
      <template #item.display_name="{ item }">
        <span class="font-weight-medium">{{ item.display_name }}</span>
      </template>
      <template #item.wz_source_id="{ item }">
        <v-chip v-if="item.wz_source_id != null" size="x-small" color="info" variant="tonal">WZ</v-chip>
      </template>
      <template #item.actions="{ item }">
        <v-icon size="small" @click.stop="openEdit(item)">mdi-pencil</v-icon>
        <v-icon size="small" class="ml-1" color="error" @click.stop="deleteItem(item)">mdi-delete</v-icon>
        <v-tooltip text="Verlauf"><template #activator="{ props }">
          <v-icon v-bind="props" size="small" class="ml-1" @click.stop="openHistory(item)">mdi-history</v-icon>
        </template></v-tooltip>
      </template>
    </v-data-table>

    <!-- Edit / New dialog -->
    <v-dialog v-model="dialog" max-width="640">
      <AddressDialog :address="editingAddress" @saved="onAddressSaved" @close="dialog = false" />
    </v-dialog>

    <HistoryDialog v-if="historyItem" v-model="historyDialog" :api-path="`/addresses/${historyItem.id}`" />

    <!-- WZ sync dialog -->
    <v-dialog v-model="syncDialog" max-width="480">
      <v-card>
        <v-card-title>WZ-Adressen synchronisieren</v-card-title>
        <v-card-text>
          <v-text-field v-model="syncForm.host" label="Host" />
          <v-text-field v-model="syncForm.database" label="Datenbank" />
          <v-text-field v-model="syncForm.user" label="Benutzer" />
          <v-text-field v-model="syncForm.password" label="Passwort" type="password" />
          <v-alert v-if="syncResult" :type="syncResult.error ? 'error' : 'success'" class="mt-2">
            {{ syncResult.error || `${syncResult.count} Adressen synchronisiert.` }}
          </v-alert>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="syncDialog = false">Schließen</v-btn>
          <v-btn color="primary" :loading="syncing" @click="runSync">Synchronisieren</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api from '../api'
import AddressDialog from '../components/AddressDialog.vue'
import HistoryDialog from '../components/HistoryDialog.vue'

const items = ref([])
const loading = ref(false)
const dialog = ref(false)
const syncing = ref(false)
const syncDialog = ref(false)
const syncResult = ref(null)
const search = ref('')
let searchTimeout = null

const syncForm = ref({ host: '', database: '', user: '', password: '' })
const editingAddress = ref(null)
const historyDialog = ref(false)
const historyItem = ref(null)

const headers = [
  { title: 'Name / Firma', key: 'display_name' },
  { title: 'Ort', key: 'ort' },
  { title: 'E-Mail', key: 'email' },
  { title: 'Telefon', key: 'telefon' },
  { title: 'WZ', key: 'wz_source_id', sortable: false },
  { title: '', key: 'actions', sortable: false, align: 'end' },
]

async function fetchItems(q) {
  loading.value = true
  try {
    const params = q ? { q } : {}
    const res = await api.get('/addresses/', { params })
    items.value = res.data.results || res.data
  } finally {
    loading.value = false
  }
}

function onSearch(val) {
  clearTimeout(searchTimeout)
  searchTimeout = setTimeout(() => fetchItems(val || undefined), 300)
}

function openHistory(item) {
  historyItem.value = item
  historyDialog.value = true
}

function openNew() {
  editingAddress.value = null
  dialog.value = true
}

function openEdit(item) {
  editingAddress.value = item
  dialog.value = true
}

function onAddressSaved() {
  dialog.value = false
  fetchItems(search.value || undefined)
}

async function deleteItem(item) {
  if (!confirm(`Adresse "${item.display_name}" wirklich löschen?`)) return
  await api.delete(`/addresses/${item.id}/`)
  await fetchItems(search.value || undefined)
}

function syncWz() {
  syncResult.value = null
  syncDialog.value = true
}

async function runSync() {
  syncing.value = true
  syncResult.value = null
  try {
    const res = await api.post('/addresses/sync-wz/', syncForm.value)
    syncResult.value = { count: res.data.count }
    await fetchItems(search.value || undefined)
  } catch (err) {
    syncResult.value = { error: err.response?.data?.error || 'Synchronisierung fehlgeschlagen.' }
  } finally {
    syncing.value = false
  }
}

onMounted(() => fetchItems())
</script>
