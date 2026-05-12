<template>
  <div>
    <v-row class="mb-2" align="center">
      <v-col><h2>Benachrichtigungen</h2></v-col>
      <v-col cols="auto" class="d-flex align-center gap-2">
        <v-switch
          v-model="unreadOnly"
          label="Nur ungelesene"
          density="compact"
          hide-details
          class="mr-4"
          @update:model-value="loadNotifications"
        />
        <v-btn
          variant="outlined"
          :disabled="notifications.unreadCount === 0"
          prepend-icon="mdi-eye-check"
          @click="markAllAsRead"
        >
          Alle als gelesen markieren
        </v-btn>
      </v-col>
    </v-row>

    <v-data-table
      :headers="headers"
      :items="notifications.items"
      :loading="notifications.loading"
      density="compact"
      items-per-page="50"
    >
      <template #item.severity="{ item }">
        <v-chip :color="severityColor(item.severity)" size="small" label>
          <v-icon start size="14">{{ severityIcon(item.severity) }}</v-icon>
          {{ severityLabel(item.severity) }}
        </v-chip>
      </template>

      <template #item.is_read="{ item }">
        <v-icon v-if="item.is_read" color="success" size="18">mdi-check-circle</v-icon>
        <v-icon v-else color="warning" size="18">mdi-circle-medium</v-icon>
      </template>

      <template #item.created_at="{ item }">
        {{ formatDate(item.created_at) }}
      </template>

      <template #item.title="{ item }">
        <router-link v-if="item.link" :to="item.link" class="text-decoration-none">
          {{ item.title }}
          <v-icon size="14" class="ml-1">mdi-open-in-app</v-icon>
        </router-link>
        <span v-else>{{ item.title }}</span>
      </template>

      <template #item.actions="{ item }">
        <v-icon
          v-if="!item.is_read"
          size="small"
          class="mr-1"
          title="Als gelesen markieren"
          @click.stop="markAsRead(item)"
        >
          mdi-eye-check
        </v-icon>
        <v-icon
          size="small"
          color="error"
          title="Verwerfen"
          @click.stop="dismiss(item)"
        >
          mdi-delete
        </v-icon>
      </template>
    </v-data-table>

    <v-snackbar v-model="snackbar.show" :color="snackbar.color" :timeout="3000">
      {{ snackbar.message }}
    </v-snackbar>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useNotificationsStore } from '../stores/notifications'

const notifications = useNotificationsStore()
const unreadOnly = ref(false)
const snackbar = ref({ show: false, message: '', color: 'error' })

const headers = [
  { title: 'Status', key: 'is_read', sortable: false, width: '80px' },
  { title: 'Schweregrad', key: 'severity', sortable: true, width: '140px' },
  { title: 'Titel', key: 'title', sortable: true },
  { title: 'Nachricht', key: 'message', sortable: false },
  { title: 'Erstellt', key: 'created_at', sortable: true, width: '160px' },
  { title: '', key: 'actions', sortable: false, align: 'end', width: '80px' },
]

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

const SEVERITY_LABEL = {
  info: 'Information',
  success: 'Erfolg',
  warning: 'Warnung',
  error: 'Fehler',
}

function severityColor(s) { return SEVERITY_COLOR[s] ?? 'info' }
function severityIcon(s) { return SEVERITY_ICON[s] ?? 'mdi-information' }
function severityLabel(s) { return SEVERITY_LABEL[s] ?? s }

function formatDate(isoString) {
  if (!isoString) return ''
  return new Date(isoString).toLocaleString('de-AT')
}

async function loadNotifications() {
  await notifications.fetchAll({ unreadOnly: unreadOnly.value })
}

async function markAsRead(item) {
  try {
    await notifications.markAsRead(item.id)
  } catch {
    snackbar.value = { show: true, message: 'Fehler beim Markieren', color: 'error' }
  }
}

async function markAllAsRead() {
  try {
    await notifications.markAllAsRead()
    await loadNotifications()
  } catch {
    snackbar.value = { show: true, message: 'Fehler beim Markieren', color: 'error' }
  }
}

async function dismiss(item) {
  try {
    await notifications.dismiss(item.id)
  } catch {
    snackbar.value = { show: true, message: 'Fehler beim Verwerfen', color: 'error' }
  }
}

onMounted(() => {
  loadNotifications()
})
</script>
