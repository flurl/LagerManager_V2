<template>
  <!-- Read-only summary of a document's address, shown inside a DetailsGroup. -->
  <v-row dense>
    <v-col v-if="address.anrede" cols="3" md="2">
      <div class="text-caption text-medium-emphasis">Anrede</div>
      <div>{{ address.anrede }}</div>
    </v-col>
    <v-col v-if="address.vorname" cols="4" md="3">
      <div class="text-caption text-medium-emphasis">Vorname</div>
      <div>{{ address.vorname }}</div>
    </v-col>
    <v-col v-if="address.nachname" cols="5" md="3">
      <div class="text-caption text-medium-emphasis">Nachname</div>
      <div>{{ address.nachname }}</div>
    </v-col>
    <v-col v-if="address.firma" cols="6" md="4">
      <div class="text-caption text-medium-emphasis">Firma</div>
      <div>{{ address.firma }}</div>
    </v-col>
    <v-col v-if="address.abteilung" cols="6" md="4">
      <div class="text-caption text-medium-emphasis">Abteilung</div>
      <div>{{ address.abteilung }}</div>
    </v-col>
  </v-row>
  <v-row dense class="mt-1">
    <v-col v-if="address.strasse" cols="6" md="5">
      <div class="text-caption text-medium-emphasis">Straße</div>
      <div>{{ address.strasse }}</div>
    </v-col>
    <v-col v-if="address.plz" cols="2">
      <div class="text-caption text-medium-emphasis">PLZ</div>
      <div>{{ address.plz }}</div>
    </v-col>
    <v-col v-if="address.ort" cols="4" md="5">
      <div class="text-caption text-medium-emphasis">Ort</div>
      <div>{{ address.ort }}</div>
    </v-col>
    <v-col v-if="address.telefon" cols="6" md="4">
      <div class="text-caption text-medium-emphasis">Telefon</div>
      <div>{{ address.telefon }}</div>
    </v-col>
    <v-col v-if="address.email" cols="6" md="4">
      <div class="text-caption text-medium-emphasis">E-Mail</div>
      <div class="text-break">{{ address.email }}</div>
    </v-col>
    <v-col v-if="address.uid" cols="6" md="4">
      <div class="text-caption text-medium-emphasis">UID-Nummer</div>
      <div>{{ address.uid }}</div>
    </v-col>
    <v-col v-if="address.anmerkung" cols="12">
      <div class="text-caption text-medium-emphasis">Anmerkung</div>
      <div>{{ address.anmerkung }}</div>
    </v-col>
  </v-row>
</template>

<script setup>
defineProps({
  address: { type: Object, required: true },
})
</script>
