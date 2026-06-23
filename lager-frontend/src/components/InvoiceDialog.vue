<template>
  <v-card width="100%">
    <v-card-title class="d-flex align-center pa-4">
      <v-icon class="mr-3">mdi-receipt-text-outline</v-icon>
      {{ isNew ? 'Neue Rechnung' : `Rechnung${invoice.number ? ' ' + invoice.number : ' #' + invoice.id}` }}
      <v-chip v-if="!isNew && !isDraft" size="small" :color="STATUS_COLORS[invoice.status]" class="ml-3">
        {{ STATUS_LABELS[invoice.status] }}
      </v-chip>
      <v-spacer />
      <v-btn icon @click="$emit('close')"><v-icon>mdi-close</v-icon></v-btn>
    </v-card-title>

    <v-card-text>
      <v-row dense>
        <v-col cols="6">
          <div class="d-flex align-start gap-1">
            <v-autocomplete v-model="form.address" :items="addresses" :item-title="a => a.display_name"
              item-value="id" label="Adresse *" :rules="[v => !!v || 'Pflichtfeld']" class="flex-grow-1"
              :disabled="!isDraft" />
            <v-tooltip v-if="isDraft" text="Neue Adresse erstellen">
              <template #activator="{ props: tip }">
                <v-btn v-bind="tip" icon size="small" variant="text" class="mt-2" @click="openNewAddress">
                  <v-icon>mdi-plus-circle-outline</v-icon>
                </v-btn>
              </template>
            </v-tooltip>
          </div>
        </v-col>
        <v-col cols="3">
          <v-text-field v-model="form.document_date" label="Rechnungsdatum *" type="date" :disabled="!isDraft" />
        </v-col>
        <v-col cols="3">
          <v-text-field v-model="form.due_date" label="Fälligkeitsdatum *" type="date"
            :min="form.document_date"
            :rules="[v => !!v || 'Pflichtfeld', v => !form.document_date || v >= form.document_date || 'Darf nicht vor dem Rechnungsdatum liegen']"
            :disabled="!isDraft" />
        </v-col>
      </v-row>

      <!-- Address detail expand -->
      <div v-if="selectedAddress" class="mb-2">
        <div class="d-flex align-center gap-1">
          <v-btn variant="text" size="x-small" density="compact"
            :append-icon="addressDetailOpen ? 'mdi-chevron-up' : 'mdi-chevron-down'"
            @click="addressDetailOpen = !addressDetailOpen">
            Adressdetails
          </v-btn>
          <v-tooltip v-if="addressDetailOpen && isDraft" text="Adresse bearbeiten">
            <template #activator="{ props: tip }">
              <v-btn v-bind="tip" icon size="x-small" variant="text" @click="openEditAddress">
                <v-icon size="small">mdi-pencil</v-icon>
              </v-btn>
            </template>
          </v-tooltip>
        </div>
        <v-expand-transition>
          <v-card v-if="addressDetailOpen" variant="tonal" class="pa-3 mt-1 text-body-2">
            <v-row dense>
              <v-col v-if="selectedAddress.anrede" cols="2">
                <div class="text-caption text-medium-emphasis">Anrede</div>
                <div>{{ selectedAddress.anrede }}</div>
              </v-col>
              <v-col v-if="selectedAddress.vorname" cols="2">
                <div class="text-caption text-medium-emphasis">Vorname</div>
                <div>{{ selectedAddress.vorname }}</div>
              </v-col>
              <v-col v-if="selectedAddress.nachname" cols="3">
                <div class="text-caption text-medium-emphasis">Nachname</div>
                <div>{{ selectedAddress.nachname }}</div>
              </v-col>
              <v-col v-if="selectedAddress.firma" cols="5">
                <div class="text-caption text-medium-emphasis">Firma</div>
                <div>{{ selectedAddress.firma }}</div>
              </v-col>
              <v-col v-if="selectedAddress.abteilung" cols="5">
                <div class="text-caption text-medium-emphasis">Abteilung</div>
                <div>{{ selectedAddress.abteilung }}</div>
              </v-col>
            </v-row>
            <v-row dense class="mt-1">
              <v-col v-if="selectedAddress.strasse" cols="4">
                <div class="text-caption text-medium-emphasis">Straße</div>
                <div>{{ selectedAddress.strasse }}</div>
              </v-col>
              <v-col v-if="selectedAddress.plz" cols="2">
                <div class="text-caption text-medium-emphasis">PLZ</div>
                <div>{{ selectedAddress.plz }}</div>
              </v-col>
              <v-col v-if="selectedAddress.ort" cols="3">
                <div class="text-caption text-medium-emphasis">Ort</div>
                <div>{{ selectedAddress.ort }}</div>
              </v-col>
              <v-col v-if="selectedAddress.telefon" cols="3">
                <div class="text-caption text-medium-emphasis">Telefon</div>
                <div>{{ selectedAddress.telefon }}</div>
              </v-col>
              <v-col v-if="selectedAddress.email" cols="4">
                <div class="text-caption text-medium-emphasis">E-Mail</div>
                <div>{{ selectedAddress.email }}</div>
              </v-col>
              <v-col v-if="selectedAddress.uid" cols="4">
                <div class="text-caption text-medium-emphasis">UID-Nummer</div>
                <div>{{ selectedAddress.uid }}</div>
              </v-col>
              <v-col v-if="selectedAddress.anmerkung" cols="12">
                <div class="text-caption text-medium-emphasis">Anmerkung</div>
                <div>{{ selectedAddress.anmerkung }}</div>
              </v-col>
            </v-row>
          </v-card>
        </v-expand-transition>
      </div>

      <v-row dense>
        <v-col cols="12">
          <v-textarea v-model="form.notes" label="Anmerkungen" rows="1" auto-grow :disabled="!isDraft" />
        </v-col>
      </v-row>

      <v-divider class="my-3" />

      <!-- Line items -->
      <v-row class="mb-1" align="center">
        <v-col><strong>Positionen</strong></v-col>
        <v-col v-if="isDraft" cols="auto" class="d-flex gap-2">
          <v-btn size="small" prepend-icon="mdi-cash-register" @click="wzImportDialogOpen = true">WZ Import</v-btn>
          <v-btn size="small" prepend-icon="mdi-tag-plus-outline" @click="articleDialogOpen = true">Neuer Artikel</v-btn>
          <v-btn size="small" prepend-icon="mdi-plus" @click="addLine">Position hinzufügen</v-btn>
        </v-col>
      </v-row>

      <v-table density="compact">
        <thead>
          <tr>
            <th rowspan="2" style="width:3em;vertical-align:middle">Pos</th>
            <th>Artikel / Bezeichnung</th>
            <th style="width:9em">Einh.</th>
            <th style="width:11em">Menge</th>
            <th rowspan="2" style="width:9em;vertical-align:middle">Netto</th>
            <th rowspan="2" style="width:9em;vertical-align:middle">Brutto</th>
            <th v-if="isDraft" rowspan="2" style="width:2em;vertical-align:middle"></th>
          </tr>
          <tr>
            <th style="font-weight:normal;opacity:.6">Beschreibung</th>
            <th style="width:11em">EP (netto)</th>
            <th style="width:15em">MwSt.</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="(line, idx) in lines" :key="idx">
            <tr style="border-bottom:none">
              <td rowspan="2" style="vertical-align:middle;padding-top:10px">{{ idx + 1 }}</td>
              <td>
                <v-autocomplete v-model="line.billing_article" :items="billingArticles"
                  item-title="name" item-value="id" density="compact" hide-details clearable
                  placeholder="Freitext" :disabled="!isDraft"
                  @update:model-value="onArticleSelect(line)"
                />
              </td>
              <td>
                <v-text-field v-model="line.unit" density="compact" hide-details :disabled="!isDraft" />
              </td>
              <td>
                <NumberInput v-model="line.quantity" hide-controls density="compact" hide-details
                  class="text-right" :disabled="!isDraft" />
              </td>
              <td rowspan="2" class="text-right text-no-wrap" style="vertical-align:middle">{{ lineNet(line) }} €</td>
              <td rowspan="2" class="text-right text-no-wrap" style="vertical-align:middle">{{ lineGross(line) }} €</td>
              <td v-if="isDraft" rowspan="2" style="vertical-align:middle">
                <v-btn icon size="x-small" color="error" variant="text" @click="removeLine(idx)">
                  <v-icon size="small">mdi-delete</v-icon>
                </v-btn>
              </td>
            </tr>
            <tr>
              <td>
                <v-text-field v-if="!line.billing_article" v-model="line.description"
                  placeholder="Beschreibung" density="compact" hide-details :disabled="!isDraft" />
                <span v-else class="text-caption text-medium-emphasis">{{ line.description }}</span>
              </td>
              <td>
                <NumberInput v-model="line.unit_price" :decimals="2" hide-controls density="compact" hide-details
                  class="text-right" :disabled="!isDraft" />
              </td>
              <td>
                <v-select v-model="line.tax_rate" :items="taxRates" item-title="name" item-value="id"
                  density="compact" hide-details clearable :disabled="!isDraft" />
              </td>
            </tr>
          </template>
        </tbody>
        <tfoot>
          <tr>
            <td colspan="4" class="text-right font-weight-medium">Nettobetrag:</td>
            <td class="text-right font-weight-bold">{{ totalNet }} €</td>
            <td colspan="2"></td>
          </tr>
          <tr>
            <td colspan="4" class="text-right font-weight-bold" style="font-size: 1.05em">Bruttobetrag:</td>
            <td class="text-right font-weight-bold" style="font-size: 1.05em">{{ totalGross }} €</td>
            <td colspan="2"></td>
          </tr>
        </tfoot>
      </v-table>
    </v-card-text>

    <v-card-actions>
      <v-spacer />
      <v-btn @click="$emit('close')">{{ isDraft ? 'Abbrechen' : 'Schließen' }}</v-btn>
      <v-btn v-if="isDraft" color="primary" :loading="saving" @click="doSave">Speichern</v-btn>
    </v-card-actions>
  </v-card>

  <v-dialog v-model="addressDialogOpen" max-width="640">
    <AddressDialog :address="addressToEdit" @saved="onAddressSaved" @close="addressDialogOpen = false" />
  </v-dialog>

  <v-dialog v-model="articleDialogOpen" max-width="560">
    <BillingArticleDialog :article="null" @saved="onArticleSaved" @close="articleDialogOpen = false" />
  </v-dialog>

  <WzImportDialog v-model="wzImportDialogOpen" @confirm="onWzImport" />
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import api from '../api'
import NumberInput from './NumberInput.vue'
import AddressDialog from './AddressDialog.vue'
import BillingArticleDialog from './BillingArticleDialog.vue'
import WzImportDialog from './WzImportDialog.vue'
import { useLineCalculations } from '../composables/useLineCalculations'

const props = defineProps({
  invoice: { type: Object, default: null },
})
const emit = defineEmits(['saved', 'close'])

const STATUS_LABELS = { draft: 'Entwurf', issued: 'Ausgestellt', sent: 'Versendet', paid: 'Bezahlt', cancelled: 'Storniert' }
const STATUS_COLORS = { draft: 'grey', issued: 'info', sent: 'primary', paid: 'success', cancelled: 'error' }

const isNew = computed(() => !props.invoice?.id)
const isDraft = computed(() => isNew.value || props.invoice?.status === 'draft')
const saving = ref(false)
const addresses = ref([])
const billingArticles = ref([])
const taxRates = ref([])
const paymentTermsDays = ref(14)

const form = ref({ address: null, document_date: today(), due_date: defaultDueDate(), notes: '' })
const lines = ref([])
const addressDetailOpen = ref(false)
const addressDialogOpen = ref(false)
const addressToEdit = ref(null)
const articleDialogOpen = ref(false)
const wzImportDialogOpen = ref(false)

const selectedAddress = computed(() => {
  if (!form.value.address) return null
  return addresses.value.find(a => a.id === form.value.address) ?? null
})

const { lineNet, lineGross, totalNet, totalGross } = useLineCalculations(taxRates, lines)

function today() { return new Date().toISOString().slice(0, 10) }

function defaultDueDate() {
  const d = new Date()
  d.setDate(d.getDate() + paymentTermsDays.value)
  return d.toISOString().slice(0, 10)
}

watch(() => form.value.address, () => {
  addressDetailOpen.value = false
})

watch(() => props.invoice, (inv) => {
  if (inv) {
    form.value = {
      address: inv.address,
      document_date: inv.document_date,
      due_date: inv.due_date || null,
      notes: inv.notes || '',
    }
    loadLines(inv.id)
  } else {
    form.value = { address: null, document_date: today(), due_date: defaultDueDate(), notes: '' }
    lines.value = []
  }
}, { immediate: true })

async function loadLines(invoiceId) {
  const res = await api.get(`/invoices/${invoiceId}/lines/`)
  lines.value = (res.data || []).map(l => ({
    id: l.id,
    billing_article: l.billing_article,
    description: l.description,
    unit: l.unit || '',
    quantity: Number(l.quantity),
    unit_price: Number(l.unit_price),
    tax_rate: l.tax_rate,
    position: l.position,
  }))
}

function openNewAddress() {
  addressToEdit.value = null
  addressDialogOpen.value = true
}

function openEditAddress() {
  addressToEdit.value = selectedAddress.value
  addressDialogOpen.value = true
}

function onAddressSaved(addr) {
  const idx = addresses.value.findIndex(a => a.id === addr.id)
  if (idx !== -1) {
    addresses.value.splice(idx, 1, addr)
    addresses.value = [...addresses.value].sort((a, b) => a.display_name.localeCompare(b.display_name, 'de'))
  } else {
    addresses.value = [...addresses.value, addr].sort((a, b) => a.display_name.localeCompare(b.display_name, 'de'))
    form.value.address = addr.id
  }
  addressDialogOpen.value = false
}

function onArticleSaved(art) {
  billingArticles.value = [...billingArticles.value, art]
  lines.value.push({
    billing_article: art.id,
    description: art.name,
    unit: art.unit || '',
    quantity: 1,
    unit_price: Number(art.unit_price),
    tax_rate: art.tax_rate || null,
  })
  articleDialogOpen.value = false
}

function addLine() {
  lines.value.push({ billing_article: null, description: '', unit: '', quantity: 1, unit_price: 0, tax_rate: taxRates.value[0]?.id || null })
}

function onWzImport(payload) {
  if (payload.mode === 'lines') {
    const defaultTaxRate = taxRates.value[0]?.id || null
    payload.lines.forEach(l => {
      lines.value.push({ ...l, tax_rate: l.tax_rate ?? defaultTaxRate })
    })
  } else if (payload.mode === 'notes') {
    const existing = form.value.notes?.trim()
    form.value.notes = existing ? `${existing}\n\n${payload.text}` : payload.text
  }
}

function removeLine(idx) { lines.value.splice(idx, 1) }

function onArticleSelect(line) {
  if (!line.billing_article) return
  const art = billingArticles.value.find(a => a.id === line.billing_article)
  if (!art) return
  line.description = art.name
  line.unit = art.unit || ''
  line.unit_price = Number(art.unit_price)
  if (art.tax_rate) line.tax_rate = art.tax_rate
}

async function doSave() {
  saving.value = true
  try {
    let id = props.invoice?.id
    if (isNew.value) {
      const res = await api.post('/invoices/', form.value)
      id = res.data.id
    } else {
      await api.put(`/invoices/${id}/`, form.value)
    }
    const linesPayload = lines.value.map((l, idx) => ({
      invoice: id,
      position: idx + 1,
      billing_article: l.billing_article || null,
      description: l.description || '',
      unit: l.unit || '',
      quantity: l.quantity,
      unit_price: l.unit_price,
      tax_rate: l.tax_rate || null,
    }))
    await api.post(`/invoices/${id}/lines/`, linesPayload)
    emit('saved')
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  const [addrRes, artRes, taxRes, cfgRes] = await Promise.all([
    api.get('/addresses/'),
    api.get('/billing-articles/?active=true'),
    api.get('/tax-rates/'),
    api.get('/config/'),
  ])
  addresses.value = (addrRes.data.results || addrRes.data).sort((a, b) => a.display_name.localeCompare(b.display_name, 'de'))
  billingArticles.value = artRes.data.results || artRes.data
  taxRates.value = taxRes.data.results || taxRes.data
  paymentTermsDays.value = cfgRes.data.config?.INVOICE_PAYMENT_TERMS_DAYS?.value ?? 14
  if (!props.invoice) {
    form.value.due_date = defaultDueDate()
  }
})
</script>
