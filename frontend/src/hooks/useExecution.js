import { useState, useCallback, useRef, useEffect } from 'react';
import toast from 'react-hot-toast';
import { executionService } from '../services/api';

export const useExecution = () => {
  const [isRunning, setIsRunning] = useState(false);
  const [output, setOutput] = useState('');
  const [history, setHistory] = useState([]);
  const [executionStatus, setExecutionStatus] = useState({
    status: 'Ready',
    lastRun: null,
    duration: 0,
    memory: 0,
    exitCode: null,
  });

  // Refs for polling
  const pollingIntervalRef = useRef(null);
  const currentFilenameRef = useRef(null);

  // Stop polling function
  const stopPolling = useCallback(() => {
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current);
      pollingIntervalRef.current = null;
    }
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => stopPolling();
  }, [stopPolling]);

  // Load history - defined first so it's available
  const loadHistory = useCallback(async () => {
    try {
      const response = await executionService.getHistory();
      setHistory(response.data.history || []);
    } catch (error) {
      console.error('Failed to load history:', error);
    }
  }, []);

  // Poll result - now loadHistory is defined
  const pollResult = useCallback(async (filename) => {
    console.log(`🔍 Polling result for: "${filename}"`);
    try {
      const response = await executionService.getResult(filename);
      const data = response.data;
      console.log('📦 Poll response:', data);

      if (!data.finished) {
        // Still running, keep polling (handled by interval)
        return;
      }

      // Finished - stop polling
      stopPolling();
      setIsRunning(false);
      
      if (data.status === 'Finished') {
        setExecutionStatus({
          status: 'Finished',
          lastRun: 'Just now',
          duration: data.execution_time || 0,
          memory: data.memory_usage || 0,
          exitCode: data.return_code || 0,
        });
        setOutput(data.output || '✅ Execution completed successfully!');
        toast.success('Execution completed!');
      } else {
        setExecutionStatus({
          status: 'Error',
          lastRun: 'Just now',
          duration: data.execution_time || 0,
          memory: 0,
          exitCode: data.return_code || -1,
        });
        setOutput(`❌ Error:\n${data.error || 'Execution failed'}`);
        toast.error('Execution failed');
      }

      // Load history
      await loadHistory();

    } catch (error) {
      console.error('Poll error:', error);
      // If error is 404, file might not be running
      if (error.response?.status === 404) {
        stopPolling();
        setIsRunning(false);
        setExecutionStatus(prev => ({ ...prev, status: 'Error' }));
        setOutput(`❌ File not found or not running. Please try again.`);
        toast.error('File not found or not running');
      } else {
        // Other errors - keep polling? better to stop
        stopPolling();
        setIsRunning(false);
        setExecutionStatus(prev => ({ ...prev, status: 'Error' }));
        setOutput(`❌ Polling error: ${error.message}`);
        toast.error('Error checking result');
      }
    }
  }, [stopPolling, loadHistory]);

  // Run file
  const runFile = useCallback(async (filename) => {
    if (!filename) {
      toast.error('No file selected');
      return;
    }

    // Clean filename
    const cleanFilename = filename.trim();
    console.log(`🚀 Running file: "${cleanFilename}"`);
    currentFilenameRef.current = cleanFilename;

    // Stop any previous polling
    stopPolling();

    try {
      setIsRunning(true);
      setOutput(`⏳ Running ${cleanFilename}...\n`);
      setExecutionStatus(prev => ({ ...prev, status: 'Running' }));

      const response = await executionService.runFile(cleanFilename);
      console.log('📦 Run response:', response.data);

      if (response.data.running) {
        // Use the backend-cleaned filename (strips 'workspace/' prefix etc.)
        // so the poll key exactly matches what the runner stored
        const pollFilename = response.data.filename || cleanFilename;
        currentFilenameRef.current = pollFilename;

        // Start polling every 500ms
        pollingIntervalRef.current = setInterval(() => {
          pollResult(pollFilename);
        }, 500);
        // Also poll immediately
        pollResult(pollFilename);
      } else {
        // Not running - error
        setIsRunning(false);
        setExecutionStatus(prev => ({ ...prev, status: 'Error' }));
        setOutput(`❌ ${response.data.message || 'Failed to start'}`);
        toast.error(response.data.message || 'Failed to start');
      }
    } catch (error) {
      console.error('Run error:', error);
      setIsRunning(false);
      setExecutionStatus(prev => ({ ...prev, status: 'Error' }));
      const msg = error.response?.data?.detail || error.message || 'Failed to run file';
      setOutput(`❌ ${msg}`);
      toast.error(msg);
    }
  }, [pollResult, stopPolling]);

  // Stop file
  const stopFile = useCallback(async () => {
    try {
      await executionService.stopFile();
      stopPolling();
      setIsRunning(false);
      setExecutionStatus(prev => ({ ...prev, status: 'Stopped' }));
      setOutput(prev => prev + '\n🛑 Program stopped by user');
      toast.success('Program stopped');
    } catch (error) {
      toast.error('Failed to stop program');
      console.error(error);
    }
  }, [stopPolling]);

  // Clear history
  const clearHistory = useCallback(async () => {
    try {
      await executionService.clearHistory();
      setHistory([]);
      toast.success('History cleared');
    } catch (error) {
      toast.error('Failed to clear history');
      console.error(error);
    }
  }, []);

  return {
    isRunning,
    output,
    history,
    executionStatus,
    runFile,
    stopFile,
    loadHistory,
    clearHistory,
    setOutput,
    setExecutionStatus,
  };
};