<template>
  <v-card>
    <v-card-title class="d-flex align-center pa-4" :class="typeConfig.bgClass">
      <v-icon :color="typeConfig.color" size="32" class="mr-3">{{ typeConfig.icon }}</v-icon>
      <span :class="`text-${typeConfig.color}`">{{ typeConfig.label }}</span>
      <span v-if="!isNew" class="ml-2 text-medium-emphasis text-body-1">#{{ form.id }}</span>
      <v-spacer />
      <v-btn icon @click="$emit('close')"><v-icon>mdi-close</v-icon></v-btn>
    </v-card-title>

    <v-card-text>
      <v-row dense>
        <v-col cols="4">
          <v-select v-model="form.partner" :items="partners" item-title="name" item-value="id" label="Partner"
            :rules="[v => !!v || 'Pflichtfeld']" />
        </v-col>
        <v-col cols="4">
          <v-text-field v-model="form.date" label="Datum" type="date" :error-messages="dateError" />
        </v-col>
        <v-col cols="4">
          <v-text-field v-model="form.comment" label="Kommentar" />
        </v-col>
      </v-row>

      <v-divider class="mb-2" />

      <v-tabs v-model="activeTab" density="compact">
        <v-tab value="positions">Positionen</v-tab>
        <v-tab value="documents" :disabled="isNew">
          Dokumente
        </v-tab>
      </v-tabs>

      <v-tabs-window v-model="activeTab">
        <v-tabs-window-item value="positions">
          <!-- Detail lines -->
          <v-row class="mb-1 mt-2" align="center">
            <v-col>
              <strong>Positionen</strong>
              <span v-if="linesError" class="ml-3 text-error text-caption">{{ linesError }}</span>
            </v-col>
            <v-col cols="auto" class="d-flex gap-2">
              <v-btn size="small" prepend-icon="mdi-import" @click="openImportDialog">Importieren</v-btn>
              <v-btn size="small" prepend-icon="mdi-plus" @click="addLine">Position hinzufügen</v-btn>
            </v-col>
          </v-row>

          <v-table density="compact">
            <thead>
              <tr>
                <th>Artikel</th>
                <th>Menge</th>
                <th>EK-Preis</th>
                <th>MwSt</th>
                <th class="text-right">Netto</th>
                <th class="text-right">Brutto</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(line, idx) in lines" :key="idx">
                <td>
                  <v-autocomplete v-model="line.article" :items="warehouseArticles" item-title="article_name"
                    item-value="article" density="compact" hide-details style="min-width: 180px" />
                </td>
                <td>
                  <NumberInput v-model="line.quantity" hide-controls density="compact" hide-details style="width: 120px" />
                </td>
                <td>
                  <div class="d-flex align-center">
                    <NumberInput v-model="line.unit_price" :decimals="4" hide-controls density="compact" hide-details
                      style="width: 130px" />
                    <v-icon size="small" class="ml-1 text-medium-emphasis" style="cursor: pointer"
                      title="Gesamtpreis durch Menge teilen"
                      @click="line.quantity ? line.unit_price = +(line.unit_price / line.quantity).toFixed(4) : null">
                      mdi-division
                    </v-icon>
                  </div>
                </td>
                <td>
                  <div class="d-flex align-center">
                    <v-select v-model="line.tax_rate" :items="taxRates" item-title="name" item-value="id" density="compact"
                      hide-details style="width: 110px" :error="!line.tax_rate" />
                    <v-icon size="small" class="ml-1 text-medium-emphasis" style="cursor: pointer"
                      title="Bruttopreis in Nettopreis umrechnen"
                      @click="line.tax_rate ? line.unit_price = +(line.unit_price / (1 + getTaxPercent(line.tax_rate) / 100)).toFixed(4) : null">
                      mdi-percent-outline
                    </v-icon>
                  </div>
                </td>
                <td class="text-right">{{ lineNet(line) }}</td>
                <td class="text-right">{{ lineGross(line) }}</td>
                <td>
                  <v-icon size="small" color="error" @click="removeLine(idx)">mdi-delete</v-icon>
                </td>
              </tr>
            </tbody>
            <tfoot>
              <tr>
                <td colspan="4"><strong>Gesamt</strong></td>
                <td class="text-right"><strong>{{ totalNet }}</strong></td>
                <td class="text-right"><strong>{{ totalGross }}</strong></td>
                <td></td>
              </tr>
            </tfoot>
          </v-table>

          <!-- Skonto -->
          <v-row class="mt-3" dense>
            <v-col cols="3">
              <NumberInput v-model="skontoPercent" label="Skonto %" density="compact" />
            </v-col>
            <v-col cols="auto" class="d-flex align-center">
              <v-btn size="small" @click="applySkonto" :disabled="!form.id">Skonto anwenden</v-btn>
            </v-col>
          </v-row>
        </v-tabs-window-item>

        <v-tabs-window-item value="documents" class="pt-3">
          <AttachmentGallery v-if="form.id" :movement-id="form.id" />
        </v-tabs-window-item>
      </v-tabs-window>
    </v-card-text>

    <v-card-actions>
      <v-spacer />
      <v-btn @click="$emit('close')">Abbrechen</v-btn>
      <v-btn :color="typeConfig.color" :loading="saving" @click="save">Speichern</v-btn>
    </v-card-actions>
  </v-card>

  <!-- Import dialog -->
  <v-dialog v-model="importDialog" max-width="860" persistent>
    <v-card>
      <v-card-title class="d-flex align-center pa-4">
        <v-icon class="mr-2">mdi-import</v-icon>
        Positionen importieren
        <v-spacer />
        <v-btn icon @click="importDialog = false"><v-icon>mdi-close</v-icon></v-btn>
      </v-card-title>

      <!-- Step 1: JSON input -->
      <v-card-text v-if="importStep === 'input'">
        <v-row dense align="start">
          <v-col>
            <v-textarea v-model="importJson" label="JSON einfügen" rows="12" auto-grow
              :error-messages="importError" hide-details="auto" />
          </v-col>
          <v-col cols="auto" class="pt-2 d-flex flex-column gap-1">
            <v-btn
              v-for="p in AI_PROVIDERS"
              :key="p.id"
              icon
              :title="`Von ${p.label} laden`"
              :loading="apiLoading && selectedProviderId === p.id"
              :disabled="apiLoading && selectedProviderId !== p.id"
              :variant="selectedProviderId === p.id ? 'tonal' : 'text'"
              @click="selectedProviderId = p.id; callAiProvider()"
            >
              <img :src="p.imgSrc" :alt="p.label" width="20" height="20" />
            </v-btn>
          </v-col>
        </v-row>
      </v-card-text>

      <!-- Step 2: Preview -->
      <v-card-text v-else>
        <v-table density="compact">
          <thead>
            <tr>
              <th style="width: 40px"></th>
              <th>Name</th>
              <th>Artikel</th>
              <th>Menge</th>
              <th>EK-Preis</th>
              <th>MwSt %</th>
              <th class="text-right">Netto</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, idx) in importPreviewLines" :key="idx"
              :class="!row.matched ? 'text-medium-emphasis' : ''">
              <td>
                <v-checkbox v-model="row.selected" hide-details density="compact" />
              </td>
              <td>{{ row.name }}</td>
              <td>
                <span v-if="row.matched">{{ row.articleName }}</span>
                <span v-else class="d-flex align-center">
                  <v-icon size="small" color="warning" class="mr-1">mdi-alert</v-icon>
                  nicht zugeordnet
                </span>
              </td>
              <td>{{ row.quantity }}</td>
              <td>{{ row.unit_price }}</td>
              <td>{{ row.taxPercent }}</td>
              <td class="text-right">{{ (row.quantity * row.unit_price).toFixed(2) }}</td>
            </tr>
          </tbody>
        </v-table>
      </v-card-text>

      <v-card-actions>
        <v-spacer />
        <v-btn @click="importDialog = false">Abbrechen</v-btn>
        <v-btn v-if="importStep === 'preview'" @click="importStep = 'input'">Zurück</v-btn>
        <v-btn v-if="importStep === 'input'" color="primary" @click="parseImportJson">Vorschau</v-btn>
        <v-btn v-else color="primary" @click="confirmImport">Übernehmen</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- Duplicate warning dialog -->
  <v-dialog v-model="duplicateDialog" max-width="480">
    <v-card>
      <v-card-title class="d-flex align-center pa-4 bg-warning-lighten-5">
        <v-icon color="warning" size="28" class="mr-2">mdi-alert</v-icon>
        <span class="text-warning">Bereits vorhanden</span>
      </v-card-title>
      <v-card-text class="pt-4">
        Es {{ duplicateCount === 1 ? 'existiert bereits ein Eintrag' : `existieren bereits ${duplicateCount} Einträge`
        }}
        für diesen Partner am selben Tag. Trotzdem speichern?
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn @click="duplicateDialog = false">Abbrechen</v-btn>
        <v-btn color="warning" @click="confirmSave">Trotzdem speichern</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { usePeriodStore } from '../stores/period'
import api from '../api'
import NumberInput from './NumberInput.vue'
import AttachmentGallery from './AttachmentGallery.vue'
import { AI_PROVIDERS, createProvider } from '../ai/index.js'

const props = defineProps({
  movement: { type: Object, default: null },
  movementType: { type: String, default: 'delivery' },
})
const emit = defineEmits(['saved', 'close'])

const periodStore = usePeriodStore()
const activeTab = ref('positions')
const saving = ref(false)
const partners = ref([])
const taxRates = ref([])
const warehouseArticles = ref([])
const skontoPercent = ref(0)
const duplicateDialog = ref(false)
const duplicateCount = ref(0)
const importDialog = ref(false)
const importStep = ref('input')
const importJson = ref('')
const importError = ref('')
const importPreviewLines = ref([])
const apiLoading = ref(false)
const dateError = ref('')
const linesError = ref('')
const defaultTaxRateId = ref(null)
const aiConfig = ref({})
const selectedProviderId = ref(AI_PROVIDERS[0].id)
const originalDetailIds = ref([])

const isNew = computed(() => !props.movement?.id)

// Derive the effective type: existing movements use their own type, new ones use the prop
const effectiveType = computed(() => props.movement?.movement_type ?? props.movementType)

const typeConfig = computed(() => {
  if (effectiveType.value === 'consumption') {
    return {
      label: isNew.value ? 'Neuer Verbrauch' : 'Verbrauch',
      icon: 'mdi-package-down',
      color: 'deep-orange',
      bgClass: 'bg-deep-orange-lighten-5',
      partnerType: 'consumer',
    }
  }
  return {
    label: isNew.value ? 'Neue Lieferung' : 'Lieferung',
    icon: 'mdi-truck-delivery',
    color: 'blue',
    bgClass: 'bg-blue-lighten-5',
    partnerType: 'supplier',
  }
})

const form = ref({ partner: null, date: null, comment: '', period: null })
const lines = ref([])

async function initForm() {
  activeTab.value = 'positions'
  dateError.value = ''
  linesError.value = ''
  if (props.movement) {
    const res = await api.get(`/stock-movements/${props.movement.id}/`)
    const full = res.data
    form.value = { ...full }
    lines.value = (full.details || []).map((d) => ({ ...d }))
    originalDetailIds.value = (full.details || []).map((d) => d.id)
  } else {
    form.value = {
      partner: null,
      date: new Date().toISOString().slice(0, 10),
      comment: '',
      movement_type: props.movementType,
      period: periodStore.currentPeriodId,
    }
    lines.value = []
  }
}

async function loadPartners() {
  const res = await api.get('/partners/', { params: { partner_type: typeConfig.value.partnerType } })
  partners.value = res.data.results || res.data
}

function addLine() {
  lines.value.push({ article: null, quantity: 1, unit_price: 0, tax_rate: defaultTaxRateId.value })
}

function removeLine(idx) {
  lines.value.splice(idx, 1)
}

function getTaxPercent(taxRateId) {
  const tr = taxRates.value.find((t) => t.id === taxRateId)
  return tr ? Number(tr.percent) : 0
}

function lineNet(line) {
  return (Number(line.quantity) * Number(line.unit_price)).toFixed(2)
}

function lineGross(line) {
  const net = Number(lineNet(line))
  const pct = getTaxPercent(line.tax_rate)
  return (net * (1 + pct / 100)).toFixed(2)
}

const totalNet = computed(() =>
  lines.value.reduce((s, l) => s + Number(lineNet(l)), 0).toFixed(2)
)
const totalGross = computed(() =>
  lines.value.reduce((s, l) => s + Number(lineGross(l)), 0).toFixed(2)
)

async function save() {
  dateError.value = ''
  linesError.value = ''

  const period = periodStore.currentPeriod
  if (form.value.date && period) {
    if (form.value.date < period.start || form.value.date > period.end) {
      dateError.value = `Datum muss zwischen ${period.start} und ${period.end} liegen`
    }
  }
  if (lines.value.length === 0) {
    linesError.value = 'Mindestens eine Position erforderlich'
  } else if (lines.value.some((l) => !l.tax_rate)) {
    linesError.value = 'Alle Positionen müssen einen Steuersatz haben'
  }
  if (dateError.value || linesError.value) return

  if (form.value.partner && form.value.date) {
    const res = await api.get('/stock-movements/', {
      params: {
        partner_id: form.value.partner,
        date: form.value.date,
        period_id: periodStore.currentPeriodId,
        movement_type: effectiveType.value,
      },
    })
    const matches = (res.data.results ?? res.data).filter((m) => m.id !== form.value.id)
    if (matches.length > 0) {
      duplicateCount.value = matches.length
      duplicateDialog.value = true
      return
    }
  }
  await doSave()
}

async function confirmSave() {
  duplicateDialog.value = false
  await doSave()
}

async function doSave() {
  saving.value = true
  try {
    let movementId = form.value.id
    if (isNew.value) {
      const res = await api.post('/stock-movements/', {
        ...form.value,
        period: periodStore.currentPeriodId,
      })
      movementId = res.data.id
    } else {
      await api.put(`/stock-movements/${movementId}/`, form.value)
      // Delete all existing details and re-create
      await Promise.all(
        originalDetailIds.value.map((id) => api.delete(`/stock-movements/${movementId}/details/${id}/`))
      )
      originalDetailIds.value = []
    }
    // Create detail lines
    await Promise.all(
      lines.value.map((l) =>
        api.post(`/stock-movements/${movementId}/details/`, { ...l, stock_movement: movementId })
      )
    )
    emit('saved')
  } finally {
    saving.value = false
  }
}

function openImportDialog() {
  importStep.value = 'input'
  importJson.value = ''
  importError.value = ''
  importPreviewLines.value = []
  importDialog.value = true
}

function parseImportJson() {
  importError.value = ''
  let data
  try {
    data = JSON.parse(importJson.value)
  } catch {
    importError.value = 'Ungültiges JSON'
    return
  }
  if (!Array.isArray(data?.articles)) {
    importError.value = 'JSON muss ein "articles"-Array enthalten'
    return
  }
  importPreviewLines.value = data.articles.map((a) => {
    const wa = a.ID != null ? warehouseArticles.value.find((w) => w.source_article_id === a.ID) : null
    const tr = taxRates.value.find((t) => Number(t.percent) === a.tax) ?? taxRates.value.find((t) => t.id === defaultTaxRateId.value)
    const net = (a.total_price ?? 0) - (a.discount ?? 0)
    const unit_price = a.quantity ? +(net / a.quantity).toFixed(4) : 0
    return {
      name: a.Name,
      quantity: a.quantity,
      unit_price,
      taxPercent: a.tax,
      tax_rate: tr?.id ?? null,
      article: wa?.article ?? null,
      articleName: wa?.article_name ?? null,
      matched: wa != null,
      selected: true,
    }
  })
  importStep.value = 'preview'
}

function confirmImport() {
  for (const row of importPreviewLines.value) {
    if (!row.selected) continue
    lines.value.push({
      article: row.article,
      quantity: row.quantity,
      unit_price: row.unit_price,
      tax_rate: row.tax_rate,
    })
  }
  importDialog.value = false
}

function buildArticleMarkdownTable() {
  const rows = warehouseArticles.value
    .filter((wa) => wa.source_article_id != null)
    .map((wa) => ` ${wa.source_article_id} | ${wa.article_name}`)
  return ' artikel_id |    artikel_bezeichnung\n------------+----------------------------\n' + rows.join('\n')
}

async function callAiProvider() {
  importError.value = ''
  if (!form.value.partner) {
    importError.value = 'Bitte zuerst einen Partner auswählen'
    return
  }

  apiLoading.value = true
  try {
    const partnerRes = await api.get(`/partners/${form.value.partner}/`)
    const partner = partnerRes.data
    const instrObj = partner.ai_instructions?.find((i) => i.provider === selectedProviderId.value)
    if (!instrObj?.instructions) {
      importError.value = `Dieser Partner hat keine Anweisungen für ${selectedProviderId.value} konfiguriert`
      return
    }

    const articleTable = buildArticleMarkdownTable()
    const prompt = instrObj.instructions.replace('%%article_table%%', articleTable)

    const attachmentUrls = []
    if (form.value.id) {
      const attRes = await api.get(`/stock-movements/${form.value.id}/attachments/`)
      const attachments = attRes.data.results ?? attRes.data
      attachmentUrls.push(...attachments.map((a) => a.file))
    }

    const provider = createProvider(selectedProviderId.value, aiConfig.value)
    importJson.value = await provider.generateJson({ attachmentUrls, prompt })
  } catch (err) {
    importError.value = err.message ?? 'Fehler beim AI-Aufruf'
    console.error('AI provider error:', err)
  } finally {
    apiLoading.value = false
  }
}

async function applySkonto() {
  if (!form.value.id) return
  await api.post(`/stock-movements/${form.value.id}/apply_discount/`, { percent: skontoPercent.value })
  const res = await api.get(`/stock-movements/${form.value.id}/`)
  lines.value = res.data.details || []
}

onMounted(async () => {
  const [t, wa, cfg] = await Promise.all([
    api.get('/tax-rates/'),
    api.get('/warehouse-articles/', { params: { period_id: periodStore.currentPeriodId } }),
    api.get('/config/'),
  ])
  taxRates.value = t.data.results || t.data
  warehouseArticles.value = wa.data.results || wa.data
  const defaultId = cfg.data.config?.DEFAULT_TAX_RATE_ID?.value
  defaultTaxRateId.value = defaultId || null
  aiConfig.value = cfg.data.config ?? {}
  await loadPartners()
  await initForm()
})

watch(() => props.movement, initForm)
watch(effectiveType, loadPartners)
</script>
