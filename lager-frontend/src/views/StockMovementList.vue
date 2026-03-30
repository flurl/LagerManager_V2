<template>
  <div>
    <v-row class="mb-2" align="center">
      <v-col>
        <v-btn-toggle v-model="movementType" mandatory>
          <v-btn value="delivery">Lieferungen</v-btn>
          <v-btn value="consumption">Verbräuche</v-btn>
        </v-btn-toggle>
      </v-col>
      <v-col cols="auto">
        <v-btn color="primary" prepend-icon="mdi-plus" @click="openNew">Neu</v-btn>
        <v-btn class="ml-2" prepend-icon="mdi-download" @click="exportCsvAction">CSV</v-btn>
      </v-col>
    </v-row>

    <v-row dense class="mb-2">
      <v-col cols="3">
        <v-autocomplete v-model="filterPartner" :items="partnerOptions" label="Partner" clearable
          density="compact" hide-details />
      </v-col>
      <v-col cols="5">
        <v-autocomplete v-model="filterArticles" :items="warehouseArticles" multiple chips closable-chips
          item-title="article_name" item-value="article" label="Artikel" clearable
          density="compact" hide-details />
      </v-col>
      <v-col cols="4">
        <v-text-field v-model="filterComment" label="Kommentar" clearable density="compact" hide-details />
      </v-col>
    </v-row>

    <v-data-table :headers="headers" :items="filteredMovements" :loading="loading" density="compact"
      @click:row="(_, { item }) => openDetail(item)">
      <template #item="{ item, columns }">
        <tr class="v-data-table__tr cursor-pointer"
          :style="hoveredRowId === item.id ? { backgroundColor: HIGHLIGHT_COLOR } : {}"
          @click="openDetail(item)"
          @mouseenter="onRowEnter(item, $event)"
          @mouseleave="onRowLeave">
          <td v-for="col in columns" :key="col.key"
            :class="col.align ? `text-${col.align}` : ''"
            class="v-data-table__td">
            <template v-if="col.key === 'date'">{{ formatDate(item.date) }}</template>
            <template v-else-if="col.key === 'total_net'">{{ formatCurrency(item.total_net) }}</template>
            <template v-else-if="col.key === 'total_gross'">{{ formatCurrency(item.total_gross) }}</template>
            <template v-else-if="col.key === 'actions'">
              <v-icon size="small" @click.stop="openDetail(item)">mdi-pencil</v-icon>
              <v-icon size="small" class="ml-1" color="error" @click.stop="deleteMovement(item)">mdi-delete</v-icon>
            </template>
            <template v-else>{{ item[col.key] }}</template>
          </td>
        </tr>
      </template>
    </v-data-table>

    <Teleport to="body">
      <div v-if="detailOverlay && hoveredItem"
        :style="overlayStyle">
        <v-card min-width="400" max-width="600" :color="HIGHLIGHT_COLOR"
          :style="{
            pointerEvents: 'auto',
            borderLeft: `2px solid ${HIGHLIGHT_COLOR}`,
            borderRight: `2px solid ${HIGHLIGHT_COLOR}`,
            borderTop: overlayAbove ? `2px solid ${HIGHLIGHT_COLOR}` : 'none',
            borderBottom: overlayAbove ? 'none' : `2px solid ${HIGHLIGHT_COLOR}`,
            borderTopLeftRadius: overlayAbove ? undefined : 0,
            borderTopRightRadius: overlayAbove ? undefined : 0,
            borderBottomLeftRadius: overlayAbove ? 0 : undefined,
            borderBottomRightRadius: overlayAbove ? 0 : undefined,
            boxShadow: 'none',
          }"
          @mouseenter="onOverlayEnter" @mouseleave="onOverlayLeave">
          <v-card-title class="text-subtitle-2 pb-1">Positionen</v-card-title>
          <v-card-text class="pa-0">
            <template v-if="detailsLoading[hoveredItem.id]">
              <div class="pa-4 text-center"><v-progress-circular indeterminate size="24" /></div>
            </template>
            <template v-else-if="detailsCache[hoveredItem.id]?.length">
              <v-table density="compact">
                <thead>
                  <tr>
                    <th>Artikel</th>
                    <th class="text-end">Menge</th>
                    <th class="text-end">EP</th>
                    <th class="text-end">Netto</th>
                    <th class="text-end">Brutto</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="d in detailsCache[hoveredItem.id]" :key="d.id">
                    <td>{{ d.article_name }}</td>
                    <td class="text-end">{{ d.quantity }}</td>
                    <td class="text-end">{{ formatCurrency(d.unit_price) }}</td>
                    <td class="text-end">{{ formatCurrency(d.line_net) }}</td>
                    <td class="text-end">{{ formatCurrency(d.line_gross) }}</td>
                  </tr>
                </tbody>
              </v-table>
            </template>
            <template v-else>
              <div class="pa-4 text-medium-emphasis text-caption">Keine Positionen</div>
            </template>
          </v-card-text>
        </v-card>
      </div>
    </Teleport>

    <v-dialog v-model="dialog" max-width="900" persistent>
      <StockMovementDialog :movement="selectedMovement" :movement-type="movementType" @saved="onSaved"
        @close="dialog = false" />
    </v-dialog>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { usePeriodStore } from '../stores/period'
import { useCsvExport } from '../composables/useCsvExport'
import api from '../api'
import StockMovementDialog from '../components/StockMovementDialog.vue'

const periodStore = usePeriodStore()
const { exportCsv } = useCsvExport()

const movements = ref([])
const loading = ref(false)
const movementType = ref('delivery')
const dialog = ref(false)
const selectedMovement = ref(null)
const detailsCache = ref({})
const detailsLoading = ref({})
const detailOverlay = ref(false)
const hoveredItem = ref(null)
const hoveredRowId = ref(null)
let showTimer = null
let hideTimer = null
const HIGHLIGHT_COLOR = '#dbeafe'
const rowBottom = ref(0)
const rowTop = ref(0)
const filterPartner = ref(null)
const filterArticles = ref([])
const filterComment = ref('')
const warehouseArticles = ref([])

const overlayAbove = computed(() => rowBottom.value > window.innerHeight / 2)

const overlayStyle = computed(() => {
  const base = { position: 'fixed', left: 0, right: 0, zIndex: 2000, display: 'flex', justifyContent: 'center', pointerEvents: 'none' }
  if (overlayAbove.value) {
    return { ...base, bottom: (window.innerHeight - rowTop.value) + 'px' }
  }
  return { ...base, top: rowBottom.value + 'px' }
})

const partnerOptions = computed(() => {
  const names = [...new Set(movements.value.map(m => m.partner_name).filter(Boolean))]
  return names.sort()
})

const filteredMovements = computed(() => {
  let list = movements.value
  if (filterPartner.value) {
    list = list.filter(m => m.partner_name === filterPartner.value)
  }
  if (filterComment.value) {
    const q = filterComment.value.toLowerCase()
    list = list.filter(m => m.comment?.toLowerCase().includes(q))
  }
  return list
})

const headers = [
  { title: 'Datum', key: 'date' },
  { title: 'Partner', key: 'partner_name' },
  { title: 'Kommentar', key: 'comment' },
  { title: 'Netto', key: 'total_net', align: 'end' },
  { title: 'Brutto', key: 'total_gross', align: 'end' },
  { title: '', key: 'actions', sortable: false, align: 'end' },
]

async function fetchMovements() {
  if (!periodStore.currentPeriodId) return
  loading.value = true
  detailsCache.value = {}
  detailsLoading.value = {}
  try {
    const params = new URLSearchParams({
      period_id: periodStore.currentPeriodId,
      movement_type: movementType.value,
    })
    filterArticles.value.forEach(id => params.append('article_id', id))
    const res = await api.get(`/stock-movements/?${params}`)
    movements.value = res.data.results || res.data
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

function onRowEnter(item, event) {
  clearTimeout(hideTimer)
  hoveredRowId.value = item.id
  const rect = event.currentTarget.getBoundingClientRect()
  showTimer = setTimeout(() => {
    rowBottom.value = rect.bottom
    rowTop.value = rect.top
    hoveredItem.value = item
    detailOverlay.value = true
    loadDetails(item.id)
  }, 1000)
}

function onRowLeave() {
  clearTimeout(showTimer)
  hideTimer = setTimeout(() => {
    detailOverlay.value = false
    hoveredRowId.value = null
  }, 150)
}

function onOverlayEnter() {
  clearTimeout(hideTimer)
}

function onOverlayLeave() {
  detailOverlay.value = false
  hoveredRowId.value = null
}

async function loadDetails(id) {
  if (detailsCache.value[id] !== undefined) return
  detailsLoading.value[id] = true
  try {
    const res = await api.get(`/stock-movements/${id}/details/`)
    detailsCache.value[id] = res.data.results || res.data
  } catch {
    detailsCache.value[id] = []
  } finally {
    detailsLoading.value[id] = false
  }
}

function openNew() {
  selectedMovement.value = null
  dialog.value = true
}

function openDetail(item) {
  selectedMovement.value = item
  dialog.value = true
}

async function deleteMovement(item) {
  if (!confirm(`Lagerbewegung #${item.id} wirklich löschen?`)) return
  await api.delete(`/stock-movements/${item.id}/`)
  await fetchMovements()
}

function onSaved() {
  dialog.value = false
  fetchMovements()
}

function exportCsvAction() {
  exportCsv(
    ['date', 'partner_name', 'comment', 'total_gross'],
    movements.value,
    'lagerbewegungen.csv'
  )
}

function formatDate(dt) {
  return dt ? new Date(dt).toLocaleDateString('de-AT') : ''
}

function formatCurrency(val) {
  return val != null ? Number(val).toFixed(2) + ' €' : ''
}

watch(() => periodStore.currentPeriodId, () => {
  filterPartner.value = null
  filterArticles.value = []
  filterComment.value = ''
  fetchMovements()
  fetchWarehouseArticles()
})
watch(movementType, () => {
  filterPartner.value = null
  filterArticles.value = []
  filterComment.value = ''
  fetchMovements()
})
watch(filterArticles, fetchMovements)
onMounted(() => {
  fetchMovements()
  fetchWarehouseArticles()
})
</script>
