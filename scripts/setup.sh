#!/bin/bash

# Health Agentic Workflow MVP - Setup Script
# This script sets up the development environment

set -e

echo "🏥 Setting up Health Agentic Workflow MVP..."

# Check if Node.js is installed
if ! command -v node &> /dev/null; then
    echo "❌ Node.js is not installed. Please install Node.js 16+ first."
    exit 1
fi

# Check Node.js version
NODE_VERSION=$(node -v | cut -d'v' -f2 | cut -d'.' -f1)
if [ "$NODE_VERSION" -lt 16 ]; then
    echo "❌ Node.js version 16+ is required. Current version: $(node -v)"
    exit 1
fi

echo "✅ Node.js version: $(node -v)"

# Check if DATABASE_URL is set
if [ -z "$DATABASE_URL" ]; then
    echo "❌ DATABASE_URL environment variable is not set."
    echo "Please set it to your PostgreSQL connection string:"
    echo "export DATABASE_URL='postgresql://user:password@localhost:5432/database'"
    exit 1
fi

echo "✅ DATABASE_URL is set"

# Install backend dependencies
echo "📦 Installing backend dependencies..."
cd backend
npm install
cd ..

# Install frontend dependencies
echo "📦 Installing frontend dependencies..."
cd frontend
npm install
cd ..

# Create .env files if they don't exist
if [ ! -f backend/.env ]; then
    echo "📝 Creating backend .env file..."
    cat > backend/.env << EOF
PORT=3001
NODE_ENV=development
DATABASE_URL=$DATABASE_URL
EOF
fi

if [ ! -f frontend/.env ]; then
    echo "📝 Creating frontend .env file..."
    cat > frontend/.env << EOF
REACT_APP_API_URL=http://localhost:3001/api
EOF
fi

echo "✅ Environment files created"

# Test database connection
echo "🔍 Testing database connection..."
cd backend
node -e "
const { connectDB } = require('./database/connection');
connectDB().query('SELECT 1')
  .then(() => {
    console.log('✅ Database connection successful');
    process.exit(0);
  })
  .catch((err) => {
    console.error('❌ Database connection failed:', err.message);
    process.exit(1);
  });
"
cd ..

echo ""
echo "🎉 Setup complete! You can now run:"
echo "  ./scripts/dev.sh    # Start development servers"
echo "  npm run dev         # Alternative: start both servers"
echo ""
echo "📚 Next steps:"
echo "  1. Run ./scripts/dev.sh to start the development servers"
echo "  2. Open http://localhost:3000 to view the application"
echo "  3. Backend API will be available at http://localhost:3001"
