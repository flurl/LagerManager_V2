<template>
  <v-dialog :model-value="modelValue" @update:model-value="emit('update:modelValue', $event)" max-width="860" persistent>
    <v-card>
      <v-card-title class="d-flex align-center pa-4">
        <v-icon class="mr-2">mdi-import</v-icon>
        Positionen importieren
        <v-spacer />
        <v-btn icon @click="emit('update:modelValue', false)"><v-icon>mdi-close</v-icon></v-btn>
      </v-card-title>

      <!-- Step 1: JSON input -->
      <v-card-text v-if="importStep === 'input'">
        <AttachmentGallery
          ref="galleryRef"
          :movement-id="movementId"
          :preloaded-attachments="!movementId ? pendingAttachments : []"
          selectable
          hide-upload
          v-model="selectedAttachmentIds"
          class="mb-3"
        />

        <v-row dense align="start">
          <v-col>
            <v-textarea v-model="importJson" label="JSON einfügen" rows="12" auto-grow
              :error-messages="importError" hide-details="auto" />
          </v-col>
          <v-col cols="auto" class="pt-2 d-flex flex-column gap-1">
            <v-btn
              v-for="p in AI_PROVIDERS"
              :key="p.id"
              icon
              :title="`Von ${p.label} laden`"
              :loading="apiLoading && selectedProviderId === p.id"
              :disabled="apiLoading && selectedProviderId !== p.id"
              :variant="selectedProviderId === p.id ? 'tonal' : 'text'"
              @click="selectedProviderId = p.id; callAiProvider()"
            >
              <img :src="p.imgSrc" :alt="p.label" width="20" height="20" />
            </v-btn>
          </v-col>
        </v-row>
      </v-card-text>

      <!-- Step 2: Preview -->
      <v-card-text v-else>
        <v-table density="compact">
          <thead>
            <tr>
              <th style="width: 40px"></th>
              <th>Name</th>
              <th>Artikel</th>
              <th>Menge</th>
              <th>EK-Preis</th>
              <th>MwSt %</th>
              <th class="text-right">Netto</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, idx) in previewLines" :key="idx"
              :class="!row.matched ? 'text-medium-emphasis' : ''">
              <td>
                <v-checkbox v-model="row.selected" hide-details density="compact" />
              </td>
              <td>{{ row.name }}</td>
              <td>
                <v-autocomplete
                  v-model="row.article"
                  :items="warehouseArticles"
                  item-title="article_name"
                  item-value="article"
                  density="compact"
                  hide-details
                  style="min-width: 180px"
                  :prepend-inner-icon="!row.article ? 'mdi-alert' : undefined"
                  :prepend-inner-icon-color="!row.article ? 'warning' : undefined"
                  clearable
                  @update:model-value="val => {
                    const wa = warehouseArticles.find(w => w.article === val)
                    row.articleName = wa?.article_name ?? null
                    row.matched = val != null
                    if (val != null) row.selected = true
                  }"
                />
              </td>
              <td>{{ row.quantity }}</td>
              <td>{{ row.unit_price }}</td>
              <td>{{ row.taxPercent }}</td>
              <td class="text-right">{{ (row.quantity * row.unit_price).toFixed(2) }}</td>
            </tr>
          </tbody>
        </v-table>
      </v-card-text>

      <v-card-actions>
        <v-spacer />
        <v-btn @click="emit('update:modelValue', false)">Abbrechen</v-btn>
        <v-btn v-if="importStep === 'preview'" @click="importStep = 'input'">Zurück</v-btn>
        <v-btn v-if="importStep === 'input'" color="primary" @click="parseImportJson">Vorschau</v-btn>
        <v-btn v-else color="primary" @click="confirmImport">Übernehmen</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup>
import { ref, watch } from 'vue'
import api from '../api'
import AttachmentGallery from './AttachmentGallery.vue'
import { AI_PROVIDERS, createProvider } from '../ai/index.js'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  pendingAttachments: { type: Array, default: () => [] },
  warehouseArticles: { type: Array, default: () => [] },
  taxRates: { type: Array, default: () => [] },
  partnerId: { type: Number, default: null },
  movementId: { type: Number, default: null },
  config: { type: Object, default: () => ({}) },
})

const emit = defineEmits(['update:modelValue', 'confirm'])

const importStep = ref('input')
const importJson = ref('')
const importError = ref('')
const previewLines = ref([])
const selectedAttachmentIds = ref([])
const galleryRef = ref(null)
const apiLoading = ref(false)
const selectedProviderId = ref(AI_PROVIDERS[0].id)

watch(() => props.modelValue, (val) => {
  if (val) {
    importStep.value = 'input'
    importJson.value = ''
    importError.value = ''
    previewLines.value = []
    selectedAttachmentIds.value = []
  }
})

function buildArticleMarkdownTable() {
  const rows = props.warehouseArticles
    .filter((wa) => wa.source_article_id != null)
    .map((wa) => ` ${wa.source_article_id} | ${wa.article_name}`)
  return ' artikel_id |    artikel_bezeichnung\n------------+----------------------------\n' + rows.join('\n')
}

function parseImportJson() {
  importError.value = ''
  let data
  try {
    data = JSON.parse(importJson.value)
  } catch {
    importError.value = 'Ungültiges JSON'
    return
  }
  if (!Array.isArray(data?.articles)) {
    importError.value = 'JSON muss ein "articles"-Array enthalten'
    return
  }
  previewLines.value = data.articles.map((a) => {
    const wa = a.ID != null ? props.warehouseArticles.find((w) => w.source_article_id === a.ID) : null
    const tr = props.taxRates.find((t) => Number(t.percent) === a.tax)
      ?? props.taxRates.find((t) => t.id === props.config?.DEFAULT_TAX_RATE_ID?.value)
    const net = (a.total_price ?? 0) - (a.discount ?? 0) + (a.beer_tax ?? 0)
    const unit_price = a.quantity ? +(net / a.quantity).toFixed(4) : 0
    return {
      name: a.Name,
      quantity: a.quantity,
      unit_price,
      taxPercent: a.tax,
      tax_rate: tr?.id ?? null,
      article: wa?.article ?? null,
      articleName: wa?.article_name ?? null,
      matched: wa != null,
      selected: wa != null,
    }
  })
  importStep.value = 'preview'
}

function confirmImport() {
  const lines = previewLines.value
    .filter((row) => row.selected)
    .map((row) => ({
      article: row.article,
      quantity: row.quantity,
      unit_price: row.unit_price,
      tax_rate: row.tax_rate,
    }))
  emit('confirm', lines)
  emit('update:modelValue', false)
}

async function callAiProvider() {
  importError.value = ''
  if (!props.partnerId) {
    importError.value = 'Bitte zuerst einen Partner auswählen'
    return
  }

  apiLoading.value = true
  try {
    const partnerRes = await api.get(`/partners/${props.partnerId}/`)
    const partner = partnerRes.data
    const instrObj = partner.ai_instructions?.find((i) => i.provider === selectedProviderId.value)
    if (!instrObj?.instructions) {
      importError.value = `Dieser Partner hat keine Anweisungen für ${selectedProviderId.value} konfiguriert`
      return
    }

    const prompt = instrObj.instructions.replace('%%article_table%%', buildArticleMarkdownTable())

    const attachmentUrls = []
    const blobUrls = []
    if (selectedAttachmentIds.value.length) {
      const providerEntry = AI_PROVIDERS.find((p) => p.id === selectedProviderId.value)
      if (providerEntry?.requiresMergedPdf) {
        const mergedRes = await api.get('/attachments/merged_pdf/', {
          responseType: 'blob',
          params: { attachment_id: selectedAttachmentIds.value },
          paramsSerializer: { indexes: null },
        })
        const blobUrl = URL.createObjectURL(mergedRes.data)
        blobUrls.push(blobUrl)
        attachmentUrls.push(blobUrl)
      } else {
        const allAttachments = galleryRef.value?.attachments ?? []
        const selected = allAttachments.filter((a) => selectedAttachmentIds.value.includes(a.id))
        attachmentUrls.push(...selected.map((a) => a.file))
      }
    }

    const provider = createProvider(selectedProviderId.value, props.config)
    try {
      importJson.value = await provider.generateJson({ attachmentUrls, prompt })
    } finally {
      blobUrls.forEach((u) => URL.revokeObjectURL(u))
    }
  } catch (err) {
    importError.value = err.message ?? 'Fehler beim AI-Aufruf'
    console.error('AI provider error:', err)
  } finally {
    apiLoading.value = false
  }
}
</script>
