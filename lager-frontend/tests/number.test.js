import assert from 'node:assert/strict'
import test, { describe } from 'node:test'

import {
  NumberFormatError,
  decimalSeparator,
  formatNumber,
  formatNumberRaw,
  localeFromLanguage,
  parseNumber,
} from '../src/utils/number.js'

describe('parseNumber', () => {
  test('accepts a dot as decimal separator', () => {
    assert.equal(parseNumber('1.5'), 1.5)
    assert.equal(parseNumber('0.25'), 0.25)
  })

  test('accepts a comma as decimal separator', () => {
    assert.equal(parseNumber('1,5'), 1.5)
    assert.equal(parseNumber('0,25'), 0.25)
  })

  test('accepts integers and signs', () => {
    assert.equal(parseNumber('42'), 42)
    assert.equal(parseNumber('-3,5'), -3.5)
    assert.equal(parseNumber('+3.5'), 3.5)
  })

  test('accepts partial input produced while typing', () => {
    assert.equal(parseNumber('1,'), 1)
    assert.equal(parseNumber(',5'), 0.5)
    assert.equal(parseNumber('.5'), 0.5)
  })

  test('trims surrounding whitespace', () => {
    assert.equal(parseNumber('  1,5  '), 1.5)
  })

  test('returns null for empty input', () => {
    assert.equal(parseNumber(''), null)
    assert.equal(parseNumber('   '), null)
    assert.equal(parseNumber(null), null)
    assert.equal(parseNumber(undefined), null)
  })

  test('a single separator is always the decimal separator, never a thousands separator', () => {
    assert.equal(parseNumber('1,000'), 1)
    assert.equal(parseNumber('1.000'), 1)
  })

  test('rejects a second separator instead of guessing', () => {
    assert.throws(() => parseNumber('1.234,56'), NumberFormatError)
    assert.throws(() => parseNumber('1,234.56'), NumberFormatError)
    assert.throws(() => parseNumber('1.2.3'), NumberFormatError)
  })

  test('rejects malformed input rather than truncating it', () => {
    assert.throws(() => parseNumber('1,5abc'), NumberFormatError)
    assert.throws(() => parseNumber('abc'), NumberFormatError)
    assert.throws(() => parseNumber('1 000'), NumberFormatError)
    assert.throws(() => parseNumber('--1'), NumberFormatError)
    assert.throws(() => parseNumber('1e3'), NumberFormatError)
  })
})

describe('formatNumber', () => {
  test('uses the locale decimal separator and pads to the given decimals', () => {
    assert.equal(formatNumber(1.5, 2, 'de-AT'), '1,50')
    assert.equal(formatNumber(1.5, 2, 'en-GB'), '1.50')
    assert.equal(formatNumber(1.567, 2, 'de-AT'), '1,57')
    assert.equal(formatNumber(3, 0, 'de-AT'), '3')
  })

  test('never emits a thousands separator', () => {
    assert.equal(formatNumber(1234567.5, 2, 'de-AT'), '1234567,50')
    assert.equal(formatNumber(1234567.5, 2, 'en-GB'), '1234567.50')
  })

  test('accepts numeric strings and rejects non-numbers', () => {
    assert.equal(formatNumber('1.5', 2, 'de-AT'), '1,50')
    assert.equal(formatNumber(null, 2, 'de-AT'), '')
    assert.equal(formatNumber(undefined, 2, 'de-AT'), '')
    assert.equal(formatNumber(NaN, 2, 'de-AT'), '')
  })
})

describe('formatNumberRaw', () => {
  test('keeps the value precision and localises the separator', () => {
    assert.equal(formatNumberRaw(1.5, 'de-AT'), '1,5')
    assert.equal(formatNumberRaw(1.5, 'en-GB'), '1.5')
    assert.equal(formatNumberRaw(3, 'de-AT'), '3')
  })

  test('is empty for missing values', () => {
    assert.equal(formatNumberRaw(null, 'de-AT'), '')
    assert.equal(formatNumberRaw(undefined, 'de-AT'), '')
  })

  test('round-trips through parseNumber', () => {
    for (const value of [0, 1.5, -3.25, 1234.5]) {
      assert.equal(parseNumber(formatNumberRaw(value, 'de-AT')), value)
      assert.equal(parseNumber(formatNumberRaw(value, 'en-GB')), value)
    }
  })
})

describe('locale selection', () => {
  test('maps the language preference to a locale', () => {
    assert.equal(localeFromLanguage('de'), 'de-AT')
    assert.equal(localeFromLanguage('en'), 'en-GB')
  })

  test('falls back to de-AT for unknown or missing languages', () => {
    assert.equal(localeFromLanguage('fr'), 'de-AT')
    assert.equal(localeFromLanguage(undefined), 'de-AT')
  })

  test('reports the separator of a locale', () => {
    assert.equal(decimalSeparator('de-AT'), ',')
    assert.equal(decimalSeparator('en-GB'), '.')
  })
})
