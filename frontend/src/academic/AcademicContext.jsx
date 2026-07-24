import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { getAcademicContext } from '../api/academicContext.js'
import { useAuth } from '../auth/AuthContext.jsx'
import { TRIMESTER_TERMS } from '../constants/terms.js'

const AcademicContext = createContext(null)

export function AcademicContextProvider({ children }) {
  const { isAuthenticated, user } = useAuth()
  const [context, setContext] = useState(null)
  const [loading, setLoading] = useState(false)
  const loadContext = useCallback(async () => {
    setLoading(true)
    try {
      const data = await getAcademicContext()
      setContext(data)
    } catch {
      setContext({
        current_term: TRIMESTER_TERMS[0],
        current_school_year: null,
        available_school_years: [],
        terms: TRIMESTER_TERMS,
      })
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    if (!isAuthenticated || user?.must_change_password) {
      setContext(null)
      return () => {
        cancelled = true
      }
    }

    async function guardedLoadContext() {
      try {
        const data = await getAcademicContext()
        if (!cancelled) setContext(data)
      } catch {
        if (!cancelled) {
          setContext({
            current_school_year: null,
            current_term: TRIMESTER_TERMS[0],
            available_school_years: [],
            terms: TRIMESTER_TERMS,
          })
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    guardedLoadContext()
    return () => {
      cancelled = true
    }
  }, [isAuthenticated, loadContext, user?.must_change_password])

  const value = useMemo(
    () => ({
      loading,
      currentSchoolYear: context?.current_school_year || '',
      currentTerm: context?.current_term || TRIMESTER_TERMS[0],
      availableSchoolYears: context?.available_school_years || [],
      terms: context?.terms?.length ? context.terms : TRIMESTER_TERMS,
      refreshAcademicContext: loadContext,
    }),
    [context, loadContext, loading],
  )

  return <AcademicContext.Provider value={value}>{children}</AcademicContext.Provider>
}

export function useAcademicContext() {
  const ctx = useContext(AcademicContext)
  if (!ctx) throw new Error('useAcademicContext must be used within an AcademicContextProvider')
  return ctx
}

export function useAcademicQueryParams({ includeTerm = true } = {}) {
  const academic = useAcademicContext()
  const [searchParams, setSearchParams] = useSearchParams()
  const selectedSchoolYear = searchParams.get('school_year') || academic.currentSchoolYear
  const selectedTerm = includeTerm ? searchParams.get('term') || academic.currentTerm : null

  useEffect(() => {
    if (!academic.currentSchoolYear) return
    let changed = false
    const next = new URLSearchParams(searchParams)
    if (!next.get('school_year')) {
      next.set('school_year', academic.currentSchoolYear)
      changed = true
    }
    if (includeTerm && !next.get('term')) {
      next.set('term', academic.currentTerm)
      changed = true
    }
    if (changed) setSearchParams(next, { replace: true })
  }, [academic.currentSchoolYear, academic.currentTerm, includeTerm, searchParams, setSearchParams])

  const setAcademicParam = (key, value) => {
    const next = new URLSearchParams(searchParams)
    if (value) next.set(key, value)
    else next.delete(key)
    setSearchParams(next)
  }

  return {
    ...academic,
    selectedSchoolYear,
    selectedTerm,
    setSelectedSchoolYear: (value) => setAcademicParam('school_year', value),
    setSelectedTerm: (value) => setAcademicParam('term', value),
  }
}
