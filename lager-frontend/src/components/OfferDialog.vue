<template>
  <v-card width="100%">
    <v-card-title class="d-flex align-center pa-4">
      <v-icon class="mr-3">mdi-file-document-outline</v-icon>
      {{ isNew ? 'Neues Angebot' : `Angebot${offer.number ? ' ' + offer.number : ' #' + offer.id}` }}
      <v-spacer />
      <v-btn icon @click="$emit('close')"><v-icon>mdi-close</v-icon></v-btn>
    </v-card-title>

    <v-card-text>
      <!-- Header fields -->
      <v-row dense>
        <v-col cols="5">
          <div class="d-flex align-start gap-1">
            <v-autocomplete v-model="form.address" :items="addresses" :item-title="a => a.display_name" item-value="id"
              label="Adresse *" :rules="[v => !!v || 'Pflichtfeld']" class="flex-grow-1" />
            <v-tooltip text="Neue Adresse erstellen">
              <template #activator="{ props: tip }">
                <v-btn v-bind="tip" icon size="small" variant="text" class="mt-2" @click="openNewAddress">
                  <v-icon>mdi-plus-circle-outline</v-icon>
                </v-btn>
              </template>
            </v-tooltip>
          </div>
        </v-col>
        <v-col cols="2">
          <v-text-field v-model="form.document_date" label="Datum *" type="date" />
        </v-col>
        <v-col cols="2">
          <v-text-field v-model="form.valid_until" label="Gültig bis" type="date"
            :min="form.document_date"
            :rules="[v => !v || v >= form.document_date || 'Darf nicht vor dem Angebotsdatum liegen']" />
        </v-col>
        <v-col cols="3">
          <v-select
            v-model="form.status"
            :items="STATUS_OPTIONS"
            item-title="title"
            item-value="value"
            label="Status"
            :disabled="form.status === 'draft' || form.status === 'converted'"
          />
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
          <v-tooltip v-if="addressDetailOpen" text="Adresse bearbeiten">
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
          <v-textarea v-model="form.notes" label="Anmerkungen" rows="1" auto-grow />
        </v-col>
      </v-row>

      <v-divider class="my-3" />

      <!-- Line items -->
      <v-row class="mb-1" align="center">
        <v-col><strong>Positionen</strong></v-col>
        <v-col cols="auto" class="d-flex gap-2">
          <v-btn size="small" prepend-icon="mdi-tag-plus-outline" @click="articleDialogOpen = true">Neuer Artikel</v-btn>
          <v-btn size="small" prepend-icon="mdi-plus" @click="addLine">Position hinzufügen</v-btn>
        </v-col>
      </v-row>

      <v-table density="compact" class="line-items-table">
        <colgroup>
          <col style="width:3em">
          <col style="width:22em">
          <col style="width:18em">
          <col style="width:14em">
          <col style="width:9em">
          <col style="width:9em">
          <col style="width:3em">
        </colgroup>
        <tbody>
          <template v-for="(line, idx) in lines" :key="idx">
            <tr class="line-top" :class="{ 'line-alt': idx % 2 === 1 }">
              <td rowspan="2" class="text-center text-medium-emphasis" style="vertical-align:middle">{{ idx + 1 }}</td>
              <td>
                <div class="field-label">Artikel / Bezeichnung</div>
                <v-autocomplete v-model="line.billing_article" :items="billingArticles" :item-title="articleDropdownLabel" item-value="id"
                  density="compact" hide-details clearable placeholder="Freitext"
                  @update:model-value="onArticleSelect(line)" />
              </td>
              <td>
                <div class="field-label">Einh.</div>
                <v-text-field v-model="line.unit" density="compact" hide-details />
              </td>
              <td>
                <div class="field-label">Menge</div>
                <NumberInput v-model="line.quantity" :reverse="false" hide-controls density="compact" hide-details />
              </td>
              <td rowspan="2" style="vertical-align:middle">
                <div class="field-label">Netto</div>
                <div class="text-no-wrap">{{ lineNet(line) }} €</div>
              </td>
              <td rowspan="2" style="vertical-align:middle">
                <div class="field-label">Brutto</div>
                <div class="text-no-wrap font-weight-medium">{{ lineGross(line) }} €</div>
              </td>
              <td rowspan="2" style="vertical-align:middle">
                <v-btn icon size="x-small" color="error" variant="text" @click="removeLine(idx)">
                  <v-icon size="small">mdi-delete</v-icon>
                </v-btn>
              </td>
            </tr>
            <tr class="line-bottom" :class="{ 'line-alt': idx % 2 === 1 }">
              <td>
                <div class="field-label">Beschreibung</div>
                <v-textarea v-if="!line.billing_article" v-model="line.description"
                  auto-grow rows="1" max-rows="3" density="compact" hide-details />
                <div v-else class="text-body-2 pt-1">{{ line.description }}</div>
              </td>
              <td>
                <div class="field-label">EP (netto)</div>
                <NumberInput v-model="line.unit_price" :decimals="2" :reverse="false" hide-controls density="compact"
                  hide-details />
              </td>
              <td>
                <div class="field-label">MwSt.</div>
                <v-select v-model="line.tax_rate" :items="taxRates" item-title="name" item-value="id"
                  density="compact" hide-details clearable />
              </td>
            </tr>
            <tr v-if="idx < lines.length - 1" class="line-gap" aria-hidden="true">
              <td colspan="7"></td>
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
      <v-btn @click="$emit('close')">Abbrechen</v-btn>
      <v-btn color="primary" :loading="saving" @click="doSave">Speichern</v-btn>
    </v-card-actions>
  </v-card>

  <v-dialog v-model="addressDialogOpen" max-width="640">
    <AddressDialog :address="addressToEdit" @saved="onAddressSaved" @close="addressDialogOpen = false" />
  </v-dialog>

  <v-dialog v-model="articleDialogOpen" max-width="560">
    <BillingArticleDialog :article="null" @saved="onArticleSaved" @close="articleDialogOpen = false" />
  </v-dialog>

  <v-snackbar v-model="errorSnackbar" color="error" timeout="-1" location="bottom">
    {{ errorMessage }}
    <template #actions>
      <v-btn variant="text" @click="errorSnackbar = false">Schließen</v-btn>
    </template>
  </v-snackbar>

</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import api from '../api'
import NumberInput from './NumberInput.vue'
import AddressDialog from './AddressDialog.vue'
import BillingArticleDialog from './BillingArticleDialog.vue'
import { useLineCalculations } from '../composables/useLineCalculations'
import { extractErrorMessage } from '../utils/errorMessage'

const props = defineProps({
  offer: { type: Object, default: null },
})
const emit = defineEmits(['saved', 'close'])

const isNew = computed(() => !props.offer?.id)
const saving = ref(false)
const addresses = ref([])
const billingArticles = ref([])
const taxRates = ref([])

const STATUS_OPTIONS = [
  { value: 'issued', title: 'Ausgestellt' },
  { value: 'sent', title: 'Versendet' },
  { value: 'accepted', title: 'Angenommen' },
  { value: 'rejected', title: 'Abgelehnt' },
]

const form = ref({ address: null, document_date: today(), valid_until: null, notes: '', status: 'draft' })
const lines = ref([])
const addressDetailOpen = ref(false)
const addressDialogOpen = ref(false)
const addressToEdit = ref(null)
const articleDialogOpen = ref(false)
const errorSnackbar = ref(false)
const errorMessage = ref('')

function showError(err, fallback) {
  errorMessage.value = extractErrorMessage(err, fallback)
  errorSnackbar.value = true
}

const selectedAddress = computed(() => {
  if (!form.value.address) return null
  return addresses.value.find(a => a.id === form.value.address) ?? null
})

const { lineNet, lineGross, totalNet, totalGross } = useLineCalculations(taxRates, lines)

function today() {
  return new Date().toISOString().slice(0, 10)
}

watch(() => form.value.address, () => {
  addressDetailOpen.value = false
})

watch(() => props.offer, (o) => {
  if (o) {
    form.value = { address: o.address, document_date: o.document_date, valid_until: o.valid_until || null, notes: o.notes || '', status: o.status }
    loadLines(o.id)
  } else {
    form.value = { address: null, document_date: today(), valid_until: null, notes: '', status: 'draft' }
    lines.value = []
  }
}, { immediate: true })

async function loadLines(offerId) {
  try {
    const res = await api.get(`/offers/${offerId}/lines/`)
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
  } catch (err) {
    showError(err, 'Positionen konnten nicht geladen werden.')
  }
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

function removeLine(idx) {
  lines.value.splice(idx, 1)
}

function articleDropdownLabel(art) {
  if (!art.description) return art.name
  const desc = art.description.length > 50 ? art.description.slice(0, 50) + '…' : art.description
  return `${art.name} – ${desc}`
}

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
    let id = props.offer?.id
    if (isNew.value) {
      const res = await api.post('/offers/', form.value)
      id = res.data.id
    } else {
      await api.put(`/offers/${id}/`, form.value)
    }
    // Replace lines
    const linesPayload = lines.value.map((l, idx) => ({
      id: l.id,
      offer: id,
      position: idx + 1,
      billing_article: l.billing_article || null,
      description: l.description || '',
      unit: l.unit || '',
      quantity: l.quantity,
      unit_price: l.unit_price,
      tax_rate: l.tax_rate || null,
    }))
    await api.post(`/offers/${id}/lines/`, linesPayload)
    emit('saved')
  } catch (err) {
    showError(err, 'Angebot konnte nicht gespeichert werden.')
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  try {
    const [addrRes, artRes, taxRes] = await Promise.all([
      api.get('/addresses/'),
      api.get('/billing-articles/?active=true'),
      api.get('/tax-rates/'),
    ])
    addresses.value = (addrRes.data.results || addrRes.data).sort((a, b) => a.display_name.localeCompare(b.display_name, 'de'))
    billingArticles.value = artRes.data.results || artRes.data
    taxRates.value = taxRes.data.results || taxRes.data
  } catch (err) {
    showError(err, 'Stammdaten konnten nicht geladen werden.')
  }
})
</script>

<style scoped>
/* Each line item is a self-contained block: faint card background, no inner borders */
.line-items-table :deep(tbody .line-top > td),
.line-items-table :deep(tbody .line-bottom > td) {
  background-color: rgba(128, 128, 128, 0.04);
  border-bottom: none !important;
}
.line-items-table :deep(tbody .line-top > td) {
  padding-top: 12px;
}
.line-items-table :deep(tbody .line-bottom > td) {
  padding-bottom: 12px;
}
/* Stronger tint on alternate items to tell them apart */
.line-items-table :deep(tbody .line-alt > td) {
  background-color: rgba(128, 128, 128, 0.12);
}
/* Transparent spacer between items */
.line-items-table :deep(tbody .line-gap > td) {
  height: 10px;
  padding: 0;
  border: none !important;
  background: transparent;
}
/* Small left-aligned heading above each field */
.field-label {
  font-size: 0.72rem;
  line-height: 1.2;
  text-align: left;
  color: rgba(var(--v-theme-on-surface), 0.6);
  margin-bottom: 2px;
}
</style>
