import { useState, useCallback } from 'react';
import toast from 'react-hot-toast';
import { fileService } from '../services/api';

export const useFileSystem = () => {
  const [files, setFiles] = useState([]);
  const [selectedFile, setSelectedFile] = useState(null);
  const [fileContent, setFileContent] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const loadFiles = useCallback(async () => {
    try {
      setIsLoading(true);
      const response = await fileService.getFiles();
      setFiles(response.data.files || []);
    } catch (error) {
      toast.error('Failed to load files');
      console.error(error);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const loadFileContent = useCallback(async (filename) => {
    try {
      setIsLoading(true);
      const response = await fileService.getFileContent(filename);
      setFileContent(response.data.content || '');
      setSelectedFile(filename);
    } catch (error) {
      toast.error('Failed to load file content');
      console.error(error);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const saveFileContent = useCallback(async (filename, content) => {
    try {
      setIsLoading(true);
      await fileService.saveFile(filename, content);
      toast.success(`File "${filename}" saved successfully!`);
    } catch (error) {
      toast.error('Failed to save file');
      console.error(error);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const uploadFile = useCallback(async (file) => {
    try {
      setIsLoading(true);
      const response = await fileService.uploadFile(file);
      toast.success(`File "${file.name}" uploaded successfully!`);
      await loadFiles();
      return response.data;
    } catch (error) {
      toast.error('Failed to upload file');
      console.error(error);
    } finally {
      setIsLoading(false);
    }
  }, [loadFiles]);

  const deleteFile = useCallback(async (filename) => {
    if (!window.confirm(`Are you sure you want to delete "${filename}"?`)) return;
    
    try {
      setIsLoading(true);
      await fileService.deleteFile(filename);
      toast.success(`File "${filename}" deleted!`);
      if (selectedFile === filename) {
        setSelectedFile(null);
        setFileContent('');
      }
      await loadFiles();
    } catch (error) {
      toast.error('Failed to delete file');
      console.error(error);
    } finally {
      setIsLoading(false);
    }
  }, [selectedFile, loadFiles]);

  return {
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
  };
};