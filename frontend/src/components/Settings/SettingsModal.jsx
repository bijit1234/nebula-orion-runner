import React, { useState } from 'react';
import { useTheme } from '../../context/ThemeContext';
import { useSettings } from '../../context/SettingsContext';
import api from '../../services/api';
import toast from 'react-hot-toast';
import {
  X, Sun, Moon, Monitor, Type, Terminal,
  User, Lock, RotateCcw, Eye, EyeOff
} from 'lucide-react';
import './SettingsModal.css';

const TABS = [
  { id: 'appearance', label: 'Appearance', icon: Monitor },
  { id: 'editor',     label: 'Editor',     icon: Type },
  { id: 'execution',  label: 'Execution',  icon: Terminal },
  { id: 'profile',    label: 'Profile',    icon: User },
];

export default function SettingsModal({ onClose }) {
  const { theme, toggleTheme } = useTheme();
  const { settings, updateSetting, resetSettings } = useSettings();

  const [activeTab, setActiveTab] = useState('appearance');
  const [oldPass, setOldPass]     = useState('');
  const [newPass, setNewPass]     = useState('');
  const [confirmPass, setConfirm] = useState('');
  const [showOld, setShowOld]     = useState(false);
  const [showNew, setShowNew]     = useState(false);
  const [savingPass, setSavingPass] = useState(false);

  const handleChangePassword = async (e) => {
    e.preventDefault();
    if (newPass !== confirmPass) { toast.error('Passwords do not match'); return; }
    if (newPass.length < 6)      { toast.error('Password must be at least 6 characters'); return; }
    setSavingPass(true);
    try {
      await api.post('/api/change-password', { old_password: oldPass, new_password: newPass });
      toast.success('Password changed successfully!');
      setOldPass(''); setNewPass(''); setConfirm('');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to change password');
    } finally {
      setSavingPass(false);
    }
  };

  const handleReset = () => {
    if (window.confirm('Reset all settings to defaults?')) {
      resetSettings();
      toast.success('Settings reset to defaults');
    }
  };

  return (
    <div className="settings-overlay" onClick={onClose}>
      <div className="settings-modal" onClick={e => e.stopPropagation()}>

        <div className="settings-header">
          <div className="settings-title">
            <span className="settings-icon">⚙️</span>
            <span>Settings</span>
          </div>
          <button className="settings-close" onClick={onClose}><X size={16} /></button>
        </div>

        <div className="settings-body">
          <nav className="settings-tabs">
            {TABS.map(tab => {
              const Icon = tab.icon;
              return (
                <button
                  key={tab.id}
                  className={`settings-tab ${activeTab === tab.id ? 'active' : ''}`}
                  onClick={() => setActiveTab(tab.id)}
                >
                  <Icon size={15} />
                  <span>{tab.label}</span>
                </button>
              );
            })}
            <button className="settings-tab reset-btn" onClick={handleReset}>
              <RotateCcw size={15} />
              <span>Reset</span>
            </button>
          </nav>

          <div className="settings-content">

            {/* APPEARANCE */}
            {activeTab === 'appearance' && (
              <div className="settings-panel">
                <h3 className="panel-title">Appearance</h3>
                <div className="setting-row">
                  <div className="setting-info">
                    <span className="setting-name">Theme</span>
                    <span className="setting-desc">Switch between dark and light mode</span>
                  </div>
                  <div className="theme-toggle">
                    <button className={`theme-btn ${theme === 'dark' ? 'active' : ''}`} onClick={() => theme !== 'dark' && toggleTheme()}>
                      <Moon size={14} /> Dark
                    </button>
                    <button className={`theme-btn ${theme === 'light' ? 'active' : ''}`} onClick={() => theme !== 'light' && toggleTheme()}>
                      <Sun size={14} /> Light
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* EDITOR */}
            {activeTab === 'editor' && (
              <div className="settings-panel">
                <h3 className="panel-title">Editor</h3>

                <div className="setting-row">
                  <div className="setting-info">
                    <span className="setting-name">Font Size</span>
                    <span className="setting-desc">Editor font size in pixels</span>
                  </div>
                  <div className="setting-control">
                    <select className="settings-select" value={settings.editorFontSize} onChange={e => updateSetting('editorFontSize', Number(e.target.value))}>
                      {[11, 12, 13, 14, 15, 16, 18, 20].map(s => <option key={s} value={s}>{s}px</option>)}
                    </select>
                  </div>
                </div>

                <div className="setting-row">
                  <div className="setting-info">
                    <span className="setting-name">Word Wrap</span>
                    <span className="setting-desc">Wrap long lines in the editor</span>
                  </div>
                  <label className="toggle-switch">
                    <input type="checkbox" checked={settings.wordWrap} onChange={e => updateSetting('wordWrap', e.target.checked)} />
                    <span className="toggle-slider" />
                  </label>
                </div>

                <div className="setting-row">
                  <div className="setting-info">
                    <span className="setting-name">Minimap</span>
                    <span className="setting-desc">Show code minimap on the right</span>
                  </div>
                  <label className="toggle-switch">
                    <input type="checkbox" checked={settings.minimap} onChange={e => updateSetting('minimap', e.target.checked)} />
                    <span className="toggle-slider" />
                  </label>
                </div>

                <div className="setting-row">
                  <div className="setting-info">
                    <span className="setting-name">Line Numbers</span>
                    <span className="setting-desc">Show line numbers in editor</span>
                  </div>
                  <label className="toggle-switch">
                    <input type="checkbox" checked={settings.lineNumbers} onChange={e => updateSetting('lineNumbers', e.target.checked)} />
                    <span className="toggle-slider" />
                  </label>
                </div>
              </div>
            )}

            {/* EXECUTION */}
            {activeTab === 'execution' && (
              <div className="settings-panel">
                <h3 className="panel-title">Execution</h3>

                <div className="setting-row">
                  <div className="setting-info">
                    <span className="setting-name">Python Path</span>
                    <span className="setting-desc">Python executable to run scripts</span>
                  </div>
                  <input className="settings-input" type="text" value={settings.pythonPath} onChange={e => updateSetting('pythonPath', e.target.value)} placeholder="python" spellCheck={false} />
                </div>

                <div className="setting-row">
                  <div className="setting-info">
                    <span className="setting-name">Execution Timeout</span>
                    <span className="setting-desc">Max seconds before auto-stopping</span>
                  </div>
                  <div className="setting-control">
                    <select className="settings-select" value={settings.execTimeout} onChange={e => updateSetting('execTimeout', Number(e.target.value))}>
                      {[10, 15, 30, 60, 120, 300].map(t => <option key={t} value={t}>{t}s</option>)}
                    </select>
                  </div>
                </div>

                <div className="setting-row info-row">
                  <div className="setting-info">
                    <span className="setting-name">Backend URL</span>
                    <span className="setting-desc">FastAPI server address</span>
                  </div>
                  <span className="setting-badge">{process.env.REACT_APP_API_URL || 'localhost:8000'}</span>
                </div>
              </div>
            )}

            {/* PROFILE */}
            {activeTab === 'profile' && (
              <div className="settings-panel">
                <h3 className="panel-title">Profile</h3>

                <div className="setting-row">
                  <div className="setting-info">
                    <span className="setting-name">Display Name</span>
                    <span className="setting-desc">Shown in the sidebar</span>
                  </div>
                  <input className="settings-input" type="text" value={settings.displayName} onChange={e => updateSetting('displayName', e.target.value)} placeholder="Your name" />
                </div>

                <div className="setting-row">
                  <div className="setting-info">
                    <span className="setting-name">Email</span>
                    <span className="setting-desc">Displayed under your name</span>
                  </div>
                  <input className="settings-input" type="email" value={settings.email} onChange={e => updateSetting('email', e.target.value)} placeholder="you@example.com" />
                </div>

                <div className="settings-divider" />
                <h4 className="sub-panel-title">Change Password</h4>

                <form onSubmit={handleChangePassword} className="password-form">
                  <div className="pass-field">
                    <label>Current Password</label>
                    <div className="pass-input-wrap">
                      <input type={showOld ? 'text' : 'password'} value={oldPass} onChange={e => setOldPass(e.target.value)} placeholder="Enter current password" className="settings-input" required />
                      <button type="button" className="pass-eye" onClick={() => setShowOld(p => !p)}>
                        {showOld ? <EyeOff size={14} /> : <Eye size={14} />}
                      </button>
                    </div>
                  </div>
                  <div className="pass-field">
                    <label>New Password</label>
                    <div className="pass-input-wrap">
                      <input type={showNew ? 'text' : 'password'} value={newPass} onChange={e => setNewPass(e.target.value)} placeholder="Min. 6 characters" className="settings-input" required />
                      <button type="button" className="pass-eye" onClick={() => setShowNew(p => !p)}>
                        {showNew ? <EyeOff size={14} /> : <Eye size={14} />}
                      </button>
                    </div>
                  </div>
                  <div className="pass-field">
                    <label>Confirm New Password</label>
                    <input type="password" value={confirmPass} onChange={e => setConfirm(e.target.value)} placeholder="Repeat new password" className="settings-input" required />
                  </div>
                  <button type="submit" className="btn-save-pass" disabled={savingPass || !oldPass || !newPass || !confirmPass}>
                    <Lock size={14} />
                    {savingPass ? 'Saving...' : 'Change Password'}
                  </button>
                </form>
              </div>
            )}

          </div>
        </div>
      </div>
    </div>
  );
}
