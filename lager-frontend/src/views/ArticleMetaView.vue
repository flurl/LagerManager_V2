<template>
  <div>
    <v-row class="mb-2" align="center">
      <v-col><h2>Artikel-Metadaten</h2></v-col>
    </v-row>

    <v-row class="mb-2" align="center" dense>
      <v-col cols="12" sm="6">
        <v-text-field
          v-model="search"
          label="Suchen…"
          prepend-inner-icon="mdi-magnify"
          clearable
          hide-details
          density="compact"
          variant="outlined"
        />
      </v-col>
      <v-col cols="12" sm="6" class="d-flex align-center">
        <v-switch
          v-model="onlyWarehouse"
          label="Nur Lagerartikel"
          hide-details
          density="compact"
          color="primary"
        />
      </v-col>
    </v-row>

    <v-data-table
      :headers="headers"
      :items="filteredRows"
      :loading="loading"
      density="compact"
      :items-per-page="100"
    >
      <template #item.is_hidden="{ item }">
        <v-checkbox-btn
          :model-value="item.meta?.is_hidden ?? false"
          density="compact"
          @update:model-value="toggleHidden(item, $event)"
        />
      </template>

      <template #item.sub_articles="{ item }">
        <span v-if="item.meta?.sub_articles?.length">
          <v-chip v-for="s in item.meta.sub_articles" :key="s" size="small" class="mr-1">{{ s }}</v-chip>
        </span>
        <span v-else class="text-disabled">—</span>
      </template>

      <template #item.package_size="{ item }">
        <span v-if="item.meta?.package_size != null">{{ item.meta.package_size }}</span>
        <span v-else class="text-disabled">—</span>
      </template>

      <template #item.actions="{ item }">
        <v-icon size="small" @click="openEdit(item)">mdi-pencil</v-icon>
      </template>
    </v-data-table>

    <v-dialog v-model="dialog" max-width="440">
      <v-card>
        <v-card-title>{{ editingArticle?.name }}</v-card-title>
        <v-card-text>
          <v-checkbox v-model="form.is_hidden" label="Versteckt" density="compact" class="mb-2" />
          <v-combobox
            v-model="form.sub_articles"
            label="Unter-Artikel"
            hint="z.B. Zitrone, Orange — Enter zum Hinzufügen"
            persistent-hint
            multiple
            chips
            closable-chips
            class="mb-4"
          />
          <v-text-field
            v-model="form.package_size"
            label="Packungsgröße"
            type="number"
            min="0"
            step="any"
            clearable
            density="compact"
            hide-details
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="dialog = false">Abbrechen</v-btn>
          <v-btn color="primary" :loading="saving" @click="save">Speichern</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import api from '../api'
import { usePeriodStore } from '../stores/period'

const periodStore = usePeriodStore()
const periodId = computed(() => periodStore.currentPeriodId)

const articles = ref([])
const metaMap = ref({})          // source_id → meta object
const warehouseSourceIds = ref(new Set())
const loading = ref(false)
const search = ref('')
const onlyWarehouse = ref(false)

const dialog = ref(false)
const saving = ref(false)
const editingArticle = ref(null)
const form = ref({ is_hidden: false, sub_articles: [], package_size: null })

const headers = [
  { title: 'Artikel', key: 'name' },
  { title: 'Versteckt', key: 'is_hidden', sortable: false },
  { title: 'Unter-Artikel', key: 'sub_articles', sortable: false },
  { title: 'Packungsgröße', key: 'package_size', sortable: false },
  { title: '', key: 'actions', sortable: false, align: 'end' },
]

const rows = computed(() =>
  articles.value.map((a) => ({ ...a, meta: metaMap.value[a.source_id] ?? null }))
)

const filteredRows = computed(() => {
  let result = rows.value
  if (onlyWarehouse.value) {
    result = result.filter((r) => warehouseSourceIds.value.has(r.source_id))
  }
  const q = search.value?.trim().toLowerCase()
  if (q) {
    result = result.filter((r) => r.name.toLowerCase().includes(q))
  }
  return result
})

async function fetchData() {
  if (!periodId.value) return
  loading.value = true
  try {
    const [artRes, metaRes, waRes] = await Promise.all([
      api.get('/articles/', { params: { period_id: periodId.value } }),
      api.get('/article-meta/', { params: { period_id: periodId.value } }),
      api.get('/warehouse-articles/', { params: { period_id: periodId.value } }),
    ])
    articles.value = artRes.data.results ?? artRes.data
    metaMap.value = Object.fromEntries(
      (metaRes.data.results ?? metaRes.data).map((m) => [m.source_id, m])
    )
    warehouseSourceIds.value = new Set(
      (waRes.data.results ?? waRes.data).map((w) => w.source_article_id)
    )
  } finally {
    loading.value = false
  }
}

async function toggleHidden(row, value) {
  await saveMeta(row, { is_hidden: value, sub_articles: row.meta?.sub_articles ?? [], package_size: row.meta?.package_size ?? null })
}

function openEdit(row) {
  editingArticle.value = row
  form.value = {
    is_hidden: row.meta?.is_hidden ?? false,
    sub_articles: row.meta?.sub_articles ? [...row.meta.sub_articles] : [],
    package_size: row.meta?.package_size ?? null,
  }
  dialog.value = true
}

async function save() {
  saving.value = true
  try {
    await saveMeta(editingArticle.value, form.value)
    dialog.value = false
  } finally {
    saving.value = false
  }
}

async function saveMeta(row, data) {
  const existing = metaMap.value[row.source_id]
  const packageSize = data.package_size === '' || data.package_size === null ? null : Number(data.package_size)
  const payload = {
    source_id: row.source_id,
    period: periodId.value,
    ...data,
    package_size: packageSize,
  }
  let res
  if (existing) {
    res = await api.put(`/article-meta/${existing.id}/`, payload)
  } else {
    res = await api.post('/article-meta/', payload)
  }
  metaMap.value = { ...metaMap.value, [row.source_id]: res.data }
}

watch(periodId, fetchData, { immediate: true })
</script>
