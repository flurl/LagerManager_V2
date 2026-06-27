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
            <!-- Logo upload -->
            <div v-if="key === 'COMPANY_LOGO'" class="mb-4">
              <div class="text-caption text-medium-emphasis mb-2">{{ configData[key]?.help_text }}</div>
              <div v-if="logoPreviewUrl" class="mb-3">
                <img :src="logoPreviewUrl" alt="Firmenlogo" style="max-height:80px;max-width:240px;display:block;border:1px solid #e0e0e0;border-radius:4px;padding:4px;">
              </div>
              <div v-else class="text-body-2 text-medium-emphasis mb-3">Kein Logo gesetzt.</div>
              <div v-if="canEdit" class="d-flex align-center gap-2">
                <v-btn variant="tonal" size="small" :loading="logoUploading" prepend-icon="mdi-upload" @click="triggerLogoUpload">
                  Logo hochladen
                </v-btn>
                <v-btn v-if="logoPreviewUrl" variant="tonal" size="small" color="error" :loading="logoDeleting" prepend-icon="mdi-delete" @click="deleteLogo">
                  Logo entfernen
                </v-btn>
              </div>
            </div>

            <v-select
              v-else-if="key === 'DEFAULT_TAX_RATE_ID' || key === 'DEFAULT_BILLING_TAX_RATE_ID'"
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
              v-else-if="key.includes('_BODY_') || key.endsWith('_BODY')"
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

    <input ref="logoInput" type="file" accept="image/png,image/jpeg,image/gif,image/webp,image/svg+xml" style="display:none" @change="uploadLogo">

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

const logoPreviewUrl = ref('')
const logoUploading = ref(false)
const logoDeleting = ref(false)
const logoInput = ref(null)

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

async function fetchLogo() {
  try {
    const res = await api.get('/config/logo/')
    logoPreviewUrl.value = res.data.url || ''
  } catch {
    logoPreviewUrl.value = ''
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

function triggerLogoUpload() {
  logoInput.value?.click()
}

async function uploadLogo(event) {
  const file = event.target.files?.[0]
  if (!file) return
  logoUploading.value = true
  error.value = ''
  try {
    const fd = new FormData()
    fd.append('logo', file)
    const res = await api.post('/config/logo/', fd, { headers: { 'Content-Type': 'multipart/form-data' } })
    logoPreviewUrl.value = res.data.url || ''
  } catch (e) {
    error.value = e.response?.data?.detail || 'Fehler beim Logo-Upload.'
  } finally {
    logoUploading.value = false
    if (logoInput.value) logoInput.value.value = ''
  }
}

async function deleteLogo() {
  logoDeleting.value = true
  error.value = ''
  try {
    await api.delete('/config/logo/')
    logoPreviewUrl.value = ''
  } catch (e) {
    error.value = e.response?.data?.detail || 'Fehler beim Löschen des Logos.'
  } finally {
    logoDeleting.value = false
  }
}

async function save() {
  error.value = ''
  saved.value = false
  saving.value = true
  try {
    // COMPANY_LOGO is managed via the dedicated logo endpoint, exclude from the patch
    const payload = Object.fromEntries(
      Object.entries(formValues.value).filter(([k]) => k !== 'COMPANY_LOGO')
    )
    await api.patch('/config/', payload)
    saved.value = true
  } catch (e) {
    error.value = e.response?.data?.detail || JSON.stringify(e.response?.data) || 'Fehler beim Speichern.'
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  fetchConfig()
  fetchLogo()
  fetchTaxRates()
})
</script>
