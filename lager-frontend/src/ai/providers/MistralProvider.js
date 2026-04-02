import { AiProvider } from '../AiProvider.js'

const MODEL = 'mistral-ocr-latest'

const ANNOTATION_SCHEMA = {
  name: 'response_schema',
  schemaDefinition: {
    $schema: 'http://json-schema.org/draft-07/schema#',
    title: 'Mistral Document AI Response',
    description: 'Schema for Mistral Document AI response format',
    type: 'object',
    properties: {
      date_of_delivery: {
        type: 'string',
        format: 'date',
        description: 'The date of delivery in YYYY-MM-DD format',
      },
      total_sum_net: {
        type: 'number',
        minimum: 0,
        description: 'The total net sum of the order',
      },
      total_sum_gross: {
        type: 'number',
        minimum: 0,
        description: 'The total gross sum of the order',
      },
      articles: {
        type: 'array',
        items: {
          type: 'object',
          properties: {
            ID: { type: ['integer', 'null'], description: 'The unique identifier of the article, can be null' },
            Name: { type: 'string', description: 'The name of the article' },
            quantity: { type: 'integer', minimum: 0, description: 'The quantity of the article' },
            total_price: { type: 'number', minimum: 0, description: 'The total price of the article' },
            discount: { type: ['number', 'null'], minimum: 0, description: 'The discount applied to the article, can be null' },
            tax: { type: 'integer', minimum: 0, maximum: 100, description: 'The tax rate applied to the article in percent' },
          },
          required: ['Name', 'quantity', 'total_price', 'tax'],
        },
      },
    },
    required: ['date_of_delivery', 'total_sum_net', 'total_sum_gross', 'articles'],
  },
  strict: true,
}

async function blobToBase64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onloadend = () => resolve(reader.result.split(',')[1])
    reader.onerror = reject
    reader.readAsDataURL(blob)
  })
}

function mimeTypeFromUrl(url) {
  return url.toLowerCase().endsWith('.pdf') ? 'application/pdf' : 'image/jpeg'
}

export class MistralProvider extends AiProvider {
  constructor(apiKey) {
    super()
    if (!apiKey) throw new Error('Kein Mistral API Key konfiguriert (Django Admin → Constance)')
    this.apiKey = apiKey
  }

  async generateJson({ attachmentUrls, prompt }) {
    const { Mistral } = await import('@mistralai/mistralai')
    const client = new Mistral({ apiKey: this.apiKey })

    if (attachmentUrls.length === 0) throw new Error('Keine Anhänge für Mistral OCR vorhanden')

    const fileRes = await fetch(attachmentUrls[0])
    const blob = await fileRes.blob()
    const base64 = await blobToBase64(blob)
    const mimeType = blob.type || mimeTypeFromUrl(attachmentUrls[0])
    const documentUrl = `data:${mimeType};base64,${base64}`

    console.log('Mistral OCR call — model:', MODEL, 'document size:', documentUrl.length)

    const response = await client.ocr.process({
      model: MODEL,
      document: { type: 'document_url', documentUrl },
      includeImageBase64: false,
      documentAnnotationFormat: { type: 'json_schema', jsonSchema: ANNOTATION_SCHEMA },
      documentAnnotationPrompt: prompt,
    })

    const result = response.documentAnnotation ?? ''
    console.log('Mistral response:', result)
    return typeof result === 'string' ? result : JSON.stringify(result)
  }
}
