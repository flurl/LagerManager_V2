import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', redirect: '/deliveries' },
  {
    path: '/deliveries',
    component: () => import('./views/DeliveryList.vue'),
    meta: { title: 'Lieferungen' },
  },
  {
    path: '/stock-levels',
    component: () => import('./views/StockLevelTable.vue'),
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
    path: '/reports/total-deliveries',
    component: () => import('./views/TotalDeliveriesReport.vue'),
    meta: { title: 'Gesamte Lieferungen' },
  },
  {
    path: '/import',
    component: () => import('./views/ImportDialog.vue'),
    meta: { title: 'Daten importieren' },
  },
  {
    path: '/suppliers',
    component: () => import('./views/SupplierCrud.vue'),
    meta: { title: 'Lieferanten' },
  },
  {
    path: '/tax-rates',
    component: () => import('./views/TaxRateCrud.vue'),
    meta: { title: 'Steuersätze' },
  },
  {
    path: '/delivery-units',
    component: () => import('./views/DeliveryUnitCrud.vue'),
    meta: { title: 'Liefereinheiten' },
  },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
