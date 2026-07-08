import { Component } from 'react'

// Top-level safety net: a render crash anywhere in the tree shows a reload
// prompt instead of a blank white page. Class component because React error
// boundaries have no hook equivalent.
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false }
  }

  static getDerivedStateFromError() {
    return { hasError: true }
  }

  componentDidCatch(error, info) {
    console.error('Unhandled render error:', error, info)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="content" style={{ padding: '3rem 1rem', textAlign: 'center' }}>
          <h2>Something went wrong / Une erreur est survenue</h2>
          <p className="muted">
            Please reload the page. / Veuillez recharger la page.
          </p>
          <button type="button" className="btn btn-primary" onClick={() => window.location.reload()}>
            Reload / Recharger
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
