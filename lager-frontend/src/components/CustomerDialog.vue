<template>
  <v-card min-width="700">
    <v-card-title>
      {{ form.id ? 'Kunde bearbeiten' : 'Neuer Kunde' }}
      <span v-if="form.customer_number" class="text-medium-emphasis text-body-2 ml-2">
        {{ form.customer_number }}
      </span>
    </v-card-title>
    <v-card-text>
      <v-alert v-if="error" type="error" density="compact" class="mb-3" closable @click:close="error = ''">
        {{ error }}
      </v-alert>

      <v-row dense>
        <v-col cols="12" sm="8"><v-text-field v-model="form.name" label="Name / Firma *" /></v-col>
        <v-col cols="12" sm="4"><v-text-field v-model="form.uid" label="UID-Nummer" /></v-col>
      </v-row>
      <v-row dense>
        <v-col cols="12" sm="6"><v-text-field v-model="form.email" label="E-Mail" /></v-col>
        <v-col cols="12" sm="6"><v-text-field v-model="form.telefon" label="Telefon" /></v-col>
      </v-row>
      <v-row dense>
        <v-col cols="12"><v-textarea v-model="form.notes" label="Notizen" rows="2" auto-grow /></v-col>
      </v-row>
      <v-row dense>
        <v-col cols="12"><v-switch v-model="form.is_active" label="Aktiv" color="primary" density="compact" hide-details /></v-col>
      </v-row>

      <!-- Addresses -->
      <template v-if="form.id">
        <v-divider class="my-3" />
        <div class="d-flex align-center mb-2">
          <span class="text-subtitle-2">Adressen</span>
          <v-spacer />
          <v-btn size="small" variant="text" prepend-icon="mdi-plus" @click="openNewAddress">
            Adresse hinzufügen
          </v-btn>
        </div>

        <!-- One v-radio-group owns the selection: standalone v-radios have
             nothing coordinating them, so each would latch on independently. -->
        <v-radio-group
          v-if="addresses.length"
          v-model="form.default_address"
          density="compact"
          hide-details
        >
          <v-table density="compact">
            <thead>
              <tr>
                <th style="width: 6em">Standard</th>
                <th>Adresse</th>
                <th>E-Mail</th>
                <th class="text-right"></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="addr in addresses" :key="addr.id">
                <td>
                  <v-radio :value="addr.id" density="compact" hide-details />
                </td>
                <td class="text-caption">{{ addressLabel(addr) }}</td>
                <td class="text-caption">{{ addr.email || '—' }}</td>
                <td class="text-right">
                  <v-icon size="small" @click="openEditAddress(addr)">mdi-pencil</v-icon>
                </td>
              </tr>
            </tbody>
          </v-table>
        </v-radio-group>
        <div v-if="!addresses.length" class="text-medium-emphasis text-caption">
          Noch keine Adressen. Ohne Adresse kann kein Dokument erstellt werden.
        </div>
      </template>
      <div v-else class="text-medium-emphasis text-caption mt-2">
        Adressen können nach dem Speichern hinzugefügt werden.
      </div>
    </v-card-text>
    <v-card-actions>
      <v-spacer />
      <v-btn @click="$emit('close')">Abbrechen</v-btn>
      <v-btn color="primary" :loading="saving" :disabled="!form.name?.trim()" @click="save">Speichern</v-btn>
    </v-card-actions>
  </v-card>

  <v-dialog v-model="addressDialog" max-width="640">
    <AddressDialog :address="editingAddress" @saved="onAddressSaved" @close="addressDialog = false" />
  </v-dialog>
</template>

<script setup>
import { ref, watch } from 'vue'
import api from '../api'
import AddressDialog from './AddressDialog.vue'
import { extractErrorMessage } from '../utils/errorMessage'

const props = defineProps({
  customer: { type: Object, default: null },
})
const emit = defineEmits(['saved', 'close'])

const saving = ref(false)
const error = ref('')
const form = ref({})
const addresses = ref([])
const addressDialog = ref(false)
const editingAddress = ref(null)

watch(() => props.customer, (c) => {
  error.value = ''
  form.value = c
    ? { ...c }
    : { name: '', email: '', telefon: '', uid: '', notes: '', is_active: true, default_address: null }
  addresses.value = c?.addresses ? [...c.addresses] : []
}, { immediate: true })

function addressLabel(addr) {
  // postal_label already omits the "Adresse #120" placeholder for nameless rows.
  return addr.postal_label || addr.display_name
}

function openNewAddress() {
  // Pre-attach the customer so the API does not auto-create a second one.
  editingAddress.value = { customer: form.value.id }
  addressDialog.value = true
}

function openEditAddress(addr) {
  editingAddress.value = addr
  addressDialog.value = true
}

async function onAddressSaved() {
  addressDialog.value = false
  await reloadAddresses()
}

async function reloadAddresses() {
  if (!form.value.id) return
  const res = await api.get(`/customers/${form.value.id}/`)
  addresses.value = res.data.addresses || []
  form.value.default_address = res.data.default_address
}

async function save() {
  saving.value = true
  error.value = ''
  try {
    const res = form.value.id
      ? await api.put(`/customers/${form.value.id}/`, form.value)
      : await api.post('/customers/', form.value)
    emit('saved', res.data)
  } catch (err) {
    error.value = extractErrorMessage(err, 'Kunde konnte nicht gespeichert werden.')
  } finally {
    saving.value = false
  }
}
</script>
