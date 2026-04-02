<template>
  <v-card>
    <v-card-title class="d-flex align-center pa-4" :class="typeConfig.bgClass">
      <v-icon :color="typeConfig.color" size="32" class="mr-3">{{ typeConfig.icon }}</v-icon>
      <span :class="`text-${typeConfig.color}`">{{ typeConfig.label }}</span>
      <span v-if="!isNew" class="ml-2 text-medium-emphasis text-body-1">#{{ form.id }}</span>
      <v-spacer />
      <v-btn icon @click="handleClose"><v-icon>mdi-close</v-icon></v-btn>
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
        <v-tab value="documents">
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
          <AttachmentGallery
            :movement-id="form.id ?? null"
            :preloaded-attachments="!form.id ? pendingAttachments : []"
            @uploaded="onPendingUploaded"
          />
        </v-tabs-window-item>
      </v-tabs-window>
    </v-card-text>

    <v-card-actions>
      <v-spacer />
      <v-btn @click="handleClose">Abbrechen</v-btn>
      <v-btn :color="typeConfig.color" :loading="saving" @click="save">Speichern</v-btn>
    </v-card-actions>
  </v-card>

  <!-- Import dialog -->
  <ImportDialog
    v-model="importDialog"
    :pending-attachments="pendingAttachments"
    :warehouse-articles="warehouseArticles"
    :tax-rates="taxRates"
    :partner-id="form.partner"
    :movement-id="form.id ?? null"
    :config="config"
    @confirm="onImportConfirm"
  />

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
import ImportDialog from './ImportDialog.vue'
import { useLineCalculations } from '../composables/useLineCalculations'

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
const pendingAttachments = ref([])
const dateError = ref('')
const linesError = ref('')
const defaultTaxRateId = ref(null)
const config = ref({})
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

const { getTaxPercent, lineNet, lineGross, totalNet, totalGross } = useLineCalculations(taxRates, lines)

async function initForm() {
  activeTab.value = 'positions'
  dateError.value = ''
  linesError.value = ''
  pendingAttachments.value = []
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
    // Assign any pending (orphaned) attachments to the newly created movement
    if (isNew.value && pendingAttachments.value.length) {
      await Promise.all(
        pendingAttachments.value.map((a) =>
          api.patch(`/attachments/${a.id}/`, { stock_movement: movementId })
        )
      )
      pendingAttachments.value = []
    }
    emit('saved')
  } finally {
    saving.value = false
  }
}

function onPendingUploaded(newAttachments) {
  if (!form.value.id) {
    pendingAttachments.value = [...pendingAttachments.value, ...newAttachments]
  }
}

async function handleClose() {
  if (pendingAttachments.value.length) {
    await Promise.all(pendingAttachments.value.map((a) => api.delete(`/attachments/${a.id}/`)))
    pendingAttachments.value = []
  }
  emit('close')
}

function openImportDialog() {
  importDialog.value = true
}

function onImportConfirm(newLines) {
  lines.value.push(...newLines)
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
  config.value = cfg.data.config ?? {}
  defaultTaxRateId.value = config.value.DEFAULT_TAX_RATE_ID?.value || null
  await loadPartners()
  await initForm()
})

watch(() => props.movement, initForm)
watch(effectiveType, loadPartners)
</script>
