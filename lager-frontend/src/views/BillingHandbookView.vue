<template>
  <v-container class="handbook-container">
    <HandbookContent ref="contentRef" :scroll-offset="80" update-url />
  </v-container>
</template>

<script setup>
import { nextTick, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import HandbookContent from '../components/HandbookContent.vue'

const route = useRoute()
const contentRef = ref(null)

onMounted(async () => {
  await nextTick()
  if (route.hash) contentRef.value?.scrollToAnchor(route.hash.slice(1), 'auto')
})
</script>

<style scoped>
.handbook-container {
  max-width: 960px;
}
</style>
