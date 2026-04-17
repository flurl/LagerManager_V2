import { ref, computed, watch } from 'vue'
import { usePeriodStore } from '../stores/period'
import api from '../api'

export function useHiddenArticles() {
  const periodStore = usePeriodStore()
  const hiddenNames = ref(new Set())
  const showHidden = ref(false)

  async function fetchHiddenStatus() {
    const periodId = periodStore.currentPeriodId
    if (!periodId) return
    const res = await api.get('/reports/article-hidden-status/', {
      params: { period_id: periodId },
    })
    hiddenNames.value = new Set(res.data.filter((a) => a.is_hidden).map((a) => a.name))
  }

  watch(() => periodStore.currentPeriodId, fetchHiddenStatus, { immediate: true })

  const hasHiddenArticles = computed(() => hiddenNames.value.size > 0)
  const hiddenCount = computed(() => hiddenNames.value.size)

  function shouldInclude(name) {
    return showHidden.value || !hiddenNames.value.has(name)
  }

  return { hasHiddenArticles, hiddenCount, showHidden, shouldInclude }
}
