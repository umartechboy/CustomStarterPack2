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
  const [pinDiaMm, setPinDiaMm] = useState(7.4)
  const [lockerDiaMm, setLockerDiaMm] = useState(13.0)
  const [uPlusBossHeightMm, setUPlusBossHeightMm] = useState(1.2)
  const [uMinusBossHeightMm, setUMinusBossHeightMm] = useState('') // '' = auto (derived from pin dia)

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
        setPinDiaMm(jigGen.u_minus_pin_dia_mm ?? 7.4)
        setLockerDiaMm(jigGen.u_plus_locker_dia_mm ?? 13.0)
        setUPlusBossHeightMm(jigGen.u_plus_boss_height_mm ?? 1.2)
        setUMinusBossHeightMm(jigGen.u_minus_boss_height_mm ?? '')
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
            overlap_z_mm: parseFloat(overlapZMm),
            u_minus_pin_dia_mm: parseFloat(pinDiaMm),
            u_plus_locker_dia_mm: parseFloat(lockerDiaMm),
            u_plus_boss_height_mm: parseFloat(uPlusBossHeightMm),
            u_minus_boss_height_mm: uMinusBossHeightMm === '' ? null : parseFloat(uMinusBossHeightMm)
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

          <div className="form-row">
            <div className="form-group">
              <label>-U Pin Diameter (mm)</label>
              <input
                type="number"
                step="0.1"
                min="0"
                value={pinDiaMm}
                onChange={(e) => setPinDiaMm(e.target.value)}
              />
              <p className="form-hint">Flat-side diameter of the -U pin's cone (60° angle fixed; height follows automatically).</p>
            </div>
            <div className="form-group">
              <label>+U Locker Hole Diameter (mm)</label>
              <input
                type="number"
                step="0.1"
                min="0"
                value={lockerDiaMm}
                onChange={(e) => setLockerDiaMm(e.target.value)}
              />
              <p className="form-hint">Diameter of the through-hole bored in the +U connector's washer.</p>
            </div>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label>+U Boss Thickness (mm)</label>
              <input
                type="number"
                step="0.1"
                min="0"
                value={uPlusBossHeightMm}
                onChange={(e) => setUPlusBossHeightMm(e.target.value)}
              />
              <p className="form-hint">Thickness of the +U connector washer (body_a).</p>
            </div>
            <div className="form-group">
              <label>-U Boss Thickness (mm)</label>
              <input
                type="number"
                step="0.1"
                min="0"
                placeholder="Auto (cone + shaft height)"
                value={uMinusBossHeightMm}
                onChange={(e) => setUMinusBossHeightMm(e.target.value)}
              />
              <p className="form-hint">Leave blank to auto-size to the pin's own cone+shaft height (always fits).</p>
            </div>
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
