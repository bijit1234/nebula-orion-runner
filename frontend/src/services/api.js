import axios from 'axios';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add token interceptor
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Handle 401 responses (unauthorized)
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      window.location.href = '/';
    }
    return Promise.reject(error);
  }
);

// Auth operations
export const authService = {
  login: (username, password) => {
    const formData = new URLSearchParams();
    formData.append('username', username);
    formData.append('password', password);
    return api.post('/api/login', formData, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    });
  },
};

// File operations
export const fileService = {
  getFiles: () => api.get('/api/files'),
  uploadFile: (file) => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post('/api/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },
  getFileContent: (filename) => api.get(`/api/view/${encodeURIComponent(filename)}`),
  saveFile: (filename, content) => {
    const blob = new Blob([content], { type: 'text/plain' });
    const file = new File([blob], filename, { type: 'text/plain' });
    const formData = new FormData();
    formData.append('file', file);
    return api.put(`/api/edit/${encodeURIComponent(filename)}`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },
  deleteFile: (filename) => api.delete(`/api/files/${encodeURIComponent(filename)}`),
  renameFile: (oldName, newName) => 
    api.put(`/api/rename/${encodeURIComponent(oldName)}?new_name=${encodeURIComponent(newName)}`),
  createFile: (filename) => api.post(`/api/create/${encodeURIComponent(filename)}`),
  downloadFile: (filename) => api.get(`/api/download/${encodeURIComponent(filename)}`, {
    responseType: 'blob',
  }),
};

// Execution operations
export const executionService = {
  runFile: (filename) => api.post(`/api/run/${encodeURIComponent(filename)}`),
  stopFile: () => api.post('/api/stop'),
  getResult: (filename) => api.get(`/api/result/${encodeURIComponent(filename)}`),
  getHistory: () => api.get('/api/history'),
  clearHistory: () => api.delete('/api/history'),
};

export default api;