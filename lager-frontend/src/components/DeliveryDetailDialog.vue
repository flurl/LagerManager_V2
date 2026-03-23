<template>
  <v-card>
    <v-card-title class="d-flex align-center pa-4">
      <span>{{ isNew ? 'Neue Lieferung' : `Lieferung #${form.id}` }}</span>
      <v-spacer />
      <v-btn icon @click="$emit('close')"><v-icon>mdi-close</v-icon></v-btn>
    </v-card-title>

    <v-card-text>
      <v-row dense>
        <v-col cols="4">
          <v-select
            v-model="form.supplier"
            :items="suppliers"
            item-title="name"
            item-value="id"
            label="Lieferant"
            :rules="[v => !!v || 'Pflichtfeld']"
          />
        </v-col>
        <v-col cols="3">
          <v-text-field v-model="form.date" label="Datum" type="datetime-local" />
        </v-col>
        <v-col cols="5">
          <v-text-field v-model="form.comment" label="Kommentar" />
        </v-col>
      </v-row>

      <v-divider class="my-3" />

      <!-- Detail lines -->
      <v-row class="mb-1" align="center">
        <v-col><strong>Positionen</strong></v-col>
        <v-col cols="auto">
          <v-btn size="small" prepend-icon="mdi-plus" @click="addLine">Position hinzufügen</v-btn>
        </v-col>
      </v-row>

      <v-table density="compact">
        <thead>
          <tr>
            <th>Artikel</th>
            <th>Menge</th>
            <th>EK-Preis</th>
            <th>MwSt</th>
            <th class="text-right">Netto</th>
            <th class="text-right">Brutto</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(line, idx) in lines" :key="idx">
            <td>
              <v-autocomplete
                v-model="line.article"
                :items="warehouseArticles"
                item-title="article_name"
                item-value="article"
                density="compact"
                hide-details
                style="min-width: 180px"
              />
            </td>
            <td>
              <v-text-field
                v-model.number="line.quantity"
                type="number"
                density="compact"
                hide-details
                style="width: 80px"
              />
            </td>
            <td>
              <v-text-field
                v-model.number="line.unit_price"
                type="number"
                density="compact"
                hide-details
                style="width: 90px"
              />
            </td>
            <td>
              <v-select
                v-model="line.tax_rate"
                :items="taxRates"
                item-title="name"
                item-value="id"
                density="compact"
                hide-details
                style="width: 110px"
              />
            </td>
            <td class="text-right">{{ lineNet(line) }}</td>
            <td class="text-right">{{ lineGross(line) }}</td>
            <td>
              <v-icon size="small" color="error" @click="removeLine(idx)">mdi-delete</v-icon>
            </td>
          </tr>
        </tbody>
        <tfoot>
          <tr>
            <td colspan="4"><strong>Gesamt</strong></td>
            <td class="text-right"><strong>{{ totalNet }}</strong></td>
            <td class="text-right"><strong>{{ totalGross }}</strong></td>
            <td></td>
          </tr>
        </tfoot>
      </v-table>

      <!-- Skonto -->
      <v-row class="mt-3" dense>
        <v-col cols="3">
          <v-text-field
            v-model.number="skontoPercent"
            label="Skonto %"
            type="number"
            density="compact"
          />
        </v-col>
        <v-col cols="auto" class="d-flex align-center">
          <v-btn size="small" @click="applySkonto" :disabled="!form.id">Skonto anwenden</v-btn>
        </v-col>
      </v-row>
    </v-card-text>

    <v-card-actions>
      <v-spacer />
      <v-btn @click="$emit('close')">Abbrechen</v-btn>
      <v-btn color="primary" :loading="saving" @click="save">Speichern</v-btn>
    </v-card-actions>
  </v-card>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { usePeriodStore } from '../stores/period'
import api from '../api'

const props = defineProps({
  delivery: { type: Object, default: null },
})
const emit = defineEmits(['saved', 'close'])

const periodStore = usePeriodStore()
const saving = ref(false)
const suppliers = ref([])
const taxRates = ref([])
const warehouseArticles = ref([])
const skontoPercent = ref(0)

const isNew = computed(() => !props.delivery?.id)
const form = ref({ supplier: null, date: null, comment: '', period: null })
const lines = ref([])

function initForm() {
  if (props.delivery) {
    form.value = { ...props.delivery }
    lines.value = (props.delivery.details || []).map((d) => ({ ...d }))
  } else {
    form.value = {
      supplier: null,
      date: new Date().toISOString().slice(0, 16),
      comment: '',
      is_consumption: false,
      period: periodStore.currentPeriodId,
    }
    lines.value = []
  }
}

function addLine() {
  lines.value.push({ article: null, quantity: 1, unit_price: 0, tax_rate: null })
}

function removeLine(idx) {
  lines.value.splice(idx, 1)
}

function getTaxPercent(taxRateId) {
  const tr = taxRates.value.find((t) => t.id === taxRateId)
  return tr ? Number(tr.percent) : 0
}

function lineNet(line) {
  return (Number(line.quantity) * Number(line.unit_price)).toFixed(2)
}

function lineGross(line) {
  const net = Number(lineNet(line))
  const pct = getTaxPercent(line.tax_rate)
  return (net * (1 + pct / 100)).toFixed(2)
}

const totalNet = computed(() =>
  lines.value.reduce((s, l) => s + Number(lineNet(l)), 0).toFixed(2)
)
const totalGross = computed(() =>
  lines.value.reduce((s, l) => s + Number(lineGross(l)), 0).toFixed(2)
)

async function save() {
  saving.value = true
  try {
    let deliveryId = form.value.id
    if (isNew.value) {
      const res = await api.post('/deliveries/', {
        ...form.value,
        period: periodStore.currentPeriodId,
      })
      deliveryId = res.data.id
    } else {
      await api.put(`/deliveries/${deliveryId}/`, form.value)
      // Delete all existing details and re-create
      const existing = props.delivery?.details || []
      await Promise.all(
        existing.map((d) => api.delete(`/deliveries/${deliveryId}/details/${d.id}/`))
      )
    }
    // Create detail lines
    await Promise.all(
      lines.value.map((l) =>
        api.post(`/deliveries/${deliveryId}/details/`, { ...l, delivery: deliveryId })
      )
    )
    emit('saved')
  } finally {
    saving.value = false
  }
}

async function applySkonto() {
  if (!form.value.id) return
  await api.post(`/deliveries/${form.value.id}/apply_discount/`, { percent: skontoPercent.value })
  // Reload details
  const res = await api.get(`/deliveries/${form.value.id}/`)
  lines.value = res.data.details || []
}

onMounted(async () => {
  const [s, t, wa] = await Promise.all([
    api.get('/suppliers/'),
    api.get('/tax-rates/'),
    api.get('/warehouse-articles/', { params: { period_id: periodStore.currentPeriodId } }),
  ])
  suppliers.value = s.data.results || s.data
  taxRates.value = t.data.results || t.data
  warehouseArticles.value = wa.data.results || wa.data
  initForm()
})

watch(() => props.delivery, initForm)
</script>
