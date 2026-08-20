import React, { useState, useEffect, useRef } from 'react';
import { useTheme } from '../../context/ThemeContext';
import { useFileSystem } from '../../hooks/useFileSystem';
import { useExecution } from '../../hooks/useExecution';
import toast from 'react-hot-toast';
import CodeEditor from '../Editor/CodeEditor';
import { useAuth } from '../../context/AuthContext';
import { fileService } from '../../services/api';
import { useSettings } from '../../context/SettingsContext';
import SettingsModal from '../Settings/SettingsModal';
import { 
  Sun, 
  Moon, 
  Play,
  Square,
  FolderOpen,
  ChevronDown,
  ChevronRight,
  Download,
  Trash2,
  Edit,
  RefreshCw,
  LogOut,
  User,
  Settings,
  Terminal as TerminalIcon,
  Upload,
  Plus,
  X,
  Check
} from 'lucide-react';
import './Layout.css';

const Layout = () => {
  const { theme, toggleTheme } = useTheme();
  const [activeTab, setActiveTab] = useState('terminal');
  const [expandedFolders, setExpandedFolders] = useState({
    'workspace': true,
  });
  const [showNewFileModal, setShowNewFileModal] = useState(false);
  const [newFileName, setNewFileName] = useState('');
  const [isCreating, setIsCreating] = useState(false);
  const newFileInputRef = useRef(null);
  
  const fileInputRef = useRef(null);

  const {
    files,
    selectedFile,
    fileContent,
    isLoading,
    loadFiles,
    loadFileContent,
    saveFileContent,
    uploadFile,
    deleteFile,
    setSelectedFile,
    setFileContent,
  } = useFileSystem();
  
  const {
    isRunning,
    output,
    history,
    executionStatus,
    runFile,
    stopFile,
    loadHistory,
    clearHistory,
    setOutput,
  } = useExecution();
  const { logout } = useAuth();
  const { settings } = useSettings();
  const [showSettings, setShowSettings] = useState(false);
  
  useEffect(() => {
    loadFiles();
    loadHistory();
  }, []);

  // Build dynamic file tree from uploaded files
  const buildFileTree = (fileList) => {
    if (!fileList || fileList.length === 0) {
      return { 'workspace': { type: 'folder', children: {} } };
    }

    const tree = {
      'workspace': {
        type: 'folder',
        children: {}
      }
    };

    fileList.forEach(filename => {
      tree.workspace.children[filename] = { type: 'file', icon: '🐍' };
    });

    return tree;
  };

  const dynamicFileStructure = buildFileTree(files);

  const toggleFolder = (path) => {
    setExpandedFolders(prev => ({
      ...prev,
      [path]: !prev[path]
    }));
  };

  const handleFileSelect = async (fullPath) => {
    // Strip any folder prefix (e.g. 'workspace/evil.py' -> 'evil.py')
    // so API calls use just the bare filename that the server knows about
    const filename = fullPath.split('/').pop();
    setSelectedFile(filename);
    await loadFileContent(filename);
    setActiveTab('editor');
  };

  const handleRunFile = async () => {
    if (!selectedFile) {
      toast.error('Please select a file first');
      return;
    }
    await runFile(selectedFile);
    setActiveTab('terminal');
  };

  const handleOpenNewFileModal = () => {
    setNewFileName('');
    setShowNewFileModal(true);
    // Focus input after modal renders
    setTimeout(() => newFileInputRef.current?.focus(), 50);
  };

  const handleCreateFile = async (e) => {
    e.preventDefault();
    let name = newFileName.trim();
    if (!name) return;

    // Auto-append .py if missing
    if (!name.endsWith('.py')) name = name + '.py';

    // Basic filename validation
    if (!/^[\w\-. ]+\.py$/.test(name)) {
      toast.error('Invalid filename. Use only letters, numbers, hyphens, underscores.');
      return;
    }

    setIsCreating(true);
    try {
      await fileService.createFile(name);
      toast.success(`File "${name}" created!`);
      setShowNewFileModal(false);
      setNewFileName('');
      await loadFiles();
      // Auto-select and open the new file
      setSelectedFile(name);
      await loadFileContent(name);
      setActiveTab('editor');
    } catch (error) {
      const msg = error.response?.data?.detail || 'Failed to create file';
      toast.error(msg);
    } finally {
      setIsCreating(false);
    }
  };

  const handleSaveFile = async () => {
    if (!selectedFile) {
      toast.error('No file selected');
      return;
    }
    await saveFileContent(selectedFile, fileContent);
    toast.success(`File "${selectedFile}" saved!`);
  };

  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    
    if (!file.name.endsWith('.py')) {
      toast.error('Only Python files are allowed');
      return;
    }
    
    await uploadFile(file);
    await loadFiles();
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    e.currentTarget.classList.add('dragover');
  };

  const handleDragLeave = (e) => {
    e.currentTarget.classList.remove('dragover');
  };

  const handleDrop = async (e) => {
    e.preventDefault();
    e.currentTarget.classList.remove('dragover');
    const file = e.dataTransfer.files[0];
    if (file && file.name.endsWith('.py')) {
      await uploadFile(file);
      await loadFiles();
    } else {
      toast.error('Only Python files are allowed');
    }
  };

  const handleStopFile = async () => {
    await stopFile();
  };

  const handleDeleteFile = async (filename) => {
    await deleteFile(filename);
    await loadFiles();
    if (selectedFile === filename) {
      setSelectedFile(null);
      setFileContent('');
    }
  };

  const renderFileTree = (node, path = '') => {
    if (node.type === 'file') {
      // Compare by basename so 'workspace/evil.py' still highlights when selectedFile is 'evil.py'
      const basename = path.split('/').pop();
      const isSelected = selectedFile === basename || selectedFile === path;
      return (
        <div 
          key={path}
          className={`file-item ${isSelected ? 'selected' : ''}`}
          onClick={() => handleFileSelect(path)}
        >
          <span className="file-icon">{node.icon}</span>
          <span className="file-name">{basename}</span>
          {isSelected && <Check size={12} className="file-check" />}
        </div>
      );
    }

    const isExpanded = expandedFolders[path] !== false;
    const folderName = path.split('/').pop() || path;

    return (
      <div key={path} className="folder-container">
        <div 
          className="folder-item"
          onClick={() => toggleFolder(path)}
        >
          <span className="folder-arrow">
            {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </span>
          <span className="folder-icon">📁</span>
          <span className="folder-name">{folderName}</span>
        </div>
        {isExpanded && node.children && (
          <div className="folder-children">
            {Object.entries(node.children).map(([name, child]) => {
              const childPath = path ? `${path}/${name}` : name;
              return renderFileTree(child, childPath);
            })}
          </div>
        )}
      </div>
    );
  };

  const getFileInfo = () => {
    if (!selectedFile) return null;
    return {
      name: selectedFile,
      type: 'Python File',
      location: `/workspace/src/`,
      size: '1.24 KB',
      lastModified: new Date().toLocaleString(),
      created: new Date().toLocaleString(),
      permissions: 'RW-F---F---'
    };
  };

  const fileInfo = getFileInfo();

  return (
    <div className="layout">
      {/* Left Sidebar - Explorer */}
      <aside className="sidebar-left">
        <div className="sidebar-header">
          <div className="brand">
            <span className="brand-icon">⚡</span>
            <div>
              <div className="brand-name">NEBULA</div>
              <div className="brand-sub">CLOUD CODE RUNNER</div>
            </div>
          </div>
        </div>

        <div className="explorer-section">
          <div className="section-header">
            <FolderOpen size={16} />
            <span>EXPLORER</span>
            <div className="section-actions">
              <button 
                className="section-btn" 
                onClick={() => fileInputRef.current?.click()}
                title="Upload file"
              >
                <Upload size={14} />
              </button>
              <button 
                className="section-btn" 
                onClick={handleOpenNewFileModal}
                title="New file"
              >
                <Plus size={14} />
              </button>
              <input
                ref={fileInputRef}
                type="file"
                accept=".py"
                style={{ display: 'none' }}
                onChange={handleFileUpload}
              />
            </div>
          </div>
          <div 
            className="file-tree"
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
          >
            {/* ✅ FIXED: Changed from fileStructure to dynamicFileStructure */}
            {Object.entries(dynamicFileStructure).map(([name, node]) => {
              const path = node.type === 'folder' ? name : name;
              return renderFileTree(node, path);
            })}
          </div>
        </div>

        <div className="cloud-sync">
          <div className="sync-header">
            <RefreshCw size={14} className="sync-icon" />
            <span>CLOUD SYNC</span>
          </div>
          <div className="sync-status">
            <span className="sync-time">Synced {isLoading ? '...' : '2m ago'}</span>
            <span className="sync-text">
              {isLoading ? 'Syncing...' : '✅ All files up to date'}
            </span>
          </div>
        </div>

        <div className="sidebar-footer">
          <div className="user-profile">
            <div className="user-avatar">
              <User size={18} />
              <span className="status-dot online"></span>
            </div>
            <div className="user-info">
              <span className="user-name">{settings.displayName}</span>
              <span className="user-email">{settings.email}</span>
            </div>
          </div>
          <div className="user-actions">
            <button className="icon-btn" onClick={toggleTheme}>
              {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
            </button>
            <button className="icon-btn" onClick={() => setShowSettings(true)} title="Settings">
              <Settings size={18} />
            </button>
            <button className="icon-btn" onClick={logout}>
              <LogOut size={18} />
            </button>
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <main className="main-content">
        <div className="tab-switcher">
          <button 
            className={`tab-btn ${activeTab === 'terminal' ? 'active' : ''}`}
            onClick={() => setActiveTab('terminal')}
          >
            <TerminalIcon size={16} />
            Terminal
          </button>
          <button 
            className={`tab-btn ${activeTab === 'editor' ? 'active' : ''}`}
            onClick={() => setActiveTab('editor')}
          >
            <Edit size={16} />
            Editor
          </button>
          {selectedFile && (
            <span className="selected-file-indicator">
              📄 {selectedFile}
            </span>
          )}
        </div>

        {activeTab === 'terminal' && (
          <div className="terminal-container">
            <div className="terminal-header">
              <div className="terminal-dots">
                <span className="dot red"></span>
                <span className="dot yellow"></span>
                <span className="dot green"></span>
              </div>
              <span className="terminal-title">TERMINAL</span>
              <div className="terminal-actions">
                <button 
                  className="terminal-btn" 
                  onClick={() => setOutput('')}
                  title="Clear output"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            </div>
            <div className="terminal-body">
              {output ? (
                <pre className="output-content">{output}</pre>
              ) : (
                <div className="output-placeholder">
                  <span className="prompt">$</span>
                  <span className="command">python main.py</span>
                  <div className="output-welcome">
                    Welcome to NEBULA Cloud Code Runner!
                  </div>
                  <div className="output-info">
                    Python Version: <span className="highlight">3.11.5</span>
                  </div>
                  <div className="output-info">
                    Current Time: <span className="highlight">
                      {new Date().toLocaleString()}
                    </span>
                  </div>
                  <div className="output-blank"></div>
                  <div className="output-ready">
                    <span className="check">✅</span> Ready to run your code!
                  </div>
                  <div className="output-blank"></div>
                  <div className="output-prompt">
                    <span className="prompt">nebula@cloud:~/workspace$</span>
                    <span className="cursor">▌</span>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {activeTab === 'editor' && (
          <div className="editor-view">
            <CodeEditor 
              fileContent={fileContent}
              fileName={selectedFile}
              onContentChange={setFileContent}
            />
            <div className="editor-actions">
              <button 
                className="btn btn-success"
                onClick={handleSaveFile}
                disabled={!selectedFile}
              >
                <Check size={16} /> Save
              </button>
              <button 
                className="btn btn-primary"
                onClick={handleRunFile}
                disabled={!selectedFile || isRunning}
              >
                <Play size={16} /> Run
              </button>
            </div>
          </div>
        )}
      </main>

      {/* Right Sidebar */}
      <aside className="sidebar-right">
        <div className="panel-section file-info-section">
          <div className="section-header">
            <span>FILE INFORMATION</span>
          </div>
          {fileInfo ? (
            <div className="file-info">
              <div className="file-name-display">
                <span className="file-icon-large">🐍</span>
                <span className="file-name-large">{fileInfo.name}</span>
              </div>
              <div className="info-grid">
                <div className="info-row">
                  <span className="info-label">Location</span>
                  <span className="info-value">{fileInfo.location}</span>
                </div>
                <div className="info-row">
                  <span className="info-label">Size</span>
                  <span className="info-value">{fileInfo.size}</span>
                </div>
                <div className="info-row">
                  <span className="info-label">Last Modified</span>
                  <span className="info-value">{fileInfo.lastModified}</span>
                </div>
                <div className="info-row">
                  <span className="info-label">Created</span>
                  <span className="info-value">{fileInfo.created}</span>
                </div>
                <div className="info-row">
                  <span className="info-label">Permissions</span>
                  <span className="info-value mono">{fileInfo.permissions}</span>
                </div>
              </div>
            </div>
          ) : (
            <div className="no-file-selected">
              <span className="empty-icon">📂</span>
              <p>Select a file from the explorer</p>
            </div>
          )}
        </div>

        <div className="panel-section controls-section">
          <div className="section-header">
            <span>EXECUTION CONTROLS</span>
          </div>
          <div className="controls">
            <button 
              className={`btn-run ${isRunning ? 'running' : ''}`}
              onClick={isRunning ? handleStopFile : handleRunFile}
              disabled={!selectedFile}
            >
              {isRunning ? (
                <>
                  <Square size={16} />
                  STOP CODE
                </>
              ) : (
                <>
                  <Play size={16} />
                  RUN CODE
                </>
              )}
            </button>
            <div className="env-info">
              <span className="env-label">Environment</span>
              <span className="env-value">Python 3.11.5</span>
            </div>
          </div>
        </div>

        <div className="panel-section status-section">
          <div className="section-header">
            <span>EXECUTION STATUS</span>
          </div>
          <div className="status-grid">
            <div className="status-item">
              <span className="status-label">Status</span>
              <span className={`status-value ${executionStatus.status.toLowerCase()}`}>
                ● {executionStatus.status}
              </span>
            </div>
            <div className="status-item">
              <span className="status-label">Last Run</span>
              <span className="status-value">{executionStatus.lastRun || 'Never'}</span>
            </div>
            <div className="status-item">
              <span className="status-label">Duration</span>
              <span className="status-value">{executionStatus.duration || '0'}s</span>
            </div>
            <div className="status-item">
              <span className="status-label">Memory</span>
              <span className="status-value">{executionStatus.memory || '0'} MB</span>
            </div>
            <div className="status-item">
              <span className="status-label">Exit Code</span>
              <span className={`status-value ${executionStatus.exitCode === 0 ? 'exit-zero' : 'exit-error'}`}>
                {executionStatus.exitCode !== null ? executionStatus.exitCode : '-'}
              </span>
            </div>
          </div>
        </div>

        <div className="panel-section settings-section">
          <div className="section-header">
            <span>ADVANCED SETTINGS</span>
          </div>
          <div className="settings-grid">
            <div className="setting-item">
              <span className="setting-label">⚙️ Python Path</span>
              <span className="setting-value">{settings.pythonPath}</span>
            </div>
            <div className="setting-item">
              <span className="setting-label">⏱️ Timeout</span>
              <span className="setting-value">{settings.execTimeout}s</span>
            </div>
            <div className="setting-item">
              <span className="setting-label">📦 Packages</span>
              <span className="setting-value">requirements.txt</span>
            </div>
          </div>
        </div>
      </aside>

      {/* ── Settings Modal ── */}
      {showSettings && <SettingsModal onClose={() => setShowSettings(false)} />}

      {/* ── New File Modal ── */}
      {showNewFileModal && (
        <div className="modal-overlay" onClick={() => setShowNewFileModal(false)}>
          <div className="modal-card" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <div className="modal-title">
                <span className="modal-icon">📄</span>
                <span>New Python File</span>
              </div>
              <button className="modal-close" onClick={() => setShowNewFileModal(false)}>
                <X size={16} />
              </button>
            </div>
            <form onSubmit={handleCreateFile} className="modal-body">
              <label className="modal-label">File name</label>
              <div className="modal-input-wrap">
                <input
                  ref={newFileInputRef}
                  className="modal-input"
                  type="text"
                  placeholder="e.g. hello_world"
                  value={newFileName}
                  onChange={e => setNewFileName(e.target.value)}
                  disabled={isCreating}
                  spellCheck={false}
                  autoComplete="off"
                />
                <span className="modal-input-hint">.py will be added automatically</span>
              </div>
              <div className="modal-actions">
                <button
                  type="button"
                  className="modal-btn modal-btn-cancel"
                  onClick={() => setShowNewFileModal(false)}
                  disabled={isCreating}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="modal-btn modal-btn-create"
                  disabled={!newFileName.trim() || isCreating}
                >
                  {isCreating ? 'Creating...' : 'Create File'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default Layout;