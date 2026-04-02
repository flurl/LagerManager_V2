import { computed } from 'vue'

export function useLineCalculations(taxRates, lines) {
  function getTaxPercent(taxRateId) {
    const tr = taxRates.value.find((t) => t.id === taxRateId)
    return tr ? Number(tr.percent) : 0
  }

  function lineNet(line) {
    return (Number(line.quantity) * Number(line.unit_price)).toFixed(2)
  }

  function lineGross(line) {
    const net = Number(lineNet(line))
    const pct = getTaxPercent(line.tax_rate)
    return (net * (1 + pct / 100)).toFixed(2)
  }

  const totalNet = computed(() =>
    lines.value.reduce((s, l) => s + Number(lineNet(l)), 0).toFixed(2)
  )

  const totalGross = computed(() =>
    lines.value.reduce((s, l) => s + Number(lineGross(l)), 0).toFixed(2)
  )

  return { getTaxPercent, lineNet, lineGross, totalNet, totalGross }
}
