<template>
  <div>
    <v-row align="center" class="mb-2">
      <v-col>
        <h2 v-if="title">{{ title }}</h2>
      </v-col>
      <v-col cols="auto">
        <v-btn v-if="csvFilename" prepend-icon="mdi-download" @click="handleExportCsv">CSV</v-btn>
      </v-col>
    </v-row>

    <slot name="controls" />

    <v-text-field
      v-model="search"
      label="Suchen..."
      prepend-inner-icon="mdi-magnify"
      clearable
      density="compact"
      hide-details
      class="mb-2"
    />

    <v-data-table
      :headers="headers"
      :items="displayItems"
      :loading="loading"
      :search="groupByKey ? undefined : search"
      :items-per-page="100"
      density="compact"
    >
      <!-- Custom item rendering when groupBy is active -->
      <template v-if="groupByKey" #item="slotProps">
        <tr v-if="slotProps.item._isGroupTotal" class="group-total-row">
          <td v-for="col in slotProps.columns" :key="col.key" :class="col.cellProps?.class" :style="col.cellProps?.style">
            <template v-if="col.key === groupByKey">
              <strong>{{ slotProps.item._groupValue }} – Gesamt</strong>
            </template>
            <strong v-else-if="typeof slotProps.item[col.key] === 'number'">
              <slot
                v-if="$slots[`item.${col.key}`]"
                :name="`item.${col.key}`"
                :item="slotProps.item"
                :value="slotProps.item[col.key]"
                :column="col"
                :index="slotProps.index"
              />
              <template v-else>{{ slotProps.item[col.key] }}</template>
            </strong>
          </td>
        </tr>
        <tr v-else v-bind="slotProps.props" :class="{ 'alt-row': slotProps.item._altRow }">
          <td
            v-for="col in slotProps.columns"
            :key="col.key"
            :class="col.cellProps?.class"
            :style="col.cellProps?.style"
          >
            <slot
              v-if="$slots[`item.${col.key}`]"
              :name="`item.${col.key}`"
              :item="slotProps.item"
              :value="slotProps.item[col.key]"
              :column="col"
              :index="slotProps.index"
            />
            <template v-else>{{ slotProps.item[col.key] }}</template>
          </td>
        </tr>
      </template>

      <!-- Pass through all slots (when no groupBy: includes 'item'; when groupBy active: excludes it) -->
      <template v-for="(_, name) in passedSlots" #[name]="slotProps">
        <slot :name="name" v-bind="slotProps ?? {}" />
      </template>
    </v-data-table>
  </div>
</template>

<script setup>
import { ref, computed, useSlots } from 'vue'
import { useCsvExport } from '../composables/useCsvExport'

const props = defineProps({
  headers: {
    type: Array,
    required: true,
  },
  items: {
    type: Array,
    default: () => [],
  },
  loading: {
    type: Boolean,
    default: false,
  },
  title: {
    type: String,
    default: '',
  },
  csvFilename: {
    type: String,
    default: '',
  },
  groupBy: {
    type: [String, Number],
    default: null,
  },
  groupByFn: {
    type: Function,
    default: null,
  },
})

const search = ref('')
const slots = useSlots()
const { exportCsv } = useCsvExport()

// Resolve groupBy to a column key string
const groupByKey = computed(() => {
  if (props.groupBy == null) return null
  if (typeof props.groupBy === 'number') return props.headers[props.groupBy]?.key ?? null
  return props.groupBy
})

// Manual search filter — only used when groupBy is active (otherwise v-data-table handles it)
const filteredItems = computed(() => {
  if (!groupByKey.value || !search.value) return props.items
  const s = search.value.toLowerCase()
  return props.items.filter((item) =>
    Object.values(item).some((v) => String(v ?? '').toLowerCase().includes(s)),
  )
})

// Column keys whose values are numeric (used for summation in total rows)
const numericKeys = computed(() =>
  props.headers
    .filter((h) => h.key !== groupByKey.value)
    .map((h) => h.key)
    .filter((key) => props.items.some((item) => typeof item[key] === 'number')),
)

// Flat list of items with group-total rows injected after each group
const displayItems = computed(() => {
  if (!groupByKey.value) return props.items

  const groups = new Map()
  for (const item of filteredItems.value) {
    const rawVal = item[groupByKey.value]
    const groupKey = props.groupByFn ? props.groupByFn(rawVal) : rawVal
    if (!groups.has(groupKey)) groups.set(groupKey, [])
    groups.get(groupKey).push(item)
  }

  const result = []
  let dataRowIndex = 0
  for (const [groupVal, groupItems] of groups) {
    for (const item of groupItems) {
      result.push({ ...item, _altRow: dataRowIndex++ % 2 === 1 })
    }
    const totalRow = { _isGroupTotal: true, _groupValue: groupVal }
    for (const key of numericKeys.value) {
      totalRow[key] = groupItems.reduce((sum, item) => sum + (Number(item[key]) || 0), 0)
    }
    result.push(totalRow)
  }
  return result
})

// When groupBy is active, exclude the 'item' slot from passthrough (we handle it above)
const passedSlots = computed(() => {
  if (!groupByKey.value) return slots
  return Object.fromEntries(Object.entries(slots).filter(([name]) => name !== 'item'))
})

function handleExportCsv() {
  const keys = props.headers.map((h) => h.key)
  exportCsv(keys, props.items, props.csvFilename)
}
</script>

<style scoped>
/* Alternating rows — non-groupBy case (v-data-table renders its own tbody) */
:deep(tbody tr:nth-child(even):not(.group-total-row)) td {
  background-color: rgba(var(--v-theme-on-surface), 0.04) !important;
}

/* Alternating rows — groupBy case (we render tr ourselves) */
.alt-row td {
  background-color: rgba(var(--v-theme-on-surface), 0.04) !important;
}

.group-total-row td {
  border-top: 2px solid rgba(var(--v-theme-on-surface), 0.15) !important;
  background-color: rgba(var(--v-theme-on-surface), 0.05) !important;
}
</style>
