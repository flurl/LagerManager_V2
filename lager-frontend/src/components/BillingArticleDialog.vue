<template>
  <v-card min-width="560">
    <v-card-title class="d-flex align-center pa-4">
      <v-icon class="mr-3">mdi-tag-outline</v-icon>
      {{ isNew ? 'Neuer Artikel' : 'Artikel bearbeiten' }}
      <v-spacer />
      <v-btn icon @click="$emit('close')"><v-icon>mdi-close</v-icon></v-btn>
    </v-card-title>

    <v-card-text>
      <v-row dense>
        <v-col cols="4">
          <v-text-field v-model="form.article_number" label="Artikel-Nr."
            hint="Leer lassen für automatische Vergabe"
            :rules="[v => !v || !v.startsWith('#') || 'Darf nicht mit # beginnen']" />
        </v-col>
        <v-col cols="8">
          <v-text-field v-model="form.name" label="Bezeichnung"
            :rules="[v => !!v || 'Pflichtfeld']" />
        </v-col>
      </v-row>
      <v-row dense>
        <v-col cols="12">
          <v-textarea v-model="form.description" label="Beschreibung" rows="2" auto-grow />
        </v-col>
      </v-row>
      <v-row dense>
        <v-col cols="4"><v-text-field v-model="form.unit" label="Einheit" /></v-col>
        <v-col cols="4"><NumberInput v-model="form.unit_price" label="Preis (netto)" /></v-col>
        <v-col cols="4">
          <v-select v-model="form.tax_rate" :items="taxRates" item-title="name" item-value="id"
            label="Steuersatz" clearable />
        </v-col>
      </v-row>
      <v-checkbox v-model="form.is_active" label="Aktiv" density="compact" />
    </v-card-text>

    <v-card-actions>
      <v-spacer />
      <v-btn @click="$emit('close')">Abbrechen</v-btn>
      <v-btn color="primary" :loading="saving" @click="doSave">Speichern</v-btn>
    </v-card-actions>
  </v-card>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import api from '../api'
import NumberInput from './NumberInput.vue'

const props = defineProps({
  article: { type: Object, default: null },
})
const emit = defineEmits(['saved', 'close'])

const isNew = computed(() => !props.article?.id)
const saving = ref(false)
const taxRates = ref([])

const emptyForm = () => ({
  article_number: '', name: '', description: '', unit: '',
  unit_price: 0, tax_rate: null, is_active: true,
})
const form = ref(emptyForm())

watch(() => props.article, (art) => {
  form.value = art ? { ...art } : emptyForm()
}, { immediate: true })

async function doSave() {
  saving.value = true
  try {
    let res
    if (isNew.value) {
      res = await api.post('/billing-articles/', form.value)
    } else {
      res = await api.put(`/billing-articles/${form.value.id}/`, form.value)
    }
    emit('saved', res.data)
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  const res = await api.get('/tax-rates/')
  taxRates.value = res.data.results || res.data
})
</script>
