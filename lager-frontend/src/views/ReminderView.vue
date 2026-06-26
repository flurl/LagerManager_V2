<template>
  <div>
    <v-row class="mb-2" align="center">
      <v-col><h2>Mahnungen</h2></v-col>
      <v-col cols="auto">
        <v-btn color="primary" prepend-icon="mdi-plus" @click="openNew">Neue Mahnung</v-btn>
      </v-col>
    </v-row>

    <v-row dense class="mb-2" align="center">
      <v-col cols="12" sm="5">
        <v-text-field v-model="filterText" label="Suche (Nr., Adresse)" prepend-inner-icon="mdi-magnify"
          clearable density="compact" hide-details />
      </v-col>
      <v-col cols="12" sm="3">
        <v-text-field v-model="filterFrom" label="Datum von" type="date" clearable density="compact" hide-details />
      </v-col>
      <v-col cols="12" sm="3">
        <v-text-field v-model="filterTo" label="Datum bis" type="date" clearable density="compact" hide-details />
      </v-col>
    </v-row>

    <v-data-table :headers="headers" :items="filteredItems" :loading="loading" density="compact">
      <template #item="{ item, columns }">
        <tr class="v-data-table__tr cursor-pointer"
          :style="{ backgroundColor: hoveredRowId === item.id ? highlightColor : undefined }"
          @click="item.status === 'draft' ? openEdit(item) : openPreview(item)"
          @mouseenter="onRowEnter(item, $event)" @mouseleave="onRowLeave">
          <td v-for="col in columns" :key="col.key" :class="col.align ? `text-${col.align}` : ''"
            class="v-data-table__td">
            <template v-if="col.key === 'invoice_number'">
              <a class="text-primary text-decoration-none cursor-pointer" @click.stop="openInvoicePreview(item)">
                {{ item.invoice_number || '#' + item.invoice }}
              </a>
            </template>
            <template v-else-if="col.key === 'status'">
              <v-chip size="x-small" :color="statusColor(item.status)">{{ statusLabel(item.status) }}</v-chip>
            </template>
            <template v-else-if="col.key === 'level'">
              <v-chip size="x-small" :color="item.level >= 3 ? 'error' : item.level === 2 ? 'warning' : 'grey'">
                Stufe {{ item.level }}
              </v-chip>
            </template>
            <template v-else-if="col.key === 'open_amount'">{{ formatCurrency(item.open_amount) }}</template>
            <template v-else-if="col.key === 'actions'">
              <v-tooltip text="Vorschau"><template #activator="{ props }">
                <v-icon v-bind="props" size="small" @click.stop="openPreview(item)">mdi-eye-outline</v-icon>
              </template></v-tooltip>
              <v-tooltip v-if="item.status === 'draft'" text="Ausstellen"><template #activator="{ props }">
                <v-icon v-bind="props" size="small" class="ml-1" @click.stop="issueReminder(item)">mdi-file-check</v-icon>
              </template></v-tooltip>
              <v-tooltip v-if="item.status === 'issued'" text="Per E-Mail versenden"><template #activator="{ props }">
                <v-icon v-bind="props" size="small" class="ml-1" @click.stop="openSend(item)">mdi-send</v-icon>
              </template></v-tooltip>
              <v-icon v-if="item.status === 'draft'" size="small" class="ml-1" @click.stop="openEdit(item)">mdi-pencil</v-icon>
              <v-icon v-if="item.status === 'draft'" size="small" class="ml-1" color="error" @click.stop="deleteItem(item)">mdi-delete</v-icon>
              <v-tooltip text="Verlauf"><template #activator="{ props }">
                <v-icon v-bind="props" size="small" class="ml-1" @click.stop="openHistory(item)">mdi-history</v-icon>
              </template></v-tooltip>
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

    <!-- Create / Edit dialog -->
    <v-dialog v-model="dialog" max-width="640">
      <v-card>
        <v-card-title>{{ form.id ? 'Mahnung bearbeiten' : 'Neue Mahnung' }}</v-card-title>
        <v-card-text>
          <v-autocomplete v-model="form.invoice" :items="invoices"
            :item-title="inv => (inv.number || '#' + inv.id) + ' — ' + (inv.address_display || '')"
            item-value="id" label="Rechnung *" />
          <v-row dense>
            <v-col cols="4">
              <v-select v-model="form.level" :items="[1,2,3]" label="Mahnstufe" />
            </v-col>
            <v-col cols="4">
              <v-text-field v-model="form.reminder_date" label="Mahnungsdatum *" type="date" />
            </v-col>
            <v-col cols="4">
              <v-text-field v-model="form.due_date" label="Zahlungsfrist *" type="date"
                :min="form.reminder_date"
                :rules="[v => !!v || 'Pflichtfeld', v => !form.reminder_date || v >= form.reminder_date || 'Darf nicht vor dem Mahnungsdatum liegen']" />
            </v-col>
          </v-row>
          <NumberInput v-model="form.fee" label="Mahngebühr (€)" class="mt-2" />
          <v-textarea v-model="form.notes" label="Anmerkungen" rows="2" auto-grow class="mt-2" />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="dialog = false">Abbrechen</v-btn>
          <v-btn color="primary" @click="save">Speichern</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <DocumentPreviewDialog v-model="previewDialog" :doc-path="previewPath" :title="previewTitle" />

    <HistoryDialog v-if="historyItem" v-model="historyDialog" :api-path="`/reminders/${historyItem.id}`" />

    <SendEmailDialog
      v-if="sendItem"
      v-model="sendDialog"
      :api-path="`/reminders/${sendItem.id}`"
      :doc-label="`Mahnung ${sendItem.number || '#' + sendItem.id}`"
      @sent="onSent"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useTheme } from 'vuetify'
import { hexToRgba } from '../utils/color'
import api from '../api'
import NumberInput from '../components/NumberInput.vue'
import DocumentPreviewDialog from '../components/DocumentPreviewDialog.vue'
import HistoryDialog from '../components/HistoryDialog.vue'
import SendEmailDialog from '../components/SendEmailDialog.vue'

const route = useRoute()
const router = useRouter()
const theme = useTheme()
const primaryColor = computed(() => theme.current.value.colors.primary)
const highlightColor = computed(() => hexToRgba(primaryColor.value, 0.12))

const items = ref([])
const invoices = ref([])
const filterText = ref('')
const filterFrom = ref('')
const filterTo = ref('')
const loading = ref(false)

const filteredItems = computed(() => {
  return items.value.filter(item => {
    if (filterText.value) {
      const q = filterText.value.toLowerCase()
      if (!(item.number || '').toLowerCase().includes(q) && !(item.invoice_number || '').toLowerCase().includes(q) && !(item.invoice_address_display || '').toLowerCase().includes(q)) return false
    }
    if (filterFrom.value && item.reminder_date < filterFrom.value) return false
    if (filterTo.value && item.reminder_date > filterTo.value) return false
    return true
  })
})
const dialog = ref(false)
const previewDialog = ref(false)
const previewPath = ref(null)
const previewTitle = ref('')
const form = ref({})
const historyDialog = ref(false)
const historyItem = ref(null)
const sendDialog = ref(false)
const sendItem = ref(null)

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
  { title: 'Rechnung', key: 'invoice_number' },
  { title: 'Adresse', key: 'invoice_address_display' },
  { title: 'Stufe', key: 'level' },
  { title: 'Datum', key: 'reminder_date' },
  { title: 'Fällig', key: 'due_date' },
  { title: 'Status', key: 'status' },
  { title: 'Offen', key: 'open_amount', align: 'end' },
  { title: '', key: 'actions', sortable: false, align: 'end' },
]

const STATUS_LABELS = { draft: 'Entwurf', issued: 'Ausgestellt', paid: 'Bezahlt' }
const STATUS_COLORS = { draft: 'grey', issued: 'warning', paid: 'success' }
function statusLabel(s) { return STATUS_LABELS[s] || s }
function statusColor(s) { return STATUS_COLORS[s] || 'grey' }

async function fetchItems() {
  loading.value = true
  linesCache.value = {}
  linesLoading.value = {}
  try {
    const [remRes, invRes] = await Promise.all([
      api.get('/reminders/'),
      api.get('/invoices/'),
    ])
    items.value = remRes.data.results || remRes.data
    invoices.value = invRes.data.results || invRes.data
  } finally {
    loading.value = false
  }
}

function openNew() {
  form.value = { invoice: null, level: 1, reminder_date: today(), due_date: '', fee: 0, notes: '' }
  dialog.value = true
}

function openEdit(item) {
  form.value = { ...item }
  dialog.value = true
}

function today() { return new Date().toISOString().slice(0, 10) }

async function save() {
  if (form.value.id) {
    await api.put(`/reminders/${form.value.id}/`, form.value)
  } else {
    await api.post('/reminders/', form.value)
  }
  dialog.value = false
  await fetchItems()
}

async function issueReminder(item) {
  if (!confirm('Mahnung ausstellen? Dabei wird eine Nummer vergeben.')) return
  await api.post(`/reminders/${item.id}/issue/`)
  await fetchItems()
}

function openHistory(item) {
  historyItem.value = item
  historyDialog.value = true
}

function openSend(item) {
  sendItem.value = item
  sendDialog.value = true
}

async function onSent() {
  await fetchItems()
}

function openPreview(item) {
  previewPath.value = `/reminders/${item.id}`
  previewTitle.value = `Mahnung ${item.number || '#' + item.id}`
  previewDialog.value = true
}

function openInvoicePreview(item) {
  previewPath.value = `/invoices/${item.invoice}`
  previewTitle.value = `Rechnung ${item.invoice_number || '#' + item.invoice}`
  previewDialog.value = true
}

async function deleteItem(item) {
  if (!confirm(`Mahnung ${item.number || '#' + item.id} wirklich löschen?`)) return
  await api.delete(`/reminders/${item.id}/`)
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
  loadLines(item)
}

function onRowLeave() {
  hideTimer = setTimeout(() => {
    detailOverlay.value = false
    hoveredRowId.value = null
  }, 150)
}

function onOverlayEnter() { clearTimeout(hideTimer) }

function onOverlayLeave() {
  detailOverlay.value = false
  hoveredRowId.value = null
}

async function loadLines(item) {
  if (linesCache.value[item.id] !== undefined) return
  linesLoading.value[item.id] = true
  try {
    const res = await api.get(`/invoices/${item.invoice}/lines/`)
    linesCache.value[item.id] = res.data.results || res.data
  } catch {
    linesCache.value[item.id] = []
  } finally {
    linesLoading.value[item.id] = false
  }
}

function formatCurrency(val) {
  return val != null ? Number(val).toFixed(2) + ' €' : ''
}

onMounted(async () => {
  await fetchItems()
  const openId = route.query.openId
  if (openId) {
    const reminder = items.value.find(i => String(i.id) === String(openId))
    if (reminder) openEdit(reminder)
    router.replace({ path: '/reminders' })
  }
})
</script>
