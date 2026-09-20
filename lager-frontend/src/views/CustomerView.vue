<template>
  <div>
    <v-row class="mb-2" align="center">
      <v-col><h2>Kunden</h2></v-col>
      <v-col cols="auto">
        <v-btn color="primary" prepend-icon="mdi-plus" @click="openNew">Neu</v-btn>
      </v-col>
    </v-row>

    <v-text-field v-model="search" label="Suche" prepend-inner-icon="mdi-magnify" clearable
      density="compact" class="mb-3" style="max-width: 360px" @update:model-value="onSearch" />

    <v-data-table :headers="headers" :items="items" :loading="loading" density="compact"
      :row-props="() => ({ style: 'cursor: pointer' })" @click:row="(_, { item }) => openEdit(item)">
      <template #item.name="{ item }">
        <span class="font-weight-medium">{{ item.display_name }}</span>
        <v-chip v-if="!item.is_active" size="x-small" color="warning" variant="tonal" class="ml-2">
          inaktiv
        </v-chip>
      </template>
      <template #item.default_address="{ item }">
        <span class="text-caption">{{ defaultAddressLabel(item) }}</span>
      </template>
      <template #item.balance="{ item }">
        <span :class="balanceClass(item.balance)">{{ fmtEuro(item.balance) }}</span>
      </template>
      <template #item.wz_source_id="{ item }">
        <v-chip v-if="item.wz_source_id != null" size="x-small" color="info" variant="tonal">WZ</v-chip>
      </template>
      <template #item.actions="{ item }">
        <v-tooltip text="Kundenkonto"><template #activator="{ props }">
          <v-icon v-bind="props" size="small" @click.stop="openLedger(item)">mdi-book-open-variant</v-icon>
        </template></v-tooltip>
        <v-icon size="small" class="ml-1" @click.stop="openEdit(item)">mdi-pencil</v-icon>
        <v-icon size="small" class="ml-1" color="error" @click.stop="deleteItem(item)">mdi-delete</v-icon>
        <v-tooltip text="Verlauf"><template #activator="{ props }">
          <v-icon v-bind="props" size="small" class="ml-1" @click.stop="openHistory(item)">mdi-history</v-icon>
        </template></v-tooltip>
      </template>
    </v-data-table>

    <v-dialog v-model="dialog" max-width="760">
      <CustomerDialog :customer="editingCustomer" @saved="onSaved" @close="dialog = false" />
    </v-dialog>

    <HistoryDialog v-if="historyItem" v-model="historyDialog" :api-path="`/customers/${historyItem.id}`" />

    <CustomerLedgerDialog
      v-if="ledgerItem"
      v-model="ledgerDialog"
      :customer-id="ledgerItem.id"
      :customer-label="ledgerItem.display_name"
      @changed="fetchItems(search || undefined)"
    />

    <v-snackbar v-model="errorSnackbar" color="error" timeout="-1" close-on-content-click>
      {{ errorMessage }}
    </v-snackbar>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import api from '../api'
import CustomerDialog from '../components/CustomerDialog.vue'
import CustomerLedgerDialog from '../components/CustomerLedgerDialog.vue'
import HistoryDialog from '../components/HistoryDialog.vue'
import { extractErrorMessage } from '../utils/errorMessage'

const items = ref([])
const loading = ref(false)
const dialog = ref(false)
const search = ref('')
let searchTimeout = null

const editingCustomer = ref(null)
const historyDialog = ref(false)
const historyItem = ref(null)
const ledgerDialog = ref(false)
const ledgerItem = ref(null)
const errorSnackbar = ref(false)
const errorMessage = ref('')

const headers = [
  { title: 'Nr.', key: 'customer_number' },
  { title: 'Name', key: 'name' },
  { title: 'Standardadresse', key: 'default_address', sortable: false },
  { title: 'E-Mail', key: 'email' },
  { title: 'Saldo', key: 'balance', align: 'end' },
  { title: 'WZ', key: 'wz_source_id', sortable: false },
  { title: '', key: 'actions', sortable: false, align: 'end' },
]

function showError(err, fallback) {
  errorMessage.value = extractErrorMessage(err, fallback)
  errorSnackbar.value = true
}

async function fetchItems(q) {
  loading.value = true
  try {
    const params = q ? { q } : {}
    const res = await api.get('/customers/', { params })
    items.value = res.data.results || res.data
  } catch (err) {
    showError(err, 'Kunden konnten nicht geladen werden.')
  } finally {
    loading.value = false
  }
}

function onSearch(val) {
  clearTimeout(searchTimeout)
  searchTimeout = setTimeout(() => fetchItems(val || undefined), 300)
}

function defaultAddressLabel(item) {
  const addr = item.addresses?.find((a) => a.id === item.default_address)
  if (!addr) return '—'
  return [addr.strasse, [addr.plz, addr.ort].filter(Boolean).join(' ')]
    .filter(Boolean).join(', ') || addr.display_name
}

function openNew() {
  editingCustomer.value = null
  dialog.value = true
}

function openEdit(item) {
  editingCustomer.value = item
  dialog.value = true
}

function openHistory(item) {
  historyItem.value = item
  historyDialog.value = true
}

function openLedger(item) {
  ledgerItem.value = item
  ledgerDialog.value = true
}

function onSaved() {
  dialog.value = false
  fetchItems(search.value || undefined)
}

async function deleteItem(item) {
  if (!confirm(`Kunde "${item.display_name}" wirklich löschen?`)) return
  try {
    await api.delete(`/customers/${item.id}/`)
    await fetchItems(search.value || undefined)
  } catch (err) {
    showError(err, 'Kunde konnte nicht gelöscht werden. Möglicherweise gibt es noch Dokumente dazu.')
  }
}

function balanceClass(v) {
  const n = Number(v ?? 0)
  if (n < 0) return 'text-error font-weight-medium'
  if (n > 0) return 'text-success font-weight-medium'
  return ''
}

function fmtEuro(v) {
  return `${Number(v ?? 0).toLocaleString('de-AT', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} €`
}

onMounted(() => fetchItems())
</script>
