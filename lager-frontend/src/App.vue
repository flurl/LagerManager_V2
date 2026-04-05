<template>
  <v-app>
    <template v-if="auth.isAuthenticated">
      <template v-if="route.meta.fullscreen">
        <v-main>
          <router-view />
        </v-main>
      </template>
      <template v-else>
        <AppShell />
      </template>
    </template>
    <template v-else>
      <LoginView />
    </template>
  </v-app>
</template>

<script setup>
import { useRoute } from 'vue-router'
import { useAuthStore } from './stores/auth'
import AppShell from './components/AppShell.vue'
import LoginView from './views/LoginView.vue'

const auth = useAuthStore()
const route = useRoute()
</script>

<style>
.v-data-table tbody tr:nth-child(even) td {
  background-color: rgba(0, 0, 0, 0.03);
}
.v-data-table tbody tr:hover td {
  background-color: rgba(21, 101, 192, 0.08) !important;
}
</style>
