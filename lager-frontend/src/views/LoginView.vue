<template>
  <v-container class="fill-height" fluid>
    <v-row align="center" justify="center">
      <v-col cols="12" sm="6" md="4">
        <v-card>
          <v-card-title class="text-h5 pa-6">
            <v-icon class="mr-2">mdi-warehouse</v-icon>
            LagerManager
          </v-card-title>
          <v-card-text>
            <v-form @submit.prevent="login">
              <v-text-field v-model="username" label="Benutzername" prepend-inner-icon="mdi-account" />
              <v-text-field
                v-model="password"
                label="Passwort"
                type="password"
                prepend-inner-icon="mdi-lock"
              />
              <v-alert v-if="error" type="error" class="mb-4">{{ error }}</v-alert>
              <v-btn type="submit" color="primary" block :loading="loading">Anmelden</v-btn>
            </v-form>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>
  </v-container>
</template>

<script setup>
import { ref } from 'vue'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const username = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)

async function login() {
  error.value = ''
  loading.value = true
  try {
    await auth.login(username.value, password.value)
  } catch (e) {
    error.value = 'Anmeldung fehlgeschlagen. Bitte überprüfen Sie Ihre Zugangsdaten.'
  } finally {
    loading.value = false
  }
}
</script>
