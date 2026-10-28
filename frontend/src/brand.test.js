import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { APP_NAME } from './lib/brand'

// "Relay" is the product name; "CampusBid" is only the repository and code name. This fails if the old name creeps back
// into anything people see (the page, its title, button text, comments in the style sheet).

const ROOTS = ['src', 'index.html']
const ALLOWED = new Set([join('src', 'lib', 'brand.js'), join('src', 'brand.test.js')]) // they explain the naming

function files(path) {
  if (!statSync(path).isDirectory()) return [path]
  return readdirSync(path).flatMap((name) => files(join(path, name)))
}

describe('the product name', () => {
  it('is Relay', () => {
    expect(APP_NAME).toBe('Relay')
  })

  it('is never written as CampusBid in the app', () => {
    const offenders = ROOTS.flatMap(files)
      .filter((f) => /\.(js|jsx|css|html)$/.test(f) && !ALLOWED.has(f))
      .filter((f) => readFileSync(f, 'utf8').includes('CampusBid'))
    expect(offenders).toEqual([])
  })

  it('shows up in the page title helper and the nav', () => {
    const nav = readFileSync(join('src', 'components', 'Layout.jsx'), 'utf8')
    expect(nav).toMatch(/Re<span className="brand-accent">lay<\/span>/)
    expect(readFileSync('index.html', 'utf8')).toMatch(/<title>Relay /)
  })
})
