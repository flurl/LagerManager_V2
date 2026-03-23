import { defineStore } from 'pinia'
import api from '../api'

export const usePeriodStore = defineStore('period', {
  state: () => ({
    periods: [],
    currentPeriodId: null,
  }),
  getters: {
    currentPeriod: (state) =>
      state.periods.find((p) => p.id === state.currentPeriodId) || null,
  },
  actions: {
    async fetchPeriods() {
      const res = await api.get('/periods/')
      this.periods = res.data.results || res.data
      if (!this.currentPeriodId && this.periods.length) {
        this.currentPeriodId = this.periods[0].id
      }
    },
    setCurrentPeriod(id) {
      this.currentPeriodId = id
    },
    async createPeriod(data) {
      const res = await api.post('/periods/', data)
      await this.fetchPeriods()
      this.currentPeriodId = res.data.id
    },
  },
})
