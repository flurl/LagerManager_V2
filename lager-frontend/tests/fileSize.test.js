import assert from 'node:assert/strict'
import test, { describe } from 'node:test'

import { formatBytes, totalBytes } from '../src/utils/fileSize.js'

describe('formatBytes', () => {
  test('shows plain bytes without decimals', () => {
    assert.equal(formatBytes(0), '0 B')
    assert.equal(formatBytes(512), '512 B')
    assert.equal(formatBytes(1023), '1023 B')
  })

  test('steps up at 1024 and uses the locale decimal separator', () => {
    assert.equal(formatBytes(1024), '1,0 KB')
    assert.equal(formatBytes(1536), '1,5 KB')
    assert.equal(formatBytes(1024 * 1024), '1,0 MB')
    assert.equal(formatBytes(2.5 * 1024 * 1024), '2,5 MB')
    assert.equal(formatBytes(1024 ** 3), '1,0 GB')
  })

  test('honours an explicit locale', () => {
    assert.equal(formatBytes(1536, 'en-GB'), '1.5 KB')
  })

  test('stops at the largest known unit', () => {
    assert.equal(formatBytes(1024 ** 4), '1,0 TB')
    // Beyond TB the number just keeps growing (with locale grouping).
    assert.match(formatBytes(1024 ** 5), /TB$/)
  })

  test('never throws on junk input', () => {
    assert.equal(formatBytes(null), '0 B')
    assert.equal(formatBytes(undefined), '0 B')
    assert.equal(formatBytes('nope'), '0 B')
    assert.equal(formatBytes(-5), '0 B')
  })
})

describe('totalBytes', () => {
  test('sums size_bytes and ignores missing values', () => {
    assert.equal(totalBytes([{ size_bytes: 100 }, { size_bytes: 24 }]), 124)
    assert.equal(totalBytes([{ size_bytes: 100 }, {}, null]), 100)
  })

  test('treats an empty or missing list as zero', () => {
    assert.equal(totalBytes([]), 0)
    assert.equal(totalBytes(undefined), 0)
  })
})
