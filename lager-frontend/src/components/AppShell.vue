<template>
  <v-app-bar elevation="1">
    <v-app-bar-title class="mr-4">
      <v-icon class="mr-1">mdi-warehouse</v-icon>
      LagerManager
    </v-app-bar-title>

    <!-- Nav groups -->
    <v-menu
      v-for="(group, i) in navGroups"
      :key="group.label"
      v-model="openMenus[i]"
      :open-delay="0"
      :close-delay="0"
      transition="false"
    >
      <template #activator="{ props }">
        <v-btn
          v-bind="props"
          :prepend-icon="group.icon"
          variant="text"
          class="text-none"
          @mouseenter="onNavHover(i)"
        >
          {{ group.label }}
          <v-icon end>mdi-chevron-down</v-icon>
        </v-btn>
      </template>
      <v-list density="compact" nav min-width="200">
        <template v-for="item in group.items" :key="item.to ?? item.title">
          <v-menu v-if="item.items" location="end" open-on-hover :open-delay="0" :close-delay="0" transition="false">
            <template #activator="{ props }">
              <v-list-item v-bind="props" :prepend-icon="item.icon" :title="item.title"
                append-icon="mdi-chevron-right" />
            </template>
            <v-list density="compact" nav min-width="180">
              <v-list-item v-for="sub in item.items" :key="sub.to" :to="sub.to" :prepend-icon="sub.icon"
                :title="sub.title" />
            </v-list>
          </v-menu>
          <v-list-item v-else :to="item.to" :href="item.href" :target="item.href ? '_blank' : undefined"
            :prepend-icon="item.icon" :title="item.title" />
        </template>
      </v-list>
    </v-menu>

    <v-spacer />

    <v-select v-model="periodStore.currentPeriodId" :items="periodStore.periods" item-title="name" item-value="id"
      label="Periode" hide-details style="max-width: 220px" />
    <v-btn icon class="ml-1 mr-1" title="Neue Periode" @click="newPeriodDialog = true">
      <v-icon>mdi-plus-circle-outline</v-icon>
    </v-btn>
    <v-btn icon title="Abmelden" @click="auth.logout()">
      <v-icon>mdi-logout</v-icon>
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
        <NumberInput v-model="newPeriod.checkpoint_year" label="Checkpoint-Jahr (optional)" :decimals="0"
          hint="Wiffzack checkpoint_jahr Wert für diesen Zeitraum" persistent-hint />
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
import { onMounted, reactive, ref } from 'vue'
import { usePeriodStore } from '../stores/period'
import { useAuthStore } from '../stores/auth'
import NumberInput from './NumberInput.vue'

const periodStore = usePeriodStore()
const auth = useAuthStore()

const navGroups = [
  {
    label: 'Stammdaten',
    icon: 'mdi-database',
    items: [
      { to: '/article-meta', icon: 'mdi-tag-edit', title: 'Artikel-Metadaten' },
      { to: '/partners', icon: 'mdi-truck', title: 'Partner' },
      { to: '/tax-rates', icon: 'mdi-percent', title: 'Steuersätze' },
      { to: '/locations', icon: 'mdi-map-marker', title: 'Standorte' },
    ],
  },
  {
    label: 'Lager',
    icon: 'mdi-warehouse',
    items: [
      { to: '/stock-movements', icon: 'mdi-receipt-text', title: 'Lagerbewegungen' },
      { to: '/period-start-stock', icon: 'mdi-format-list-numbered', title: 'Periode Start-Stand' },
      { to: '/initial-inventory', icon: 'mdi-clipboard-list', title: 'Initialer Stand' },
      { to: '/physical-counts', icon: 'mdi-counter', title: 'Gezählter Stand' },
      { to: '/stock-count', icon: 'mdi-cellphone-check', title: 'Bestandszählung' },
      { to: '/stock-count-entries', icon: 'mdi-table-edit', title: 'Zählergebnisse' },
    ],
  },
  {
    label: 'Berichte',
    icon: 'mdi-chart-bar',
    items: [
      {
        title: 'Lager',
        icon: 'mdi-warehouse',
        items: [
          { to: '/reports/stock-level', icon: 'mdi-chart-line', title: 'Lagerstand' },
          { to: '/reports/current-stock-level', icon: 'mdi-package-variant', title: 'Aktueller Lagerstand' },
          { to: '/reports/inventory', icon: 'mdi-clipboard-text', title: 'Inventur' },
          { to: '/reports/consumption', icon: 'mdi-chart-areaspline', title: 'Verbrauch' },
          { to: '/reports/consumption-totals', icon: 'mdi-sigma', title: 'Gesamtverbrauch' },
          { to: '/reports/total-movements', icon: 'mdi-table', title: 'Gesamte Bewegungen' },
        ],

      },
      //{ to: '/reports/stock-level', icon: 'mdi-chart-line', title: 'Lagerstand' },
    ],
  },
  {
    label: 'System',
    icon: 'mdi-cog',
    items: [
      { to: '/import', icon: 'mdi-database-import', title: 'Daten importieren' },
      { to: '/settings', icon: 'mdi-tune', title: 'Einstellungen' },
      { href: '/admin/', icon: 'mdi-shield-account', title: 'Django Admin' },
    ],
  },
]

// Desktop-style nav: hovering over another menu button while one is open switches immediately
const openMenus = reactive(navGroups.map(() => false))

function onNavHover(i) {
  if (openMenus.some(Boolean) && !openMenus[i]) {
    openMenus.fill(false)
    openMenus[i] = true
  }
}

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
