<template>
  <div>
    <div class="text-h6 mb-4">Personalverbrauch Import</div>

    <v-data-table
      :headers="headers"
      :items="groups"
      :loading="loading"
      density="compact"
      :items-per-page="100"
      no-data-text="Keine Einträge vorhanden."
    >
      <template #item.departments="{ item }">
        {{ item.departments.join(', ') }}
      </template>
      <template #item.period_id="{ item }">
        <v-chip v-if="item.period_id" size="small" color="success">Periode gefunden</v-chip>
        <v-chip v-else size="small" color="error">Keine Periode</v-chip>
      </template>
      <template #item.actions="{ item }">
        <v-btn
          size="small"
          color="primary"
          variant="tonal"
          :disabled="!item.period_id"
          @click="openImportDialog(item)"
        >
          Importieren
        </v-btn>
      </template>
    </v-data-table>

    <!-- Import dialog -->
    <v-dialog v-model="dialog.show" max-width="900" persistent scrollable>
      <v-card>
        <v-card-title>
          Import Personalverbrauch {{ dialog.yearMonth }}
        </v-card-title>

        <v-card-text>
          <div v-if="dialog.loading" class="text-center py-6">
            <v-progress-circular indeterminate />
          </div>

          <template v-else>
            <div
              v-for="mapping in dialog.mappings"
              :key="mapping.departmentName"
              class="mb-6"
            >
              <div class="text-subtitle-1 font-weight-medium mb-2">
                {{ mapping.departmentName }}
              </div>

              <v-autocomplete
                v-model="mapping.partnerId"
                :items="partners"
                item-title="name"
                item-value="id"
                label="Partner"
                density="compact"
                clearable
                hide-details
                class="mb-3"
              />

              <!-- Editable entries table -->
              <v-table density="compact">
                <thead>
                  <tr>
                    <th style="width: 40px"></th>
                    <th>Artikel</th>
                    <th style="width: 120px">Anzahl</th>
                    <th>Lagerartikel</th>
                    <th style="width: 40px"></th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="entry in mapping.entries" :key="entry.key" :class="{ 'text-disabled': !entry.included }">
                    <td>
                      <v-checkbox
                        v-model="entry.included"
                        density="compact"
                        hide-details
                      />
                    </td>
                    <td>
                      {{ entry.articleName }}
                      <v-chip v-if="entry.isFreeText" size="x-small" color="orange" class="ml-1">frei</v-chip>
                    </td>
                    <td>
                      <v-text-field
                        v-model.number="entry.count"
                        type="number"
                        density="compact"
                        hide-details
                        min="1"
                        style="min-width: 80px"
                        :disabled="!entry.included"
                      />
                    </td>
                    <td>
                      <template v-if="entry.isFreeText">
                        <v-autocomplete
                          v-model="entry.articlePk"
                          :items="warehouseArticles"
                          item-title="article_name"
                          item-value="article_pk"
                          label="Lagerartikel zuordnen"
                          density="compact"
                          clearable
                          hide-details
                          :disabled="!entry.included"
                          style="min-width: 240px"
                        />
                      </template>
                      <template v-else>
                        <span class="text-body-2 text-medium-emphasis">{{ entry.warehouseArticleName }}</span>
                      </template>
                    </td>
                    <td>
                      <v-btn
                        icon="mdi-delete"
                        size="small"
                        variant="text"
                        color="error"
                        @click="pendingDelete = { mapping, entry }"
                      />
                    </td>
                  </tr>
                </tbody>
              </v-table>
            </div>

            <v-alert
              v-if="dialog.mappings.length === 0"
              type="info"
              density="compact"
            >
              Keine Einträge für diesen Monat gefunden.
            </v-alert>
          </template>
        </v-card-text>

        <v-card-actions>
          <v-btn
            color="error"
            variant="tonal"
            :loading="dialog.deleting"
            :disabled="dialog.loading || dialog.importing"
            @click="confirmDelete = true"
          >
            Alles löschen
          </v-btn>
          <v-spacer />
          <v-btn @click="dialog.show = false">Abbrechen</v-btn>
          <v-btn
            color="primary"
            :loading="dialog.importing"
            :disabled="dialog.loading || !canImport"
            @click="doImport"
          >
            Importieren
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Delete single entry confirmation dialog -->
    <v-dialog :model-value="!!pendingDelete" max-width="420" @update:model-value="pendingDelete = null">
      <v-card>
        <v-card-title>Artikel löschen</v-card-title>
        <v-card-text>
          <strong>{{ pendingDelete?.entry.articleName }}</strong> aus
          <strong>{{ pendingDelete?.entry.departmentName }}</strong> wirklich löschen?
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="pendingDelete = null">Abbrechen</v-btn>
          <v-btn color="error" @click="deleteEntry(pendingDelete.mapping, pendingDelete.entry)">Löschen</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Delete all confirmation dialog -->
    <v-dialog v-model="confirmDelete" max-width="420">
      <v-card>
        <v-card-title>Alle Einträge löschen</v-card-title>
        <v-card-text>
          Alle Personalverbrauch-Einträge für <strong>{{ dialog.yearMonth }}</strong> werden
          unwiderruflich gelöscht. Fortfahren?
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="confirmDelete = false">Abbrechen</v-btn>
          <v-btn color="error" @click="doDelete">Löschen</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-snackbar v-model="snackbar.show" :color="snackbar.color" :timeout="4000">
      {{ snackbar.message }}
    </v-snackbar>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import api from '../api'

const groups = ref([])
const loading = ref(false)
const partners = ref([])
const warehouseArticles = ref([])
const taxRateId = ref(null)

const snackbar = ref({ show: false, message: '', color: 'success' })

const confirmDelete = ref(false)
const pendingDelete = ref(null)

const dialog = reactive({
  show: false,
  loading: false,
  importing: false,
  deleting: false,
  yearMonth: '',
  periodId: null,
  mappings: [],
  /**
   * mappings: [{
   *   departmentName: string,
   *   partnerId: number | null,
   *   entries: [{
   *     key: string,           // unique key for v-for
   *     articleName: string,
   *     articlePk: number | null,
   *     warehouseArticleName: string | null,  // for regular entries
   *     count: number,
   *     isFreeText: boolean,
   *     included: boolean,
   *   }]
   * }]
   */
})

const headers = [
  { title: 'Monat', key: 'year_month' },
  { title: 'Abteilungen', key: 'departments', sortable: false },
  { title: 'Einträge', key: 'entry_count' },
  { title: 'Periode', key: 'period_id', sortable: false },
  { title: '', key: 'actions', sortable: false, align: 'end' },
]

const canImport = computed(() =>
  dialog.mappings.length > 0 &&
  dialog.mappings.every((m) => m.partnerId != null) &&
  dialog.mappings.some((m) => m.entries.some((e) => e.included && e.articlePk))
)

onMounted(async () => {
  await Promise.all([loadGroups(), loadPartners(), loadTaxRates()])
})

async function loadGroups() {
  loading.value = true
  try {
    const res = await api.get('/staff-consumption/entries/grouped/')
    groups.value = res.data
  } finally {
    loading.value = false
  }
}

async function loadPartners() {
  const res = await api.get('/partners/')
  partners.value = res.data.results ?? res.data
}

async function loadTaxRates() {
  const res = await api.get('/tax-rates/')
  const rates = res.data.results ?? res.data
  const rate20 = rates.find((r) => Number(r.percent) === 20)
  taxRateId.value = rate20?.id ?? null
}

async function openImportDialog(group) {
  dialog.yearMonth = group.year_month
  dialog.periodId = group.period_id
  dialog.mappings = []
  dialog.show = true
  dialog.loading = true

  try {
    const [entriesRes, articlesRes] = await Promise.all([
      api.get('/staff-consumption/entries/', { params: { year_month: group.year_month } }),
      api.get('/staff-consumption/articles/', { params: { period_id: group.period_id } }),
    ])

    warehouseArticles.value = articlesRes.data

    // Build source_id → { pk, name } lookup
    const sourceIdToArticle = {}
    for (const a of articlesRes.data) {
      sourceIdToArticle[a.article_id] = { pk: a.article_pk, name: a.article_name }
    }

    // Group entries by department
    const byDept = {}
    for (const entry of entriesRes.data) {
      if (!byDept[entry.department_name]) {
        byDept[entry.department_name] = []
      }
      const isFreeText = entry.article_id.startsWith('free-text-')
      const warehouseEntry = isFreeText ? null : (sourceIdToArticle[entry.article_id] ?? null)
      byDept[entry.department_name].push({
        key: `${entry.department_name}-${entry.article_id}`,
        articleId: entry.article_id,      // original article_id for backend delete
        departmentName: entry.department_name,
        articleName: entry.article_name,
        articlePk: warehouseEntry?.pk ?? null,
        warehouseArticleName: warehouseEntry?.name ?? null,
        count: entry.count,
        isFreeText,
        included: true,
      })
    }

    dialog.mappings = Object.entries(byDept)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([deptName, entries]) => ({
        departmentName: deptName,
        partnerId: null,
        entries,
      }))
  } finally {
    dialog.loading = false
  }
}

async function doImport() {
  if (!taxRateId.value) {
    showSnackbar('Kein 20%-Steuersatz gefunden. Bitte in den Stammdaten anlegen.', 'error')
    return
  }

  dialog.importing = true
  try {
    const mappings = dialog.mappings.map((m) => ({
      department_name: m.departmentName,
      partner_id: m.partnerId,
      entries: m.entries
        .filter((e) => e.included && e.articlePk && e.count > 0)
        .map((e) => ({ article_id: e.articlePk, quantity: e.count, tax_rate_id: taxRateId.value })),
    }))

    const res = await api.post('/staff-consumption/import/', {
      year_month: dialog.yearMonth,
      mappings,
    })

    dialog.show = false
    const { created, skipped_departments } = res.data
    let msg = `${created} Lagerbewegung(en) erstellt.`
    if (skipped_departments?.length) {
      msg += ` Übersprungen (keine Artikel): ${skipped_departments.join(', ')}.`
    }
    showSnackbar(msg)
    await loadGroups()
  } catch {
    showSnackbar('Fehler beim Import. Bitte erneut versuchen.', 'error')
  } finally {
    dialog.importing = false
  }
}

async function deleteEntry(mapping, entry) {
  pendingDelete.value = null
  try {
    await api.delete('/staff-consumption/entries/', {
      params: {
        year_month: dialog.yearMonth,
        department_name: entry.departmentName,
        article_id: entry.articleId,
      },
    })
    mapping.entries = mapping.entries.filter((e) => e.key !== entry.key)
  } catch {
    showSnackbar('Fehler beim Löschen des Artikels.', 'error')
  }
}

async function doDelete() {
  confirmDelete.value = false
  dialog.deleting = true
  try {
    const res = await api.delete('/staff-consumption/entries/', {
      params: { year_month: dialog.yearMonth },
    })
    dialog.show = false
    showSnackbar(`${res.data.deleted} Einträge gelöscht.`)
    await loadGroups()
  } catch {
    showSnackbar('Fehler beim Löschen. Bitte erneut versuchen.', 'error')
  } finally {
    dialog.deleting = false
  }
}

function showSnackbar(message, color = 'success') {
  snackbar.value = { show: true, message, color }
}
</script>
