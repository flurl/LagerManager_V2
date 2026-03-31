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
      :items="items"
      :loading="loading"
      :search="search"
      density="compact"
    >
      <template v-for="(_, name) in $slots" #[name]="slotProps">
        <slot :name="name" v-bind="slotProps ?? {}" />
      </template>
    </v-data-table>
  </div>
</template>

<script setup>
import { ref } from 'vue'
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
})

const search = ref('')
const { exportCsv } = useCsvExport()

function handleExportCsv() {
  const keys = props.headers.map((h) => h.key)
  exportCsv(keys, props.items, props.csvFilename)
}
</script>
