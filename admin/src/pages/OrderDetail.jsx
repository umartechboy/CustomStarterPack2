import { useState, useEffect } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { ArrowLeft, Download, RefreshCw, User, Mail, Package, Palette, Image, Trash2, FileImage, Box, RotateCcw, Paintbrush } from 'lucide-react'
import { supabase, API_BASE_URL } from '../lib/supabase'
import TexturePreview from '../components/TexturePreview'

export default function OrderDetail() {
  const { jobId } = useParams()
  const navigate = useNavigate()
  const [order, setOrder] = useState(null)
  const [files, setFiles] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [deleting, setDeleting] = useState(false)
  const [retrying, setRetrying] = useState(false)
  const [showRetryMenu, setShowRetryMenu] = useState(false)
  const [regeneratingTexture, setRegeneratingTexture] = useState(false)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [showKeychain, setShowKeychain] = useState(false)

  const fetchOrder = async () => {
    setLoading(true)
    setError(null)
    try {
      const { data, error: fetchError } = await supabase
        .from('orders')
        .select('*')
        .eq('job_id', jobId)
        .single()

      if (fetchError) throw fetchError
      setOrder(data)

      // Also fetch files
      const filesRes = await fetch(`${API_BASE_URL}/starter-pack/order/${jobId}/files`)
      const filesData = await filesRes.json()
      if (filesData.success) {
        setFiles(filesData.files)
      }

    } catch (err) {
      console.error('Error fetching order:', err)
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  // Close retry menu when clicking outside
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (showRetryMenu && !e.target.closest('.retry-dropdown')) {
        setShowRetryMenu(false)
      }
    }
    document.addEventListener('click', handleClickOutside)
    return () => document.removeEventListener('click', handleClickOutside)
  }, [showRetryMenu])

  useEffect(() => {
    fetchOrder()

    // Set up polling for status updates if order is processing
    const interval = setInterval(async () => {
      if (order && (order.status === 'pending' || order.status === 'processing')) {
        const { data } = await supabase
          .from('orders')
          .select('status')
          .eq('job_id', jobId)
          .single()

        if (data && data.status !== order.status) {
          fetchOrder() // Refresh all data when status changes
        }
      }
    }, 5000)

    return () => clearInterval(interval)
  }, [jobId, order?.status])

  const getStatusBadge = (status) => {
    const styles = {
      pending: { bg: '#fef3c7', color: '#92400e' },
      processing: { bg: '#dbeafe', color: '#1e40af' },
      completed: { bg: '#d1fae5', color: '#065f46' },
      failed: { bg: '#fee2e2', color: '#991b1b' }
    }
    const s = styles[status] || styles.pending
    return (
      <span className="status-badge large" style={{ backgroundColor: s.bg, color: s.color }}>
        {status}
      </span>
    )
  }

  const downloadFile = (url, filename) => {
    const fullUrl = url.startsWith('http') ? url : `${API_BASE_URL}${url}`
    const link = document.createElement('a')
    link.href = fullUrl
    link.download = filename
    link.target = '_blank'
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  }

  const handleDelete = async () => {
    if (!confirm(`Are you sure you want to delete order ${jobId}? This will delete all files.`)) {
      return
    }

    setDeleting(true)
    try {
      const res = await fetch(`${API_BASE_URL}/starter-pack/order/${jobId}`, {
        method: 'DELETE'
      })
      const data = await res.json()
      if (data.success) {
        navigate('/orders')
      } else {
        alert('Failed to delete order')
      }
    } catch (err) {
      alert(`Error deleting order: ${err.message}`)
    } finally {
      setDeleting(false)
    }
  }

  const handleRetry = async (fromStep) => {
    setRetrying(true)
    setShowRetryMenu(false)
    try {
      const res = await fetch(`${API_BASE_URL}/starter-pack/order/${jobId}/retry?from_step=${fromStep}`, {
        method: 'POST'
      })
      const data = await res.json()
      if (data.success) {
        alert(`Order queued for retry from Step ${fromStep}: ${data.step_name}`)
        fetchOrder() // Refresh to see new status
      } else {
        alert(`Failed to retry: ${data.error}`)
      }
    } catch (err) {
      alert(`Error retrying order: ${err.message}`)
    } finally {
      setRetrying(false)
    }
  }

  const handleRegenerateTexture = async () => {
    setRegeneratingTexture(true)
    try {
      const res = await fetch(`${API_BASE_URL}/starter-pack/order/${jobId}/regenerate-texture`, {
        method: 'POST'
      })
      const data = await res.json()
      if (data.success) {
        alert('Texture regenerated successfully!')
        fetchOrder() // Refresh to see new texture
      } else {
        alert(`Failed to regenerate texture: ${data.error}`)
      }
    } catch (err) {
      alert(`Error regenerating texture: ${err.message}`)
    } finally {
      setRegeneratingTexture(false)
    }
  }

  const retrySteps = [
    { step: 1, name: 'Image Generation', desc: 'Re-generate all images with GPT' },
    { step: 2, name: 'Background Image', desc: 'Re-generate background only' },
    { step: 3, name: 'Background Removal', desc: 'Skip (GPT provides transparent PNGs)' },
    { step: 4, name: '3D + Depth Maps', desc: 'Figure → FAL.AI GLB, Accessories → Sculptok depth' },
    { step: 5, name: 'Blender 2.5D Card', desc: 'Depth map displacement → card STL + texture' },
    { step: 6, name: 'PrintMaker', desc: 'Figure STL, jigs, printing assets' },
    { step: 7, name: 'Stickers', desc: 'Re-generate front/back stickers' }
  ]

  const getTextColorDisplay = (color) => {
    return (
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: '8px' }}>
        <span style={{
          display: 'inline-block',
          width: '24px',
          height: '24px',
          backgroundColor: color || 'red',
          border: '2px solid #000',
          borderRadius: '4px'
        }} />
        <span style={{ textTransform: 'capitalize' }}>{color || 'red'}</span>
      </span>
    )
  }

  if (loading) {
    return (
      <div className="order-detail">
        <div className="loading-state">Loading order...</div>
      </div>
    )
  }

  if (error || !order) {
    return (
      <div className="order-detail">
        <div className="error-state">
          <p>Error: {error || 'Order not found'}</p>
          <Link to="/orders" className="btn">Back to Orders</Link>
        </div>
      </div>
    )
  }

  const accessories = order.accessories || []

  return (
    <div className="order-detail">
      <div className="page-header">
        <Link to="/orders" className="btn btn-secondary">
          <ArrowLeft size={16} />
          Back
        </Link>
        <div className="header-right">
          {getStatusBadge(order.status)}
          <button className="btn btn-secondary" onClick={fetchOrder}>
            <RefreshCw size={16} />
            Refresh
          </button>
          <button className="btn btn-secondary" onClick={handleDelete} disabled={deleting} style={{ color: '#ef4444' }}>
            <Trash2 size={16} />
            {deleting ? 'Deleting...' : 'Delete'}
          </button>

          {/* Retry Dropdown */}
          <div className="retry-dropdown" style={{ position: 'relative' }}>
            <button
              className="btn btn-primary"
              onClick={() => setShowRetryMenu(!showRetryMenu)}
              disabled={retrying || order.status === 'processing'}
            >
              <RotateCcw size={16} />
              {retrying ? 'Retrying...' : 'Retry'}
            </button>
            {showRetryMenu && (
              <div className="retry-menu" style={{
                position: 'absolute',
                top: '100%',
                right: 0,
                marginTop: '4px',
                background: 'white',
                border: '1px solid #e2e8f0',
                borderRadius: '8px',
                boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
                minWidth: '280px',
                zIndex: 100
              }}>
                <div style={{ padding: '12px 16px', borderBottom: '1px solid #e2e8f0', fontWeight: 600, color: '#1e293b' }}>
                  Retry from step:
                </div>
                {retrySteps.map(({ step, name, desc }) => (
                  <button
                    key={step}
                    onClick={() => handleRetry(step)}
                    style={{
                      display: 'block',
                      width: '100%',
                      padding: '10px 16px',
                      textAlign: 'left',
                      background: 'none',
                      border: 'none',
                      cursor: 'pointer',
                      color: '#1e293b',
                      borderBottom: step < 6 ? '1px solid #f1f5f9' : 'none'
                    }}
                    onMouseEnter={(e) => e.target.style.background = '#f1f5f9'}
                    onMouseLeave={(e) => e.target.style.background = 'none'}
                  >
                    <div style={{ fontWeight: 500, color: '#1e293b' }}>Step {step}: {name}</div>
                    <div style={{ fontSize: '12px', color: '#64748b' }}>{desc}</div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="order-header">
        <h1>
          Order: {order.order_number || order.job_id}
          {order.is_test && <span className="order-test-badge" style={{ marginLeft: '12px', fontSize: '14px' }}>TEST</span>}
        </h1>
        <p className="order-date">Created: {new Date(order.created_at).toLocaleString()}</p>
      </div>

      <div className="detail-grid">
        {/* Customer Info */}
        <div className="detail-card">
          <h3><User size={18} /> Customer Information</h3>
          <div className="detail-row">
            <label>Name:</label>
            <span>{order.customer_name || 'N/A'}</span>
          </div>
          <div className="detail-row">
            <label>Email:</label>
            <span>{order.customer_email || 'N/A'}</span>
          </div>
          <div className="detail-row">
            <label>Shopify Order ID:</label>
            <span>{order.shopify_order_id || 'N/A'}</span>
          </div>
        </div>

        {/* Card Customization */}
        <div className="detail-card">
          <h3><Palette size={18} /> Card Customization</h3>
          <div className="detail-row">
            <label>Title:</label>
            <span className="title-preview">{order.title || 'N/A'}</span>
          </div>
          <div className="detail-row">
            <label>Subtitle:</label>
            <span>{order.subtitle || 'None'}</span>
          </div>
          <div className="detail-row">
            <label>Text Color:</label>
            {getTextColorDisplay(order.text_color)}
          </div>
          <div className="detail-row">
            <label>Background:</label>
            <span>
              {order.background_type === 'solid'
                ? `Solid - ${order.background_color}`
                : order.background_type || 'transparent'}
            </span>
          </div>
        </div>

        {/* Accessories */}
        <div className="detail-card">
          <h3><Package size={18} /> Accessories</h3>
          {accessories.length > 0 ? (
            <ul className="accessories-list">
              {accessories.map((acc, i) => (
                <li key={i}>{i + 1}. {acc}</li>
              ))}
            </ul>
          ) : (
            <p className="empty-text">No accessories specified</p>
          )}
        </div>

        {/* Input Image */}
        <div className="detail-card">
          <h3><Image size={18} /> Input Image</h3>
          {files?.input_image ? (
            <div className="image-preview-container">
              <img
                src={`${API_BASE_URL}${files.input_image}`}
                alt="Input"
                className="preview-image"
              />
              <button
                className="btn btn-small"
                onClick={() => downloadFile(files.input_image, `${order.job_id}_input.png`)}
              >
                <Download size={14} /> Download
              </button>
            </div>
          ) : order.input_image_path ? (
            <p className="file-path">{order.input_image_path}</p>
          ) : (
            <p className="empty-text">No input image</p>
          )}
        </div>
      </div>

      {/* ================================================================ */}
      {/* 1. IMAGES                                                       */}
      {/* ================================================================ */}

      {/* 1.1 Generated Images (GPT) */}
      {files?.generated_images?.length > 0 && (
        <div className="files-section">
          <h2><FileImage size={20} /> Generated Images (GPT)</h2>
          <div className="images-grid">
            {files.generated_images.map((img, i) => (
              <div key={i} className="image-card">
                <img src={`${API_BASE_URL}${img.url}`} alt={img.name} />
                <div className="image-card-footer">
                  <span className="image-type">{img.type}</span>
                  <button className="btn btn-small" onClick={() => downloadFile(img.url, img.name)}>
                    <Download size={14} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 1.3 Depth Maps [advanced] */}
      {showAdvanced && files?.depth_maps?.length > 0 && (
        <div className="files-section">
          <h2><Box size={20} /> Depth Maps (Sculptok) <span className="advanced-badge">Advanced</span></h2>
          <div className="images-grid">
            {files.depth_maps.map((img, i) => (
              <div key={i} className="image-card">
                <img src={`${API_BASE_URL}${img.url}`} alt={img.name} />
                <div className="image-card-footer">
                  <span className="image-type">Depth</span>
                  <button className="btn btn-small" onClick={() => downloadFile(img.url, img.name)}>
                    <Download size={14} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 1.4 Background Image [advanced] */}
      {showAdvanced && files?.background_image && (
        <div className="files-section">
          <h2><Image size={20} /> Background Image <span className="advanced-badge">Advanced</span></h2>
          <div className="images-grid">
            <div className="image-card" style={{ maxWidth: '300px' }}>
              <img src={`${API_BASE_URL}${files.background_image}`} alt="Background" />
              <div className="image-card-footer">
                <span className="image-type">Background</span>
                <button className="btn btn-small" onClick={() => downloadFile(files.background_image, `${order.job_id}_background.png`)}>
                  <Download size={14} />
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ================================================================ */}
      {/* 2. MANUFACTURING                                                */}
      {/* ================================================================ */}
      {order.status === 'completed' && (
        <div className="download-section">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
            <h2 style={{ margin: 0 }}><Package size={20} /> Manufacturing</h2>
            <div style={{ display: 'flex', gap: '20px' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '14px', color: '#64748b' }}>
                <input
                  type="checkbox"
                  checked={showKeychain}
                  onChange={(e) => setShowKeychain(e.target.checked)}
                  style={{ width: '16px', height: '16px', cursor: 'pointer' }}
                />
                Show Keychain
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '14px', color: '#64748b' }}>
                <input
                  type="checkbox"
                  checked={showAdvanced}
                  onChange={(e) => setShowAdvanced(e.target.checked)}
                  style={{ width: '16px', height: '16px', cursor: 'pointer' }}
                />
                Show Advanced
              </label>
            </div>
          </div>

          {/* ---- 2.1 Card ---- */}
          <h3 style={{ margin: '24px 0 12px', color: '#334155', fontSize: '18px' }}>Card</h3>
          {(files?.outputs?.stl_25d || files?.outputs?.texture_25d) ? (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '16px' }}>
              <div className="jig-side-card">
                <div className="jig-side-header">2.5D Card</div>
                {files?.outputs?.texture_25d && (
                  <div className="jig-side-thumb">
                    <img src={`${API_BASE_URL}${files.outputs.texture_25d}`} alt="Card Texture" />
                  </div>
                )}
                <div className="jig-side-actions">
                  {files?.outputs?.stl_25d && (
                    <button className="btn btn-small" onClick={() => downloadFile(files.outputs.stl_25d, `${order.job_id}_card.stl`)}>
                      <Download size={14} /> STL
                    </button>
                  )}
                  {files?.outputs?.texture_25d && (
                    <button className="btn btn-small" onClick={() => downloadFile(files.outputs.texture_25d, `${order.job_id}_card_texture.png`)} style={{ background: '#f59e0b' }}>
                      <Download size={14} /> PNG
                    </button>
                  )}
                  {showAdvanced && files?.outputs?.blend_25d && (
                    <button className="btn btn-small" onClick={() => downloadFile(files.outputs.blend_25d, `${order.job_id}_card.blend`)} style={{ background: '#f59e0b' }}>
                      <Download size={14} /> BLEND
                    </button>
                  )}
                </div>
              </div>
            </div>
          ) : (
            <p className="empty-text">No card files yet</p>
          )}

          {/* ---- 2.2 Figure ---- */}
          <h3 style={{ margin: '32px 0 12px', color: '#334155', fontSize: '18px' }}>Figure</h3>
          <div className="download-grid">
            {files?.outputs?.figure_stl && (
              <button className="download-card" onClick={() => downloadFile(files.outputs.figure_stl, `${order.job_id}_figure.stl`)}>
                <div className="download-icon stl">STL</div>
                <div className="download-info">
                  <span className="download-title">Figure STL</span>
                  <span className="download-desc">3D figure mesh for printing</span>
                </div>
                <Download size={20} />
              </button>
            )}
            {showAdvanced && files?.outputs?.figure_glb && (
              <button className="download-card" onClick={() => downloadFile(files.outputs.figure_glb, `${order.job_id}_figure.glb`)}>
                <div className="download-icon" style={{ background: '#8b5cf6' }}>GLB</div>
                <div className="download-info">
                  <span className="download-title">Figure GLB <span className="advanced-badge">Advanced</span></span>
                  <span className="download-desc">Textured 3D model from fal.ai</span>
                </div>
                <Download size={20} />
              </button>
            )}
          </div>

          {/* ---- Card Jigs ---- */}
          {files?.outputs?.card?.jigs?.length > 0 && (() => {
            const variant = files.outputs.card
            const axes = ['X', 'Y', 'Z']
            // Build per-side lookup maps
            const printMap = {}; (variant.printing_files || []).filter(p => p.type !== 'reference').forEach(p => { printMap[p.side] = p })
            const refMap = {}; (variant.printing_files || []).filter(p => p.type === 'reference').forEach(p => { refMap[p.side] = p })
            const cutMap = {}; (variant.cutting_files || []).forEach(c => { cutMap[c.side] = c })
            const sides = {}
            axes.forEach(ax => {
              sides[ax] = variant.jigs.filter(j => j.side.endsWith(ax)).sort((a, b) => a.side.startsWith('+') ? -1 : 1)
            })
            return (
              <>
                <h4 style={{ margin: '24px 0 12px', color: '#475569', fontSize: '15px' }}>Jigs</h4>
                {axes.filter(ax => sides[ax].length > 0).map(ax => (
                  <div key={ax} style={{ marginBottom: '20px' }}>
                    <h5 style={{ margin: '12px 0 8px', color: '#64748b', fontSize: '14px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>{ax}-Axis</h5>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '16px' }}>
                      {sides[ax].map(jig => {
                        const print = printMap[jig.side]
                        const ref = refMap[jig.side]
                        const cut = cutMap[jig.side]
                        return (
                          <div key={jig.side} className="jig-side-card">
                            <div className="jig-side-header">{jig.side}</div>
                            {print && (
                              <div className="jig-side-thumb">
                                <img src={`${API_BASE_URL}${print.url}`} alt={`Jig ${jig.side}`} />
                              </div>
                            )}
                            <div className="jig-side-actions">
                              <button className="btn btn-small" onClick={() => downloadFile(jig.url, jig.name)}>
                                <Download size={14} /> STL
                              </button>
                              {print && (
                                <button className="btn btn-small" onClick={() => downloadFile(print.url, print.name)} style={{ background: '#f59e0b' }}>
                                  <Download size={14} /> PNG
                                </button>
                              )}
                              {showAdvanced && ref && (
                                <button className="btn btn-small" onClick={() => downloadFile(ref.url, ref.name)} style={{ background: '#64748b' }}>
                                  <Download size={14} /> REF
                                </button>
                              )}
                              {showAdvanced && cut && (
                                <button className="btn btn-small" onClick={() => downloadFile(cut.url, cut.name)} style={{ background: '#ef4444' }}>
                                  <Download size={14} /> DXF
                                </button>
                              )}
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                ))}
                {showAdvanced && variant.blend && (
                  <div className="download-grid" style={{ marginTop: '8px' }}>
                    <button className="download-card" onClick={() => downloadFile(variant.blend, `${order.job_id}_card_jigs.blend`)}>
                      <div className="download-icon blend">BLEND</div>
                      <div className="download-info">
                        <span className="download-title">Card Jigs Blend <span className="advanced-badge">Advanced</span></span>
                        <span className="download-desc">Blender source for card jigs</span>
                      </div>
                      <Download size={20} />
                    </button>
                  </div>
                )}
              </>
            )
          })()}

          {/* ---- Keychain (toggled) ---- */}
          {showKeychain && files?.outputs?.keychain?.jigs?.length > 0 && (() => {
            const kc = files.outputs.keychain
            const axes = ['X', 'Y', 'Z']
            const printMap = {}; (kc.printing_files || []).filter(p => p.type !== 'reference').forEach(p => { printMap[p.side] = p })
            const refMap = {}; (kc.printing_files || []).filter(p => p.type === 'reference').forEach(p => { refMap[p.side] = p })
            const cutMap = {}; (kc.cutting_files || []).forEach(c => { cutMap[c.side] = c })
            const sides = {}
            axes.forEach(ax => {
              sides[ax] = kc.jigs.filter(j => j.side.endsWith(ax)).sort((a, b) => a.side.startsWith('+') ? -1 : 1)
            })
            return (
              <>
                <h3 style={{ margin: '32px 0 12px', color: '#334155', fontSize: '18px' }}>Keychain</h3>
                <div className="download-grid">
                  {kc.figure_stl && (
                    <button className="download-card" onClick={() => downloadFile(kc.figure_stl, `${order.job_id}_keychain_figure.stl`)}>
                      <div className="download-icon stl">STL</div>
                      <div className="download-info">
                        <span className="download-title">Keychain Figure STL</span>
                        <span className="download-desc">Figure mesh for keychain</span>
                      </div>
                      <Download size={20} />
                    </button>
                  )}
                </div>
                <h4 style={{ margin: '24px 0 12px', color: '#475569', fontSize: '15px' }}>Keychain Jigs</h4>
                {axes.filter(ax => sides[ax].length > 0).map(ax => (
                  <div key={ax} style={{ marginBottom: '20px' }}>
                    <h5 style={{ margin: '12px 0 8px', color: '#64748b', fontSize: '14px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>{ax}-Axis</h5>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '16px' }}>
                      {sides[ax].map(jig => {
                        const print = printMap[jig.side]
                        const ref = refMap[jig.side]
                        const cut = cutMap[jig.side]
                        return (
                          <div key={jig.side} className="jig-side-card">
                            <div className="jig-side-header">{jig.side}</div>
                            {print && (
                              <div className="jig-side-thumb">
                                <img src={`${API_BASE_URL}${print.url}`} alt={`Jig ${jig.side}`} />
                              </div>
                            )}
                            <div className="jig-side-actions">
                              <button className="btn btn-small" onClick={() => downloadFile(jig.url, jig.name)}>
                                <Download size={14} /> STL
                              </button>
                              {print && (
                                <button className="btn btn-small" onClick={() => downloadFile(print.url, print.name)} style={{ background: '#f59e0b' }}>
                                  <Download size={14} /> PNG
                                </button>
                              )}
                              {showAdvanced && ref && (
                                <button className="btn btn-small" onClick={() => downloadFile(ref.url, ref.name)} style={{ background: '#64748b' }}>
                                  <Download size={14} /> REF
                                </button>
                              )}
                              {showAdvanced && cut && (
                                <button className="btn btn-small" onClick={() => downloadFile(cut.url, cut.name)} style={{ background: '#ef4444' }}>
                                  <Download size={14} /> DXF
                                </button>
                              )}
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                ))}
                {showAdvanced && kc.blend && (
                  <div className="download-grid" style={{ marginTop: '8px' }}>
                    <button className="download-card" onClick={() => downloadFile(kc.blend, `${order.job_id}_keychain_jigs.blend`)}>
                      <div className="download-icon blend">BLEND</div>
                      <div className="download-info">
                        <span className="download-title">Keychain Jigs Blend <span className="advanced-badge">Advanced</span></span>
                        <span className="download-desc">Blender source for keychain jigs</span>
                      </div>
                      <Download size={20} />
                    </button>
                  </div>
                )}
              </>
            )
          })()}

          {/* ---- 2.3 Stickers ---- */}
          <h3 style={{ margin: '32px 0 12px', color: '#334155', fontSize: '18px' }}>Stickers</h3>
          {(files?.outputs?.sticker_front || files?.outputs?.sticker_back) ? (
            <div className="stickers-grid" style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
              gap: '24px'
            }}>
              {files?.outputs?.sticker_front && (
                <div style={{ background: '#f8fafc', borderRadius: '12px', padding: '16px', border: '1px solid #e2e8f0' }}>
                  <h4 style={{ margin: '0 0 12px 0', color: '#475569' }}>Front</h4>
                  <div style={{ background: '#fff', borderRadius: '8px', padding: '8px', marginBottom: '12px' }}>
                    <img src={`${API_BASE_URL}${files.outputs.sticker_front}`} alt="Front Sticker" style={{ width: '100%', height: 'auto', borderRadius: '4px', boxShadow: '0 2px 8px rgba(0,0,0,0.1)' }} />
                  </div>
                  <button className="btn btn-small" onClick={() => downloadFile(files.outputs.sticker_front, `${order.job_id}_sticker_front.png`)} style={{ width: '100%' }}>
                    <Download size={14} /> Download Front
                  </button>
                </div>
              )}
              {files?.outputs?.sticker_back && (
                <div style={{ background: '#f8fafc', borderRadius: '12px', padding: '16px', border: '1px solid #e2e8f0' }}>
                  <h4 style={{ margin: '0 0 12px 0', color: '#475569' }}>Back</h4>
                  <div style={{ background: '#fff', borderRadius: '8px', padding: '8px', marginBottom: '12px' }}>
                    <img src={`${API_BASE_URL}${files.outputs.sticker_back}`} alt="Back Sticker" style={{ width: '100%', height: 'auto', borderRadius: '4px', boxShadow: '0 2px 8px rgba(0,0,0,0.1)' }} />
                  </div>
                  <button className="btn btn-small" onClick={() => downloadFile(files.outputs.sticker_back, `${order.job_id}_sticker_back.png`)} style={{ width: '100%' }}>
                    <Download size={14} /> Download Back
                  </button>
                </div>
              )}
            </div>
          ) : (
            <p className="empty-text">No stickers generated yet</p>
          )}

          {!files?.outputs?.stl_25d && !files?.outputs?.figure_stl && !files?.outputs?.sticker_front && (
            <p className="empty-text">No manufacturing files available yet</p>
          )}
        </div>
      )}

      {/* ================================================================ */}
      {/* 3. TEXTURE PREVIEW                                              */}
      {/* ================================================================ */}
      {order.status === 'completed' && (files?.outputs?.texture_25d || files?.outputs?.texture) && (
        <>
          <div className="texture-actions" style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: '12px',
            marginTop: '24px'
          }}>
            <h2 style={{ margin: 0 }}><Paintbrush size={20} /> Texture Preview</h2>
            <button
              className="btn btn-secondary"
              onClick={handleRegenerateTexture}
              disabled={regeneratingTexture}
              style={{ display: 'flex', alignItems: 'center', gap: '8px' }}
            >
              <RefreshCw size={16} className={regeneratingTexture ? 'spinning' : ''} />
              {regeneratingTexture ? 'Regenerating...' : 'Regenerate Texture Only'}
            </button>
          </div>
          <TexturePreview
            textureUrl={files?.outputs?.texture_25d || order.texture_url || files?.outputs?.texture}
            baseUrl={API_BASE_URL}
          />
        </>
      )}

      {/* Processing Status */}
      {(order.status === 'pending' || order.status === 'processing') && (
        <div className="processing-section">
          <div className="processing-indicator">
            <RefreshCw size={24} className="spinning" />
            <div>
              <h3>{order.status === 'pending' ? 'Order Queued' : 'Processing Order'}</h3>
              <p>{order.status === 'pending'
                ? 'Your order is waiting in the queue...'
                : 'Generating images and 3D model... This may take several minutes.'}</p>
            </div>
          </div>
        </div>
      )}

      {/* Error Message */}
      {order.status === 'failed' && order.error_message && (
        <div className="error-section">
          <h3>Error Details</h3>
          <pre>{order.error_message}</pre>
        </div>
      )}
    </div>
  )
}
