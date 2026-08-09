// Parsing and formatting of user-entered numbers.
//
// Input is separator-agnostic: both '.' and ',' are accepted as the decimal
// separator, no matter which one the display locale uses — a numpad user should
// not have to think about it. Thousands separators are NOT supported: every
// separator is read as a decimal separator, so a second one makes the value
// ambiguous ("1.234,56") and is rejected instead of silently truncated.
//
// Display formatting follows the user's locale, derived from the `language`
// preference (see UserPreferences on the backend).

const LOCALE_BY_LANGUAGE = {
  de: 'de-AT',
  en: 'en-GB',
}

export const DEFAULT_LOCALE = 'de-AT'

/** Raised for input that is not a well-formed number. `message` is user-facing (German). */
export class NumberFormatError extends Error {}

// Optional sign, then digits with at most one separator on either side of it.
const NUMBER_RE = /^[+-]?(\d+([.,]\d*)?|[.,]\d+)$/

/** Maps a UserPreferences language code to the locale used for number display. */
export function localeFromLanguage(language) {
  return LOCALE_BY_LANGUAGE[language] ?? DEFAULT_LOCALE
}

/** The decimal separator a locale uses for display, e.g. ',' for de-AT. */
export function decimalSeparator(locale = DEFAULT_LOCALE) {
  const parts = new Intl.NumberFormat(locale).formatToParts(1.1)
  return parts.find((p) => p.type === 'decimal')?.value ?? '.'
}

/**
 * Parses user input into a number.
 * Returns null for empty input; throws NumberFormatError for anything malformed.
 */
export function parseNumber(raw) {
  const trimmed = String(raw ?? '').trim()
  if (trimmed === '') return null
  const separators = trimmed.match(/[.,]/g) ?? []
  if (separators.length > 1) {
    throw new NumberFormatError('Nur ein Dezimaltrennzeichen erlaubt (kein Tausendertrennzeichen)')
  }
  if (!NUMBER_RE.test(trimmed)) throw new NumberFormatError('Keine gültige Zahl')
  const value = parseFloat(trimmed.replace(',', '.'))
  if (!Number.isFinite(value)) throw new NumberFormatError('Keine gültige Zahl')
  return value
}

/** Formats a number for display with a fixed number of decimals, without grouping. */
export function formatNumber(value, decimals = 2, locale = DEFAULT_LOCALE) {
  const num = typeof value === 'string' ? parseFloat(value) : value
  if (num === null || num === undefined || !Number.isFinite(num)) return ''
  return new Intl.NumberFormat(locale, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
    useGrouping: false,
  }).format(num)
}

/**
 * Formats a number for *editing*: the value's own precision (no padding to a
 * fixed number of decimals), with the locale's decimal separator.
 */
export function formatNumberRaw(value, locale = DEFAULT_LOCALE) {
  const num = typeof value === 'string' ? parseFloat(value) : value
  if (num === null || num === undefined || !Number.isFinite(num)) return ''
  return String(num).replace('.', decimalSeparator(locale))
}
