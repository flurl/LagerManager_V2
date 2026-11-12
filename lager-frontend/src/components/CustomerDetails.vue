<template>
  <!-- Read-only summary of a document's customer, shown inside a DetailsGroup. -->
  <v-row dense>
    <v-col v-if="customer.customer_number" cols="4" md="3">
      <div class="text-caption text-medium-emphasis">Kundennummer</div>
      <div>{{ customer.customer_number }}</div>
    </v-col>
    <v-col cols="8" md="5">
      <div class="text-caption text-medium-emphasis">Name / Firma</div>
      <div>
        {{ customer.name }}
        <v-chip v-if="!customer.is_active" size="x-small" class="ml-1">Inaktiv</v-chip>
      </div>
    </v-col>
    <v-col v-if="customer.uid" cols="6" md="4">
      <div class="text-caption text-medium-emphasis">UID-Nummer</div>
      <div>{{ customer.uid }}</div>
    </v-col>
    <v-col v-if="customer.email" cols="6" md="5">
      <div class="text-caption text-medium-emphasis">E-Mail</div>
      <div class="text-break">{{ customer.email }}</div>
    </v-col>
    <v-col v-if="customer.telefon" cols="6" md="4">
      <div class="text-caption text-medium-emphasis">Telefon</div>
      <div>{{ customer.telefon }}</div>
    </v-col>
    <v-col v-if="customer.notes" cols="12">
      <div class="text-caption text-medium-emphasis">Notizen</div>
      <div style="white-space: pre-line">{{ customer.notes }}</div>
    </v-col>
  </v-row>
</template>

<script setup>
defineProps({
  customer: { type: Object, required: true },
})
</script>
