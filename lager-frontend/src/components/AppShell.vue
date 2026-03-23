<template>
  <v-navigation-drawer v-model="drawer" permanent width="240">
    <v-list-item
      title="LagerManager"
      subtitle="Lagerverwaltung"
      prepend-icon="mdi-warehouse"
      nav
    />
    <v-divider />

    <v-list density="compact" nav>
      <v-list-subheader>STAMMDATEN</v-list-subheader>
      <v-list-item to="/suppliers" prepend-icon="mdi-truck" title="Lieferanten" />
      <v-list-item to="/tax-rates" prepend-icon="mdi-percent" title="Steuersätze" />
      <v-list-item to="/delivery-units" prepend-icon="mdi-package-variant" title="Liefereinheiten" />

      <v-list-subheader>LAGER</v-list-subheader>
      <v-list-item to="/deliveries" prepend-icon="mdi-receipt-text" title="Lieferungen" />
      <v-list-item to="/stock-levels" prepend-icon="mdi-format-list-numbered" title="Lagerstand" />
      <v-list-item to="/initial-inventory" prepend-icon="mdi-clipboard-list" title="Initialer Stand" />
      <v-list-item to="/physical-counts" prepend-icon="mdi-counter" title="Gezählter Stand" />

      <v-list-subheader>BERICHTE</v-list-subheader>
      <v-list-item to="/reports/stock-level" prepend-icon="mdi-chart-line" title="Lagerstand" />
      <v-list-item to="/reports/inventory" prepend-icon="mdi-clipboard-text" title="Inventur" />
      <v-list-item to="/reports/consumption" prepend-icon="mdi-chart-area" title="Verbrauch" />
      <v-list-item to="/reports/total-deliveries" prepend-icon="mdi-table" title="Gesamte Lieferungen" />

      <v-list-subheader>SYSTEM</v-list-subheader>
      <v-list-item to="/import" prepend-icon="mdi-database-import" title="Daten importieren" />
    </v-list>

    <template #append>
      <v-list density="compact">
        <v-list-item
          prepend-icon="mdi-logout"
          title="Abmelden"
          @click="auth.logout()"
        />
      </v-list>
    </template>
  </v-navigation-drawer>

  <v-app-bar elevation="1">
    <v-app-bar-title>{{ currentRoute }}</v-app-bar-title>
    <v-spacer />
    <v-select
      v-model="periodStore.currentPeriodId"
      :items="periodStore.periods"
      item-title="name"
      item-value="id"
      label="Periode"
      hide-details
      style="max-width: 220px"
    />
    <v-btn icon class="ml-1 mr-3" title="Neue Periode" @click="newPeriodDialog = true">
      <v-icon>mdi-plus-circle-outline</v-icon>
    </v-btn>
  </v-app-bar>

  <!-- New Period Dialog -->
  <v-dialog v-model="newPeriodDialog" max-width="420" persistent>
    <v-card>
      <v-card-title>Neue Periode</v-card-title>
      <v-card-text>
        <v-text-field v-model="newPeriod.name" label="Bezeichnung" placeholder="z.B. 2025" class="mb-2" />
        <v-text-field v-model="newPeriod.start" label="Von" type="datetime-local" class="mb-2" />
        <v-text-field v-model="newPeriod.end" label="Bis" type="datetime-local" class="mb-2" />
        <v-text-field
          v-model.number="newPeriod.checkpoint_year"
          label="Checkpoint-Jahr (optional)"
          type="number"
          hint="Wiffzack checkpoint_jahr Wert für diesen Zeitraum"
          persistent-hint
        />
        <v-alert v-if="newPeriodError" type="error" class="mt-3" density="compact">{{ newPeriodError }}</v-alert>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn @click="newPeriodDialog = false">Abbrechen</v-btn>
        <v-btn color="primary" :loading="newPeriodSaving" @click="savePeriod">Erstellen</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <v-main>
    <v-container fluid>
      <router-view />
    </v-container>
  </v-main>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { usePeriodStore } from '../stores/period'
import { useAuthStore } from '../stores/auth'

const drawer = ref(true)
const route = useRoute()
const periodStore = usePeriodStore()
const auth = useAuthStore()

const currentRoute = computed(() => route.meta?.title || 'LagerManager')

// New period dialog
const newPeriodDialog = ref(false)
const newPeriodSaving = ref(false)
const newPeriodError = ref('')
const newPeriod = reactive({ name: '', start: '', end: '', checkpoint_year: null })

async function savePeriod() {
  newPeriodError.value = ''
  if (!newPeriod.name || !newPeriod.start || !newPeriod.end) {
    newPeriodError.value = 'Bezeichnung, Von und Bis sind Pflichtfelder.'
    return
  }
  newPeriodSaving.value = true
  try {
    await periodStore.createPeriod({
      name: newPeriod.name,
      start: newPeriod.start,
      end: newPeriod.end,
      checkpoint_year: newPeriod.checkpoint_year || null,
    })
    newPeriodDialog.value = false
    Object.assign(newPeriod, { name: '', start: '', end: '', checkpoint_year: null })
  } catch (e) {
    newPeriodError.value = e.response?.data
      ? JSON.stringify(e.response.data)
      : 'Fehler beim Erstellen der Periode.'
  } finally {
    newPeriodSaving.value = false
  }
}

onMounted(() => {
  periodStore.fetchPeriods()
})
</script>
