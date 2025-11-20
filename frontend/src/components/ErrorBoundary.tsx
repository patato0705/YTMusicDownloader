// frontend/src/components/ErrorBoundary.tsx
import React from "react"

type Props = { children: React.ReactNode }
type State = { hasError: boolean; error?: Error | null }

export default class ErrorBoundary extends React.Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: any) {
    // tu peux aussi envoyer vers un logger ici
    console.error("Caught by ErrorBoundary:", error, errorInfo)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: 20 }}>
          <h1>Une erreur est survenue</h1>
          <pre>{String(this.state.error?.message ?? this.state.error)}</pre>
        </div>
      )
    }
    return this.props.children
  }
}