import { defineStore } from 'pinia'
import api from '../api'

export const useNotificationsStore = defineStore('notifications', {
  state: () => ({
    /** @type {Array<Object>} */
    items: [],
    unreadCount: 0,
    loading: false,
    /** @type {number|null} */
    pollHandle: null,
    /** @type {Function|null} */
    visibilityHandler: null,
  }),

  actions: {
    async fetchUnreadCount() {
      try {
        const res = await api.get('/notifications/unread-count/')
        this.unreadCount = res.data.count
      } catch {
        // Silently ignore — background poll, don't disrupt the user
      }
    },

    async fetchAll({ unreadOnly = false } = {}) {
      this.loading = true
      try {
        const params = unreadOnly ? { unread: 'true' } : {}
        const res = await api.get('/notifications/', { params })
        this.items = res.data.results ?? res.data
      } catch {
        // Ignore
      } finally {
        this.loading = false
      }
    },

    async markAsRead(id) {
      const res = await api.post(`/notifications/${id}/mark-read/`)
      const idx = this.items.findIndex((n) => n.id === id)
      if (idx !== -1) this.items[idx] = res.data
      if (!this.items[idx]?.is_read) this.unreadCount = Math.max(0, this.unreadCount - 1)
      await this.fetchUnreadCount()
    },

    async markAllAsRead() {
      await api.post('/notifications/mark-all-read/')
      this.items = this.items.map((n) => ({ ...n, is_read: true, read_at: new Date().toISOString() }))
      this.unreadCount = 0
    },

    async dismiss(id) {
      const notification = this.items.find((n) => n.id === id)
      await api.delete(`/notifications/${id}/`)
      this.items = this.items.filter((n) => n.id !== id)
      if (notification && !notification.is_read) {
        this.unreadCount = Math.max(0, this.unreadCount - 1)
      }
    },

    startPolling(intervalMs = 60000) {
      if (this.pollHandle !== null) return

      const poll = () => this.fetchUnreadCount()

      this.pollHandle = setInterval(poll, intervalMs)

      const handler = () => {
        if (document.hidden) {
          clearInterval(this.pollHandle)
          this.pollHandle = null
        } else {
          this.fetchUnreadCount()
          if (this.pollHandle === null) {
            this.pollHandle = setInterval(poll, intervalMs)
          }
        }
      }
      this.visibilityHandler = handler
      document.addEventListener('visibilitychange', handler)
    },

    stopPolling() {
      if (this.pollHandle !== null) {
        clearInterval(this.pollHandle)
        this.pollHandle = null
      }
      if (this.visibilityHandler !== null) {
        document.removeEventListener('visibilitychange', this.visibilityHandler)
        this.visibilityHandler = null
      }
    },

    reset() {
      this.stopPolling()
      this.items = []
      this.unreadCount = 0
      this.loading = false
    },
  },
})
