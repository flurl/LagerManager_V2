<template>
  <div>
    <v-row class="mb-2" align="center">
      <v-col><h2>Rechnungen</h2></v-col>
      <v-col cols="auto">
        <v-btn color="primary" prepend-icon="mdi-plus" @click="openNew">Neue Rechnung</v-btn>
      </v-col>
      <v-col cols="auto">
        <v-btn variant="tonal" prepend-icon="mdi-file-document-multiple-outline" @click="openTemplatePicker">
          Aus Vorlage
        </v-btn>
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
          :style="{
            backgroundColor: hoveredRowId === item.id ? highlightColor : isOverdue(item) ? overdueColor : undefined,
            textDecoration: item.status === 'cancelled' ? 'line-through' : undefined,
            opacity: item.status === 'cancelled' ? 0.5 : undefined,
          }"
          @click="item.status === 'draft' ? openEdit(item) : openPreview(item)"
          @mouseenter="onRowEnter(item, $event)" @mouseleave="onRowLeave">
          <td v-for="col in columns" :key="col.key" :class="col.align ? `text-${col.align}` : ''"
            class="v-data-table__td">
            <template v-if="col.key === 'number'">
              <div class="d-flex align-center">
                <v-tooltip v-if="isOverdue(item)" text="Überfällig"><template #activator="{ props }">
                  <v-icon v-bind="props" size="x-small" color="error" class="mr-1">mdi-clock-alert-outline</v-icon>
                </template></v-tooltip>
                <v-icon v-if="item.reverses" size="x-small" color="deep-orange" class="mr-1">mdi-file-undo</v-icon>
                <span>{{ item.number || '—' }}</span>
              </div>
              <div v-if="item.reverses_number" class="text-caption text-deep-orange" style="cursor:pointer; line-height:1.2" @click.stop="openOriginal(item)">
                ↩ {{ item.reverses_number }}
              </div>
            </template>
            <template v-else-if="col.key === 'status'">
              <v-chip size="x-small" :color="statusColor(item.status)">{{ statusLabel(item.status) }}</v-chip>
            </template>
            <template v-else-if="col.key === 'document_date'">{{ datumDisplay(item) }}</template>
            <template v-else-if="col.key === 'gross_total'">{{ Number(item.gross_total).toFixed(2) }} €</template>
            <template v-else-if="col.key === 'actions'">
              <v-tooltip text="Vorschau"><template #activator="{ props }">
                <v-icon v-bind="props" size="small" @click.stop="openPreview(item)">mdi-eye-outline</v-icon>
              </template></v-tooltip>
              <v-tooltip v-if="item.status === 'draft'" text="Ausstellen"><template #activator="{ props }">
                <v-icon v-bind="props" size="small" class="ml-1" @click.stop="issueInvoice(item)">mdi-file-check</v-icon>
              </template></v-tooltip>
              <v-tooltip v-if="['issued','sent'].includes(item.status) && !item.reverses" text="Per E-Mail versenden"><template #activator="{ props }">
                <v-icon v-bind="props" size="small" class="ml-1" @click.stop="openSend(item)">mdi-send</v-icon>
              </template></v-tooltip>
              <v-tooltip v-if="['issued','sent'].includes(item.status) && !item.reverses" text="Als bezahlt markieren"><template #activator="{ props }">
                <v-icon v-bind="props" size="small" class="ml-1" color="success" @click.stop="markPaid(item)">mdi-check-circle</v-icon>
              </template></v-tooltip>
              <v-tooltip v-if="isOverdue(item) && !item.reverses" text="Mahnung erstellen"><template #activator="{ props }">
                <v-icon v-bind="props" size="small" class="ml-1" color="warning" @click.stop="createReminder(item)">mdi-bell-alert</v-icon>
              </template></v-tooltip>
              <v-tooltip v-if="['issued','sent'].includes(item.status) && !item.reverses" text="Stornieren"><template #activator="{ props }">
                <v-icon v-bind="props" size="small" class="ml-1" color="error" @click.stop="cancelInvoice(item)">mdi-cancel</v-icon>
              </template></v-tooltip>
              <v-tooltip v-if="!item.reverses" text="Duplizieren"><template #activator="{ props }">
                <v-icon v-bind="props" size="small" class="ml-1" @click.stop="duplicateInvoice(item)">mdi-content-copy</v-icon>
              </template></v-tooltip>
              <v-tooltip v-if="!item.reverses" text="Als Vorlage speichern"><template #activator="{ props }">
                <v-icon v-bind="props" size="small" class="ml-1" @click.stop="openSaveTemplateForInvoice(item)">mdi-content-save-outline</v-icon>
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

    <v-dialog v-model="dialog" max-width="1400" persistent>
      <InvoiceDialog :invoice="selectedInvoice" :prefill="templatePrefill" @saved="onSaved" @close="dialog = false" />
    </v-dialog>

    <DocumentPreviewDialog v-model="previewDialog" :doc-path="previewPath" :title="previewTitle" />

    <HistoryDialog v-if="historyItem" v-model="historyDialog" :api-path="`/invoices/${historyItem.id}`" />

    <SendEmailDialog
      v-if="sendItem"
      v-model="sendDialog"
      :api-path="`/invoices/${sendItem.id}`"
      :doc-label="`${sendItem.reverses ? 'Stornorechnung' : 'Rechnung'} ${sendItem.number || '#' + sendItem.id}`"
      @sent="onSent"
    />

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

    <!-- Issue date dialog -->
    <v-dialog v-model="issueDialog" max-width="420" persistent>
      <v-card>
        <v-card-title>Rechnung ausstellen</v-card-title>
        <v-card-subtitle v-if="issueInvoiceItem" class="pb-0">
          {{ issueInvoiceItem.number || '#' + issueInvoiceItem.id }}
        </v-card-subtitle>
        <v-card-text>
          <p class="mb-3 text-body-2 text-medium-emphasis">
            Das Rechnungsdatum wird auf das heutige Datum ({{ fmtDate(today) }}) gesetzt.
          </p>
          <v-text-field
            v-model="issueDueDate"
            label="Fälligkeitsdatum *"
            type="date"
            :min="today"
            :rules="[v => !!v || 'Pflichtfeld', v => v >= today || 'Darf nicht vor dem Rechnungsdatum liegen']"
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="issueDialog = false">Abbrechen</v-btn>
          <v-btn color="primary" :disabled="!issueDueDate || issueDueDate < today" @click="confirmIssue">Ausstellen</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Cancel / Storno dialog -->
    <v-dialog v-model="cancelDialog" max-width="500" persistent>
      <v-card>
        <v-card-title>Rechnung stornieren</v-card-title>
        <v-card-subtitle v-if="cancelInvoiceItem" class="pb-0">
          {{ cancelInvoiceItem.number || '#' + cancelInvoiceItem.id }}
        </v-card-subtitle>
        <v-card-text>
          <v-textarea
            v-model="cancelReason"
            label="Stornierungsgrund *"
            rows="3"
            auto-grow
            :rules="[v => !!v?.trim() || 'Stornierungsgrund ist erforderlich']"
          />
          <v-radio-group v-model="cancelCreateDraft" class="mt-2">
            <v-radio :value="false" label="Nur Stornorechnung erstellen" />
            <v-radio :value="true" label="Stornorechnung erstellen und neuen Rechnungsentwurf aus Originalrechnung anlegen" />
          </v-radio-group>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="cancelDialog = false">Abbrechen</v-btn>
          <v-btn color="error" :disabled="!cancelReason?.trim()" @click="confirmCancel">Stornieren</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Template picker dialog -->
    <v-dialog v-model="templatePickerDialog" max-width="600">
      <v-card>
        <v-card-title>Rechnung aus Vorlage erstellen</v-card-title>
        <v-card-text>
          <div v-if="templatesLoading" class="d-flex justify-center pa-4">
            <v-progress-circular indeterminate />
          </div>
          <div v-else-if="!templates.length" class="text-medium-emphasis pa-2">
            Keine Vorlagen vorhanden.
          </div>
          <v-list v-else>
            <v-list-item v-for="tpl in templates" :key="tpl.id" @click="useTemplate(tpl)">
              <v-list-item-title>{{ tpl.name }}</v-list-item-title>
              <v-list-item-subtitle>{{ Number(tpl.gross_total).toFixed(2) }} €</v-list-item-subtitle>
              <template #append>
                <v-icon size="small" class="mr-3" @click.stop="renameTemplate(tpl)">mdi-pencil</v-icon>
                <v-icon size="small" color="error" @click.stop="deleteTemplate(tpl)">mdi-delete</v-icon>
              </template>
            </v-list-item>
          </v-list>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="templatePickerDialog = false">Schließen</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Rename template dialog -->
    <v-dialog v-model="renameTemplateDialog" max-width="380">
      <v-card>
        <v-card-title>Vorlage umbenennen</v-card-title>
        <v-card-text>
          <v-text-field v-model="renameTemplateName" label="Name *" :rules="[v => !!v?.trim() || 'Pflichtfeld']"
            autofocus @keyup.enter="confirmRenameTemplate" />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="renameTemplateDialog = false">Abbrechen</v-btn>
          <v-btn color="primary" :disabled="!renameTemplateName?.trim()" @click="confirmRenameTemplate">Speichern</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Save invoice as template dialog -->
    <v-dialog v-model="saveTemplateDialog" max-width="420">
      <v-card>
        <v-card-title>Als Vorlage speichern</v-card-title>
        <v-card-subtitle v-if="saveTemplateItem" class="pb-0">
          {{ saveTemplateItem.number || '#' + saveTemplateItem.id }}
        </v-card-subtitle>
        <v-card-text>
          <v-text-field v-model="saveTemplateName" label="Vorlagenname *" :rules="[v => !!v?.trim() || 'Pflichtfeld']"
            autofocus @keyup.enter="confirmSaveTemplateForInvoice" />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="saveTemplateDialog = false">Abbrechen</v-btn>
          <v-btn color="primary" :disabled="!saveTemplateName?.trim()" @click="confirmSaveTemplateForInvoice">Speichern</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-snackbar v-model="errorSnackbar" color="error" timeout="-1" location="bottom">
      {{ errorMessage }}
      <template #actions>
        <v-btn variant="text" @click="errorSnackbar = false">Schließen</v-btn>
      </template>
    </v-snackbar>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useTheme } from 'vuetify'
import { hexToRgba } from '../utils/color'
import { extractErrorMessage } from '../utils/errorMessage'
import api from '../api'
import InvoiceDialog from '../components/InvoiceDialog.vue'
import DocumentPreviewDialog from '../components/DocumentPreviewDialog.vue'
import HistoryDialog from '../components/HistoryDialog.vue'
import SendEmailDialog from '../components/SendEmailDialog.vue'

const route = useRoute()
const router = useRouter()
const theme = useTheme()
const primaryColor = computed(() => theme.current.value.colors.primary)
const highlightColor = computed(() => hexToRgba(primaryColor.value, 0.12))
const overdueColor = computed(() => hexToRgba(theme.current.value.colors.error, 0.15))

const today = new Date().toISOString().slice(0, 10)
function isOverdue(item) {
  return ['issued', 'sent'].includes(item.status) && item.due_date && item.due_date < today
}

const items = ref([])
const filterText = ref('')
const filterFrom = ref('')
const filterTo = ref('')
const loading = ref(false)

const filteredItems = computed(() => {
  return items.value.filter(item => {
    if (filterText.value) {
      const q = filterText.value.toLowerCase()
      if (!(item.number || '').toLowerCase().includes(q) && !(item.address_display || '').toLowerCase().includes(q)) return false
    }
    if (filterFrom.value && item.document_date < filterFrom.value) return false
    if (filterTo.value && item.document_date > filterTo.value) return false
    return true
  })
})
const dialog = ref(false)
const selectedInvoice = ref(null)
const templatePrefill = ref(null)
const templatePickerDialog = ref(false)
const templates = ref([])
const templatesLoading = ref(false)
const renameTemplateDialog = ref(false)
const renameTemplateItem = ref(null)
const renameTemplateName = ref('')
const saveTemplateDialog = ref(false)
const saveTemplateItem = ref(null)
const saveTemplateName = ref('')
const errorSnackbar = ref(false)
const errorMessage = ref('')
const previewDialog = ref(false)
const previewPath = ref(null)
const previewTitle = ref('')
const historyDialog = ref(false)
const historyItem = ref(null)
const sendDialog = ref(false)
const sendItem = ref(null)
const paidDialog = ref(false)
const paidDate = ref('')
const paidInvoiceId = ref(null)

const cancelDialog = ref(false)
const cancelInvoiceItem = ref(null)
const cancelReason = ref('')
const cancelCreateDraft = ref(false)

const issueDialog = ref(false)
const issueInvoiceItem = ref(null)
const issueDueDate = ref('')
const paymentTermsDays = ref(14)

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
  { title: 'Leistungsdt. (Rechnungsdt.)', key: 'document_date' },
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

function openNew() { selectedInvoice.value = null; templatePrefill.value = null; dialog.value = true }
function openEdit(item) { selectedInvoice.value = item; templatePrefill.value = null; dialog.value = true }
async function onSaved() { dialog.value = false; await fetchItems() }

async function openTemplatePicker() {
  templatePickerDialog.value = true
  templatesLoading.value = true
  try {
    const res = await api.get('/invoice-templates/')
    templates.value = res.data.results || res.data
  } finally {
    templatesLoading.value = false
  }
}

async function useTemplate(tpl) {
  const res = await api.get(`/invoice-templates/${tpl.id}/`)
  selectedInvoice.value = null
  templatePrefill.value = { notes: res.data.notes, lines: res.data.lines }
  templatePickerDialog.value = false
  dialog.value = true
}

function renameTemplate(tpl) {
  renameTemplateItem.value = tpl
  renameTemplateName.value = tpl.name
  renameTemplateDialog.value = true
}

async function confirmRenameTemplate() {
  const name = renameTemplateName.value?.trim()
  if (!name || !renameTemplateItem.value) return
  const res = await api.patch(`/invoice-templates/${renameTemplateItem.value.id}/`, { name })
  const idx = templates.value.findIndex(t => t.id === renameTemplateItem.value.id)
  if (idx !== -1) templates.value.splice(idx, 1, res.data)
  renameTemplateDialog.value = false
}

async function deleteTemplate(tpl) {
  if (!confirm(`Vorlage "${tpl.name}" wirklich löschen?`)) return
  await api.delete(`/invoice-templates/${tpl.id}/`)
  templates.value = templates.value.filter(t => t.id !== tpl.id)
}

function openSaveTemplateForInvoice(item) {
  saveTemplateItem.value = item
  saveTemplateName.value = ''
  saveTemplateDialog.value = true
}

async function confirmSaveTemplateForInvoice() {
  const name = saveTemplateName.value?.trim()
  if (!name || !saveTemplateItem.value) return
  try {
    await api.post(`/invoices/${saveTemplateItem.value.id}/save-as-template/`, { name })
    saveTemplateDialog.value = false
  } catch (err) {
    errorMessage.value = extractErrorMessage(err, 'Vorlage konnte nicht gespeichert werden.')
    errorSnackbar.value = true
  }
}

function fmtDate(iso) {
  if (!iso) return ''
  const [y, m, d] = iso.split('-')
  return `${d}.${m}.${y}`
}

function datumDisplay(item) {
  if (!item.service_date) {
    return item.status === 'draft' ? '—' : fmtDate(item.document_date)
  }
  return `${fmtDate(item.service_date)} (${fmtDate(item.document_date)})`
}

function issueInvoice(item) {
  issueInvoiceItem.value = item
  const d = new Date(today)
  d.setDate(d.getDate() + paymentTermsDays.value)
  issueDueDate.value = d.toISOString().slice(0, 10)
  issueDialog.value = true
}

async function confirmIssue() {
  const item = issueInvoiceItem.value
  if (!item || !issueDueDate.value) return
  await api.post(`/invoices/${item.id}/issue/`, { due_date: issueDueDate.value })
  issueDialog.value = false
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

function cancelInvoice(item) {
  cancelInvoiceItem.value = item
  cancelReason.value = ''
  cancelCreateDraft.value = false
  cancelDialog.value = true
}

async function confirmCancel() {
  const item = cancelInvoiceItem.value
  if (!item || !cancelReason.value?.trim()) return
  const res = await api.post(`/invoices/${item.id}/cancel/`, {
    reason: cancelReason.value.trim(),
    create_draft: cancelCreateDraft.value,
  })
  cancelDialog.value = false
  await fetchItems()
  if (res.data.draft) {
    openEdit(res.data.draft)
  }
}

async function createReminder(item) {
  const res = await api.post(`/invoices/${item.id}/create-reminder/`)
  router.push({ path: '/reminders', query: { openId: res.data.id } })
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
  previewPath.value = `/invoices/${item.id}`
  previewTitle.value = `${item.reverses ? 'Stornorechnung' : 'Rechnung'} ${item.number || '#' + item.id}`
  previewDialog.value = true
}

function openOriginal(item) {
  previewPath.value = `/invoices/${item.reverses}`
  previewTitle.value = `Rechnung ${item.reverses_number || '#' + item.reverses}`
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
  try {
    const cfgRes = await api.get('/config/')
    paymentTermsDays.value = cfgRes.data.config?.INVOICE_PAYMENT_TERMS_DAYS?.value ?? 14
  } catch {
    // keep default
  }
  const openId = route.query.openId
  if (openId) {
    const invoice = items.value.find(i => String(i.id) === String(openId))
    if (invoice) openEdit(invoice)
    router.replace({ path: '/invoices' })
  }
})
</script>
