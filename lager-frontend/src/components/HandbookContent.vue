<template>
  <!-- eslint-disable-next-line vue/no-v-html -- trusted content from our own repository -->
  <div ref="rootEl" class="handbook" @click="onClick" v-html="html" />
</template>

<script setup>
import { ref } from 'vue'
// Bundled straight from docs/ at build time (and hot-reloaded in dev), so the handbook always
// matches the deployed version — there is no separate copy to keep in sync.
import markdown from '../../../docs/fakturierung-handbuch.md?raw'
import { imageUrlMap, renderMarkdown } from '../utils/markdown'

const props = defineProps({
  // Space kept above a heading scrolled to in the page, e.g. for the fixed app bar.
  scrollOffset: { type: Number, default: 8 },
  // Reflect in-document navigation in the URL hash (only sensible on the standalone page).
  updateUrl: { type: Boolean, default: false },
})

const images = import.meta.glob('../../../docs/img/fakturierung/*', {
  eager: true,
  query: '?url',
  import: 'default',
})

const html = renderMarkdown(markdown, imageUrlMap(images, '../../../docs/'))
const rootEl = ref(null)

// Scrolls the nearest ancestor marked with `data-handbook-scroll` (the sidebar), or the window.
// Done by hand rather than with scrollIntoView, which would also scroll the page behind the
// sidebar and can't account for the fixed app bar.
function scrollToAnchor(id, behavior = 'smooth') {
  if (!id || !rootEl.value) return
  const target = rootEl.value.querySelector(`[id="${CSS.escape(decodeURIComponent(id))}"]`)
  if (!target) return
  const container = rootEl.value.closest('[data-handbook-scroll]')
  const targetTop = target.getBoundingClientRect().top
  if (container) {
    const top = targetTop - container.getBoundingClientRect().top + container.scrollTop - props.scrollOffset
    container.scrollTo({ top, behavior })
  } else {
    window.scrollTo({ top: targetTop + window.scrollY - props.scrollOffset, behavior })
  }
}

function onClick(event) {
  const link = event.target.closest('a')
  if (!link) return
  const href = link.getAttribute('href') ?? ''
  if (href.startsWith('#')) {
    event.preventDefault()
    if (props.updateUrl) history.replaceState(history.state, '', href)
    scrollToAnchor(href.slice(1))
  } else if (/^https?:/.test(href)) {
    link.target = '_blank'
    link.rel = 'noopener'
  }
}

defineExpose({ scrollToAnchor })
</script>

<style scoped>
.handbook :deep(h1),
.handbook :deep(h2),
.handbook :deep(h3),
.handbook :deep(h4) {
  margin: 1.5em 0 0.5em;
  line-height: 1.3;
}

.handbook :deep(h1) {
  margin-top: 0;
}

.handbook :deep(h2) {
  padding-bottom: 0.3em;
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.handbook :deep(p),
.handbook :deep(ul),
.handbook :deep(ol),
.handbook :deep(table),
.handbook :deep(blockquote) {
  margin-bottom: 1em;
}

.handbook :deep(ul),
.handbook :deep(ol) {
  padding-left: 1.75em;
}

.handbook :deep(img) {
  display: block;
  max-width: 100%;
  margin: 1em 0;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 4px;
}

.handbook :deep(table) {
  border-collapse: collapse;
  width: 100%;
}

.handbook :deep(th),
.handbook :deep(td) {
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  padding: 6px 10px;
  text-align: left;
  vertical-align: top;
}

.handbook :deep(th) {
  background: rgba(var(--v-theme-on-surface), 0.05);
}

.handbook :deep(blockquote) {
  padding: 0.5em 1em;
  border-left: 4px solid rgb(var(--v-theme-primary));
  background: rgba(var(--v-theme-primary), 0.06);
}

.handbook :deep(blockquote p:last-child) {
  margin-bottom: 0;
}

.handbook :deep(code) {
  padding: 0.1em 0.3em;
  border-radius: 3px;
  background: rgba(var(--v-theme-on-surface), 0.08);
  font-size: 0.9em;
}

.handbook :deep(hr) {
  margin: 2em 0;
  border: none;
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.handbook :deep(a) {
  color: rgb(var(--v-theme-primary));
}
</style>
