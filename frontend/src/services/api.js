const API_BASE = 'http://localhost:3001/api';

class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

const apiRequest = async (endpoint, options = {}) => {
  const url = `${API_BASE}${endpoint}`;
  const config = {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  };

  try {
    const response = await fetch(url, config);
    
    if (!response.ok) {
      throw new ApiError(`HTTP error! status: ${response.status}`, response.status);
    }
    
    const data = await response.json();
    return data;
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
    throw new ApiError(`Network error: ${error.message}`, 0);
  }
};

// API methods - simplified to match actual backend routes
export const getWeeklyData = (weeks = 10) => {
  return apiRequest(`/weekly?weeks=${weeks}`);
};

export const getDailyData = (startDate, endDate) => {
  return apiRequest(`/daily/${startDate}/${endDate}`);
};

export const getParameters = () => {
  return apiRequest('/parameters');
};

export const getHealthMetricsSummary = () => {
  return apiRequest('/summary');
};

export const healthCheck = () => {
  return apiRequest('/health');
};

// Legacy method names for backward compatibility
export const getCurrentParameters = getParameters;
export const getDailyDataForWeek = getDailyData;

export default {
  getWeeklyData,
  getDailyData,
  getParameters,
  getHealthMetricsSummary,
  healthCheck,
  // Legacy exports
  getCurrentParameters,
  getDailyDataForWeek,
};
