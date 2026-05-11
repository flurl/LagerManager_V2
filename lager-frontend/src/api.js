import axios from 'axios'
import { useAuthStore } from './stores/auth'

const api = axios.create({
  baseURL: '/api',
})

api.interceptors.request.use((config) => {
  const auth = useAuthStore()
  if (auth.token) {
    config.headers.Authorization = `Bearer ${auth.token}`
  }
  return config
})

let refreshing = false
let refreshQueue = /** @type {{ resolve: (token: string) => void, reject: (err: unknown) => void }[]} */ ([])

api.interceptors.response.use(
  (res) => res,
  async (err) => {
    if (err.response?.status !== 401) return Promise.reject(err)

    const auth = useAuthStore()

    if (!auth.refreshToken) {
      await auth.logout()
      return Promise.reject(err)
    }

    const originalRequest = err.config

    if (refreshing) {
      return new Promise((resolve, reject) => {
        refreshQueue.push({ resolve, reject })
      }).then((token) => {
        originalRequest.headers.Authorization = `Bearer ${token}`
        return api(originalRequest)
      })
    }

    refreshing = true
    try {
      // Use raw axios so this request bypasses the interceptors and never loops.
      const res = await axios.post('/api/token/refresh/', { refresh: auth.refreshToken })
      const newToken = /** @type {string} */ (res.data.access)
      auth.token = newToken
      localStorage.setItem('token', newToken)
      if (res.data.refresh) {
        auth.refreshToken = res.data.refresh
        localStorage.setItem('refreshToken', res.data.refresh)
      }

      refreshQueue.forEach((p) => p.resolve(newToken))
      refreshQueue = []

      originalRequest.headers.Authorization = `Bearer ${newToken}`
      return api(originalRequest)
    } catch (refreshErr) {
      // Refresh failed with a network error → user is offline, keep them logged in.
      // Refresh failed with a 4xx → refresh token is expired, log out.
      const isNetworkError =
        !navigator.onLine ||
        /** @type {any} */ (refreshErr).code === 'ERR_NETWORK' ||
        /** @type {any} */ (refreshErr).message === 'Network Error'

      refreshQueue.forEach((p) => p.reject(refreshErr))
      refreshQueue = []

      if (!isNetworkError) {
        await auth.logout()
      }
      return Promise.reject(err)
    } finally {
      refreshing = false
    }
  },
)

export default api
