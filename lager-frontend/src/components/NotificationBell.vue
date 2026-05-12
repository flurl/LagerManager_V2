<template>
  <v-menu v-model="open" :open-delay="0" :close-delay="0" @update:model-value="onMenuToggle">
    <template #activator="{ props }">
      <v-btn v-bind="props" icon class="ml-1" title="Benachrichtigungen">
        <v-badge :model-value="notifications.unreadCount > 0" :content="notifications.unreadCount" color="error">
          <v-icon>mdi-bell-outline</v-icon>
        </v-badge>
      </v-btn>
    </template>

    <v-card min-width="360" max-width="440">
      <v-card-title class="d-flex align-center pa-3 pb-1">
        <span class="text-body-1 font-weight-medium">Benachrichtigungen</span>
        <v-spacer />
        <v-btn
          variant="text"
          size="small"
          :disabled="notifications.unreadCount === 0"
          @click="markAllAsRead"
        >
          Alle als gelesen
        </v-btn>
      </v-card-title>

      <v-divider />

      <v-list density="compact" lines="two" max-height="400" style="overflow-y: auto">
        <template v-if="notifications.loading">
          <v-list-item>
            <v-progress-linear indeterminate />
          </v-list-item>
        </template>
        <template v-else-if="displayItems.length === 0">
          <v-list-item>
            <v-list-item-title class="text-medium-emphasis text-center py-2">
              Keine Benachrichtigungen
            </v-list-item-title>
          </v-list-item>
        </template>
        <template v-else>
          <v-list-item
            v-for="item in displayItems"
            :key="item.id"
            :class="{ 'font-weight-bold': !item.is_read }"
          >
            <template #prepend>
              <v-icon :color="severityColor(item.severity)" size="20" class="mr-1">
                {{ severityIcon(item.severity) }}
              </v-icon>
            </template>

            <v-list-item-title :class="{ 'font-weight-medium': !item.is_read }">
              {{ item.title }}
            </v-list-item-title>
            <v-list-item-subtitle v-if="item.message" class="text-truncate">
              {{ item.message }}
            </v-list-item-subtitle>
            <v-list-item-subtitle class="text-caption text-medium-emphasis">
              {{ formatTime(item.created_at) }}
            </v-list-item-subtitle>

            <template #append>
              <v-btn
                v-if="!item.is_read"
                icon
                size="x-small"
                variant="text"
                title="Als gelesen markieren"
                @click.stop="notifications.markAsRead(item.id)"
              >
                <v-icon size="16">mdi-eye-check</v-icon>
              </v-btn>
              <v-btn
                icon
                size="x-small"
                variant="text"
                title="Verwerfen"
                @click.stop="notifications.dismiss(item.id)"
              >
                <v-icon size="16">mdi-close</v-icon>
              </v-btn>
            </template>
          </v-list-item>
        </template>
      </v-list>

      <v-divider />

      <v-card-actions class="pa-2">
        <v-btn variant="text" size="small" prepend-icon="mdi-bell" @click="goToAll">
          Alle anzeigen
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-menu>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useNotificationsStore } from '../stores/notifications'

const notifications = useNotificationsStore()
const router = useRouter()
const open = ref(false)

const displayItems = computed(() => notifications.items.slice(0, 10))

function onMenuToggle(val) {
  if (val) notifications.fetchAll()
}

async function markAllAsRead() {
  await notifications.markAllAsRead()
}

function goToAll() {
  open.value = false
  router.push('/notifications')
}

const SEVERITY_COLOR = {
  info: 'info',
  success: 'success',
  warning: 'warning',
  error: 'error',
}

const SEVERITY_ICON = {
  info: 'mdi-information',
  success: 'mdi-check-circle',
  warning: 'mdi-alert',
  error: 'mdi-alert-circle',
}

function severityColor(severity) {
  return SEVERITY_COLOR[severity] ?? 'info'
}

function severityIcon(severity) {
  return SEVERITY_ICON[severity] ?? 'mdi-information'
}

function formatTime(isoString) {
  if (!isoString) return ''
  const date = new Date(isoString)
  const now = new Date()
  const diffMs = now - date
  const diffMin = Math.floor(diffMs / 60000)
  if (diffMin < 1) return 'Gerade eben'
  if (diffMin < 60) return `vor ${diffMin} Min.`
  const diffH = Math.floor(diffMin / 60)
  if (diffH < 24) return `vor ${diffH} Std.`
  const diffD = Math.floor(diffH / 24)
  if (diffD < 7) return `vor ${diffD} Tag${diffD === 1 ? '' : 'en'}`
  return date.toLocaleDateString('de-AT')
}
</script>
