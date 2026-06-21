<template>
  <div>
    <v-row class="mb-2" align="center">
      <v-col><h2>Angebote</h2></v-col>
      <v-col cols="auto">
        <v-btn color="primary" prepend-icon="mdi-plus" @click="openNew">Neues Angebot</v-btn>
      </v-col>
    </v-row>

    <v-data-table :headers="headers" :items="items" :loading="loading" density="compact">
      <template #item="{ item, columns }">
        <tr class="v-data-table__tr cursor-pointer"
          :style="hoveredRowId === item.id ? { backgroundColor: highlightColor } : {}"
          @click="openEdit(item)"
          @mouseenter="onRowEnter(item, $event)" @mouseleave="onRowLeave">
          <td v-for="col in columns" :key="col.key" :class="col.align ? `text-${col.align}` : ''"
            class="v-data-table__td">
            <template v-if="col.key === 'status'">
              <v-chip size="x-small" :color="statusColor(item.status)">{{ statusLabel(item.status) }}</v-chip>
            </template>
            <template v-else-if="col.key === 'gross_total'">{{ Number(item.gross_total).toFixed(2) }} €</template>
            <template v-else-if="col.key === 'actions'">
              <v-tooltip text="Vorschau"><template #activator="{ props }">
                <v-icon v-bind="props" size="small" @click.stop="openPreview(item)">mdi-eye-outline</v-icon>
              </template></v-tooltip>
              <v-tooltip v-if="item.status === 'draft'" text="Ausstellen"><template #activator="{ props }">
                <v-icon v-bind="props" size="small" class="ml-1" @click.stop="issueOffer(item)">mdi-file-check</v-icon>
              </template></v-tooltip>
              <v-tooltip v-if="item.status === 'issued'" text="Per E-Mail versenden (demnächst)"><template #activator="{ props }">
                <v-icon v-bind="props" size="small" class="ml-1" disabled>mdi-send</v-icon>
              </template></v-tooltip>
              <v-tooltip v-if="['issued','sent','accepted'].includes(item.status)" text="In Rechnung umwandeln">
                <template #activator="{ props }">
                  <v-icon v-bind="props" size="small" class="ml-1" color="success" @click.stop="convertToInvoice(item)">mdi-file-send</v-icon>
                </template>
              </v-tooltip>
              <v-icon size="small" class="ml-1" @click.stop="openEdit(item)">mdi-pencil</v-icon>
              <v-icon size="small" class="ml-1" color="error" @click.stop="deleteItem(item)">mdi-delete</v-icon>
            </template>
            <template v-else>{{ item[col.key] }}</template>
          </td>
        </tr>
      </template>
    </v-data-table>

    <Teleport to="body">
      <div v-if="detailOverlay && hoveredItem" :style="overlayStyle">
        <v-card min-width="400" max-width="700" :style="{
          pointerEvents: 'auto',
          backgroundColor: highlightColor,
          borderLeft: `2px solid ${primaryColor}`,
          borderRight: `2px solid ${primaryColor}`,
          borderTop: overlayAbove ? `2px solid ${primaryColor}` : 'none',
          borderBottom: overlayAbove ? 'none' : `2px solid ${primaryColor}`,
          borderTopLeftRadius: overlayAbove ? undefined : 0,
          borderTopRightRadius: overlayAbove ? undefined : 0,
          borderBottomLeftRadius: overlayAbove ? 0 : undefined,
          borderBottomRightRadius: overlayAbove ? 0 : undefined,
          boxShadow: '0 4px 16px rgba(0,0,0,0.5)',
        }" @mouseenter="onOverlayEnter" @mouseleave="onOverlayLeave">
          <v-card-text class="pa-0">
            <template v-if="linesLoading[hoveredItem.id]">
              <div class="pa-4 text-center"><v-progress-circular indeterminate size="24" /></div>
            </template>
            <template v-else-if="linesCache[hoveredItem.id]?.length">
              <v-table density="compact">
                <thead>
                  <tr>
                    <th class="text-subtitle-2" :style="{ backgroundColor: highlightColor }">Bezeichnung</th>
                    <th class="text-end text-subtitle-2" :style="{ backgroundColor: highlightColor }">Menge</th>
                    <th class="text-end text-subtitle-2" :style="{ backgroundColor: highlightColor }">EP</th>
                    <th class="text-end text-subtitle-2" :style="{ backgroundColor: highlightColor }">Netto</th>
                    <th class="text-end text-subtitle-2" :style="{ backgroundColor: highlightColor }">Brutto</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="line in linesCache[hoveredItem.id]" :key="line.id">
                    <td>{{ line.description || line.billing_article_name }}</td>
                    <td class="text-end">{{ Number(line.quantity).toFixed(2) }} {{ line.unit }}</td>
                    <td class="text-end">{{ formatCurrency(line.unit_price) }}</td>
                    <td class="text-end">{{ formatCurrency(line.net_amount) }}</td>
                    <td class="text-end">{{ formatCurrency(line.gross_amount) }}</td>
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

    <!-- Edit / New dialog -->
    <v-dialog v-model="dialog" max-width="1400" persistent>
      <OfferDialog :offer="selectedOffer" @saved="onSaved" @close="dialog = false" />
    </v-dialog>

    <!-- Preview dialog -->
    <DocumentPreviewDialog
      v-model="previewDialog"
      :doc-path="previewPath"
      :title="previewTitle"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useTheme } from 'vuetify'
import { hexToRgba } from '../utils/color'
import api from '../api'
import OfferDialog from '../components/OfferDialog.vue'
import DocumentPreviewDialog from '../components/DocumentPreviewDialog.vue'

const router = useRouter()
const theme = useTheme()
const primaryColor = computed(() => theme.current.value.colors.primary)
const highlightColor = computed(() => hexToRgba(primaryColor.value, 0.12))

const items = ref([])
const loading = ref(false)
const dialog = ref(false)
const selectedOffer = ref(null)
const previewDialog = ref(false)
const previewPath = ref(null)
const previewTitle = ref('')

const linesCache = ref({})
const linesLoading = ref({})
const detailOverlay = ref(false)
const hoveredItem = ref(null)
const hoveredRowId = ref(null)
let hideTimer = null
const rowBottom = ref(0)
const rowTop = ref(0)

const overlayAbove = computed(() => rowBottom.value > window.innerHeight / 2)

const overlayStyle = computed(() => {
  const base = { position: 'fixed', left: 0, right: 0, zIndex: 2000, display: 'flex', justifyContent: 'center', pointerEvents: 'none' }
  if (overlayAbove.value) {
    return { ...base, bottom: (window.innerHeight - rowTop.value) + 'px' }
  }
  return { ...base, top: rowBottom.value + 'px' }
})

const headers = [
  { title: 'Nr.', key: 'number' },
  { title: 'Adresse', key: 'address_display' },
  { title: 'Datum', key: 'document_date' },
  { title: 'Gültig bis', key: 'valid_until' },
  { title: 'Status', key: 'status' },
  { title: 'Brutto', key: 'gross_total', align: 'end' },
  { title: '', key: 'actions', sortable: false, align: 'end' },
]

const STATUS_LABELS = {
  draft: 'Entwurf', issued: 'Ausgestellt', sent: 'Versendet',
  accepted: 'Angenommen', rejected: 'Abgelehnt', converted: 'Umgewandelt',
}
const STATUS_COLORS = {
  draft: 'grey', issued: 'info', sent: 'primary',
  accepted: 'success', rejected: 'error', converted: 'purple',
}
function statusLabel(s) { return STATUS_LABELS[s] || s }
function statusColor(s) { return STATUS_COLORS[s] || 'grey' }

async function fetchItems() {
  loading.value = true
  linesCache.value = {}
  linesLoading.value = {}
  try {
    const res = await api.get('/offers/')
    items.value = res.data.results || res.data
  } finally {
    loading.value = false
  }
}

function openNew() { selectedOffer.value = null; dialog.value = true }
function openEdit(item) { selectedOffer.value = item; dialog.value = true }

async function onSaved() {
  dialog.value = false
  await fetchItems()
}

async function issueOffer(item) {
  if (!confirm(`Angebot ausstellen? Dabei wird eine Nummer vergeben.`)) return
  await api.post(`/offers/${item.id}/issue/`)
  await fetchItems()
}

async function convertToInvoice(item) {
  if (!confirm(`Angebot ${item.number || '#' + item.id} in eine Rechnung umwandeln?`)) return
  const res = await api.post(`/offers/${item.id}/convert/`)
  router.push({ path: '/invoices', query: { openId: res.data.id } })
}

function openPreview(item) {
  previewPath.value = `/offers/${item.id}`
  previewTitle.value = `Angebot ${item.number || '#' + item.id}`
  previewDialog.value = true
}

async function deleteItem(item) {
  if (!confirm(`Angebot ${item.number || '#' + item.id} wirklich löschen?`)) return
  await api.delete(`/offers/${item.id}/`)
  await fetchItems()
}

function onRowEnter(item, event) {
  clearTimeout(hideTimer)
  hoveredRowId.value = item.id
  const rect = event.currentTarget.getBoundingClientRect()
  rowBottom.value = rect.bottom
  rowTop.value = rect.top
  hoveredItem.value = item
  detailOverlay.value = true
  loadLines(item.id)
}

function onRowLeave() {
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

async function loadLines(id) {
  if (linesCache.value[id] !== undefined) return
  linesLoading.value[id] = true
  try {
    const res = await api.get(`/offers/${id}/lines/`)
    linesCache.value[id] = res.data.results || res.data
  } catch {
    linesCache.value[id] = []
  } finally {
    linesLoading.value[id] = false
  }
}

function formatCurrency(val) {
  return val != null ? Number(val).toFixed(2) + ' €' : ''
}

onMounted(fetchItems)
</script>
