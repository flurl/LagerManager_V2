import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', redirect: '/stock-movements' },
  {
    path: '/stock-movements',
    component: () => import('./views/StockMovementList.vue'),
    meta: { title: 'Lagerbewegungen' },
  },
  {
    path: '/period-start-stock',
    component: () => import('./views/PeriodStartStockView.vue'),
    meta: { title: 'Lagerstand' },
  },
  {
    path: '/initial-inventory',
    component: () => import('./views/InitialInventoryTable.vue'),
    meta: { title: 'Initialer Stand' },
  },
  {
    path: '/physical-counts',
    component: () => import('./views/PhysicalCountTable.vue'),
    meta: { title: 'Gezählter Stand' },
  },
  {
    path: '/reports/stock-level',
    component: () => import('./views/StockLevelChart.vue'),
    meta: { title: 'Lagerstand Bericht' },
  },
  {
    path: '/reports/current-stock-level',
    component: () => import('./views/CurrentStockLevelReport.vue'),
    meta: { title: 'Aktueller Lagerstand' },
  },
  {
    path: '/reports/inventory',
    component: () => import('./views/InventoryReport.vue'),
    meta: { title: 'Inventur' },
  },
  {
    path: '/reports/consumption',
    component: () => import('./views/ConsumptionChart.vue'),
    meta: { title: 'Verbrauch' },
  },
  {
    path: '/reports/consumption-totals',
    component: () => import('./views/ConsumptionTotalsReport.vue'),
    meta: { title: 'Gesamtverbrauch' },
  },
  {
    path: '/reports/total-movements',
    component: () => import('./views/TotalMovementsReport.vue'),
    meta: { title: 'Gesamte Bewegungen' },
  },
  {
    path: '/import',
    component: () => import('./views/ImportDialog.vue'),
    meta: { title: 'Daten importieren' },
  },
  {
    path: '/partners',
    component: () => import('./views/PartnerCrud.vue'),
    meta: { title: 'Partner' },
  },
  {
    path: '/tax-rates',
    component: () => import('./views/TaxRateCrud.vue'),
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
