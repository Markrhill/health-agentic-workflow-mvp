const express = require('express');
const cors = require('cors');
const apiRoutes = require('./routes/api');
const { connectDB } = require('./database/connection');

const app = express();
const PORT = process.env.PORT || 3001;

// Middleware
app.use(cors());
app.use(express.json());

// Database connection
connectDB();

// Routes
app.use('/api', apiRoutes);

// Root endpoint
app.get('/', (req, res) => {
  res.json({
    message: 'Health Agentic Workflow MVP Backend API',
    version: '1.0.0',
    endpoints: {
      health: '/health',
      parameters: '/api/parameters',
      goals: '/api/goals',
      weekly: '/api/weekly',
      daily: '/api/daily/:startDate/:endDate',
      summary: '/api/summary'
    },
    documentation: 'See README.md for API usage examples'
  });
});

// Health check endpoint
app.get('/health', (req, res) => {
  res.json({ status: 'OK', timestamp: new Date().toISOString() });
});

// Error handling middleware
app.use((err, req, res, next) => {
  console.error('Error:', err);
  res.status(500).json({ error: 'Internal server error' });
});

app.listen(PORT, () => {
  console.log(`Health MVP Backend running on port ${PORT}`);
});
