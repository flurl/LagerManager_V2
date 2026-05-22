import { reactive, ref } from 'vue'
import api from '../api'

export function useStockCountImport(onSuccess) {
  const importing = ref(false)
  const importMode = ref(null)
  const importDate = ref(null)
  const conflictDialog = ref(false)
  const conflictInfo = ref(null)
  const snackbar = reactive({ show: false, message: '', color: 'success' })

  function showSnack(message, color = 'success') {
    snackbar.message = message
    snackbar.color = color
    snackbar.show = true
  }

  function buildSuccessMsg(data) {
    let msg = `${data.created} erstellt, ${data.updated} aktualisiert.`
    if (data.not_found?.length) msg += ` ${data.not_found.length} Artikel nicht gefunden.`
    if (data.warnings?.length) msg += ` Warnung: ${data.warnings.join('; ')}`
    return msg
  }

  async function importCumulative(dateStr, force = false) {
    importing.value = true
    importMode.value = 'cumulative'
    importDate.value = dateStr
    try {
      const payload = { cumulative_date: dateStr, ...(force ? { force: true } : {}) }
      const res = await api.post('/stock-count/entries/import/', payload)
      showSnack(buildSuccessMsg(res.data), res.data.warnings?.length ? 'warning' : 'success')
      onSuccess?.()
    } catch (err) {
      if (err.response?.status === 409) {
        conflictInfo.value = err.response.data
        conflictDialog.value = true
        return
      }
      showSnack('Import fehlgeschlagen.', 'error')
    } finally {
      importing.value = false
    }
  }

  async function forceImport() {
    conflictDialog.value = false
    await importCumulative(importDate.value, true)
  }

  return {
    importing,
    conflictDialog,
    conflictInfo,
    snackbar,
    importCumulative,
    forceImport,
  }
}
