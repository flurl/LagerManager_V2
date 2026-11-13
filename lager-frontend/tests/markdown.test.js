import assert from 'node:assert/strict'
import test, { describe } from 'node:test'

import { imageUrlMap, renderMarkdown } from '../src/utils/markdown.js'

describe('renderMarkdown', () => {
  // The handbook's table of contents links to GitHub-style anchors (umlauts kept, punctuation
  // dropped, spaces → dashes); the rendered headings must carry exactly those ids.
  test('gives headings GitHub-compatible ids so the TOC links resolve', () => {
    const html = renderMarkdown('## 1. Überblick & Voraussetzungen')
    assert.match(html, /<h2 id="1-überblick--voraussetzungen">/)
  })

  // Images are bundled by Vite under hashed URLs, so the relative paths from the Markdown
  // have to be swapped for the bundled ones or the screenshots would 404.
  test('replaces relative image paths with the bundled URLs', () => {
    const html = renderMarkdown('![Menü](img/a.png)', { 'img/a.png': '/assets/a-123.png' })
    assert.match(html, /<img src="\/assets\/a-123\.png" alt="Menü">/)
  })

  // An image missing from the map is left untouched rather than dropped.
  test('keeps image paths that are not in the map', () => {
    const html = renderMarkdown('![x](img/unknown.png)', {})
    assert.match(html, /src="img\/unknown\.png"/)
  })

  // Tables are used throughout the handbook and require GFM.
  test('renders GFM tables', () => {
    const html = renderMarkdown('| a | b |\n|---|---|\n| 1 | 2 |')
    assert.match(html, /<table>/)
  })
})

describe('imageUrlMap', () => {
  // import.meta.glob keys are relative to the importing module; strip that prefix so the keys
  // match the paths written in the Markdown.
  test('strips the glob prefix from the keys', () => {
    const map = imageUrlMap({ '../../../docs/img/a.png': '/assets/a.png' }, '../../../docs/')
    assert.deepEqual(map, { 'img/a.png': '/assets/a.png' })
  })
})
