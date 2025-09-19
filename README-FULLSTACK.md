# Health Agentic Workflow MVP - Full Stack Application

A complete full-stack application for personalized health coaching with data-driven insights.

## 🏗️ Architecture

### Backend (Node.js + Express + PostgreSQL)
- **API Server**: Express.js REST API
- **Database**: PostgreSQL with connection pooling
- **Routes**: Health data endpoints
- **Port**: 3001

### Frontend (React)
- **UI Framework**: React 18 with functional components
- **Styling**: CSS Grid and Flexbox
- **API Integration**: Fetch-based service layer
- **Port**: 3000

## 🚀 Quick Start

### Prerequisites
- Node.js 16+ 
- PostgreSQL database
- DATABASE_URL environment variable

### Setup
```bash
# 1. Set up environment
export DATABASE_URL="postgresql://user:password@localhost:5432/database"

# 2. Run setup script
./scripts/setup.sh

# 3. Start development servers
./scripts/dev.sh
```

### Alternative Setup
```bash
# Install all dependencies
npm run install:all

# Start both servers
npm run dev
```

## 📁 Project Structure

```
health-agentic-workflow-mvp/
├── backend/                 # Node.js API server
│   ├── server.js           # Express server entry point
│   ├── database/           # Database layer
│   │   ├── connection.js   # PostgreSQL connection
│   │   └── queries.js      # SQL queries
│   └── routes/             # API routes
│       └── api.js          # Health data endpoints
├── frontend/               # React application
│   ├── src/
│   │   ├── components/     # React components
│   │   │   └── HealthMVP.jsx
│   │   ├── services/       # API service layer
│   │   │   └── api.js
│   │   └── App.js          # Main app component
│   └── public/             # Static assets
├── scripts/                # Development scripts
│   ├── setup.sh           # Environment setup
│   └── dev.sh             # Start dev servers
└── package.json           # Root package configuration
```

## 🔌 API Endpoints

### Health Data
- `GET /api/parameters` - Current model parameters
- `GET /api/weekly?limit=10` - Weekly aggregated data
- `GET /api/daily/:startDate/:endDate` - Daily data for specific week
- `GET /api/summary` - Health metrics summary
- `GET /api/health` - API health check

### System
- `GET /health` - Server health check

## 🎨 UI Features

### Weekly Dashboard
- Week picker with date range selection
- Fat mass trends (EMA smoothed)
- Energy balance tracking
- Data quality indicators
- Parameter transparency

### Daily Breakdown
- Day-by-day metrics
- Raw vs compensated exercise values
- Fat mass uncertainty estimates
- Imputation flags and methods

### Model Parameters
- Current parameter values
- Version tracking
- Transparency display

## 🛠️ Development

### Backend Development
```bash
cd backend
npm run dev          # Start with nodemon
npm test            # Run tests
npm run lint        # Lint code
```

### Frontend Development
```bash
cd frontend
npm start           # Start React dev server
npm test            # Run tests
npm run build       # Build for production
```

### Full Stack Development
```bash
npm run dev         # Start both servers
npm run lint        # Lint all code
npm test            # Run all tests
```

## 🔧 Configuration

### Environment Variables

#### Backend (.env)
```
PORT=3001
NODE_ENV=development
DATABASE_URL=postgresql://user:password@localhost:5432/database
```

#### Frontend (.env)
```
REACT_APP_API_URL=http://localhost:3001/api
```

## 📊 Data Flow

1. **Database**: PostgreSQL stores health metrics and parameters
2. **Backend API**: Express server queries database and serves JSON
3. **Frontend**: React app consumes API and renders UI
4. **Real-time**: Development servers auto-reload on changes

## 🚀 Deployment

### Production Build
```bash
# Build frontend
npm run build

# Start production servers
npm run start
```

### Environment Setup
- Set production DATABASE_URL
- Configure CORS for production domain
- Set NODE_ENV=production

## 🧪 Testing

### Backend Tests
```bash
cd backend
npm test
```

### Frontend Tests
```bash
cd frontend
npm test
```

### Full Test Suite
```bash
npm test
```

## 📝 Scripts Reference

- `./scripts/setup.sh` - Initial environment setup
- `./scripts/dev.sh` - Start development servers
- `npm run dev` - Start both servers concurrently
- `npm run install:all` - Install all dependencies
- `npm run lint` - Lint all code
- `npm test` - Run all tests

## 🔍 Troubleshooting

### Common Issues

1. **Database Connection Failed**
   - Check DATABASE_URL is set correctly
   - Verify PostgreSQL is running
   - Test connection with `psql $DATABASE_URL`

2. **Port Already in Use**
   - Backend (3001): Change PORT in backend/.env
   - Frontend (3000): React will prompt to use different port

3. **CORS Issues**
   - Check REACT_APP_API_URL matches backend port
   - Verify backend CORS configuration

4. **Missing Dependencies**
   - Run `npm run install:all`
   - Check Node.js version (16+ required)

## 📚 Next Steps

1. **Data Visualization**: Add charts for fat mass trends
2. **Real-time Updates**: WebSocket integration
3. **User Authentication**: Add user management
4. **Mobile Responsive**: Optimize for mobile devices
5. **Testing**: Add comprehensive test coverage
6. **Deployment**: Docker containerization
