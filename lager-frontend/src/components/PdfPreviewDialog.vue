<template>
  <v-dialog v-model="model" max-width="1000" scrollable>
    <v-card>
      <v-card-title class="d-flex align-center pa-4">
        <v-icon class="mr-2">mdi-file-eye-outline</v-icon>
        {{ title || 'Vorschau' }}
        <v-spacer />
        <v-btn
          variant="text"
          prepend-icon="mdi-download"
          class="mr-2"
          :disabled="!displaySrc"
          @click="download"
        >
          Herunterladen
        </v-btn>
        <v-btn icon variant="text" @click="model = false"><v-icon>mdi-close</v-icon></v-btn>
      </v-card-title>

      <v-card-text class="pa-0" style="height: 75vh">
        <div v-if="loading" class="d-flex align-center justify-center" style="height: 100%">
          <v-progress-circular indeterminate />
        </div>
        <v-alert v-else-if="error" type="error" density="compact" class="ma-4">
          {{ error }}
        </v-alert>
        <iframe
          v-else-if="displaySrc"
          :src="displaySrc"
          title="Vorschau"
          style="width: 100%; height: 100%; border: 0"
        />
      </v-card-text>

      <v-card-actions>
        <v-spacer />
        <v-btn @click="model = false">Schließen</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'

import api from '../api'
import { filenameFromContentDisposition } from '../utils/contentDisposition'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  // Path below /api/, fetched as a blob so the JWT interceptor applies.
  apiPath: { type: String, default: null },
  // Ready-to-use URL (e.g. an uploaded file under /media/), used as-is.
  url: { type: String, default: null },
  title: { type: String, default: '' },
  downloadName: { type: String, default: 'dokument.pdf' },
})
const emit = defineEmits(['update:modelValue'])

const model = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const loading = ref(false)
const error = ref('')
const objectUrl = ref('')
// The name the server suggested for this content, preferred over downloadName.
const serverFilename = ref('')

// Always a blob: URL.  Pointing the iframe at the file itself fails when the
// server sends X-Frame-Options: DENY (Django does, including for /media/ in
// dev), and the browser then shows "localhost refused to connect".
const displaySrc = computed(() => objectUrl.value)

function releaseObjectUrl() {
  if (objectUrl.value) {
    URL.revokeObjectURL(objectUrl.value)
    objectUrl.value = ''
  }
}

/** DRF error bodies arrive as a Blob when responseType is 'blob'. */
async function detailFromBlobError(err) {
  const data = err?.response?.data
  if (!(data instanceof Blob)) return ''
  try {
    return JSON.parse(await data.text())?.detail || ''
  } catch {
    return ''
  }
}

watch(() => [props.modelValue, props.apiPath, props.url], async ([open]) => {
  if (!open) {
    releaseObjectUrl()
    return
  }
  error.value = ''
  serverFilename.value = ''
  releaseObjectUrl()
  if (!props.apiPath && !props.url) return

  loading.value = true
  try {
    objectUrl.value = URL.createObjectURL(await fetchBlob())
  } catch (err) {
    error.value = (await detailFromBlobError(err))
      || 'Vorschau konnte nicht geladen werden.'
  } finally {
    loading.value = false
  }
}, { immediate: true })

/**
 * The content to show, as a Blob.  API paths go through the axios instance so
 * the JWT is sent; a plain URL (an uploaded file under /media/, which needs no
 * token and is not under /api/) is fetched directly.  Either way the Blob keeps
 * the response's content type, so the browser renders PDFs and images alike.
 */
async function fetchBlob() {
  if (props.apiPath) {
    const res = await api.get(props.apiPath, { responseType: 'blob' })
    serverFilename.value = filenameFromContentDisposition(res.headers['content-disposition'])
    return res.data
  }
  const res = await fetch(props.url)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.blob()
}

onBeforeUnmount(releaseObjectUrl)

function download() {
  const href = objectUrl.value || props.url
  if (!href) return
  const a = document.createElement('a')
  a.href = href
  a.download = serverFilename.value || props.downloadName
  a.click()
}
</script>
