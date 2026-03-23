<template>
  <v-app>
    <template v-if="auth.isAuthenticated">
      <AppShell />
    </template>
    <template v-else>
      <LoginView />
    </template>
  </v-app>
</template>

<script setup>
import { useAuthStore } from './stores/auth'
import AppShell from './components/AppShell.vue'
import LoginView from './views/LoginView.vue'

const auth = useAuthStore()
</script>
