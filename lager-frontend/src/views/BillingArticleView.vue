<template>
  <div>
    <v-row class="mb-2" align="center">
      <v-col><h2>Faktura-Artikel</h2></v-col>
      <v-col cols="auto">
        <v-btn color="primary" prepend-icon="mdi-plus" @click="openNew">Neu</v-btn>
      </v-col>
    </v-row>

    <v-data-table :headers="headers" :items="items" :loading="loading" density="compact"
      :row-props="() => ({ style: 'cursor: pointer' })" @click:row="(_, { item }) => openEdit(item)">
      <template #item.unit_price="{ item }">{{ Number(item.unit_price).toFixed(2) }} €</template>
      <template #item.tax_rate_percent="{ item }">
        {{ item.tax_rate_percent != null ? item.tax_rate_percent + ' %' : '—' }}
      </template>
      <template #item.is_active="{ item }">
        <v-icon :color="item.is_active ? 'success' : 'error'">
          {{ item.is_active ? 'mdi-check-circle' : 'mdi-close-circle' }}
        </v-icon>
      </template>
      <template #item.actions="{ item }">
        <v-icon size="small" @click.stop="openEdit(item)">mdi-pencil</v-icon>
        <v-icon size="small" class="ml-1" color="error" @click.stop="deleteItem(item)">mdi-delete</v-icon>
      </template>
    </v-data-table>

    <v-dialog v-model="dialog" max-width="560">
      <BillingArticleDialog :article="selected" @saved="onSaved" @close="dialog = false" />
    </v-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api from '../api'
import BillingArticleDialog from '../components/BillingArticleDialog.vue'

const items = ref([])
const loading = ref(false)
const dialog = ref(false)
const selected = ref(null)

const headers = [
  { title: 'Art.-Nr.', key: 'article_number' },
  { title: 'Bezeichnung', key: 'name' },
  { title: 'Einheit', key: 'unit' },
  { title: 'Preis (netto)', key: 'unit_price', align: 'end' },
  { title: 'MwSt.', key: 'tax_rate_percent', align: 'end' },
  { title: 'Aktiv', key: 'is_active', align: 'center' },
  { title: '', key: 'actions', sortable: false, align: 'end' },
]

async function fetchItems() {
  loading.value = true
  try {
    const res = await api.get('/billing-articles/')
    items.value = res.data.results || res.data
  } finally {
    loading.value = false
  }
}

function openNew() {
  selected.value = null
  dialog.value = true
}

function openEdit(item) {
  selected.value = item
  dialog.value = true
}

async function onSaved() {
  dialog.value = false
  await fetchItems()
}

async function deleteItem(item) {
  if (!confirm(`"${item.name}" wirklich löschen?`)) return
  await api.delete(`/billing-articles/${item.id}/`)
  await fetchItems()
}

onMounted(fetchItems)
</script>
