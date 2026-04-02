import { GeminiProvider } from './providers/GeminiProvider.js'
import geminiIcon from '../assets/gemini-icon.svg'

/**
 * All registered AI providers.
 * Each entry defines the display label, imgSrc (local asset path), and a factory
 * that receives the Django Constance config object and returns an AiProvider instance.
 */
export const AI_PROVIDERS = [
  {
    id: 'gemini',
    label: 'Gemini',
    imgSrc: geminiIcon,
    factory: (config) => new GeminiProvider(config.GEMINI_API_KEY?.value ?? ''),
  },
]

/**
 * Create an AiProvider by id.
 *
 * @param {string} providerId
 * @param {Record<string, { value: any }>} config - The config object from /api/config/
 * @returns {import('./AiProvider.js').AiProvider}
 */
export function createProvider(providerId, config) {
  const entry = AI_PROVIDERS.find((p) => p.id === providerId)
  if (!entry) throw new Error(`Unbekannter AI-Provider: "${providerId}"`)
  return entry.factory(config)
}
