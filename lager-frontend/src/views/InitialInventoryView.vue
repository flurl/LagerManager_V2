<template>
  <div>
    <v-row class="mb-2" align="center">
      <v-col>
        <h2>Initialer Stand</h2>
      </v-col>
      <v-col cols="auto">
        <v-select v-model="locationId" :items="locations" item-title="name" item-value="id" label="Arbeitsplatz"
          hide-details :disabled="busy" style="max-width: 200px" />
      </v-col>
      <v-col cols="auto">
        <v-btn color="primary" prepend-icon="mdi-plus" :disabled="!locationId || busy"
          @click="openAddDialog">Hinzufügen</v-btn>
        <v-btn class="ml-2" color="secondary" :loading="initLoading" :disabled="!locationId || busy"
          @click="initPeriod">Periode init.</v-btn>
        <v-btn class="ml-2" prepend-icon="mdi-download" :disabled="busy" @click="exportCsvAction">CSV</v-btn>
      </v-col>
    </v-row>

    <v-data-table :headers="headers" :items="items" :loading="loading" density="compact">
      <template #item.quantity="{ item }">
        <NumberInput v-model="item.quantity" density="compact" hide-details style="width: 100px"
          @change="saveItem(item)" />
      </template>
      <template #item.actions="{ item }">
        <v-btn icon="mdi-delete" size="small" variant="text" color="error" :disabled="busy"
          @click="promptDelete(item)" />
      </template>
    </v-data-table>

    <!-- Add dialog -->
    <v-dialog v-model="addDialog" max-width="420">
      <v-card title="Artikel hinzufügen">
        <v-card-text>
          <v-autocomplete v-model="newArticleId" :items="availableArticles" item-title="article_name"
            item-value="article" label="Artikel" hide-details clearable class="mb-4" />
          <NumberInput v-model="newQuantity" label="Menge" hide-details />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="addDialog = false">Abbrechen</v-btn>
          <v-btn color="primary" :disabled="!newArticleId" :loading="addLoading" @click="addItem">Hinzufügen</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Delete confirmation dialog -->
    <v-dialog v-model="deleteDialog" max-width="350">
      <v-card title="Eintrag löschen?">
        <v-card-text v-if="deleteTarget">
          {{ deleteTarget.article_name }} — Menge: {{ deleteTarget.quantity }}
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="deleteDialog = false">Abbrechen</v-btn>
          <v-btn color="error" :loading="deleteLoading" @click="confirmDelete">Löschen</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { usePeriodStore } from '../stores/period'
import { useCsvExport } from '../composables/useCsvExport'
import api from '../api'
import NumberInput from '../components/NumberInput.vue'

const periodStore = usePeriodStore()
const { exportCsv } = useCsvExport()

const items = ref([])
const locations = ref([])
const locationId = ref(null)
const warehouseArticles = ref([])

const loading = ref(false)
const initLoading = ref(false)
const addLoading = ref(false)
const deleteLoading = ref(false)

const addDialog = ref(false)
const newArticleId = ref(null)
const newQuantity = ref(0)

const deleteDialog = ref(false)
const deleteTarget = ref(null)

const busy = computed(() =>
  loading.value || initLoading.value || addLoading.value || deleteLoading.value
)

const headers = [
  { title: 'Artikel', key: 'article_name' },
  { title: 'Arbeitsplatz', key: 'location_name' },
  { title: 'Menge', key: 'quantity' },
  { title: '', key: 'actions', sortable: false, align: 'end' },
]

// Articles not yet added to the current location+period
const availableArticles = computed(() => {
  const usedArticleIds = new Set(items.value.map((i) => i.article))
  return warehouseArticles.value.filter((wa) => !usedArticleIds.has(wa.article))
})

async function fetchItems() {
  if (!periodStore.currentPeriodId || !locationId.value) return
  loading.value = true
  try {
    const res = await api.get('/initial-inventory/', {
      params: { period_id: periodStore.currentPeriodId, location_id: locationId.value },
    })
    items.value = res.data.results || res.data
  } finally {
    loading.value = false
  }
}

async function fetchWarehouseArticles() {
  if (!periodStore.currentPeriodId) return
  const res = await api.get('/warehouse-articles/', {
    params: { period_id: periodStore.currentPeriodId },
  })
  warehouseArticles.value = res.data.results || res.data
}

async function saveItem(item) {
  await api.patch(`/initial-inventory/${item.id}/`, { quantity: item.quantity })
}

async function initPeriod() {
  if (!locationId.value) return
  initLoading.value = true
  try {
    await api.post('/initial-inventory/init_period/', {
      period_id: periodStore.currentPeriodId,
      location_id: locationId.value,
    })
    await fetchItems()
  } finally {
    initLoading.value = false
  }
}

function openAddDialog() {
  newArticleId.value = null
  newQuantity.value = 0
  addDialog.value = true
}

async function addItem() {
  if (!newArticleId.value || !locationId.value) return
  addLoading.value = true
  try {
    await api.post('/initial-inventory/', {
      article: newArticleId.value,
      quantity: newQuantity.value,
      location: locationId.value,
      period: periodStore.currentPeriodId,
    })
    addDialog.value = false
    await fetchItems()
  } finally {
    addLoading.value = false
  }
}

function promptDelete(item) {
  deleteTarget.value = item
  deleteDialog.value = true
}

async function confirmDelete() {
  if (!deleteTarget.value) return
  deleteLoading.value = true
  try {
    await api.delete(`/initial-inventory/${deleteTarget.value.id}/`)
    deleteDialog.value = false
    deleteTarget.value = null
    await fetchItems()
  } finally {
    deleteLoading.value = false
  }
}

function exportCsvAction() {
  exportCsv(['article_name', 'location_name', 'quantity'], items.value, 'initialer_stand.csv')
}

onMounted(async () => {
  const [locRes] = await Promise.all([
    api.get('/locations/'),
    fetchWarehouseArticles(),
  ])
  locations.value = locRes.data.results || locRes.data
  if (locations.value.length > 0) {
    locationId.value = locations.value[0].id
  }
  await fetchItems()
})

watch(() => periodStore.currentPeriodId, async () => {
  await fetchWarehouseArticles()
  await fetchItems()
})
watch(locationId, fetchItems)
</script>
