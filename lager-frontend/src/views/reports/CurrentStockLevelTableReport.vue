<template>
  <ReportTable :headers="headers" :items="filteredItems" :loading="loading" title="Aktueller Lagerstand"
    csv-filename="aktueller-lagerstand.csv">
    <template v-if="hasHiddenArticles" #controls>
      <v-row class="mb-2" align="center">
        <v-col cols="auto">
          <v-chip color="warning" size="small" prepend-icon="mdi-eye-off">
            {{ hiddenCount }} Artikel ausgeblendet
          </v-chip>
        </v-col>
        <v-col cols="auto">
          <v-checkbox v-model="showHidden" label="Ausgeblendete anzeigen" density="compact" hide-details />
        </v-col>
      </v-row>
    </template>
    <template #item.stock="{ item }">{{ item.stock.toFixed(3) }}</template>
    <template #item.purchase_price="{ item }">{{ item.purchase_price?.toFixed(4) ?? '—' }}</template>
    <template #item.total_value="{ item }">{{ item.total_value?.toFixed(2) ?? '—' }}</template>
    <template #item.warehouse_unit_multiplier="{ item }">{{ item.warehouse_unit_multiplier?.toFixed(4) ?? '—' }}</template>
  </ReportTable>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { usePeriodStore } from '../../stores/period'
import { useHiddenArticles } from '../../composables/useHiddenArticles'
import api from '../../api'
import ReportTable from '../../components/ReportTable.vue'

const periodStore = usePeriodStore()
const items = ref([])
const loading = ref(false)

const { hasHiddenArticles, hiddenCount, showHidden, shouldInclude } = useHiddenArticles()

const filteredItems = computed(() => items.value.filter((item) => shouldInclude(item.article)))

const headers = [
  { title: 'Artikel', key: 'article' },
  { title: 'Bestand', key: 'stock', align: 'end' },
  { title: 'EK-Preis', key: 'purchase_price', align: 'end' },
  { title: 'Warenwert', key: 'total_value', align: 'end' },
  { title: 'Einheit', key: 'warehouse_unit' },
  { title: 'Multiplikator', key: 'warehouse_unit_multiplier', align: 'end' },
]

async function fetchData() {
  if (!periodStore.currentPeriodId) return
  loading.value = true
  try {
    const res = await api.get('/reports/current-stock-level/', {
      params: { period_id: periodStore.currentPeriodId },
    })
    items.value = res.data
  } finally {
    loading.value = false
  }
}

watch(() => periodStore.currentPeriodId, fetchData)
onMounted(fetchData)
</script>
