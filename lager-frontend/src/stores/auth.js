import { defineStore } from 'pinia'
import axios from 'axios'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem('token') || null,
    refreshToken: localStorage.getItem('refreshToken') || null,
  }),
  getters: {
    isAuthenticated: (state) => !!state.token,
  },
  actions: {
    async login(username, password) {
      const res = await axios.post('/api/token/', { username, password })
      this.token = res.data.access
      this.refreshToken = res.data.refresh
      localStorage.setItem('token', this.token)
      localStorage.setItem('refreshToken', this.refreshToken)
    },
    async logout() {
      this.token = null
      this.refreshToken = null
      localStorage.removeItem('token')
      localStorage.removeItem('refreshToken')
    },
  },
})
