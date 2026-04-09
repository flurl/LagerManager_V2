import { defineStore } from 'pinia'
import api from '../api'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem('token') || null,
    refreshToken: localStorage.getItem('refreshToken') || null,
    user: null,
    permissions: /** @type {string[]} */ ([]),
    preferences: /** @type {{ language: string, period_colors: Record<string, string> }} */ (
      { language: 'de', period_colors: {} }
    ),
    ready: false,
  }),
  getters: {
    isAuthenticated: (state) => !!state.token,
    hasPermission: (state) => (/** @type {string} */ perm) => state.permissions.includes(perm),
  },
  actions: {
    async login(username, password) {
      const { default: axios } = await import('axios')
      const res = await axios.post('/api/token/', { username, password })
      this.token = res.data.access
      this.refreshToken = res.data.refresh
      localStorage.setItem('token', this.token)
      localStorage.setItem('refreshToken', this.refreshToken)
      await this.fetchMe()
    },
    async fetchMe() {
      const res = await api.get('/me/')
      this.user = res.data
      this.permissions = res.data.permissions
      this.preferences = res.data.preferences
      this.ready = true
    },
    async updatePreferences(prefs) {
      const res = await api.patch('/me/', prefs)
      this.preferences = res.data
    },
    async logout() {
      this.token = null
      this.refreshToken = null
      this.user = null
      this.permissions = []
      this.preferences = { language: 'de', period_colors: {} }
      this.ready = false
      localStorage.removeItem('token')
      localStorage.removeItem('refreshToken')
    },
  },
})
