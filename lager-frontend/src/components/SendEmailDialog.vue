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
          <div class="text-caption text-medium-emphasis mb-4">
            <v-icon size="x-small" class="mr-1">mdi-paperclip</v-icon>
            Das Dokument wird als PDF-Anhang beigefügt.
          </div>

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
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import api from '../api'

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

const loading = ref(false)
const sending = ref(false)
const error = ref('')
const log = ref([])
const form = ref({ recipient: '', subject: '', body: '' })

watch(() => props.modelValue, async (open) => {
  if (!open || !props.apiPath) return
  error.value = ''
  loading.value = true
  try {
    const res = await api.get(`${props.apiPath}/email-info/`)
    form.value = { ...res.data.defaults }
    log.value = res.data.log || []
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
    await api.post(`${props.apiPath}/send-email/`, form.value)
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
