const { Pool, types } = require('pg');

// Prevent pg from converting DATE fields to JavaScript Date objects
types.setTypeParser(1082, val => val);

let pool;

const connectDB = () => {
  if (pool) {
    return pool;
  }

  pool = new Pool({
    connectionString: process.env.DATABASE_URL,
    ssl: process.env.NODE_ENV === 'production' ? { rejectUnauthorized: false } : false,
  });

  pool.on('error', (err) => {
    console.error('Unexpected error on idle client', err);
    process.exit(-1);
  });

  return pool;
};

const getPool = () => {
  if (!pool) {
    connectDB();
  }
  return pool;
};

module.exports = {
  connectDB,
  getPool
};
