<template>
  <v-card min-width="560">
    <v-card-title>{{ form.id ? 'Adresse bearbeiten' : 'Neue Adresse' }}</v-card-title>
    <v-card-text>
      <v-row dense>
        <v-col cols="4"><v-text-field v-model="form.anrede" label="Anrede" /></v-col>
        <v-col cols="4"><v-text-field v-model="form.vorname" label="Vorname" /></v-col>
        <v-col cols="4"><v-text-field v-model="form.nachname" label="Nachname" /></v-col>
      </v-row>
      <v-row dense>
        <v-col cols="8"><v-text-field v-model="form.firma" label="Firma" /></v-col>
        <v-col cols="4"><v-text-field v-model="form.abteilung" label="Abteilung" /></v-col>
      </v-row>
      <v-row dense>
        <v-col cols="12"><v-text-field v-model="form.strasse" label="Straße" /></v-col>
      </v-row>
      <v-row dense>
        <v-col cols="3"><v-text-field v-model="form.plz" label="PLZ" /></v-col>
        <v-col cols="9"><v-text-field v-model="form.ort" label="Ort" /></v-col>
      </v-row>
      <v-row dense>
        <v-col cols="6"><v-text-field v-model="form.telefon" label="Telefon" /></v-col>
        <v-col cols="6"><v-text-field v-model="form.email" label="E-Mail" /></v-col>
      </v-row>
      <v-row dense>
        <v-col cols="12"><v-text-field v-model="form.uid" label="UID-Nummer" /></v-col>
      </v-row>
      <v-row dense>
        <v-col cols="12"><v-textarea v-model="form.anmerkung" label="Anmerkung" rows="2" auto-grow /></v-col>
      </v-row>
      <v-row dense>
        <v-col cols="12">
          <v-autocomplete
            v-model="form.customer"
            :items="customers"
            :loading="loadingCustomers"
            item-title="display_name"
            item-value="id"
            label="Kunde"
            clearable
            :hint="form.customer ? '' : 'Ohne Kunden wird beim Speichern automatisch einer angelegt.'"
            persistent-hint
            @update:search="onCustomerSearch"
          />
        </v-col>
      </v-row>
    </v-card-text>
    <v-card-actions>
      <v-spacer />
      <v-btn @click="$emit('close')">Abbrechen</v-btn>
      <v-btn color="primary" :loading="saving" @click="save">Speichern</v-btn>
    </v-card-actions>
  </v-card>
</template>

<script setup>
import { onMounted, ref, watch } from 'vue'
import api from '../api'

const EMPTY = {
  anrede: '', vorname: '', nachname: '', firma: '', abteilung: '',
  strasse: '', plz: '', ort: '', telefon: '', email: '', uid: '', anmerkung: '',
  customer: null,
}

const props = defineProps({
  address: { type: Object, default: null },
})
const emit = defineEmits(['saved', 'close'])

const saving = ref(false)
const form = ref({ ...EMPTY })
const customers = ref([])
const loadingCustomers = ref(false)
let customerSearchTimeout = null

// Merged onto EMPTY so a partial seed (e.g. { customer: 7 } from the customer
// editor) still yields a complete form.
watch(() => props.address, (a) => {
  form.value = { ...EMPTY, ...(a || {}) }
  ensureCustomerLoaded()
}, { immediate: true })

async function fetchCustomers(q) {
  loadingCustomers.value = true
  try {
    const res = await api.get('/customers/', { params: q ? { q } : {} })
    customers.value = res.data.results || res.data
  } finally {
    loadingCustomers.value = false
  }
}

function onCustomerSearch(q) {
  clearTimeout(customerSearchTimeout)
  customerSearchTimeout = setTimeout(() => fetchCustomers(q || undefined), 300)
}

async function ensureCustomerLoaded() {
  // The preselected customer may not be in the first page of results.
  const id = form.value.customer
  if (!id || customers.value.some((c) => c.id === id)) return
  try {
    const res = await api.get(`/customers/${id}/`)
    customers.value = [res.data, ...customers.value]
  } catch { /* the autocomplete just shows the raw id */ }
}

async function save() {
  saving.value = true
  try {
    const res = form.value.id
      ? await api.put(`/addresses/${form.value.id}/`, form.value)
      : await api.post('/addresses/', form.value)
    emit('saved', res.data)
  } finally {
    saving.value = false
  }
}

onMounted(() => fetchCustomers())
</script>
