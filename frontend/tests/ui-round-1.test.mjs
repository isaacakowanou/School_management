import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import { resetPasswordErrorMessage } from '../src/utils/resetPasswordErrors.js'

const readSource = (path) => readFileSync(new URL(`../${path}`, import.meta.url), 'utf8')
const translate = (key) => key

test('password reset distinguishes an invalid link from network and server failures', () => {
  assert.equal(
    resetPasswordErrorMessage({ code: 'invalid_reset_link', message: 'generic' }, translate),
    'forgotPassword.invalidResetLink',
  )
  assert.equal(
    resetPasswordErrorMessage({ status: 0, message: 'Could not reach the server.' }, translate),
    'Could not reach the server.',
  )
  assert.equal(
    resetPasswordErrorMessage({ status: 503, message: 'The action could not be completed.' }, translate),
    'The action could not be completed.',
  )
})

test('all three spreadsheet importers use the same row-error styling', () => {
  for (const path of [
    'src/pages/AdminStudentImportPage.jsx',
    'src/pages/AdminTeacherImportPage.jsx',
    'src/pages/AdminParentLinkImportPage.jsx',
  ]) {
    const source = readSource(path)
    assert.match(source, /className="import-issue import-issue-error"/)
    assert.doesNotMatch(source, /className="import-error"/)
  }
})

test('parent dashboard exposes a direct reports link for each student', () => {
  const source = readSource('src/pages/DashboardPage.jsx')
  assert.ok(source.includes('to={`/students/${student.id}/reports`}'))
})

test('phone-width rules wrap the top bar, collapse admin navigation, and stack parent filters', () => {
  const css = readSource('src/styles/index.css')
  const adminLayout = readSource('src/components/AdminLayout.jsx')

  assert.match(css, /@media \(max-width: 720px\)[\s\S]*?\.topbar \{[\s\S]*?flex-wrap: wrap;/)
  assert.match(css, /\.topbar \.admin-menu-toggle \{\s*display: none;/)
  assert.match(css, /@media \(max-width: 720px\)[\s\S]*?\.admin-sidebar \{[\s\S]*?display: none;/)
  assert.match(css, /@media \(max-width: 720px\)[\s\S]*?\.admin-sidebar-open \{[\s\S]*?display: flex;/)
  assert.match(css, /@media \(max-width: 720px\)[\s\S]*?\.parent-grade-filters \{[\s\S]*?flex-direction: column;/)
  assert.match(adminLayout, /aria-expanded=\{mobileNavOpen\}/)
})
