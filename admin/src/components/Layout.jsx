import { Outlet, Link, useLocation } from 'react-router-dom'
import { LayoutDashboard, Package, FlaskConical, Settings as SettingsIcon } from 'lucide-react'

export default function Layout() {
  const location = useLocation()

  const navItems = [
    { path: '/', icon: LayoutDashboard, label: 'Dashboard' },
    { path: '/orders', icon: Package, label: 'Orders' },
    { path: '/test', icon: FlaskConical, label: 'Test Orders' },
    { path: '/settings', icon: SettingsIcon, label: 'Settings' },
  ]

  return (
    <div className="app-layout">
      <aside className="sidebar">
        <div className="sidebar-header">
          <h1>SimpleMe</h1>
          <span>Admin</span>
        </div>
        <nav className="sidebar-nav">
          {navItems.map(item => (
            <Link
              key={item.path}
              to={item.path}
              className={`nav-item ${location.pathname === item.path ? 'active' : ''}`}
            >
              <item.icon size={20} />
              <span>{item.label}</span>
            </Link>
          ))}
        </nav>
      </aside>
      <main className="main-content">
        <Outlet />
      </main>
    </div>
  )
}
