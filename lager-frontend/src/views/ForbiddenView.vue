<template>
  <v-container class="d-flex align-center justify-center" style="min-height: 60vh">
    <v-card max-width="420" class="text-center pa-6">
      <v-icon size="64" color="warning">mdi-lock</v-icon>
      <v-card-title class="text-h5 mt-3">Kein Zugriff</v-card-title>
      <v-card-text>
        Sie haben keine Berechtigung, diese Seite aufzurufen.
        Wenden Sie sich an einen Administrator.
      </v-card-text>
      <v-card-actions class="justify-center">
        <v-btn color="primary" @click="router.back()">Zurück</v-btn>
      </v-card-actions>
    </v-card>
  </v-container>
</template>

<script setup>
import { useRouter } from 'vue-router'
const router = useRouter()
</script>
