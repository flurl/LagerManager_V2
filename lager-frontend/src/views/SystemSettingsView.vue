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

    <v-progress-linear v-if="loading" indeterminate color="primary" class="mb-4" />

    <v-expansion-panels v-if="!loading" v-model="openPanels" multiple>
      <v-expansion-panel v-for="group in groups" :key="group.label" :title="group.label">
        <v-expansion-panel-text>
          <template v-for="key in group.keys" :key="key">
            <v-select
              v-if="key === 'DEFAULT_TAX_RATE_ID' || key === 'DEFAULT_BILLING_TAX_RATE_ID'"
              v-model="formValues[key]"
              :items="taxRateChoices"
              item-title="label"
              item-value="value"
              :label="configData[key]?.help_text"
              :disabled="!canEdit"
              :loading="taxRatesLoading"
              class="mb-2"
            />
            <v-switch
              v-else-if="configData[key]?.type === 'bool'"
              v-model="formValues[key]"
              :label="configData[key]?.help_text"
              :disabled="!canEdit"
              color="primary"
              class="mb-2"
            />
            <v-text-field
              v-else-if="configData[key]?.type === 'int' || configData[key]?.type === 'float'"
              v-model.number="formValues[key]"
              :label="configData[key]?.help_text"
              type="number"
              :disabled="!canEdit"
              class="mb-2"
            />
            <v-textarea
              v-else-if="key.endsWith('_BODY')"
              v-model="formValues[key]"
              :label="configData[key]?.help_text"
              :disabled="!canEdit"
              rows="5"
              auto-grow
              class="mb-2"
            />
            <v-text-field
              v-else
              v-model="formValues[key]"
              :label="configData[key]?.help_text"
              :disabled="!canEdit"
              class="mb-2"
            />
          </template>
        </v-expansion-panel-text>
      </v-expansion-panel>
    </v-expansion-panels>

    <v-row v-if="canEdit && !loading" class="mt-4">
      <v-col>
        <v-btn color="primary" :loading="saving" @click="save">Speichern</v-btn>
      </v-col>
    </v-row>
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
const groups = ref([])
const openPanels = ref([0])
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
    groups.value = res.data.groups ?? []
    formValues.value = Object.fromEntries(
      Object.entries(res.data.config).map(([k, v]) => [k, v.value])
    )
    openPanels.value = groups.value.map((_, i) => i)
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
