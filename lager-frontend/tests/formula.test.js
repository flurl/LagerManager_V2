import assert from 'node:assert/strict'
import test, { describe } from 'node:test'

import { evaluateFormula } from '../src/utils/formula.js'

describe('evaluateFormula', () => {
  test('evaluates basic arithmetic', () => {
    assert.equal(evaluateFormula('1+2'), 3)
    assert.equal(evaluateFormula('2*3'), 6)
    assert.equal(evaluateFormula('(1+2)*3'), 9)
    assert.equal(evaluateFormula('10 / 4'), 2.5)
  })

  test('accepts a dot as decimal separator', () => {
    assert.equal(evaluateFormula('1.5*2'), 3)
  })

  test('accepts a comma as decimal separator', () => {
    assert.equal(evaluateFormula('1,5*2'), 3)
    assert.equal(evaluateFormula('0,25+0,25'), 0.5)
  })

  test('handles several comma numbers in one expression', () => {
    assert.equal(evaluateFormula('1,5*2,5'), 3.75)
    assert.equal(evaluateFormula('(1,5+2,5)*2'), 8)
  })

  test('never treats a comma as a sequence operator', () => {
    // '1,5' must be 1.5 — the JS comma operator would yield 5.
    assert.equal(evaluateFormula('1,5'), 1.5)
    assert.equal(evaluateFormula('(1,5)'), 1.5)
  })

  test('rejects a number with two separators', () => {
    assert.throws(() => evaluateFormula('1.234,56'))
    assert.throws(() => evaluateFormula('1,234.56*2'))
    assert.throws(() => evaluateFormula('1.2.3'))
  })

  test('rejects anything that is not arithmetic', () => {
    assert.throws(() => evaluateFormula('alert(1)'))
    assert.throws(() => evaluateFormula('1+'))
    assert.throws(() => evaluateFormula(''))
  })

  test('rejects non-finite results', () => {
    assert.throws(() => evaluateFormula('1/0'))
  })
})
