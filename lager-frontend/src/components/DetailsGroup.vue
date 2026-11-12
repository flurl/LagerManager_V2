<template>
  <!-- A selection field (customer or address dropdown) framed together with its
       collapsible details, so both read as one unit. The toggle strip says
       outright that the details can be expanded and edited. -->
  <v-sheet border rounded="lg" class="details-group mb-3">
    <div class="pa-3 pb-1">
      <slot name="field" />
    </div>

    <template v-if="hasDetails">
      <v-divider />
      <div class="details-toggle d-flex align-center px-3 py-2" role="button" tabindex="0"
        :aria-expanded="open" @click="open = !open" @keydown.enter.prevent="open = !open"
        @keydown.space.prevent="open = !open">
        <v-icon size="small" class="mr-2 text-medium-emphasis">{{ icon }}</v-icon>
        <span class="text-body-2 font-weight-medium">{{ title }}</span>
        <v-spacer />
        <span class="text-caption text-medium-emphasis mr-1">
          {{ open ? 'einklappen' : (editable ? 'anzeigen & bearbeiten' : 'anzeigen') }}
        </span>
        <v-icon size="small">{{ open ? 'mdi-chevron-up' : 'mdi-chevron-down' }}</v-icon>
      </div>
      <v-expand-transition>
        <div v-if="open" class="details-body px-3 pb-3 pt-1 text-body-2">
          <slot />
          <div v-if="editable" class="d-flex justify-end mt-2">
            <v-btn size="small" variant="tonal" prepend-icon="mdi-pencil" @click="$emit('edit')">
              {{ editLabel }}
            </v-btn>
          </div>
        </div>
      </v-expand-transition>
    </template>
  </v-sheet>
</template>

<script setup>
import { ref, watch } from 'vue'

const props = defineProps({
  /** Heading of the toggle strip, e.g. "Kundendetails". */
  title: { type: String, required: true },
  icon: { type: String, default: 'mdi-information-outline' },
  /** Label of the edit button shown inside the expanded details. */
  editLabel: { type: String, default: 'Bearbeiten' },
  /** Whether the details can be edited (documents that can still be changed). */
  editable: { type: Boolean, default: true },
  /** Whether there is a selection whose details can be shown. */
  hasDetails: { type: Boolean, default: false },
  /** Collapse whenever this changes, i.e. when another record is selected. */
  resetKey: { type: [String, Number], default: null },
})
defineEmits(['edit'])

const open = ref(false)

watch(() => props.resetKey, () => { open.value = false })
</script>

<style scoped>
.details-toggle {
  cursor: pointer;
  user-select: none;
  transition: background-color 0.15s;
}
.details-toggle:hover,
.details-toggle:focus-visible {
  background-color: rgba(var(--v-theme-on-surface), 0.06);
  outline: none;
}
.details-body {
  background-color: rgba(var(--v-theme-on-surface), 0.03);
}
</style>
