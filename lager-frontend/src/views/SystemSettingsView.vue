<template>
  <div>
    <v-row class="mb-2" align="center">
      <v-col><h2>Systemeinstellungen</h2></v-col>
    </v-row>

    <v-alert v-if="!canEdit && !loading" type="info" variant="tonal" density="compact" class="mb-4">
      Nur Lesezugriff – Sie haben keine Berechtigung zum Bearbeiten.
    </v-alert>

    <v-alert v-if="error" type="error" density="compact" class="mb-4">{{ error }}</v-alert>
    <v-alert v-if="saved" type="success" density="compact" class="mb-4">Einstellungen gespeichert.</v-alert>

    <v-card :loading="loading" max-width="600">
      <v-card-text>
        <template v-for="(meta, key) in configData" :key="key">
          <!-- Bool -->
          <v-switch
            v-if="meta.type === 'bool'"
            v-model="formValues[key]"
            :label="meta.help_text"
            :disabled="!canEdit"
            color="primary"
            class="mb-2"
          />
          <!-- TaxRate dropdown -->
          <v-select
            v-else-if="key === 'DEFAULT_TAX_RATE_ID'"
            v-model="formValues[key]"
            :items="taxRateChoices"
            item-title="label"
            item-value="value"
            :label="meta.help_text"
            :disabled="!canEdit"
            :loading="taxRatesLoading"
            class="mb-2"
          />
          <!-- int / float -->
          <v-text-field
            v-else-if="meta.type === 'int' || meta.type === 'float'"
            v-model.number="formValues[key]"
            :label="meta.help_text"
            type="number"
            :disabled="!canEdit"
            class="mb-2"
          />
          <!-- str fallback -->
          <v-text-field
            v-else
            v-model="formValues[key]"
            :label="meta.help_text"
            :disabled="!canEdit"
            class="mb-2"
          />
        </template>
      </v-card-text>
      <v-card-actions v-if="canEdit">
        <v-spacer />
        <v-btn color="primary" :loading="saving" @click="save">Speichern</v-btn>
      </v-card-actions>
    </v-card>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import api from '../api'

const loading = ref(false)
const saving = ref(false)
const canEdit = ref(false)
const configData = ref({})
const formValues = ref({})
const taxRateChoices = ref([])
const taxRatesLoading = ref(false)
const error = ref('')
const saved = ref(false)

async function fetchConfig() {
  loading.value = true
  try {
    const res = await api.get('/config/')
    canEdit.value = res.data.can_edit
    configData.value = res.data.config
    formValues.value = Object.fromEntries(
      Object.entries(res.data.config).map(([k, v]) => [k, v.value])
    )
  } finally {
    loading.value = false
  }
}

async function fetchTaxRates() {
  taxRatesLoading.value = true
  try {
    const res = await api.get('/tax-rates/')
    const items = res.data.results || res.data
    taxRateChoices.value = [
      { value: 0, label: '— keiner —' },
      ...items.map((t) => ({ value: t.id, label: `${t.name} (${t.percent} %)` })),
    ]
  } finally {
    taxRatesLoading.value = false
  }
}

async function save() {
  error.value = ''
  saved.value = false
  saving.value = true
  try {
    await api.patch('/config/', formValues.value)
    saved.value = true
  } catch (e) {
    error.value = e.response?.data?.detail || JSON.stringify(e.response?.data) || 'Fehler beim Speichern.'
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  fetchConfig()
  fetchTaxRates()
})
</script>
