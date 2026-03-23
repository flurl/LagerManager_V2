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

api.interceptors.response.use(
  (res) => res,
  async (err) => {
    if (err.response?.status === 401) {
      const auth = useAuthStore()
      await auth.logout()
    }
    return Promise.reject(err)
  }
)

export default api
