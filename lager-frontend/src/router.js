import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from './stores/auth'

const routes = [
  { path: '/', redirect: '/stock-movements' },
  {
    path: '/stock-movements',
    component: () => import('./views/StockMovementView.vue'),
    meta: { title: 'Lagerbewegungen', permission: 'deliveries.view_stockmovement' },
  },
  {
    path: '/period-start-stock',
    component: () => import('./views/PeriodStartStockView.vue'),
    meta: { title: 'Lagerstand', permission: 'inventory.view_periodstartstocklevel' },
  },
  {
    path: '/initial-inventory',
    component: () => import('./views/InitialInventoryView.vue'),
    meta: { title: 'Initialer Stand', permission: 'inventory.view_initialinventory' },
  },
  {
    path: '/physical-counts',
    component: () => import('./views/PhysicalCountView.vue'),
    meta: { title: 'Gezählter Stand', permission: 'inventory.view_physicalcount' },
  },
  {
    path: '/stock-count',
    component: () => import('./views/StockCountView.vue'),
    meta: { title: 'Bestandszählung', fullscreen: true, permission: 'stock_count.view_stockcountentry' },
  },
  {
    path: '/stock-count-entries',
    component: () => import('./views/StockCountEntriesView.vue'),
    meta: { title: 'Zählergebnisse', permission: 'stock_count.view_stockcountentry' },
  },
  {
    path: '/reports/stock-level',
    component: () => import('./views/reports/StockLevelChartReport.vue'),
    meta: { title: 'Lagerstand Bericht', permission: 'core.view_reports' },
  },
  {
    path: '/reports/current-stock-level',
    component: () => import('./views/reports/CurrentStockLevelTableReport.vue'),
    meta: { title: 'Aktueller Lagerstand', permission: 'core.view_reports' },
  },
  {
    path: '/reports/inventory',
    component: () => import('./views/reports/InventoryTableReport.vue'),
    meta: { title: 'Inventur', permission: 'core.view_reports' },
  },
  {
    path: '/reports/consumption',
    component: () => import('./views/reports/ConsumptionChartReport.vue'),
    meta: { title: 'Verbrauch', permission: 'core.view_reports' },
  },
  {
    path: '/reports/consumption-totals',
    component: () => import('./views/reports/ConsumptionTotalsTableReport.vue'),
    meta: { title: 'Gesamtverbrauch', permission: 'core.view_reports' },
  },
  {
    path: '/reports/total-movements',
    component: () => import('./views/reports/TotalMovementsTableReport.vue'),
    meta: { title: 'Gesamte Bewegungen', permission: 'core.view_reports' },
  },
  {
    path: '/import',
    component: () => import('./views/ImportView.vue'),
    meta: { title: 'Daten importieren', permission: 'core.run_import' },
  },
  {
    path: '/article-meta',
    component: () => import('./views/ArticleMetaView.vue'),
    meta: { title: 'Artikel-Metadaten', permission: 'pos_import.view_articlemeta' },
  },
  {
    path: '/partners',
    component: () => import('./views/PartnerView.vue'),
    meta: { title: 'Partner', permission: 'deliveries.view_partner' },
  },
  {
    path: '/tax-rates',
    component: () => import('./views/TaxRateView.vue'),
    meta: { title: 'Steuersätze', permission: 'deliveries.view_taxrate' },
  },
  {
    path: '/locations',
    component: () => import('./views/LocationView.vue'),
    meta: { title: 'Standorte', permission: 'core.view_location' },
  },
  {
    path: '/settings',
    component: () => import('./views/SystemSettingsView.vue'),
    meta: { title: 'Einstellungen', permission: 'constance.change_config' },
  },
  {
    path: '/forbidden',
    component: () => import('./views/ForbiddenView.vue'),
    meta: { title: 'Kein Zugriff', public: true },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (!auth.isAuthenticated) return true  // App.vue handles the login wall
  if (to.meta.public) return true
  if (!auth.ready) {
    try {
      await auth.fetchMe()
    } catch {
      if (!navigator.onLine) {
        // Network unavailable — token is still valid, don't log out
        return true  // App.vue will show the login wall (no cached user data)
      }
      await auth.logout()
      return true  // App.vue will show the login wall
    }
  }
  const perm = to.meta.permission
  if (!perm || !auth.hasPermission(perm)) {
    return { path: '/forbidden' }
  }
})

export default router
