<template>
  <v-app>
    <template v-if="auth.isAuthenticated || route.meta.public">
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
import { onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from './stores/auth'
import { useNotificationsStore } from './stores/notifications'
import { useAppTheme } from './composables/useAppTheme'
import AppShell from './components/AppShell.vue'
import LoginView from './views/LoginView.vue'

const auth = useAuthStore()
const notifications = useNotificationsStore()
const route = useRoute()
useAppTheme()

onMounted(async () => {
  if (auth.isAuthenticated && !auth.user) {
    try {
      await auth.fetchMe()
    } catch {
      await auth.logout()
    }
  }
})

watch(
  () => auth.isAuthenticated,
  (authenticated) => {
    if (authenticated) {
      notifications.fetchUnreadCount()
      notifications.startPolling()
    } else {
      notifications.stopPolling()
      notifications.reset()
    }
  },
  { immediate: true },
)
</script>

<style>
.v-data-table tbody tr:nth-child(even) td {
  background-color: rgba(0, 0, 0, 0.04);
}
.v-theme--dark .v-data-table tbody tr:nth-child(even) td {
  background-color: rgba(255, 255, 255, 0.07);
}
.v-data-table tbody tr:hover td {
  background-color: var(--period-primary-hover, rgba(21, 101, 192, 0.08)) !important;
}
</style>
