import { AiProvider } from '../AiProvider.js'

const MODEL = 'gemini-2.5-flash'
const CONFIG = { thinkingConfig: { thinkingBudget: -1 }, responseMimeType: 'application/json' }

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

export class GeminiProvider extends AiProvider {
  constructor(apiKey) {
    super()
    if (!apiKey) throw new Error('Kein Gemini API Key konfiguriert (Django Admin → Constance)')
    this.apiKey = apiKey
  }

  async generateJson({ attachmentUrls, prompt }) {
    const { GoogleGenAI } = await import('@google/genai')
    const ai = new GoogleGenAI({ apiKey: this.apiKey })

    const parts = []

    for (const url of attachmentUrls) {
      const fileRes = await fetch(url)
      const blob = await fileRes.blob()
      const base64 = await blobToBase64(blob)
      const mimeType = blob.type || mimeTypeFromUrl(url)
      parts.push({ inlineData: { data: base64, mimeType } })
    }

    parts.push({ text: prompt })

    const contents = [{ role: 'user', parts }]

    console.log('Gemini API call — model:', MODEL, 'config:', CONFIG, 'contents:', contents)

    const response = await ai.models.generateContentStream({ model: MODEL, config: CONFIG, contents })

    let result = ''
    for await (const chunk of response) {
      console.log('Gemini chunk:', chunk.text)
      result += chunk.text ?? ''
    }

    return result
  }
}
