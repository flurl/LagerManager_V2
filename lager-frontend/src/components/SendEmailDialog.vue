<template>
  <v-dialog v-model="model" max-width="680" persistent scrollable>
    <v-card>
      <v-card-title class="d-flex align-center pa-4">
        <v-icon class="mr-2">mdi-email-outline</v-icon>
        Dokument versenden
        <template v-if="docLabel"> — {{ docLabel }}</template>
        <v-spacer />
        <v-btn icon variant="text" @click="model = false"><v-icon>mdi-close</v-icon></v-btn>
      </v-card-title>

      <v-card-text class="pa-4" style="overflow-y: auto">
        <div v-if="loading" class="text-center py-6">
          <v-progress-circular indeterminate />
        </div>

        <template v-else>
          <!-- Send form -->
          <v-text-field
            v-model="form.recipient"
            label="An *"
            prepend-inner-icon="mdi-email-outline"
            density="compact"
            class="mb-2"
            :rules="[v => !!v?.trim() || 'Pflichtfeld', v => /.+@.+\..+/.test(v) || 'Ungültige E-Mail-Adresse']"
          />
          <v-text-field
            v-model="form.subject"
            label="Betreff"
            density="compact"
            class="mb-2"
          />
          <v-textarea
            v-model="form.body"
            label="Nachricht"
            rows="5"
            auto-grow
            density="compact"
            class="mb-1"
          />
          <!-- The document itself is always attached -->
          <div class="d-flex align-center mb-1">
            <v-icon size="x-small" class="mr-1">mdi-paperclip</v-icon>
            <span class="text-caption text-medium-emphasis">
              Das Dokument wird als PDF-Anhang beigefügt<template v-if="mergedCount">
                – inklusive {{ mergedCount }}
                {{ mergedCount === 1 ? 'Ergänzung' : 'Ergänzungen' }}</template>.
            </span>
            <v-tooltip text="Dokument-Vorschau"><template #activator="{ props: p }">
              <v-icon v-bind="p" size="small" class="ml-2" @click="previewDocument">
                mdi-file-eye-outline
              </v-icon>
            </template></v-tooltip>
          </div>

          <!-- Attachment picker -->
          <template v-if="attachments.length">
            <div class="text-subtitle-2 mb-1">Anhänge mitsenden</div>
            <v-checkbox
              v-for="item in attachments"
              :key="item.id"
              :model-value="selectedIds.includes(item.id)"
              :disabled="mandatoryIds.includes(item.id)"
              density="compact"
              hide-details
              @update:model-value="v => toggleAttachment(item.id, v)"
            >
              <template #label>
                <span class="mr-2">{{ item.display_title }}</span>
                <v-chip size="x-small" class="mr-2">{{ item.kind_label }}</v-chip>
                <v-tooltip
                  v-if="mandatoryIds.includes(item.id)"
                  :text="`${item.kind_label} wird immer mitgeschickt.`"
                >
                  <template #activator="{ props: p }">
                    <v-chip v-bind="p" size="x-small" color="deep-orange" class="mr-2">Pflicht</v-chip>
                  </template>
                </v-tooltip>
                <span class="text-caption text-medium-emphasis mr-2">
                  {{ item.effective_delivery === 'merge'
                     ? 'wird an das PDF angehängt'
                     : 'als eigene Datei' }}
                  <template v-if="item.size_bytes">
                    · {{ formatBytes(item.size_bytes) }}
                  </template>
                </span>
                <v-tooltip
                  v-if="previewMode(item) === 'download'"
                  text="Nicht als Vorschau darstellbar — herunterladen"
                >
                  <template #activator="{ props: p }">
                    <v-icon v-bind="p" size="small" @click.stop.prevent="openAttachment(item)">
                      mdi-download
                    </v-icon>
                  </template>
                </v-tooltip>
                <v-tooltip
                  v-else-if="previewMode(item)"
                  :text="item.effective_delivery === 'merge'
                    ? 'Vorschau des gesamten Dokuments'
                    : 'Vorschau'"
                >
                  <template #activator="{ props: p }">
                    <v-icon v-bind="p" size="small" @click.stop.prevent="openAttachment(item)">
                      mdi-file-eye-outline
                    </v-icon>
                  </template>
                </v-tooltip>
              </template>
            </v-checkbox>
            <div
              v-if="selectedBytes > 0"
              class="text-caption mb-4 mt-1"
              :class="selectedBytes > SIZE_WARN_BYTES ? 'text-warning' : 'text-medium-emphasis'"
            >
              Zusätzliche Dateien: {{ formatBytes(selectedBytes) }}
              <template v-if="selectedBytes > SIZE_WARN_BYTES">
                — große E-Mails werden von manchen Servern abgewiesen.
              </template>
            </div>
            <div v-else class="mb-4" />
          </template>
          <div v-else class="mb-4" />

          <!-- Error alert -->
          <v-alert v-if="error" type="error" density="compact" class="mb-4" closable @click:close="error = ''">
            {{ error }}
          </v-alert>

          <!-- Send history -->
          <template v-if="log.length">
            <v-divider class="mb-3" />
            <div class="text-subtitle-2 mb-2">Versand-Verlauf</div>
            <v-table density="compact">
              <thead>
                <tr>
                  <th class="text-no-wrap">Zeitpunkt</th>
                  <th>Benutzer</th>
                  <th>An</th>
                  <th>Status</th>
                  <th>Anhänge</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="entry in log" :key="entry.id">
                  <td class="text-no-wrap text-caption">{{ fmtTimestamp(entry.sent_at) }}</td>
                  <td>{{ entry.sent_by_name || '—' }}</td>
                  <td class="text-caption">{{ entry.recipient }}</td>
                  <td>
                    <v-chip size="x-small" :color="entry.status === 'sent' ? 'success' : 'error'">
                      {{ entry.status === 'sent' ? 'Versendet' : 'Fehler' }}
                    </v-chip>
                    <div v-if="entry.error_message" class="text-caption text-error" style="max-width:200px">
                      {{ entry.error_message }}
                    </div>
                  </td>
                  <td>
                    <template v-if="entry.attachments?.length">
                      <v-tooltip v-for="att in entry.attachments" :key="att.id" :text="att.original_filename">
                        <template #activator="{ props }">
                          <a :href="att.file_url" target="_blank" rel="noopener" v-bind="props">
                            <v-icon size="small" color="primary">mdi-file-pdf-box</v-icon>
                          </a>
                        </template>
                      </v-tooltip>
                    </template>
                    <span v-else class="text-medium-emphasis text-caption">—</span>
                  </td>
                </tr>
              </tbody>
            </v-table>
          </template>
        </template>
      </v-card-text>

      <v-card-actions class="pa-4">
        <v-spacer />
        <v-btn @click="model = false">Abbrechen</v-btn>
        <v-btn
          color="primary"
          prepend-icon="mdi-send"
          :loading="sending"
          :disabled="loading || !form.recipient?.trim()"
          @click="send"
        >
          Senden
        </v-btn>
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
import { ref, computed, watch } from 'vue'
import api from '../api'
import { formatBytes } from '../utils/fileSize'
import {
  attachmentPreviewTarget,
  documentPreviewPath,
} from '../utils/attachmentPreview'
import PdfPreviewDialog from './PdfPreviewDialog.vue'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  apiPath: { type: String, default: null },
  docLabel: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue', 'sent'])

const model = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

// Above this, warn that the mail may bounce off a size limit.
const SIZE_WARN_BYTES = 10 * 1024 * 1024

const loading = ref(false)
const sending = ref(false)
const error = ref('')
const log = ref([])
const form = ref({ recipient: '', subject: '', body: '' })
const attachments = ref([])
const selectedIds = ref([])
// Which attachments are preselected (and which are compulsory) is decided by
// the backend, so this dialog needs no notion of attachment types.
const mandatoryIds = ref([])

// Only separately sent files add to the mail size; merged ones become pages of
// the document PDF that is attached anyway.
const selectedBytes = computed(() => attachments.value
  .filter(a => selectedIds.value.includes(a.id) && a.effective_delivery !== 'merge')
  .reduce((sum, a) => sum + (Number(a.size_bytes) || 0), 0))

const mergedCount = computed(() => attachments.value.filter(
  a => selectedIds.value.includes(a.id) && a.effective_delivery === 'merge').length)

const previewDialog = ref(false)
const previewApiPath = ref(null)
const previewUrl = ref(null)
const previewTitle = ref('')
const previewDownloadName = ref('dokument.pdf')

function previewMode(item) {
  return attachmentPreviewTarget(item, {
    selectedIds: selectedIds.value,
    apiPath: props.apiPath,
  })?.mode ?? null
}

function showPdf({ apiPath = null, url = null, title, downloadName }) {
  previewApiPath.value = apiPath
  previewUrl.value = url
  previewTitle.value = title
  previewDownloadName.value = downloadName
  previewDialog.value = true
}

function previewDocument() {
  showPdf({
    apiPath: documentPreviewPath(props.apiPath, selectedIds.value),
    title: props.docLabel || 'Dokument',
    downloadName: 'dokument.pdf',
  })
}

/** Preview the attachment, or hand over the file when it cannot be displayed. */
function openAttachment(item) {
  const target = attachmentPreviewTarget(item, {
    selectedIds: selectedIds.value,
    apiPath: props.apiPath,
  })
  if (!target) return

  if (target.mode === 'download') {
    window.open(target.url, '_blank')
    return
  }
  if (target.mode === 'document') {
    // Merged attachments only exist as pages of the document itself.
    showPdf({
      apiPath: documentPreviewPath(props.apiPath, target.ids),
      title: `${props.docLabel || 'Dokument'} — inkl. ${item.display_title}`,
      downloadName: 'dokument.pdf',
    })
    return
  }
  showPdf({
    apiPath: target.mode === 'api' ? target.path : null,
    url: target.mode === 'url' ? target.url : null,
    title: item.display_title,
    downloadName: item.original_filename || `${item.display_title}.pdf`,
  })
}

function toggleAttachment(id, checked) {
  if (checked) {
    if (!selectedIds.value.includes(id)) selectedIds.value = [...selectedIds.value, id]
  } else {
    selectedIds.value = selectedIds.value.filter(x => x !== id)
  }
}

watch(() => props.modelValue, async (open) => {
  if (!open || !props.apiPath) return
  error.value = ''
  loading.value = true
  try {
    const res = await api.get(`${props.apiPath}/email-info/`)
    form.value = { ...res.data.defaults }
    log.value = res.data.log || []
    attachments.value = res.data.attachments || []
    mandatoryIds.value = res.data.mandatory_attachment_ids || []
    selectedIds.value = [...new Set([
      ...(res.data.default_attachment_ids || []),
      ...mandatoryIds.value,
    ])]
  } catch {
    error.value = 'Fehler beim Laden der E-Mail-Voreinstellungen.'
  } finally {
    loading.value = false
  }
}, { immediate: true })

async function send() {
  if (!form.value.recipient?.trim()) return
  sending.value = true
  error.value = ''
  try {
    await api.post(`${props.apiPath}/send-email/`, {
      ...form.value,
      attachment_ids: selectedIds.value,
    })
    // Refresh the send log so history shows up immediately
    const res = await api.get(`${props.apiPath}/email-info/`)
    log.value = res.data.log || []
    emit('sent')
    model.value = false
  } catch (err) {
    error.value = err?.response?.data?.detail || 'E-Mail konnte nicht gesendet werden.'
    // Refresh log so the failed attempt shows up
    try {
      const res = await api.get(`${props.apiPath}/email-info/`)
      log.value = res.data.log || []
    } catch { /* ignore */ }
  } finally {
    sending.value = false
  }
}

function fmtTimestamp(ts) {
  if (!ts) return ''
  return new Date(ts).toLocaleString('de-AT', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}
</script>
