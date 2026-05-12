<template>
  <v-app-bar color="primary" elevation="1">
    <v-app-bar-title class="mr-4">
      <v-icon class="mr-1">mdi-warehouse</v-icon>
      LagerManager
    </v-app-bar-title>

    <!-- Nav groups -->
    <v-menu v-for="(group, i) in visibleNavGroups" :key="group.label" v-model="openMenus[i]" :open-delay="0"
      :close-delay="0" transition="false">
      <template #activator="{ props }">
        <v-btn v-bind="props" :prepend-icon="group.icon" variant="text" class="text-none" @mouseenter="onNavHover(i)">
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
            :prepend-icon="item.icon" :title="item.title" @click="item.action ? item.action() : undefined" />
        </template>
      </v-list>
    </v-menu>

    <v-spacer />

    <v-select v-model="periodStore.currentPeriodId" :items="periodStore.periods" item-title="name" item-value="id"
      label="Periode" hide-details style="max-width: 220px" />
    <v-btn icon class="ml-1" title="Neue Periode" @click="newPeriodDialog = true">
      <v-icon>mdi-plus-circle-outline</v-icon>
    </v-btn>

    <NotificationBell />

    <!-- User menu -->
    <v-menu :open-delay="0" :close-delay="0">
      <template #activator="{ props }">
        <v-btn v-bind="props" icon class="ml-1 mr-1" :title="auth.user?.username ?? 'Benutzer'">
          <v-icon>mdi-account-circle</v-icon>
        </v-btn>
      </template>
      <v-list density="compact" nav min-width="200">
        <v-list-item :subtitle="auth.user?.username ?? ''" prepend-icon="mdi-account" title="Konto" disabled />
        <v-divider class="my-1" />
        <v-list-item prepend-icon="mdi-tune" title="Einstellungen" @click="prefsDialog = true" />
        <v-list-item prepend-icon="mdi-logout" title="Abmelden" @click="auth.logout()" />
      </v-list>
    </v-menu>
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

  <!-- Preferences Dialog -->
  <v-dialog v-model="prefsDialog" max-width="420">
    <v-card>
      <v-card-title>Benutzereinstellungen</v-card-title>
      <v-card-text>
        <v-select v-model="prefsForm.theme" :items="themeOptions" item-title="label" item-value="value"
          label="Design" class="mb-4" />
        <v-select v-model="prefsForm.language" :items="languageOptions" item-title="label" item-value="value"
          label="Sprache" class="mb-4" />
        <div class="text-subtitle-2 mb-2">Periodenfarben</div>
        <v-row v-for="period in periodStore.periods" :key="period.id" align="center" class="mb-1">
          <v-col>{{ period.name }}</v-col>
          <v-col cols="auto">
            <input type="color" :value="prefsForm.period_colors[String(period.id)] ?? '#1565C0'"
              style="width: 40px; height: 32px; cursor: pointer; border: none; padding: 0"
              @input="prefsForm.period_colors[String(period.id)] = $event.target.value" />
          </v-col>
        </v-row>
        <v-alert v-if="prefsError" type="error" class="mt-3" density="compact">{{ prefsError }}</v-alert>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn @click="prefsDialog = false">Abbrechen</v-btn>
        <v-btn color="primary" :loading="prefsSaving" @click="savePrefs">Speichern</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- About Dialog -->
  <v-dialog v-model="aboutDialog" max-width="360">
    <v-card>
      <v-card-title class="d-flex align-center ga-2">
        <v-icon>mdi-warehouse</v-icon>
        Über LagerManager
      </v-card-title>
      <v-card-text>
        <div v-if="aboutLoading" class="text-center py-4">
          <v-progress-circular indeterminate size="24" />
        </div>
        <template v-else>
          <div class="text-body-1">LagerManager {{ aboutVersion }} ({{ aboutHash }})</div>
          <div class="text-body-2 text-medium-emphasis mt-1">
            Frontend V2.{{ frontendCommitCount }} ({{ frontendCommitHash }})
          </div>
        </template>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn @click="aboutDialog = false">Schließen</v-btn>
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
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { usePeriodStore } from '../stores/period'
import { useAuthStore } from '../stores/auth'
import NumberInput from './NumberInput.vue'
import NotificationBell from './NotificationBell.vue'
import api from '../api'

const periodStore = usePeriodStore()
const auth = useAuthStore()

const allNavGroups = [
  {
    label: 'Stammdaten',
    icon: 'mdi-database',
    items: [
      { to: '/article-meta', icon: 'mdi-tag-edit', title: 'Artikel-Metadaten', permission: 'pos_import.view_articlemeta' },
      { to: '/partners', icon: 'mdi-truck', title: 'Partner', permission: 'deliveries.view_partner' },
      { to: '/tax-rates', icon: 'mdi-percent', title: 'Steuersätze', permission: 'deliveries.view_taxrate' },
      { to: '/locations', icon: 'mdi-map-marker', title: 'Standorte', permission: 'core.view_location' },
      { to: '/departments', icon: 'mdi-folder-account', title: 'Abteilungen', permission: 'core.view_department' },
    ],
  },
  {
    label: 'Lager',
    icon: 'mdi-warehouse',
    items: [
      { to: '/stock-movements', icon: 'mdi-receipt-text', title: 'Lagerbewegungen', permission: 'deliveries.view_stockmovement' },
      { to: '/period-start-stock', icon: 'mdi-format-list-numbered', title: 'Periode Anfangs-Stand', permission: 'inventory.view_periodstartstocklevel' },
      { to: '/initial-inventory', icon: 'mdi-clipboard-list', title: 'Initialer Stand', permission: 'inventory.view_initialinventory' },
      { to: '/physical-counts', icon: 'mdi-counter', title: 'Gezählter Stand', permission: 'inventory.view_physicalcount' },
      {
        title: 'Bestandszählung',
        icon: 'mdi-table-edit',
        permission: 'stock_count.view_stockcountentry',
        items: [
          { to: '/stock-count', icon: 'mdi-cellphone-check', title: 'Bestandszählung App', permission: 'stock_count.view_stockcountentry' },
          { to: '/stock-count-entries', icon: 'mdi-database-import', title: 'Bestandszählung Import', permission: 'stock_count.view_stockcountentry' },]
      },
      {
        title: 'Personal-/Eigenverbrauch',
        icon: 'mdi-glass-mug-variant',
        permission: 'deliveries.add_stockmovement',
        items: [
          { to: '/staff-consumption', icon: 'mdi-cellphone-check', title: 'Verbrauch App' },
          { to: '/staff-consumption-import', icon: 'mdi-database-import', title: 'Verbrauch Import', permission: 'deliveries.add_stockmovement' },
        ]
      },
    ],
  },
  {
    label: 'Berichte',
    icon: 'mdi-chart-bar',
    items: [
      {
        title: 'Lager',
        icon: 'mdi-warehouse',
        permission: 'core.view_reports',
        items: [
          { to: '/reports/stock-level', icon: 'mdi-chart-line', title: 'Lagerstand' },
          { to: '/reports/current-stock-level', icon: 'mdi-package-variant', title: 'Aktueller Lagerstand' },
          { to: '/reports/below-minimum-stock', icon: 'mdi-alert-circle-outline', title: 'Unter Mindestbestand' },
          { to: '/reports/inventory', icon: 'mdi-clipboard-text', title: 'Inventur' },
          { to: '/reports/consumption', icon: 'mdi-chart-areaspline', title: 'Verbrauch' },
          { to: '/reports/consumption-totals', icon: 'mdi-sigma', title: 'Gesamtverbrauch' },
          { to: '/reports/total-movements', icon: 'mdi-table', title: 'Gesamte Bewegungen' },
        ],
      },
    ],
  },
  {
    label: 'System',
    icon: 'mdi-cog',
    items: [
      { to: '/import', icon: 'mdi-database-import', title: 'Daten importieren', permission: 'core.run_import' },
      { to: '/settings', icon: 'mdi-tune', title: 'Einstellungen', permission: 'constance.change_config' },
      { href: '/admin/', icon: 'mdi-shield-account', title: 'Django Admin' },
      { icon: 'mdi-information-outline', title: 'Über', action: openAbout },
    ],
  },
]

function filterItems(items) {
  return items
    .filter((item) => !item.permission || auth.hasPermission(item.permission))
    .map((item) => item.items ? { ...item, items: item.items } : item)
}

const visibleNavGroups = computed(() =>
  allNavGroups
    .map((group) => ({ ...group, items: filterItems(group.items) }))
    .filter((group) => group.items.length > 0)
)

// Desktop-style nav: hovering over another menu button while one is open switches immediately
const openMenus = reactive(allNavGroups.map(() => false))

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

// Preferences dialog
const prefsDialog = ref(false)
const prefsSaving = ref(false)
const prefsError = ref('')
const prefsForm = reactive({ language: 'de', theme: 'auto', period_colors: {} })
const languageOptions = [
  { label: 'Deutsch', value: 'de' },
  { label: 'English', value: 'en' },
]
const themeOptions = [
  { label: 'System', value: 'auto' },
  { label: 'Hell', value: 'light' },
  { label: 'Dunkel', value: 'dark' },
]

watch(prefsDialog, (open) => {
  if (open) {
    prefsForm.language = auth.preferences.language ?? 'de'
    prefsForm.theme = auth.preferences.theme ?? 'auto'
    prefsForm.period_colors = { ...auth.preferences.period_colors }
    prefsError.value = ''
  }
})

async function savePrefs() {
  prefsError.value = ''
  prefsSaving.value = true
  try {
    await auth.updatePreferences({ language: prefsForm.language, theme: prefsForm.theme, period_colors: { ...prefsForm.period_colors } })
    prefsDialog.value = false
  } catch {
    prefsError.value = 'Fehler beim Speichern der Einstellungen.'
  } finally {
    prefsSaving.value = false
  }
}

// About dialog
/* eslint-disable no-undef */
const frontendCommitCount = __APP_COMMIT_COUNT__
const frontendCommitHash = __APP_COMMIT_HASH__
/* eslint-enable no-undef */
const aboutDialog = ref(false)
const aboutLoading = ref(false)
const aboutVersion = ref('')
const aboutHash = ref('')

async function openAbout() {
  aboutDialog.value = true
  if (aboutVersion.value) return
  aboutLoading.value = true
  try {
    const { data } = await api.get('/version/')
    aboutVersion.value = data.version
    aboutHash.value = data.hash
  } finally {
    aboutLoading.value = false
  }
}

onMounted(() => {
  periodStore.fetchPeriods()
})
</script>
