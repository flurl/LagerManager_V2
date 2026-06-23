<template>
  <v-dialog :model-value="modelValue" max-width="1000" @update:model-value="$emit('update:modelValue', $event)">
    <v-card>
      <v-card-title class="d-flex align-center pa-3">
        <span>{{ title }}</span>
        <v-spacer />
        <v-btn variant="tonal" prepend-icon="mdi-download" :loading="pdfLoading" class="mr-2" @click="downloadPdf">
          PDF herunterladen
        </v-btn>
        <v-btn icon @click="$emit('update:modelValue', false)"><v-icon>mdi-close</v-icon></v-btn>
      </v-card-title>

      <v-divider />

      <v-card-text class="pa-0" style="height: 82vh; overflow: hidden">
        <div v-if="loading" class="d-flex justify-center align-center" style="height: 100%">
          <v-progress-circular indeterminate color="primary" />
        </div>
        <div v-else-if="error" class="d-flex justify-center align-center pa-8">
          <v-alert type="error">{{ error }}</v-alert>
        </div>
        <iframe v-else :srcdoc="html" style="width: 100%; height: 100%; border: none;" />
      </v-card-text>
    </v-card>
  </v-dialog>
</template>

<script setup>
import { ref, watch } from 'vue'
import api from '../api'

const props = defineProps({
  modelValue: Boolean,
  /** API base path, e.g. '/offers/5' or '/invoices/3' */
  docPath: { type: String, default: null },
  title: { type: String, default: 'Vorschau' },
})

const emit = defineEmits(['update:modelValue'])

const html = ref('')
const loading = ref(false)
const error = ref(null)
const pdfLoading = ref(false)

watch(
  () => [props.modelValue, props.docPath],
  async ([open, path]) => {
    if (!open || !path) return
    loading.value = true
    error.value = null
    html.value = ''
    try {
      const res = await api.get(`${path}/preview/`, { responseType: 'text' })
      html.value = res.data
    } catch (err) {
      error.value = err.response?.data?.detail || 'Vorschau konnte nicht geladen werden.'
    } finally {
      loading.value = false
    }
  },
  { immediate: true },
)

async function downloadPdf() {
  if (!props.docPath) return
  pdfLoading.value = true
  try {
    const res = await api.get(`${props.docPath}/pdf/`, { responseType: 'blob' })
    const url = URL.createObjectURL(res.data)
    const a = document.createElement('a')
    // Try to get filename from Content-Disposition header
    const cd = res.headers['content-disposition'] || ''
    const match = cd.match(/filename="(.+?)"/)
    a.download = match ? match[1] : 'dokument.pdf'
    a.href = url
    a.click()
    URL.revokeObjectURL(url)
  } catch (err) {
    alert('PDF-Export fehlgeschlagen: ' + (err.response?.data?.detail || err.message))
  } finally {
    pdfLoading.value = false
  }
}
</script>
