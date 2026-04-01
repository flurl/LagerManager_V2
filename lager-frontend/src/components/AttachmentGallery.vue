<template>
  <div>
    <!-- Upload area -->
    <v-row dense align="center" class="mb-2">
      <v-col>
        <v-file-input
          v-model="filesToUpload"
          label="Dokument hochladen (Bild oder PDF)"
          accept="image/*,.pdf"
          multiple
          density="compact"
          prepend-icon="mdi-paperclip"
          hide-details
          :loading="uploading"
        />
      </v-col>
      <v-col cols="auto">
        <v-btn
          :disabled="!filesToUpload?.length || uploading"
          :loading="uploading"
          color="primary"
          size="small"
          @click="upload"
        >
          Hochladen
        </v-btn>
      </v-col>
    </v-row>

    <v-alert v-if="uploadError" type="error" density="compact" class="mb-2" closable @click:close="uploadError = ''">
      {{ uploadError }}
    </v-alert>

    <v-progress-linear v-if="loading" indeterminate class="mb-2" />

    <!-- Thumbnail grid -->
    <v-row v-if="attachments.length" dense>
      <v-col
        v-for="att in attachments"
        :key="att.id"
        cols="6"
        sm="4"
        md="3"
        lg="2"
      >
        <v-card variant="outlined" class="pa-1 position-relative" style="cursor: pointer" @click="viewImage(att)">
          <v-img :src="att.file" height="150" cover />
          <v-card-subtitle class="text-caption text-truncate px-1 py-0">
            {{ att.source_filename
              ? `${att.source_filename} S.${att.page_number}`
              : att.original_filename
            }}
          </v-card-subtitle>
          <v-btn
            icon
            size="x-small"
            color="error"
            variant="flat"
            class="position-absolute"
            style="top: 4px; right: 4px;"
            @click.stop="deleteAttachment(att)"
          >
            <v-icon size="small">mdi-delete</v-icon>
          </v-btn>
        </v-card>
      </v-col>
    </v-row>

    <div v-else-if="!loading" class="text-medium-emphasis pa-4 text-center">
      Keine Dokumente vorhanden
    </div>

    <!-- Full-size viewer -->
    <v-dialog v-model="viewerOpen" max-width="90vw">
      <v-card>
        <v-card-title class="d-flex align-center pa-3">
          <span class="text-body-1">{{ viewerTitle }}</span>
          <v-spacer />
          <v-btn icon size="small" variant="text" @click="viewerOpen = false">
            <v-icon>mdi-close</v-icon>
          </v-btn>
        </v-card-title>
        <v-card-text class="d-flex justify-center pa-2">
          <v-img :src="viewerSrc" max-height="80vh" contain />
        </v-card-text>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api from '../api'

const props = defineProps({
  movementId: { type: Number, required: true },
})

const attachments = ref([])
const loading = ref(false)
const uploading = ref(false)
const uploadError = ref('')
const filesToUpload = ref([])

const viewerOpen = ref(false)
const viewerSrc = ref('')
const viewerTitle = ref('')

async function loadAttachments() {
  loading.value = true
  try {
    const res = await api.get(`/stock-movements/${props.movementId}/attachments/`)
    attachments.value = res.data.results ?? res.data
  } finally {
    loading.value = false
  }
}

async function upload() {
  if (!filesToUpload.value?.length) return
  uploading.value = true
  uploadError.value = ''
  try {
    for (const file of filesToUpload.value) {
      const fd = new FormData()
      fd.append('file', file)
      await api.post(`/stock-movements/${props.movementId}/attachments/`, fd)
    }
    filesToUpload.value = []
    await loadAttachments()
  } catch (err) {
    uploadError.value = err.response?.data?.error ?? 'Fehler beim Hochladen.'
  } finally {
    uploading.value = false
  }
}

async function deleteAttachment(att) {
  await api.delete(`/stock-movements/${props.movementId}/attachments/${att.id}/`)
  attachments.value = attachments.value.filter((a) => a.id !== att.id)
}

function viewImage(att) {
  viewerSrc.value = att.file
  viewerTitle.value = att.source_filename
    ? `${att.source_filename} — Seite ${att.page_number}`
    : att.original_filename
  viewerOpen.value = true
}

onMounted(loadAttachments)
</script>
