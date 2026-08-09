const SAFE_FORMULA_RE = /^[0-9+\-*/().,\s]+$/
// Two separators inside one number ("1.234,56" / "1.2.3") — ambiguous, see utils/number.js.
const AMBIGUOUS_NUMBER_RE = /\d*[.,]\d*[.,]/

// Evaluates a basic arithmetic expression (+, -, *, /, parentheses). Throws on invalid input.
// Both '.' and ',' are accepted as decimal separators; every comma is rewritten to a dot
// before evaluation, so a comma can never reach the evaluator as a sequence operator.
export function evaluateFormula(expr) {
  if (!SAFE_FORMULA_RE.test(expr)) throw new Error('Formula contains invalid characters')
  if (AMBIGUOUS_NUMBER_RE.test(expr)) throw new Error('Number has more than one decimal separator')
  const normalised = expr.replace(/,/g, '.')
  // eslint-disable-next-line no-new-func
  const result = new Function(`"use strict"; return (${normalised})`)()
  if (typeof result !== 'number' || !Number.isFinite(result)) throw new Error('Invalid formula result')
  return result
}
