const DB_NAME = 'staff-consumption-db'
const DB_VERSION = 1
const STORE_NAME = 'consumed-articles'

/** @returns {Promise<IDBDatabase>} */
function openDb() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION)
    req.onupgradeneeded = (event) => {
      const db = /** @type {IDBOpenDBRequest} */ (event.target).result
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME, { autoIncrement: true })
      }
    }
    req.onsuccess = (event) => resolve(/** @type {IDBOpenDBRequest} */ (event.target).result)
    req.onerror = (event) => reject(/** @type {IDBOpenDBRequest} */ (event.target).error)
  })
}

/**
 * @typedef {{ timestamp: number, yearMonth: string, departmentName: string, articleId: string, articleName: string, count: number }} ConsumptionEntry
 * @typedef {{ key: number } & ConsumptionEntry} ConsumptionEntryWithKey
 */

/**
 * Save a single consumption entry to IndexedDB.
 * @param {ConsumptionEntry} entry
 * @returns {Promise<void>}
 */
export async function saveConsumption(entry) {
  const db = await openDb()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readwrite')
    tx.objectStore(STORE_NAME).add(entry)
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
  })
}

/**
 * Return all entries with their auto-increment keys.
 * @returns {Promise<ConsumptionEntryWithKey[]>}
 */
export async function getAllEntries() {
  const db = await openDb()
  return new Promise((resolve, reject) => {
    const result = /** @type {ConsumptionEntryWithKey[]} */ ([])
    const tx = db.transaction(STORE_NAME, 'readonly')
    const req = tx.objectStore(STORE_NAME).openCursor()
    req.onsuccess = (event) => {
      const cursor = /** @type {IDBRequest} */ (event.target).result
      if (cursor) {
        result.push({ key: cursor.key, ...cursor.value })
        cursor.continue()
      } else {
        resolve(result)
      }
    }
    req.onerror = () => reject(req.error)
  })
}

/**
 * Delete entries whose timestamp is older than 2 months ago.
 * @returns {Promise<number>} number of deleted records
 */
export async function deleteOldEntries() {
  const db = await openDb()
  const cutoff = new Date()
  cutoff.setDate(1)
  cutoff.setMonth(cutoff.getMonth() - 2)
  const cutoffTs = Math.floor(cutoff.getTime() / 1000)

  return new Promise((resolve, reject) => {
    let deleted = 0
    const tx = db.transaction(STORE_NAME, 'readwrite')
    const req = tx.objectStore(STORE_NAME).openCursor()
    req.onsuccess = (event) => {
      const cursor = /** @type {IDBRequest} */ (event.target).result
      if (cursor) {
        if (cursor.value.timestamp < cutoffTs) {
          cursor.delete()
          deleted++
        }
        cursor.continue()
      }
    }
    tx.oncomplete = () => resolve(deleted)
    tx.onerror = () => reject(tx.error)
  })
}

/**
 * Delete specific entries by their auto-increment keys.
 * @param {number[]} keys
 * @returns {Promise<void>}
 */
export async function deleteEntriesByKeys(keys) {
  const db = await openDb()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readwrite')
    const store = tx.objectStore(STORE_NAME)
    for (const key of keys) {
      store.delete(key)
    }
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
  })
}
