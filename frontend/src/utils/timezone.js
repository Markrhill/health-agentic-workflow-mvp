/**
 * Timezone utilities for consistent date handling
 * 
 * Timezone is configured in backend .env as HEALTH_TZ (default: America/Los_Angeles)
 * Frontend uses browser's local timezone, which should match for Bay Area users.
 * 
 * For production: Fetch timezone from backend config API if needed.
 */

// Default timezone (should match .env HEALTH_TZ)
const DEFAULT_TIMEZONE = 'America/Los_Angeles';

/**
 * Parse YYYY-MM-DD string as local date (no timezone shift)
 * @param {string} dateString - Date in YYYY-MM-DD format
 * @returns {Date} - Local Date object
 */
export const parseLocalDate = (dateString) => {
  const [year, month, day] = dateString.split('-').map(Number);
  return new Date(year, month - 1, day);
};

/**
 * Convert Date object to YYYY-MM-DD string (local timezone)
 * @param {Date} date - Date object
 * @returns {string} - Date in YYYY-MM-DD format
 */
export const toLocalDateString = (date) => {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

/**
 * Get today's date in YYYY-MM-DD format (local timezone)
 * @returns {string} - Today's date in YYYY-MM-DD format
 */
export const getTodayLocal = () => {
  return toLocalDateString(new Date());
};

/**
 * Format date for display (e.g., "Oct 5")
 * @param {string} dateString - Date in YYYY-MM-DD format
 * @returns {string} - Formatted date (e.g., "Oct 5")
 */
export const formatDisplayDate = (dateString) => {
  const date = parseLocalDate(dateString);
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric'
  });
};

/**
 * Add days to a date string
 * @param {string} dateString - Date in YYYY-MM-DD format
 * @param {number} days - Number of days to add (can be negative)
 * @returns {string} - New date in YYYY-MM-DD format
 */
export const addDays = (dateString, days) => {
  const date = parseLocalDate(dateString);
  date.setDate(date.getDate() + days);
  return toLocalDateString(date);
};

/**
 * Get week end date (Monday + 6 days = Sunday)
 * @param {string} mondayDateString - Monday date in YYYY-MM-DD format
 * @returns {string} - Sunday date in YYYY-MM-DD format
 */
export const getWeekEnd = (mondayDateString) => {
  return addDays(mondayDateString, 6);
};

// Export default timezone for reference
export const TIMEZONE = DEFAULT_TIMEZONE;

