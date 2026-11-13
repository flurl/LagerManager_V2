import { Marked } from 'marked'
import { gfmHeadingId } from 'marked-gfm-heading-id'

/**
 * Render a handbook Markdown file (from `docs/`) to HTML.
 *
 * Headings get GitHub-style ids so the handbook's own table of contents and cross-references
 * (`#1-überblick--voraussetzungen`) keep working. Relative image paths are resolved through
 * `imageUrls` — a map from the path as written in the Markdown (e.g.
 * `img/fakturierung/01-menue.png`) to the URL the bundler serves the file under.
 */
export function renderMarkdown(markdown, imageUrls = {}) {
  const marked = new Marked({ gfm: true })
  marked.use(gfmHeadingId())
  marked.use({
    walkTokens(token) {
      if (token.type === 'image' && imageUrls[token.href]) token.href = imageUrls[token.href]
    },
  })
  return marked.parse(markdown)
}

/**
 * Turn the result of `import.meta.glob('<prefix>img/**', { query: '?url', import: 'default' })`
 * into the path → URL map `renderMarkdown` expects, by stripping the glob's path prefix.
 */
export function imageUrlMap(globResult, prefix) {
  return Object.fromEntries(
    Object.entries(globResult).map(([path, url]) => [path.startsWith(prefix) ? path.slice(prefix.length) : path, url]),
  )
}
