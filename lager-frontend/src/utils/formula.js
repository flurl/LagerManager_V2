const SAFE_FORMULA_RE = /^[0-9+\-*/().\s]+$/

// Evaluates a basic arithmetic expression (+, -, *, /, parentheses). Throws on invalid input.
export function evaluateFormula(expr) {
  if (!SAFE_FORMULA_RE.test(expr)) throw new Error('Formula contains invalid characters')
  // eslint-disable-next-line no-new-func
  const result = new Function(`"use strict"; return (${expr})`)()
  if (typeof result !== 'number' || !Number.isFinite(result)) throw new Error('Invalid formula result')
  return result
}
