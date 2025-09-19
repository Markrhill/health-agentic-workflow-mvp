const express = require('express');
const router = express.Router();
const {
  getCurrentParameters,
  getWeeklyData,
  getDailyDataForWeek,
  getHealthMetricsSummary
} = require('../database/queries');

// Get current model parameters
router.get('/parameters', async (req, res) => {
  try {
    const parameters = await getCurrentParameters();
    res.json(parameters);
  } catch (error) {
    console.error('Error fetching parameters:', error);
    res.status(500).json({ error: 'Failed to fetch parameters' });
  }
});

// Get weekly data for UI
router.get('/weekly', async (req, res) => {
  try {
    const limit = parseInt(req.query.limit) || 10;
    const weeklyData = await getWeeklyData(limit);
    res.json(weeklyData);
  } catch (error) {
    console.error('Error fetching weekly data:', error);
    res.status(500).json({ error: 'Failed to fetch weekly data' });
  }
});

// Get daily data for specific week
router.get('/daily/:startDate/:endDate', async (req, res) => {
  try {
    const { startDate, endDate } = req.params;
    const dailyData = await getDailyDataForWeek(startDate, endDate);
    res.json(dailyData);
  } catch (error) {
    console.error('Error fetching daily data:', error);
    res.status(500).json({ error: 'Failed to fetch daily data' });
  }
});

// Get health metrics summary
router.get('/summary', async (req, res) => {
  try {
    const summary = await getHealthMetricsSummary();
    res.json(summary);
  } catch (error) {
    console.error('Error fetching health summary:', error);
    res.status(500).json({ error: 'Failed to fetch health summary' });
  }
});

// Health check endpoint
router.get('/health', (req, res) => {
  res.json({ status: 'API OK', timestamp: new Date().toISOString() });
});

module.exports = router;
