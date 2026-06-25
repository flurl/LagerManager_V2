<template>
  <v-dialog v-model="model" max-width="900" scrollable>
    <v-card>
      <v-card-title class="d-flex align-center pa-4">
        <v-icon class="mr-2">mdi-history</v-icon>
        Änderungsverlauf
        <v-spacer />
        <v-btn icon @click="model = false"><v-icon>mdi-close</v-icon></v-btn>
      </v-card-title>

      <v-card-text class="pa-0">
        <div v-if="loading" class="text-center pa-6">
          <v-progress-circular indeterminate />
        </div>
        <template v-else-if="entries.length">
          <v-table density="compact">
            <thead>
              <tr>
                <th style="white-space:nowrap">Zeitpunkt</th>
                <th>Benutzer</th>
                <th>Aktion</th>
                <th v-if="hasLineEntries">Objekt</th>
                <th>Änderungen</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="e in entries" :key="e.id">
                <td class="text-no-wrap text-caption">{{ fmtTimestamp(e.timestamp) }}</td>
                <td class="text-no-wrap">{{ e.actor || '—' }}</td>
                <td>
                  <v-chip size="x-small" :color="actionColor(e.action)">{{ actionLabel(e.action) }}</v-chip>
                </td>
                <td v-if="hasLineEntries" class="py-1">
                  <v-chip v-if="e.source === 'line'" size="x-small" variant="outlined" color="secondary">
                    Position
                  </v-chip>
                  <span v-if="e.source === 'line' && e.object_repr"
                    class="text-caption text-medium-emphasis d-block" style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"
                    :title="e.object_repr">
                    {{ e.object_repr }}
                  </span>
                </td>
                <td class="py-1">
                  <div v-if="!e.changes || Object.keys(e.changes).length === 0"
                    class="text-medium-emphasis text-caption">—</div>
                  <div v-for="(vals, field) in e.changes" :key="field" class="text-caption">
                    <strong>{{ field }}</strong>:
                    <template v-if="e.action === ACTION_CREATE">
                      <span class="text-success">{{ vals[1] ?? '—' }}</span>
                    </template>
                    <template v-else-if="e.action === ACTION_DELETE">
                      <span class="text-error">{{ vals[0] ?? '—' }}</span>
                    </template>
                    <template v-else>
                      <span class="text-error" style="text-decoration:line-through">{{ vals[0] ?? '—' }}</span>
                      →
                      <span class="text-success">{{ vals[1] ?? '—' }}</span>
                    </template>
                  </div>
                </td>
              </tr>
            </tbody>
          </v-table>
        </template>
        <div v-else class="text-medium-emphasis text-caption pa-4">Kein Verlauf vorhanden.</div>
      </v-card-text>
    </v-card>
  </v-dialog>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import api from '../api'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  apiPath: { type: String, default: null },
})
const emit = defineEmits(['update:modelValue'])

const ACTION_CREATE = 0
const ACTION_DELETE = 2

const model = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const entries = ref([])
const loading = ref(false)

const hasLineEntries = computed(() => entries.value.some(e => e.source === 'line'))

watch(() => props.modelValue, async (open) => {
  if (!open || !props.apiPath) return
  loading.value = true
  entries.value = []
  try {
    const res = await api.get(`${props.apiPath}/history/`)
    entries.value = res.data
  } catch {
    entries.value = []
  } finally {
    loading.value = false
  }
}, { immediate: true })

function fmtTimestamp(ts) {
  if (!ts) return ''
  return new Date(ts).toLocaleString('de-AT', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  })
}

const ACTION_LABELS = { 0: 'Erstellt', 1: 'Geändert', 2: 'Gelöscht', 3: 'Abgerufen' }
const ACTION_COLORS = { 0: 'success', 1: 'info', 2: 'error', 3: 'grey' }
function actionLabel(a) { return ACTION_LABELS[a] ?? String(a) }
function actionColor(a) { return ACTION_COLORS[a] ?? 'grey' }
</script>
