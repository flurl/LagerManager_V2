<template>
  <div>
    <h2 class="mb-4">Daten importieren (Wiffzack)</h2>
    <v-card max-width="500">
      <v-card-text>
        <v-form @submit.prevent="runImport">
          <v-text-field v-model="form.host" label="Host" />
          <v-text-field v-model="form.database" label="Datenbank" />
          <v-text-field v-model="form.user" label="Benutzer" />
          <v-text-field v-model="form.password" label="Passwort" type="password" />

          <v-alert v-if="error" type="error" class="mb-4">{{ error }}</v-alert>
          <v-alert v-if="summary" type="success" class="mb-4">
            Import erfolgreich!
            <ul>
              <li v-for="(count, table) in summary" :key="table">{{ table }}: {{ count }} Zeilen</li>
            </ul>
          </v-alert>

          <v-btn
            type="submit"
            color="primary"
            block
            :loading="loading"
            :disabled="!periodStore.currentPeriodId"
          >
            Import starten
          </v-btn>
        </v-form>
      </v-card-text>
    </v-card>

    <!-- Loading overlay -->
    <v-overlay v-model="loading" class="align-center justify-center">
      <v-card class="pa-6 text-center">
        <v-progress-circular indeterminate color="primary" size="64" class="mb-4" />
        <div>Import läuft... Bitte warten.</div>
        <div class="text-caption text-medium-emphasis mt-2">Dies kann mehrere Minuten dauern.</div>
      </v-card>
    </v-overlay>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { usePeriodStore } from '../stores/period'
import api from '../api'

const periodStore = usePeriodStore()
const loading = ref(false)
const error = ref('')
const summary = ref(null)

const form = reactive({
  host: '',
  database: '',
  user: '',
  password: '',
})

async function runImport() {
  error.value = ''
  summary.value = null
  loading.value = true
  try {
    const res = await api.post('/import/run/', {
      ...form,
      period_id: periodStore.currentPeriodId,
    }, { timeout: 600000 }) // 10 min timeout
    summary.value = res.data.summary
  } catch (e) {
    error.value = e.response?.data?.error || 'Import fehlgeschlagen.'
  } finally {
    loading.value = false
  }
}
</script>
