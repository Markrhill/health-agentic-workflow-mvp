import React from 'react';
import HealthMVP from './components/HealthMVP';
import './App.css';

function App() {
  return (
    <div className="App">
      <header className="App-header">
        <h1>Health Agentic Workflow MVP</h1>
        <p>Personalized health coaching with data-driven insights</p>
      </header>
      <main>
        <HealthMVP />
      </main>
    </div>
  );
}

export default App;
