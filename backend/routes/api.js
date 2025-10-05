const express = require('express');
const router = express.Router();
const { exec } = require('child_process');
const path = require('path');
const {
  getCurrentParameters,
  getCurrentPerformanceGoals,
  getWeeklyData,
  getDailyDataForWeek,
  getHealthMetricsSummary
} = require('../database/queries');

// Health check endpoint
router.get('/health', (req, res) => {
  res.json({ 
    status: 'ok', 
    timestamp: new Date().toISOString(),
    service: 'health-agentic-workflow-backend'
  });
});

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

// Get current performance goals
router.get('/goals', async (req, res) => {
  try {
    const goals = await getCurrentPerformanceGoals();
    res.json(goals);
  } catch (error) {
    console.error('Error fetching performance goals:', error);
    res.status(500).json({ error: 'Failed to fetch performance goals' });
  }
});

// Get weekly data for UI
router.get('/weekly', async (req, res) => {
  try {
    const limit = parseInt(req.query.limit) || 52;
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

// Manual data refresh endpoint - triggers HAE import and materialization
router.post('/refresh', async (req, res) => {
  try {
    const { date } = req.body;
    const targetDate = date || new Date().toISOString().split('T')[0]; // Default to today (for partial data updates)
    
    console.log(`[API] Manual refresh triggered for ${targetDate}`);
    
    // Get project root (backend is one level down from root)
    const projectRoot = path.resolve(__dirname, '../..');
    const wrapperScript = path.join(projectRoot, 'backend/ingest/hae_daily_pipeline_wrapper.sh');
    
    // Execute the pipeline wrapper script
    exec(`bash "${wrapperScript}" "${targetDate}"`, 
      { cwd: projectRoot, maxBuffer: 1024 * 1024 * 10 }, // 10MB buffer
      (error, stdout, stderr) => {
        if (error) {
          console.error(`[API] Refresh failed for ${targetDate}:`, error);
          console.error('STDERR:', stderr);
          res.status(500).json({ 
            success: false, 
            error: error.message,
            stderr: stderr,
            date: targetDate
          });
          return;
        }
        
        console.log(`[API] Refresh completed for ${targetDate}`);
        console.log('STDOUT:', stdout);
        
        res.json({ 
          success: true, 
          message: `Data refreshed for ${targetDate}`,
          date: targetDate,
          output: stdout
        });
      }
    );
  } catch (error) {
    console.error('[API] Refresh endpoint error:', error);
    res.status(500).json({ 
      success: false, 
      error: error.message 
    });
  }
});

// Health check endpoint
router.get('/health', (req, res) => {
  res.json({ status: 'API OK', timestamp: new Date().toISOString() });
});

module.exports = router;
