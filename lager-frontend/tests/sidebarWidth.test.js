import assert from 'node:assert/strict'
import test, { describe } from 'node:test'

import { clampSidebarWidth, SIDEBAR_DEFAULT_WIDTH, SIDEBAR_MIN_WIDTH } from '../src/utils/sidebarWidth.js'

describe('clampSidebarWidth', () => {
  // A width inside the allowed range is kept as is.
  test('keeps widths within the range', () => {
    assert.equal(clampSidebarWidth(600, 1600), 600)
  })

  // Dragging the handle all the way right must not collapse the sidebar into an unusable strip.
  test('enforces the minimum width', () => {
    assert.equal(clampSidebarWidth(100, 1600), SIDEBAR_MIN_WIDTH)
  })

  // Dragging all the way left must leave 20 % of the viewport for the main content.
  test('caps the width at 80 % of the viewport', () => {
    assert.equal(clampSidebarWidth(1500, 1000), 800)
  })

  // On viewports too narrow for both limits the minimum wins, so the sidebar stays readable.
  test('prefers the minimum on very narrow viewports', () => {
    assert.equal(clampSidebarWidth(500, 300), SIDEBAR_MIN_WIDTH)
  })

  // A missing or corrupt value from localStorage (NaN) falls back to the default width.
  test('falls back to the default for non-numeric input', () => {
    assert.equal(clampSidebarWidth(NaN, 1600), SIDEBAR_DEFAULT_WIDTH)
  })
})
