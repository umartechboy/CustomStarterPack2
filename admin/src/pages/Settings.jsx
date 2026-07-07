import { useState, useEffect } from 'react'
import { Save, Loader2, CheckCircle, XCircle } from 'lucide-react'
import { API_BASE_URL } from '../lib/supabase'

const ALL_JIG_DIRECTIONS = ['+Z', '-Z', '+X', '-X', '+Y', '-Y', '+U', '-U']

export default function Settings() {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saveResult, setSaveResult] = useState(null) // { success, error }
  const [jigsRequested, setJigsRequested] = useState([])
  const [overlapZMm, setOverlapZMm] = useState(2)

  useEffect(() => {
    let cancelled = false

    const load = async () => {
      try {
        const response = await fetch(`${API_BASE_URL}/printmaker/settings`)
        const json = await response.json()
        if (cancelled) return
        const jigGen = json.settings?.jig_generation || {}
        setJigsRequested(jigGen.jigs_requested || ['+U', '-U'])
        setOverlapZMm(jigGen.overlap_z_mm ?? 2)
      } catch (error) {
        if (!cancelled) setSaveResult({ success: false, error: `Failed to load settings: ${error.message}` })
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    load()
    return () => { cancelled = true }
  }, [])

  const toggleDirection = (dir) => {
    setJigsRequested(prev =>
      prev.includes(dir) ? prev.filter(d => d !== dir) : [...prev, dir]
    )
  }

  const handleSave = async (e) => {
    e.preventDefault()
    setSaving(true)
    setSaveResult(null)

    try {
      const response = await fetch(`${API_BASE_URL}/printmaker/settings`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          jig_generation: {
            jigs_requested: jigsRequested,
            overlap_z_mm: parseFloat(overlapZMm)
          }
        })
      })

      if (!response.ok) throw new Error(`Server responded ${response.status}`)
      setSaveResult({ success: true })
    } catch (error) {
      setSaveResult({ success: false, error: error.message })
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="settings-page">
        <div className="page-header">
          <h1>Settings</h1>
        </div>
        <p>Loading settings...</p>
      </div>
    )
  }

  return (
    <div className="settings-page">
      <div className="page-header">
        <h1>Settings</h1>
      </div>

      {saveResult && (
        <div className={`submission-alert ${saveResult.success ? 'success' : 'error'}`}>
          {saveResult.success ? (
            <>
              <CheckCircle size={20} />
              <div>
                <strong>Settings Saved</strong>
                <p>New PrintMaker runs will use these values.</p>
              </div>
            </>
          ) : (
            <>
              <XCircle size={20} />
              <div>
                <strong>Failed to Save Settings</strong>
                <p>{saveResult.error}</p>
              </div>
            </>
          )}
          <button className="alert-close" onClick={() => setSaveResult(null)}>×</button>
        </div>
      )}

      <form onSubmit={handleSave} className="test-form">
        <div className="form-section">
          <h3>Jig Generation Settings</h3>

          <div className="form-group">
            <label>Jigs to produce by default</label>
            <div className="checkbox-grid">
              {ALL_JIG_DIRECTIONS.map(dir => (
                <label key={dir} className="checkbox-item">
                  <input
                    type="checkbox"
                    checked={jigsRequested.includes(dir)}
                    onChange={() => toggleDirection(dir)}
                  />
                  <span>{dir}</span>
                </label>
              ))}
            </div>
            <p className="form-hint">+U / -U are the universal jigs (cone + connector). +Z/-Z/+X/-X/+Y/-Y are the per-side card jigs.</p>
          </div>

          <div className="form-group">
            <label>Overlap (mm)</label>
            <input
              type="number"
              step="0.1"
              min="0"
              value={overlapZMm}
              onChange={(e) => setOverlapZMm(e.target.value)}
            />
            <p className="form-hint">Controls the universal jig's plate depth (overlap + 1mm fixed backing).</p>
          </div>
        </div>

        <button type="submit" className="btn btn-primary btn-large" disabled={saving}>
          {saving ? (
            <>
              <Loader2 size={20} className="spinning" />
              Saving...
            </>
          ) : (
            <>
              <Save size={20} />
              Save Settings
            </>
          )}
        </button>
      </form>
    </div>
  )
}
