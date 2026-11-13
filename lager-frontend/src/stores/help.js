import { defineStore } from 'pinia'

// State of the handbook sidebar, so any view can open it (optionally at a given section).
export const useHelpStore = defineStore('help', {
  state: () => ({
    sidebarOpen: false,
    // Heading id to scroll to, e.g. '7-mahnungen'; null keeps the current position.
    anchor: null,
    // Bumped on every open, so re-opening at the same anchor scrolls there again.
    openRequest: 0,
  }),
  actions: {
    openHandbook(anchor = null) {
      this.anchor = anchor
      this.sidebarOpen = true
      this.openRequest++
    },
    closeHandbook() {
      this.sidebarOpen = false
    },
  },
})
