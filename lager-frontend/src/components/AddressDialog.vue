<template>
  <v-card min-width="560">
    <v-card-title>{{ form.id ? 'Adresse bearbeiten' : 'Neue Adresse' }}</v-card-title>
    <v-card-text>
      <v-row dense>
        <v-col cols="4"><v-text-field v-model="form.anrede" label="Anrede" /></v-col>
        <v-col cols="4"><v-text-field v-model="form.vorname" label="Vorname" /></v-col>
        <v-col cols="4"><v-text-field v-model="form.nachname" label="Nachname" /></v-col>
      </v-row>
      <v-row dense>
        <v-col cols="8"><v-text-field v-model="form.firma" label="Firma" /></v-col>
        <v-col cols="4"><v-text-field v-model="form.abteilung" label="Abteilung" /></v-col>
      </v-row>
      <v-row dense>
        <v-col cols="12"><v-text-field v-model="form.strasse" label="Straße" /></v-col>
      </v-row>
      <v-row dense>
        <v-col cols="3"><v-text-field v-model="form.plz" label="PLZ" /></v-col>
        <v-col cols="9"><v-text-field v-model="form.ort" label="Ort" /></v-col>
      </v-row>
      <v-row dense>
        <v-col cols="6"><v-text-field v-model="form.telefon" label="Telefon" /></v-col>
        <v-col cols="6"><v-text-field v-model="form.email" label="E-Mail" /></v-col>
      </v-row>
      <v-row dense>
        <v-col cols="12"><v-text-field v-model="form.uid" label="UID-Nummer" /></v-col>
      </v-row>
      <v-row dense>
        <v-col cols="12"><v-textarea v-model="form.anmerkung" label="Anmerkung" rows="2" auto-grow /></v-col>
      </v-row>
    </v-card-text>
    <v-card-actions>
      <v-spacer />
      <v-btn @click="$emit('close')">Abbrechen</v-btn>
      <v-btn color="primary" :loading="saving" @click="save">Speichern</v-btn>
    </v-card-actions>
  </v-card>
</template>

<script setup>
import { ref, watch } from 'vue'
import api from '../api'

const props = defineProps({
  address: { type: Object, default: null },
})
const emit = defineEmits(['saved', 'close'])

const saving = ref(false)
const form = ref({})

watch(() => props.address, (a) => {
  form.value = a ? { ...a } : {
    anrede: '', vorname: '', nachname: '', firma: '', abteilung: '',
    strasse: '', plz: '', ort: '', telefon: '', email: '', uid: '', anmerkung: '',
  }
}, { immediate: true })

async function save() {
  saving.value = true
  try {
    const res = form.value.id
      ? await api.put(`/addresses/${form.value.id}/`, form.value)
      : await api.post('/addresses/', form.value)
    emit('saved', res.data)
  } finally {
    saving.value = false
  }
}
</script>
