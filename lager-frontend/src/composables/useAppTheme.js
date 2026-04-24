import { watchEffect, onUnmounted } from 'vue'
import { useTheme } from 'vuetify'
import { useAuthStore } from '../stores/auth'
import { usePeriodStore } from '../stores/period'
import { hexToRgb } from '../utils/color'

const DEFAULT_PRIMARY = { light: '#1565C0', dark: '#64B5F6' }

export function useAppTheme() {
  const theme = useTheme()
  const auth = useAuthStore()
  const periodStore = usePeriodStore()

  const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')

  function apply() {
    const pref = auth.preferences?.theme ?? 'auto'
    const mode =
      pref === 'auto'
        ? mediaQuery.matches ? 'dark' : 'light'
        : pref

    theme.global.name.value = mode

    const periodColor = auth.preferences?.period_colors?.[String(periodStore.currentPeriodId)]
    const primary = periodColor || DEFAULT_PRIMARY[mode]

    theme.themes.value[mode].colors.primary = primary

    document.documentElement.style.setProperty('--period-primary', primary)
    const rgb = hexToRgb(primary)
    if (rgb) {
      document.documentElement.style.setProperty(
        '--period-primary-hover',
        `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, 0.08)`,
      )
    }
  }

  const stop = watchEffect(apply)

  mediaQuery.addEventListener('change', apply)
  onUnmounted(() => {
    stop()
    mediaQuery.removeEventListener('change', apply)
  })
}
