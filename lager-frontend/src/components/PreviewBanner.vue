<template>
  <!-- Preview environment (scripts/preview.sh): not production, data is a throwaway copy -->
  <v-system-bar v-if="branch" height="40" class="preview-banner justify-center">
    <v-icon size="24" class="mr-2">mdi-alert-octagon</v-icon>
    <span class="text-subtitle-1 font-weight-black">
      VORSCHAU – Branch „{{ branch }}“ – nicht die Produktivversion!
    </span>
    <span class="text-body-2 ml-3 d-none d-md-inline">
      Daten sind eine Kopie<template v-if="snapshot"> vom {{ snapshot }}</template>;
      Änderungen werden nicht übernommen, E-Mails gehen nur an den Absender.
    </span>
    <v-icon size="24" class="ml-2">mdi-alert-octagon</v-icon>
  </v-system-bar>
</template>

<script setup>
const branch = import.meta.env.VITE_PREVIEW_BRANCH ?? ''
const snapshot = import.meta.env.VITE_PREVIEW_SNAPSHOT ?? ''

if (branch && !document.title.startsWith('[VORSCHAU]')) {
  document.title = `[VORSCHAU] ${document.title}`
}
</script>

<style scoped>
.preview-banner {
  color: #fff !important;
  background: repeating-linear-gradient(
    -45deg,
    #b71c1c,
    #b71c1c 24px,
    #d32f2f 24px,
    #d32f2f 48px
  ) !important;
  opacity: 1;
}
</style>
