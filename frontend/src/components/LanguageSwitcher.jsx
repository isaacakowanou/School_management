import { useTranslation } from 'react-i18next'

export default function LanguageSwitcher() {
  const { i18n } = useTranslation()
  const current = i18n.language?.startsWith('fr') ? 'fr' : 'en'

  return (
    <div className="lang-switcher" aria-label="Language / Langue">
      <button
        type="button"
        className={`lang-btn${current === 'fr' ? ' lang-btn-active' : ''}`}
        onClick={() => i18n.changeLanguage('fr')}
        aria-pressed={current === 'fr'}
      >
        FR
      </button>
      <span className="lang-sep" aria-hidden="true">|</span>
      <button
        type="button"
        className={`lang-btn${current === 'en' ? ' lang-btn-active' : ''}`}
        onClick={() => i18n.changeLanguage('en')}
        aria-pressed={current === 'en'}
      >
        EN
      </button>
    </div>
  )
}
