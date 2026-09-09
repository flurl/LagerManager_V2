import assert from 'node:assert/strict'
import test, { describe } from 'node:test'

import { isVersionMismatch } from '../src/utils/version.js'

describe('isVersionMismatch', () => {
  test('reports no mismatch for identical hashes', () => {
    assert.equal(isVersionMismatch('46fd397', '46fd397'), false)
  })

  test('reports a mismatch for different hashes', () => {
    assert.equal(isVersionMismatch('46fd397', '50a5b8b'), true)
  })

  test('treats differently abbreviated hashes of the same commit as equal', () => {
    assert.equal(isVersionMismatch('46fd397', '46fd3971a2b'), false)
    assert.equal(isVersionMismatch('46fd3971a2b', '46fd397'), false)
  })

  test('ignores case and surrounding whitespace', () => {
    assert.equal(isVersionMismatch('46FD397', ' 46fd397\n'), false)
  })

  test('never nags when a hash is unknown or missing', () => {
    assert.equal(isVersionMismatch('unknown', '46fd397'), false)
    assert.equal(isVersionMismatch('46fd397', 'unknown'), false)
    assert.equal(isVersionMismatch('', '46fd397'), false)
    assert.equal(isVersionMismatch('46fd397', ''), false)
    assert.equal(isVersionMismatch(null, undefined), false)
  })
})
