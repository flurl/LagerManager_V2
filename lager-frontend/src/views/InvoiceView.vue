<template>
  <div>
    <v-row class="mb-2" align="center">
      <v-col><h2>Rechnungen</h2></v-col>
      <v-col cols="auto">
        <v-btn color="primary" prepend-icon="mdi-plus" @click="openNew">Neue Rechnung</v-btn>
      </v-col>
    </v-row>

    <v-data-table :headers="headers" :items="items" :loading="loading" density="compact">
      <template #item="{ item, columns }">
        <tr class="v-data-table__tr cursor-pointer"
          :style="{
            backgroundColor: hoveredRowId === item.id ? highlightColor : undefined,
            textDecoration: item.status === 'cancelled' ? 'line-through' : undefined,
            opacity: item.status === 'cancelled' ? 0.5 : undefined,
          }"
          @click="item.status === 'draft' ? openEdit(item) : openPreview(item)"
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
                <v-icon v-bind="props" size="small" class="ml-1" @click.stop="issueInvoice(item)">mdi-file-check</v-icon>
              </template></v-tooltip>
              <v-tooltip v-if="item.status === 'issued'" text="Per E-Mail versenden (demnächst)"><template #activator="{ props }">
                <v-icon v-bind="props" size="small" class="ml-1" disabled>mdi-send</v-icon>
              </template></v-tooltip>
              <v-tooltip v-if="['issued','sent'].includes(item.status)" text="Als bezahlt markieren"><template #activator="{ props }">
                <v-icon v-bind="props" size="small" class="ml-1" color="success" @click.stop="markPaid(item)">mdi-check-circle</v-icon>
              </template></v-tooltip>
              <v-tooltip v-if="['issued','sent'].includes(item.status)" text="Mahnung erstellen"><template #activator="{ props }">
                <v-icon v-bind="props" size="small" class="ml-1" color="warning" @click.stop="createReminder(item)">mdi-bell-alert</v-icon>
              </template></v-tooltip>
              <v-tooltip v-if="['issued','sent'].includes(item.status)" text="Stornieren"><template #activator="{ props }">
                <v-icon v-bind="props" size="small" class="ml-1" color="error" @click.stop="cancelInvoice(item)">mdi-cancel</v-icon>
              </template></v-tooltip>
              <v-tooltip text="Duplizieren"><template #activator="{ props }">
                <v-icon v-bind="props" size="small" class="ml-1" @click.stop="duplicateInvoice(item)">mdi-content-copy</v-icon>
              </template></v-tooltip>
              <v-icon v-if="item.status === 'draft'" size="small" class="ml-1" @click.stop="openEdit(item)">mdi-pencil</v-icon>
              <v-icon v-if="item.status === 'draft'" size="small" class="ml-1" color="error" @click.stop="deleteItem(item)">mdi-delete</v-icon>
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

    <v-dialog v-model="dialog" max-width="1400" persistent>
      <InvoiceDialog :invoice="selectedInvoice" @saved="onSaved" @close="dialog = false" />
    </v-dialog>

    <DocumentPreviewDialog v-model="previewDialog" :doc-path="previewPath" :title="previewTitle" />

    <!-- Mark paid dialog -->
    <v-dialog v-model="paidDialog" max-width="340">
      <v-card>
        <v-card-title>Als bezahlt markieren</v-card-title>
        <v-card-text>
          <v-text-field v-model="paidDate" label="Zahlungsdatum" type="date" />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="paidDialog = false">Abbrechen</v-btn>
          <v-btn color="success" @click="confirmMarkPaid">Bestätigen</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useTheme } from 'vuetify'
import { hexToRgba } from '../utils/color'
import api from '../api'
import InvoiceDialog from '../components/InvoiceDialog.vue'
import DocumentPreviewDialog from '../components/DocumentPreviewDialog.vue'

const route = useRoute()
const router = useRouter()
const theme = useTheme()
const primaryColor = computed(() => theme.current.value.colors.primary)
const highlightColor = computed(() => hexToRgba(primaryColor.value, 0.12))

const items = ref([])
const loading = ref(false)
const dialog = ref(false)
const selectedInvoice = ref(null)
const previewDialog = ref(false)
const previewPath = ref(null)
const previewTitle = ref('')
const paidDialog = ref(false)
const paidDate = ref('')
const paidInvoiceId = ref(null)

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
  { title: 'Fällig', key: 'due_date' },
  { title: 'Status', key: 'status' },
  { title: 'Brutto', key: 'gross_total', align: 'end' },
  { title: '', key: 'actions', sortable: false, align: 'end' },
]

const STATUS_LABELS = { draft: 'Entwurf', issued: 'Ausgestellt', sent: 'Versendet', paid: 'Bezahlt', cancelled: 'Storniert' }
const STATUS_COLORS = { draft: 'grey', issued: 'info', sent: 'primary', paid: 'success', cancelled: 'error' }
function statusLabel(s) { return STATUS_LABELS[s] || s }
function statusColor(s) { return STATUS_COLORS[s] || 'grey' }

async function fetchItems() {
  loading.value = true
  linesCache.value = {}
  linesLoading.value = {}
  try {
    const res = await api.get('/invoices/')
    items.value = res.data.results || res.data
  } finally {
    loading.value = false
  }
}

function openNew() { selectedInvoice.value = null; dialog.value = true }
function openEdit(item) { selectedInvoice.value = item; dialog.value = true }
async function onSaved() { dialog.value = false; await fetchItems() }

async function issueInvoice(item) {
  if (!confirm('Rechnung ausstellen? Dabei wird eine Nummer vergeben.')) return
  await api.post(`/invoices/${item.id}/issue/`)
  await fetchItems()
}

function markPaid(item) {
  paidInvoiceId.value = item.id
  paidDate.value = new Date().toISOString().slice(0, 10)
  paidDialog.value = true
}

async function confirmMarkPaid() {
  await api.post(`/invoices/${paidInvoiceId.value}/mark-paid/`, { paid_at: paidDate.value })
  paidDialog.value = false
  await fetchItems()
}

async function cancelInvoice(item) {
  if (!confirm(`Rechnung ${item.number || '#' + item.id} wirklich stornieren?`)) return
  await api.post(`/invoices/${item.id}/cancel/`)
  await fetchItems()
}

async function createReminder(item) {
  alert(`Für Rechnung ${item.number} eine Mahnung erstellen: gehen Sie zu "Mahnungen" und wählen Sie diese Rechnung.`)
}

function openPreview(item) {
  previewPath.value = `/invoices/${item.id}`
  previewTitle.value = `Rechnung ${item.number || '#' + item.id}`
  previewDialog.value = true
}

async function deleteItem(item) {
  if (!confirm(`Rechnung ${item.number || '#' + item.id} wirklich löschen?`)) return
  await api.delete(`/invoices/${item.id}/`)
  await fetchItems()
}

async function duplicateInvoice(item) {
  const res = await api.post(`/invoices/${item.id}/duplicate/`)
  await fetchItems()
  openEdit(res.data)
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
    const res = await api.get(`/invoices/${id}/lines/`)
    linesCache.value[id] = res.data.results || res.data
  } catch {
    linesCache.value[id] = []
  } finally {
    linesLoading.value[id] = false
  }
}

function formatCurrency(val) {
  return val != null ? Number(val).toFixed(2) + ' €' : ''
}

onMounted(async () => {
  await fetchItems()
  const openId = route.query.openId
  if (openId) {
    const invoice = items.value.find(i => String(i.id) === String(openId))
    if (invoice) openEdit(invoice)
    router.replace({ path: '/invoices' })
  }
})
</script>
