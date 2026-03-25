<template>
  <div>
    <v-row class="mb-2" align="center">
      <v-col><h2>Partner</h2></v-col>
      <v-col cols="auto">
        <v-btn color="primary" prepend-icon="mdi-plus" @click="openNew">Neu</v-btn>
      </v-col>
    </v-row>

    <v-data-table :headers="headers" :items="items" :loading="loading" density="compact">
      <template #item.partner_type="{ item }">
        {{ partnerTypeLabel(item.partner_type) }}
      </template>
      <template #item.actions="{ item }">
        <v-icon size="small" @click="openEdit(item)">mdi-pencil</v-icon>
        <v-icon size="small" class="ml-1" color="error" @click="deleteItem(item)">mdi-delete</v-icon>
      </template>
    </v-data-table>

    <v-dialog v-model="dialog" max-width="400">
      <v-card>
        <v-card-title>{{ form.id ? 'Bearbeiten' : 'Neu' }}</v-card-title>
        <v-card-text>
          <v-text-field v-model="form.name" label="Name" />
          <v-select
            v-model="form.partner_type"
            :items="partnerTypeOptions"
            item-title="label"
            item-value="value"
            label="Typ"
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="dialog = false">Abbrechen</v-btn>
          <v-btn color="primary" @click="save">Speichern</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api from '../api'

const items = ref([])
const loading = ref(false)
const dialog = ref(false)
const form = ref({ name: '', partner_type: 'supplier' })

const partnerTypeOptions = [
  { value: 'supplier', label: 'Lieferant' },
  { value: 'consumer', label: 'Verbraucher' },
]

const headers = [
  { title: 'Name', key: 'name' },
  { title: 'Typ', key: 'partner_type' },
  { title: '', key: 'actions', sortable: false, align: 'end' },
]

function partnerTypeLabel(type) {
  return partnerTypeOptions.find((o) => o.value === type)?.label ?? type
}

async function fetchItems() {
  loading.value = true
  try {
    const res = await api.get('/partners/')
    items.value = res.data.results || res.data
  } finally {
    loading.value = false
  }
}

function openNew() {
  form.value = { name: '', partner_type: 'supplier' }
  dialog.value = true
}

function openEdit(item) {
  form.value = { ...item }
  dialog.value = true
}

async function save() {
  if (form.value.id) {
    await api.put(`/partners/${form.value.id}/`, form.value)
  } else {
    await api.post('/partners/', form.value)
  }
  dialog.value = false
  await fetchItems()
}

async function deleteItem(item) {
  if (!confirm(`"${item.name}" wirklich löschen?`)) return
  await api.delete(`/partners/${item.id}/`)
  await fetchItems()
}

onMounted(fetchItems)
</script>
