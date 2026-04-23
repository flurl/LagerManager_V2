<template>
  <div>
    <v-row class="mb-2" align="center">
      <v-col><h2>Partner</h2></v-col>
      <v-col cols="auto">
        <v-btn color="primary" prepend-icon="mdi-plus" @click="openNew">Neu</v-btn>
      </v-col>
    </v-row>

    <v-data-table :headers="headers" :items="items" :loading="loading" density="compact"
      :row-props="() => ({ style: 'cursor: pointer' })" @click:row="(_, { item }) => openEdit(item)">
      <template #item.actions="{ item }">
        <v-icon size="small" @click.stop="openEdit(item)">mdi-pencil</v-icon>
        <v-icon size="small" class="ml-1" color="error" @click.stop="deleteItem(item)">mdi-delete</v-icon>
      </template>
    </v-data-table>

    <v-dialog v-model="dialog" max-width="500">
      <v-card>
        <v-card-title>{{ form.id ? 'Bearbeiten' : 'Neu' }}</v-card-title>
        <v-card-text>
          <v-text-field v-model="form.name" label="Name" />
          <div v-for="p in AI_PROVIDERS" :key="p.id">
            <v-textarea
              v-model="instructionFor(p.id).instructions"
              :label="`${p.label} – Anweisungen`"
              rows="4"
              clearable
              class="mt-2"
            >
              <template #prepend>
                <img :src="p.imgSrc" :alt="p.label" width="20" height="20" style="margin-top:2px" />
              </template>
            </v-textarea>
          </div>
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
import { AI_PROVIDERS } from '../ai/index.js'

const items = ref([])
const loading = ref(false)
const dialog = ref(false)
const form = ref({ name: '' })

const headers = [
  { title: 'Name', key: 'name' },
  { title: '', key: 'actions', sortable: false, align: 'end' },
]

async function fetchItems() {
  loading.value = true
  try {
    const res = await api.get('/partners/')
    items.value = res.data.results || res.data
  } finally {
    loading.value = false
  }
}

function blankInstructions() {
  return AI_PROVIDERS.map((p) => ({ provider: p.id, instructions: '' }))
}

function instructionFor(providerId) {
  return form.value.ai_instructions.find((i) => i.provider === providerId)
}

function openNew() {
  form.value = { name: '', ai_instructions: blankInstructions() }
  dialog.value = true
}

function openEdit(item) {
  form.value = {
    ...item,
    ai_instructions: AI_PROVIDERS.map((p) => ({
      provider: p.id,
      instructions: item.ai_instructions?.find((i) => i.provider === p.id)?.instructions ?? '',
    })),
  }
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
