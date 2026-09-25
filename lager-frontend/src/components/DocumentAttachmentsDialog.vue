<template>
  <v-dialog v-model="model" max-width="860" persistent scrollable>
    <v-card>
      <v-card-title class="d-flex align-center pa-4">
        <v-icon class="mr-2">mdi-paperclip</v-icon>
        Anhänge
        <template v-if="docLabel"> — {{ docLabel }}</template>
        <v-spacer />
        <v-btn icon variant="text" @click="model = false"><v-icon>mdi-close</v-icon></v-btn>
      </v-card-title>

      <v-card-text class="pa-4" style="overflow-y: auto">
        <div v-if="loading" class="text-center py-6">
          <v-progress-circular indeterminate />
        </div>

        <template v-else>
          <v-alert v-if="error" type="error" density="compact" class="mb-4" closable @click:close="error = ''">
            {{ error }}
          </v-alert>

          <!-- Existing attachments -->
          <div v-if="!attachments.length" class="text-medium-emphasis text-body-2 mb-4">
            Noch keine Anhänge.
          </div>
          <v-table v-else density="compact" class="mb-4">
            <thead>
              <tr>
                <th>Typ</th>
                <th>Bezeichnung</th>
                <th>Versand</th>
                <th class="text-right">Größe</th>
                <th class="text-right">Aktionen</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in attachments" :key="item.id">
                <td>
                  <v-chip size="x-small" :color="item.kind === 'supplement' ? 'primary' : undefined">
                    {{ item.kind_label }}
                  </v-chip>
                </td>
                <td>
                  <div>{{ item.display_title }}</div>
                  <div v-if="item.kind === 'file' && item.original_filename"
                       class="text-caption text-medium-emphasis">
                    {{ item.original_filename }}
                  </div>
                </td>
                <td style="min-width: 210px">
                  <v-select
                    v-if="item.supports_merge"
                    :model-value="item.delivery"
                    :items="deliveryChoices"
                    item-title="title"
                    item-value="value"
                    density="compact"
                    variant="plain"
                    hide-details
                    :disabled="savingId === item.id"
                    @update:model-value="v => changeDelivery(item, v)"
                  />
                  <span v-else class="text-caption text-medium-emphasis">Eigene Datei</span>
                </td>
                <td class="text-right text-caption">
                  {{ item.size_bytes ? formatBytes(item.size_bytes) : '—' }}
                </td>
                <td class="text-right text-no-wrap">
                  <v-tooltip
                    v-if="previewMode(item) === 'download'"
                    text="Nicht als Vorschau darstellbar — herunterladen"
                  >
                    <template #activator="{ props: p }">
                      <v-icon v-bind="p" size="small" @click="openAttachment(item)">mdi-download</v-icon>
                    </template>
                  </v-tooltip>
                  <v-tooltip
                    v-else-if="previewMode(item)"
                    :text="item.effective_delivery === 'merge'
                      ? 'Vorschau des gesamten Dokuments'
                      : 'Vorschau'"
                  >
                    <template #activator="{ props: p }">
                      <v-icon v-bind="p" size="small" @click="openAttachment(item)">
                        mdi-file-eye-outline
                      </v-icon>
                    </template>
                  </v-tooltip>
                  <v-tooltip v-if="item.kind === 'supplement'" text="Bearbeiten"><template #activator="{ props: p }">
                    <v-icon v-bind="p" size="small" class="ml-1" @click="startEdit(item)">mdi-pencil</v-icon>
                  </template></v-tooltip>
                  <v-tooltip text="Löschen"><template #activator="{ props: p }">
                    <v-icon v-bind="p" size="small" class="ml-1" color="error"
                            :disabled="deletingId === item.id"
                            @click="removeAttachment(item)">mdi-delete</v-icon>
                  </template></v-tooltip>
                </td>
              </tr>
            </tbody>
          </v-table>

          <v-divider class="mb-4" />

          <!-- Ergänzung -->
          <div class="text-subtitle-2 mb-2">
            {{ editingId ? 'Ergänzung bearbeiten' : 'Ergänzung hinzufügen' }}
          </div>
          <v-text-field
            v-model="supplementForm.title"
            label="Titel"
            density="compact"
            class="mb-2"
          />
          <v-textarea
            v-model="supplementForm.body"
            label="Text"
            rows="4"
            auto-grow
            density="compact"
            class="mb-1"
          />
          <v-switch
            v-model="supplementForm.merge"
            label="Als zusätzliche Seiten an das Dokument-PDF anhängen"
            color="primary"
            density="compact"
            hide-details
            class="mb-2"
          />
          <div class="d-flex ga-2 mb-4">
            <v-btn
              color="primary"
              size="small"
              :loading="savingSupplement"
              :disabled="!canSaveSupplement"
              @click="saveSupplement"
            >
              {{ editingId ? 'Speichern' : 'Hinzufügen' }}
            </v-btn>
            <v-btn v-if="editingId" size="small" variant="text" @click="cancelEdit">Abbrechen</v-btn>
          </div>

          <v-divider class="mb-4" />

          <!-- Dateien -->
          <div class="text-subtitle-2 mb-2">Dateien hochladen</div>
          <v-file-input
            v-model="filesToUpload"
            label="Dateien auswählen"
            multiple
            density="compact"
            prepend-icon="mdi-paperclip"
            hide-details
            class="mb-2"
            :disabled="uploading"
          />
          <div v-for="(file, index) in filesToUpload" :key="`${file.name}-${index}`" class="mb-2">
            <v-text-field
              v-model="fileDescriptions[index]"
              :label="`Beschreibung für „${file.name}“`"
              density="compact"
              hide-details
            />
          </div>
          <v-btn
            color="primary"
            size="small"
            :disabled="!filesToUpload.length || uploading"
            :loading="uploading"
            @click="upload"
          >
            Hochladen
          </v-btn>
          <div class="text-caption text-medium-emphasis mt-2">
            Dateien werden immer als eigener Anhang mitgeschickt.
          </div>
        </template>
      </v-card-text>

      <v-card-actions>
        <v-spacer />
        <v-btn @click="model = false">Schließen</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <PdfPreviewDialog
    v-model="previewDialog"
    :api-path="previewApiPath"
    :url="previewUrl"
    :title="previewTitle"
    :download-name="previewDownloadName"
  />
</template>

<script setup>
import { computed, ref, watch } from 'vue'

import api from '../api'
import { formatBytes } from '../utils/fileSize'
import { extractErrorMessage } from '../utils/errorMessage'
import {
  attachmentPreviewTarget,
  documentPreviewPath,
} from '../utils/attachmentPreview'
import PdfPreviewDialog from './PdfPreviewDialog.vue'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  // The document this dialog manages attachments for, e.g. '/invoices/12'.
  apiPath: { type: String, default: null },
  docLabel: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue', 'changed'])

const model = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const deliveryChoices = [
  { value: 'merge', title: 'Im Dokument-PDF' },
  { value: 'separate', title: 'Eigene Datei' },
]

const loading = ref(false)
const error = ref('')
const attachments = ref([])

const supplementForm = ref({ title: '', body: '', merge: true })
const editingId = ref(null)
const savingSupplement = ref(false)
const savingId = ref(null)
const deletingId = ref(null)

const filesToUpload = ref([])
const fileDescriptions = ref([])
const uploading = ref(false)

const previewDialog = ref(false)
const previewApiPath = ref(null)
const previewUrl = ref(null)
const previewTitle = ref('')
const previewDownloadName = ref('dokument.pdf')

const canSaveSupplement = computed(
  () => !!(supplementForm.value.title.trim() || supplementForm.value.body.trim()),
)

watch(() => props.modelValue, async (open) => {
  if (!open || !props.apiPath) return
  error.value = ''
  cancelEdit()
  filesToUpload.value = []
  fileDescriptions.value = []
  await load()
}, { immediate: true })

// Keep one description slot per selected file.
watch(filesToUpload, (files) => {
  fileDescriptions.value = files.map((_, i) => fileDescriptions.value[i] ?? '')
})

async function load() {
  loading.value = true
  try {
    const res = await api.get(`${props.apiPath}/attachments/`)
    attachments.value = res.data
  } catch (err) {
    error.value = extractErrorMessage(err, 'Anhänge konnten nicht geladen werden.')
  } finally {
    loading.value = false
  }
}

function previewMode(item) {
  return attachmentPreviewTarget(item, { apiPath: props.apiPath })?.mode ?? null
}

/** Preview the attachment, or hand over the file when it cannot be displayed. */
function openAttachment(item) {
  const target = attachmentPreviewTarget(item, { apiPath: props.apiPath })
  if (!target) return

  if (target.mode === 'download') {
    window.open(target.url, '_blank')
    return
  }
  if (target.mode === 'document') {
    // Merged attachments only exist as pages of the document itself, so that
    // is what the preview has to show.
    previewApiPath.value = documentPreviewPath(props.apiPath, target.ids)
    previewUrl.value = null
    previewTitle.value = `${props.docLabel || 'Dokument'} — inkl. ${item.display_title}`
    previewDownloadName.value = 'dokument.pdf'
  } else {
    previewApiPath.value = target.mode === 'api' ? target.path : null
    previewUrl.value = target.mode === 'url' ? target.url : null
    previewTitle.value = item.display_title
    previewDownloadName.value = item.original_filename || `${item.display_title}.pdf`
  }
  previewDialog.value = true
}

function startEdit(item) {
  editingId.value = item.id
  supplementForm.value = {
    title: item.title ?? '',
    body: item.body ?? '',
    merge: item.delivery === 'merge',
  }
}

function cancelEdit() {
  editingId.value = null
  supplementForm.value = { title: '', body: '', merge: true }
}

async function saveSupplement() {
  savingSupplement.value = true
  error.value = ''
  const payload = {
    kind: 'supplement',
    title: supplementForm.value.title,
    body: supplementForm.value.body,
    delivery: supplementForm.value.merge ? 'merge' : 'separate',
  }
  try {
    if (editingId.value) {
      await api.patch(`${props.apiPath}/attachments/${editingId.value}/`, payload)
    } else {
      await api.post(`${props.apiPath}/attachments/`, payload)
    }
    cancelEdit()
    await load()
    emit('changed')
  } catch (err) {
    error.value = extractErrorMessage(err, 'Ergänzung konnte nicht gespeichert werden.')
  } finally {
    savingSupplement.value = false
  }
}

async function changeDelivery(item, delivery) {
  savingId.value = item.id
  error.value = ''
  try {
    await api.patch(`${props.apiPath}/attachments/${item.id}/`, { delivery })
    await load()
    emit('changed')
  } catch (err) {
    error.value = extractErrorMessage(err, 'Versandart konnte nicht geändert werden.')
  } finally {
    savingId.value = null
  }
}

async function upload() {
  if (!filesToUpload.value.length) return
  uploading.value = true
  error.value = ''
  try {
    // One request per file, like AttachmentGallery — a failing file then does
    // not take the successful ones with it.
    for (const [index, file] of filesToUpload.value.entries()) {
      const fd = new FormData()
      fd.append('kind', 'file')
      fd.append('file', file)
      fd.append('title', fileDescriptions.value[index] ?? '')
      await api.post(`${props.apiPath}/attachments/`, fd)
    }
    filesToUpload.value = []
    fileDescriptions.value = []
    await load()
    emit('changed')
  } catch (err) {
    error.value = extractErrorMessage(err, 'Datei konnte nicht hochgeladen werden.')
    await load()
  } finally {
    uploading.value = false
  }
}

async function removeAttachment(item) {
  if (!window.confirm(`Anhang „${item.display_title}“ wirklich löschen?`)) return
  deletingId.value = item.id
  error.value = ''
  try {
    await api.delete(`${props.apiPath}/attachments/${item.id}/`)
    if (editingId.value === item.id) cancelEdit()
    await load()
    emit('changed')
  } catch (err) {
    error.value = extractErrorMessage(err, 'Anhang konnte nicht gelöscht werden.')
  } finally {
    deletingId.value = null
  }
}
</script>
