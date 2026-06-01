export default function ErrorBanner({ message }) {
  return (
    <div className="state state-error" role="alert">
      {message}
    </div>
  )
}
