<template>
  <div>
    <!-- Upload area -->
    <v-row v-if="!hideUpload" dense align="center" class="mb-2">
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

    <!-- Selectable mode: fixed-size grid with hover zoom -->
    <div v-if="selectable && attachments.length" class="selectable-grid">
      <div
        v-for="att in attachments"
        :key="att.id"
        class="selectable-thumb"
        :class="{ selected: modelValue.includes(att.id) }"
        @click="toggleSelection(att.id)"
        @mouseenter="onThumbEnter(att, $event)"
        @mouseleave="onThumbLeave"
      >
        <v-img :src="att.file" height="80" width="100" cover />
        <div class="thumb-label text-truncate">
          {{ att.source_filename ? `${att.source_filename} S.${att.page_number}` : att.original_filename }}
        </div>
        <v-icon
          class="thumb-check"
          size="small"
          :color="modelValue.includes(att.id) ? 'primary' : 'grey-lighten-1'"
        >
          {{ modelValue.includes(att.id) ? 'mdi-checkbox-marked-circle' : 'mdi-checkbox-blank-circle-outline' }}
        </v-icon>
      </div>
    </div>

    <!-- Standard mode: thumbnail grid -->
    <v-row v-else-if="!selectable && attachments.length" dense>
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

    <!-- Full-size viewer (standard mode only) -->
    <v-dialog v-if="!selectable" v-model="viewerOpen" max-width="90vw">
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

  <!-- Hover preview (teleported to body to escape dialog overflow) -->
  <Teleport to="body">
    <div
      v-if="hoveredAtt"
      class="thumb-hover-preview"
      :style="{ top: hoverPos.top + 'px', left: hoverPos.left + 'px' }"
    >
      <img :src="hoveredAtt.file" />
    </div>
  </Teleport>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api from '../api'

const props = defineProps({
  movementId: { type: Number, default: null },
  selectable: { type: Boolean, default: false },
  hideUpload: { type: Boolean, default: false },
  modelValue: { type: Array, default: () => [] },
  // Seed the attachment list when no movementId (e.g. pending attachments for a new movement)
  preloadedAttachments: { type: Array, default: () => [] },
})
const emit = defineEmits(['update:modelValue', 'uploaded'])

const attachments = ref([])
const loading = ref(false)
const uploading = ref(false)
const uploadError = ref('')
const filesToUpload = ref([])

const viewerOpen = ref(false)
const viewerSrc = ref('')
const viewerTitle = ref('')

const hoveredAtt = ref(null)
const hoverPos = ref({ top: 0, left: 0 })

async function loadAttachments() {
  loading.value = true
  try {
    const res = await api.get(`/stock-movements/${props.movementId}/attachments/`)
    attachments.value = res.data.results ?? res.data
    if (props.selectable) {
      emit('update:modelValue', attachments.value.map((a) => a.id))
    }
  } finally {
    loading.value = false
  }
}

async function upload() {
  if (!filesToUpload.value?.length) return
  uploading.value = true
  uploadError.value = ''
  try {
    const newAttachments = []
    for (const file of filesToUpload.value) {
      const fd = new FormData()
      fd.append('file', file)
      const url = props.movementId
        ? `/stock-movements/${props.movementId}/attachments/`
        : '/attachments/'
      const res = await api.post(url, fd)
      newAttachments.push(...(Array.isArray(res.data) ? res.data : [res.data]))
    }
    filesToUpload.value = []
    attachments.value = [...attachments.value, ...newAttachments]
    if (props.selectable) {
      emit('update:modelValue', attachments.value.map((a) => a.id))
    }
    emit('uploaded', newAttachments)
  } catch (err) {
    uploadError.value = err.response?.data?.error ?? 'Fehler beim Hochladen.'
  } finally {
    uploading.value = false
  }
}

async function deleteAttachment(att) {
  await api.delete(`/attachments/${att.id}/`)
  attachments.value = attachments.value.filter((a) => a.id !== att.id)
  if (props.selectable) {
    emit('update:modelValue', attachments.value.map((a) => a.id))
  }
}

function onThumbEnter(att, event) {
  hoveredAtt.value = att
  const rect = event.currentTarget.getBoundingClientRect()
  const previewWidth = 320
  const previewHeight = 400
  let left = rect.right + 12
  if (left + previewWidth > window.innerWidth) {
    left = rect.left - previewWidth - 12
  }
  let top = rect.top
  if (top + previewHeight > window.innerHeight) {
    top = window.innerHeight - previewHeight - 8
  }
  hoverPos.value = { top, left }
}

function onThumbLeave() {
  hoveredAtt.value = null
}

function toggleSelection(id) {
  const current = props.modelValue
  const idx = current.indexOf(id)
  const updated = idx === -1 ? [...current, id] : current.filter((v) => v !== id)
  emit('update:modelValue', updated)
}

function viewImage(att) {
  viewerSrc.value = att.file
  viewerTitle.value = att.source_filename
    ? `${att.source_filename} — Seite ${att.page_number}`
    : att.original_filename
  viewerOpen.value = true
}

defineExpose({ attachments })

onMounted(() => {
  if (props.movementId) {
    loadAttachments()
  } else if (props.preloadedAttachments.length) {
    attachments.value = [...props.preloadedAttachments]
    if (props.selectable) {
      emit('update:modelValue', attachments.value.map((a) => a.id))
    }
  }
})
</script>

<style scoped>
.selectable-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  overflow: visible;
}

.selectable-thumb {
  position: relative;
  width: 100px;
  cursor: pointer;
  border: 2px solid transparent;
  border-radius: 4px;
  overflow: hidden;
}

.selectable-thumb.selected {
  border-color: rgb(var(--v-theme-primary));
}

.thumb-hover-preview {
  position: fixed;
  z-index: 9999;
  pointer-events: none;
  border-radius: 6px;
  overflow: hidden;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.35);
}

.thumb-hover-preview img {
  display: block;
  width: 320px;
  height: auto;
}

.thumb-label {
  font-size: 10px;
  padding: 0 4px;
  max-width: 96px;
  background: white;
}

.thumb-check {
  position: absolute;
  top: 2px;
  left: 2px;
  background: rgba(255, 255, 255, 0.85);
  border-radius: 50%;
}
</style>
