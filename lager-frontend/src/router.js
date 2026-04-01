import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', redirect: '/stock-movements' },
  {
    path: '/stock-movements',
    component: () => import('./views/StockMovementView.vue'),
    meta: { title: 'Lagerbewegungen' },
  },
  {
    path: '/period-start-stock',
    component: () => import('./views/PeriodStartStockView.vue'),
    meta: { title: 'Lagerstand' },
  },
  {
    path: '/initial-inventory',
    component: () => import('./views/InitialInventoryView.vue'),
    meta: { title: 'Initialer Stand' },
  },
  {
    path: '/physical-counts',
    component: () => import('./views/PhysicalCountView.vue'),
    meta: { title: 'Gezählter Stand' },
  },
  {
    path: '/reports/stock-level',
    component: () => import('./views/reports/StockLevelChartReport.vue'),
    meta: { title: 'Lagerstand Bericht' },
  },
  {
    path: '/reports/current-stock-level',
    component: () => import('./views/reports/CurrentStockLevelTableReport.vue'),
    meta: { title: 'Aktueller Lagerstand' },
  },
  {
    path: '/reports/inventory',
    component: () => import('./views/reports/InventoryTableReport.vue'),
    meta: { title: 'Inventur' },
  },
  {
    path: '/reports/consumption',
    component: () => import('./views/reports/ConsumptionChartReport.vue'),
    meta: { title: 'Verbrauch' },
  },
  {
    path: '/reports/consumption-totals',
    component: () => import('./views/reports/ConsumptionTotalsTableReport.vue'),
    meta: { title: 'Gesamtverbrauch' },
  },
  {
    path: '/reports/total-movements',
    component: () => import('./views/reports/TotalMovementsTableReport.vue'),
    meta: { title: 'Gesamte Bewegungen' },
  },
  {
    path: '/import',
    component: () => import('./views/ImportView.vue'),
    meta: { title: 'Daten importieren' },
  },
  {
    path: '/partners',
    component: () => import('./views/PartnerView.vue'),
    meta: { title: 'Partner' },
  },
  {
    path: '/tax-rates',
    component: () => import('./views/TaxRateView.vue'),
    meta: { title: 'Steuersätze' },
  },
  {
    path: '/settings',
    component: () => import('./views/SystemSettingsView.vue'),
    meta: { title: 'Einstellungen' },
  },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
