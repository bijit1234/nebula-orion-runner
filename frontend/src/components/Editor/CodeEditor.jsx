import React, { useEffect, useRef } from 'react';
import Editor from '@monaco-editor/react';
import { useSettings } from '../../context/SettingsContext';
import './CodeEditor.css';

const CodeEditor = ({ fileContent, fileName, onContentChange, readOnly = false }) => {
  const editorRef = useRef(null);
  const { settings } = useSettings();

  const handleEditorDidMount = (editor, monaco) => {
    editorRef.current = editor;
    editor.updateOptions({
      fontSize: settings.editorFontSize,
      fontFamily: 'JetBrains Mono, monospace',
      minimap: { enabled: settings.minimap },
      scrollBeyondLastLine: false,
      lineNumbers: settings.lineNumbers ? 'on' : 'off',
      renderWhitespace: 'selection',
      wordWrap: settings.wordWrap ? 'on' : 'off',
      tabSize: 4,
      insertSpaces: true,
    });

    monaco.languages.register({ id: 'python' });
    monaco.languages.setLanguageConfiguration('python', {
      comments: { lineComment: '#' },
    });
  };

  const handleEditorChange = (value) => {
    if (onContentChange) {
      onContentChange(value);
    }
  };

  // Live-apply settings changes without remounting the editor
  useEffect(() => {
    if (editorRef.current) {
      editorRef.current.updateOptions({
        fontSize: settings.editorFontSize,
        minimap: { enabled: settings.minimap },
        lineNumbers: settings.lineNumbers ? 'on' : 'off',
        wordWrap: settings.wordWrap ? 'on' : 'off',
      });
    }
  }, [settings.editorFontSize, settings.minimap, settings.lineNumbers, settings.wordWrap]);

  return (
    <div className="code-editor-container">
      <div className="editor-tabs">
        <div className={`editor-tab ${fileName ? 'active' : ''}`}>
          <span className="tab-icon">🐍</span>
          <span className="tab-name">{fileName || 'untitled.py'}</span>
          {!readOnly && (
            <button className="tab-close" onClick={() => {}}>×</button>
          )}
        </div>
      </div>
      <Editor
        height="100%"
        defaultLanguage="python"
        value={fileContent || '# Write your Python code here\n\nprint("Hello, NEBULA!")'}
        onChange={handleEditorChange}
        onMount={handleEditorDidMount}
        theme="vs-dark"
        options={{
          readOnly: readOnly,
          automaticLayout: true,
        }}
      />
    </div>
  );
};

export default CodeEditor;