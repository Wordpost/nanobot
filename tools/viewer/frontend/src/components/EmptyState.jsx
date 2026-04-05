/** @module components/EmptyState (fork-local) */

export function EmptyState({ icon = '📋', title, message, children }) {
  return (
    <div class="empty-state">
      <div class="empty-icon">{icon}</div>
      <h2>{title}</h2>
      {message && <p>{message}</p>}
      {children && <div class="empty-extras">{children}</div>}
    </div>
  )
}
