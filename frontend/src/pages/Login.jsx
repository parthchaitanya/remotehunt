import { useState } from 'react'
import { api } from '../api.js'
import { Button, ErrorNote } from '../components/ui.jsx'

export default function Login({ onDone }) {
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await api.post('/auth/login', { password })
      onDone()
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <form onSubmit={submit} className="card w-full max-w-sm space-y-4 p-6">
        <div className="flex items-center gap-2">
          <img src="/favicon.svg" alt="" className="h-8 w-8" />
          <h1 className="text-xl font-semibold">RemoteHunt</h1>
        </div>
        <p className="text-sm muted">This is a private instance. Enter your password to continue.</p>
        <input
          type="password"
          autoFocus
          autoComplete="current-password"
          className="input w-full"
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        <ErrorNote error={error} />
        <Button variant="primary" busy={busy} className="w-full justify-center">Sign in</Button>
      </form>
    </div>
  )
}
