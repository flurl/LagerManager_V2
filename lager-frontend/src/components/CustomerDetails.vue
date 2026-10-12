<template>
  <!-- Collapsible read-only summary of a document's customer, the counterpart to
       the "Adressdetails" block in the offer and invoice dialogs. -->
  <div class="mb-2">
    <div class="d-flex align-center gap-1">
      <v-btn variant="text" size="x-small" density="compact"
        :append-icon="open ? 'mdi-chevron-up' : 'mdi-chevron-down'"
        @click="open = !open">
        Kundendetails
      </v-btn>
      <v-tooltip v-if="open && editable" text="Kunde bearbeiten">
        <template #activator="{ props: tip }">
          <v-btn v-bind="tip" icon size="x-small" variant="text" @click="$emit('edit')">
            <v-icon size="small">mdi-pencil</v-icon>
          </v-btn>
        </template>
      </v-tooltip>
    </div>
    <v-expand-transition>
      <v-card v-if="open" variant="tonal" class="pa-3 mt-1 text-body-2">
        <v-row dense>
          <v-col v-if="customer.customer_number" cols="2">
            <div class="text-caption text-medium-emphasis">Kundennummer</div>
            <div>{{ customer.customer_number }}</div>
          </v-col>
          <v-col cols="5">
            <div class="text-caption text-medium-emphasis">Name / Firma</div>
            <div>
              {{ customer.name }}
              <v-chip v-if="!customer.is_active" size="x-small" class="ml-1">Inaktiv</v-chip>
            </div>
          </v-col>
          <v-col v-if="customer.uid" cols="3">
            <div class="text-caption text-medium-emphasis">UID-Nummer</div>
            <div>{{ customer.uid }}</div>
          </v-col>
        </v-row>
        <v-row v-if="customer.email || customer.telefon || customer.notes" dense class="mt-1">
          <v-col v-if="customer.email" cols="4">
            <div class="text-caption text-medium-emphasis">E-Mail</div>
            <div>{{ customer.email }}</div>
          </v-col>
          <v-col v-if="customer.telefon" cols="3">
            <div class="text-caption text-medium-emphasis">Telefon</div>
            <div>{{ customer.telefon }}</div>
          </v-col>
          <v-col v-if="customer.notes" cols="12">
            <div class="text-caption text-medium-emphasis">Notizen</div>
            <div style="white-space: pre-line">{{ customer.notes }}</div>
          </v-col>
        </v-row>
      </v-card>
    </v-expand-transition>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'

const props = defineProps({
  customer: { type: Object, required: true },
  /** Show the edit pencil (documents that can still be changed). */
  editable: { type: Boolean, default: true },
})
defineEmits(['edit'])

const open = ref(false)

// Collapse when the document switches to another customer, like the address block.
watch(() => props.customer.id, () => { open.value = false })
</script>
