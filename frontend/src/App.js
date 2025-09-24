import React from 'react';
import HealthMVP from './components/HealthMVP';

function App() {
  return (
    <div className="min-h-screen bg-gray-100">
      <header className="bg-gray-800 text-white py-8 px-6 mb-8 shadow-lg">
        <div className="max-w-6xl mx-auto">
          <h1 className="text-4xl font-bold mb-3">Health Agentic Workflow MVP - Dynamic Goals Active</h1>
          <p className="text-xl opacity-90">Personalized health coaching with data-driven insights</p>
        </div>
      </header>
      <main className="max-w-6xl mx-auto px-6 pb-8">
        <div className="bg-white rounded-lg shadow-lg p-8">
          <HealthMVP />
        </div>
      </main>
    </div>
  );
}

export default App;
