import { defineStore } from 'pinia'
import api from '../api'

export const useAuthStore = defineStore('auth', {
  state: () => {
    const cachedUser = JSON.parse(localStorage.getItem('authUser') || 'null')
    const cachedPermissions = /** @type {string[]} */ (
      JSON.parse(localStorage.getItem('authPermissions') || 'null') || []
    )
    const cachedPreferences = /** @type {{ language: string, theme: string, period_colors: Record<string, string> }} */ (
      JSON.parse(localStorage.getItem('authPreferences') || 'null') || { language: 'de', theme: 'auto', period_colors: {} }
    )
    return {
      token: localStorage.getItem('token') || null,
      refreshToken: localStorage.getItem('refreshToken') || null,
      user: cachedUser,
      permissions: cachedPermissions,
      preferences: cachedPreferences,
      ready: !!cachedUser,
    }
  },
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
      localStorage.setItem('authUser', JSON.stringify(res.data))
      localStorage.setItem('authPermissions', JSON.stringify(res.data.permissions))
      localStorage.setItem('authPreferences', JSON.stringify(res.data.preferences))
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
      this.preferences = { language: 'de', theme: 'auto', period_colors: {} }
      this.ready = false
      localStorage.removeItem('token')
      localStorage.removeItem('refreshToken')
      localStorage.removeItem('authUser')
      localStorage.removeItem('authPermissions')
      localStorage.removeItem('authPreferences')
    },
  },
})
