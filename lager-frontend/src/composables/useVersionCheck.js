import { onMounted, onUnmounted, ref } from 'vue'
import api from '../api'
import { isVersionMismatch } from '../utils/version'

const CHECK_INTERVAL_MS = 5 * 60 * 1000

/**
 * Polls /api/version/ and reports whether the running frontend bundle is older
 * than the deployed backend. Checks once on mount (i.e. on every app reload)
 * and then every five minutes.
 *
 * The nag can be snoozed, but the next check re-opens it as long as the
 * versions still differ.
 *
 * @param {string} localHash commit hash baked into this bundle at build time
 */
export function useVersionCheck(localHash) {
  const outdated = ref(false)
  const backendHash = ref('')
  const snoozed = ref(false)
  let timer = null

  async function check() {
    let data
    try {
      ({ data } = await api.get('/version/'))
    } catch {
      // Offline, backend restarting or token expired — try again next tick.
      return
    }
    backendHash.value = data.hash ?? ''
    outdated.value = isVersionMismatch(localHash, data.hash)
    if (outdated.value) snoozed.value = false
  }

  function onVisibilityChange() {
    if (!document.hidden) check()
  }

  async function reload() {
    // The PWA service worker serves the old bundle until it has picked up the
    // new one; nudging it first makes a single reload succeed more often.
    if ('serviceWorker' in navigator) {
      try {
        const registrations = await navigator.serviceWorker.getRegistrations()
        await Promise.all(registrations.map((registration) => registration.update()))
      } catch {
        // Best effort only — reload regardless.
      }
    }
    window.location.reload()
  }

  onMounted(() => {
    check()
    timer = setInterval(check, CHECK_INTERVAL_MS)
    document.addEventListener('visibilitychange', onVisibilityChange)
  })

  onUnmounted(() => {
    if (timer) clearInterval(timer)
    document.removeEventListener('visibilitychange', onVisibilityChange)
  })

  return {
    outdated,
    backendHash,
    snoozed,
    check,
    reload,
    snooze: () => { snoozed.value = true },
  }
}
