import React, { useState, useEffect } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { getWeeklyData, getDailyData, getParameters } from '../services/api';

const HealthMVP = () => {
  const [selectedWeekIndex, setSelectedWeekIndex] = useState(0);
  const [weeklyData, setWeeklyData] = useState([]);
  const [dailyData, setDailyData] = useState([]);
  const [parameters, setParameters] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Load daily data when week selection changes
  const loadDailyDataForWeek = async (weekIndex) => {
    try {
      const week = weeklyData[weekIndex];
      if (!week) return;
      
      const weekStart = new Date(week.week_start_monday);
      const weekEnd = new Date(weekStart);
      weekEnd.setDate(weekStart.getDate() + 6);
      
      const dailyData = await getDailyData(
        week.week_start_monday,
        weekEnd.toISOString().split('T')[0]
      );
      
      setDailyData(dailyData);
      
    } catch (err) {
      console.error('Daily data error:', err);
    }
  };

  const handleWeekChange = async (direction) => {
    const newIndex = direction === 'prev' ? selectedWeekIndex + 1 : selectedWeekIndex - 1;
    if (newIndex >= 0 && newIndex < weeklyData.length) {
      setSelectedWeekIndex(newIndex);
      await loadDailyDataForWeek(newIndex);
    }
  };

  const formatDate = (dateString) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric'
    });
  };

  useEffect(() => {
    const loadData = async () => {
      try {
        setLoading(true);
        
        const [weeklyData, parametersData] = await Promise.all([
          getWeeklyData(10),
          getParameters()
        ]);
        
        setWeeklyData(weeklyData);
        setParameters(parametersData);
        
        // Load daily data for first week
        if (weeklyData.length > 0) {
          await loadDailyDataForWeek(0);
        }
        
      } catch (err) {
        setError(`Failed to load data: ${err.message}`);
      } finally {
        setLoading(false);
      }
    };
    
    loadData();
  }, []);

  if (loading) return <div className="p-6 text-center">Loading...</div>;
  if (error) return <div className="p-6 text-red-600">Error: {error}</div>;

  const currentWeek = weeklyData[selectedWeekIndex];
  
  // Transform API data to match the visual component structure
  const currentWeekData = currentWeek && dailyData.length > 0 ? {
    weekStart: formatDate(currentWeek.week_start_monday).split(' ')[0] + ' ' + formatDate(currentWeek.week_start_monday).split(' ')[1],
    weekEnd: formatDate(new Date(new Date(currentWeek.week_start_monday).getTime() + 6 * 24 * 60 * 60 * 1000)).split(' ')[0] + ' ' + formatDate(new Date(new Date(currentWeek.week_start_monday).getTime() + 6 * 24 * 60 * 60 * 1000)).split(' ')[1],
    dailyData: dailyData.map(day => ({
      day: day.day_name.trim().substring(0, 3),
      date: day.fact_date.split('T')[0].substring(5).replace('-', '-'),
      fatMassLbs: parseFloat(day.fat_mass_ema_lbs || 0),
      netKcal: Math.round(parseFloat(day.net_kcal || 0)),
      intake: Math.round(parseFloat(day.intake_kcal || 0)),
      rawExercise: Math.round(parseFloat(day.raw_exercise_kcal || 0)),
      compensatedExercise: Math.round(parseFloat(day.compensated_exercise_kcal || 0)),
      rawFatMass: parseFloat(day.raw_fat_mass_lbs || day.fat_mass_ema_lbs || 0),
      uncertainty: parseFloat(day.fat_mass_uncertainty_lbs || 0)
    })),
    trendData: weeklyData.slice(0, 13).map(week => ({
      date: formatDate(week.week_start_monday).split(' ')[0] + ' ' + formatDate(week.week_start_monday).split(' ')[1],
      fatMass: parseFloat(week.avg_fat_mass_ema || 0) * 2.20462, // Convert kg to lbs
      raw: parseFloat(week.avg_fat_mass_ema || 0) * 2.20462 // Use same value for now
    }))
  } : null;
  
  // Calculate dynamic range for bar chart
  const chartData = currentWeekData ? (() => {
    const days = currentWeekData.dailyData;
    const maxIntake = Math.max(...days.map(d => d.intake));
    const maxExercise = Math.max(...days.map(d => d.rawExercise));
    const maxNet = Math.max(...days.map(d => Math.abs(d.netKcal)));
    const chartMax = Math.ceil(Math.max(maxIntake, maxExercise, maxNet) / 500) * 500;
    const avgBMR = 1625; // Average BMR for the week
    
    // Calculate weekly averages
    const avgIntake = Math.round(days.reduce((sum, day) => sum + day.intake, 0) / days.length);
    const avgExercise = Math.round(days.reduce((sum, day) => sum + day.rawExercise, 0) / days.length);
    const avgNet = Math.round(days.reduce((sum, day) => sum + day.netKcal, 0) / days.length);
    
    return {
      chartMax,
      avgBMR,
      avgIntake,
      avgExercise,
      avgNet
    };
  })() : null;
  
  // Calculate weekly stats
  const weeklyStats = currentWeekData ? (() => {
    const days = currentWeekData.dailyData;
    const weeklyNetKcal = days.reduce((sum, day) => sum + day.netKcal, 0) / days.length;
    const targetDays = days.filter(day => day.netKcal <= -500).length; // Count days with net ≤ -500
    const startFatMass = currentWeekData.trendData[11]?.fatMass || 0; // Jul 20 value
    const endFatMass = currentWeekData.trendData[12]?.fatMass || 0; // Aug 3 value
    const actualChange = endFatMass - startFatMass;
    
    return {
      weeklyNetKcal: Math.round(weeklyNetKcal),
      targetDays,
      totalDays: days.length,
      startFatMass: startFatMass.toFixed(1),
      endFatMass: endFatMass.toFixed(1),
      actualChange: actualChange.toFixed(1),
      predictedChange: -0.2,
      uncertainty: 0.4,
      targetDeficit: -500 // Target daily deficit from schema
    };
  })() : null;

  return (
    <div className="max-w-6xl mx-auto p-6 bg-gray-50 min-h-screen">
      {/* 13-Week Fat Mass Trend */}
      <div className="bg-white rounded-lg shadow-sm p-6 mb-6">
        <h2 className="text-xl font-bold text-blue-900 mb-4">
          13-Week Fat Mass Trend
        </h2>
        
        <div className="relative h-80">
          <svg className="w-full h-full" viewBox="0 0 800 300">
            {/* Grid lines - Updated scale 30-50 lbs */}
            {[30, 32, 34, 36, 38, 40, 42, 44, 46, 48, 50].map((weight, i) => (
              <g key={weight}>
                <line x1="60" y1={250 - (weight - 30) * 10} x2="740" y2={250 - (weight - 30) * 10} 
                      stroke="#f3f4f6" strokeWidth="1"/>
                <text x="45" y={255 - (weight - 30) * 10} fontSize="12" fill="#6b7280" textAnchor="end">
                  {weight}.0
                </text>
              </g>
            ))}
            
            {/* X-axis labels */}
            {currentWeekData?.trendData.map((point, i) => (
              <text key={i} x={60 + i * 52} y="275" fontSize="10" fill="#6b7280" textAnchor="middle">
                {point.date}
              </text>
            ))}
            
            {/* Error bars around EMA line */}
            {currentWeekData?.trendData.map((point, i) => {
              const uncertainty = 1.0; // ±1.0 lb uncertainty
              const centerY = 250 - (point.fatMass - 30) * 10;
              const upperY = centerY - (uncertainty * 10);
              const lowerY = centerY + (uncertainty * 10);
              const x = 60 + i * 52;
              
              return (
                <g key={`error-${i}`}>
                  {/* Error bar line */}
                  <line x1={x} y1={upperY} x2={x} y2={lowerY} stroke="#dc2626" strokeWidth="1" opacity="0.4"/>
                  {/* Top cap */}
                  <line x1={x-3} y1={upperY} x2={x+3} y2={upperY} stroke="#dc2626" strokeWidth="1" opacity="0.4"/>
                  {/* Bottom cap */}
                  <line x1={x-3} y1={lowerY} x2={x+3} y2={lowerY} stroke="#dc2626" strokeWidth="1" opacity="0.4"/>
                </g>
              );
            })}
            
            {/* Raw Withings data points (gray) - Made more visible */}
            {currentWeekData?.trendData.map((point, i) => (
              <circle
                key={`raw-${i}`}
                cx={60 + i * 52}
                cy={250 - (point.raw - 30) * 10}
                r="4"
                fill="#6b7280"
                stroke="#374151"
                strokeWidth="1"
                opacity="1"
              />
            ))}
            
            {/* EMA smoothed line (red) */}
            <polyline
              fill="none"
              stroke="#dc2626"
              strokeWidth="3"
              points={currentWeekData?.trendData.map((point, i) => 
                `${60 + i * 52},${250 - (point.fatMass - 30) * 10}`
              ).join(' ')}
            />
            
            {/* EMA data points (red) */}
            {currentWeekData?.trendData.map((point, i) => (
              <g key={`ema-${i}`}>
                <circle
                  cx={60 + i * 52}
                  cy={250 - (point.fatMass - 30) * 10}
                  r="4"
                  fill="#dc2626"
                />
                <text x={60 + i * 52} y={235 - (point.fatMass - 30) * 10} fontSize="10" 
                      fill="#dc2626" textAnchor="middle" fontWeight="bold">
                  {point.fatMass.toFixed(1)}
                </text>
              </g>
            ))}
            
            {/* Y-axis label */}
            <text x="15" y="150" fontSize="14" fill="#6b7280" textAnchor="middle" transform="rotate(-90 15 150)">
              Fat Mass
            </text>
            
            {/* X-axis label */}
            <text x="400" y="295" fontSize="12" fill="#6b7280" textAnchor="middle">
              Sundays
            </text>
          </svg>
          
          {/* Legend */}
          <div className="absolute top-4 right-4 flex gap-4 text-sm">
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full bg-gray-400"></div>
              <span>Raw Withings</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full bg-red-600"></div>
              <span>Smoothed Fat Mass (α=0.25)</span>
            </div>
          </div>
        </div>
      </div>

      {/* Weekly Process Discipline */}
      <div className="bg-white rounded-lg shadow-sm p-6">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-xl font-bold text-gray-900">Weekly Process Discipline</h2>
          <div className="flex items-center gap-4">
            <button 
              onClick={() => handleWeekChange('prev')}
              disabled={selectedWeekIndex >= weeklyData.length - 1}
              className="p-2 hover:bg-gray-100 rounded disabled:opacity-50"
            >
              <ChevronLeft className="w-5 h-5" />
            </button>
            <span className="font-medium text-lg bg-yellow-100 px-4 py-2 rounded">
              Week of {currentWeekData?.weekStart} - {currentWeekData?.weekEnd}, 2025
            </span>
            <button 
              onClick={() => handleWeekChange('next')}
              disabled={selectedWeekIndex <= 0}
              className="p-2 hover:bg-gray-100 rounded disabled:opacity-50"
            >
              <ChevronRight className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Bar Chart */}
        <div className="relative h-96 mb-6">
          <svg className="w-full h-full" viewBox="0 0 800 350">
            {/* Grid lines - Dynamic range based on data */}
            {chartData && Array.from({length: Math.ceil(chartData.chartMax / 500) + 7}, (_, i) => (i - 6) * 500)
              .filter(value => value >= -3000)
              .map((value) => (
              <g key={value}>
                <line x1="80" y1={175 - value * 0.04} x2="720" y2={175 - value * 0.04} 
                      stroke={value === 0 ? "#374151" : "#f3f4f6"} strokeWidth={value === 0 ? 2 : 1}/>
                <text x="60" y={180 - value * 0.04} fontSize="10" fill="#6b7280" textAnchor="end">
                  {value === 0 ? '0' : value.toLocaleString()}
                </text>
              </g>
            ))}

            {/* Average BMR horizontal dashed line */}
            {chartData && (
              <>
                <line 
                  x1="80" 
                  y1={175 + chartData.avgBMR * 0.04} 
                  x2="720" 
                  y2={175 + chartData.avgBMR * 0.04} 
                  stroke="#8b5cf6" 
                  strokeWidth="2" 
                  strokeDasharray="5,5"
                />
                <text x="730" y={175 + chartData.avgBMR * 0.04 + 4} fontSize="10" 
                      fill="#8b5cf6" textAnchor="start" fontWeight="bold">
                  Avg BMR ({chartData.avgBMR})
                </text>
              </>
            )}

            {currentWeekData?.dailyData.map((day, i) => {
              const x = 100 + i * 88;
              const baseY = 175;
              
              return (
                <g key={day.day}>
                  {/* Intake bar (red) */}
                  <rect
                    x={x - 15}
                    y={baseY - (day.intake * 0.04)}
                    width="15"
                    height={day.intake * 0.04}
                    fill="#ef4444"
                  />
                  <text x={x - 7.5} y={baseY - (day.intake * 0.04) - 5} fontSize="10" 
                        fill="#ef4444" textAnchor="middle" fontWeight="bold">
                    {day.intake.toLocaleString()}
                  </text>
                  
                  {/* Exercise bar (green, below baseline, aligned under intake) */}
                  {day.rawExercise > 0 && (
                    <>
                      <rect
                        x={x - 15}
                        y={baseY}
                        width="15"
                        height={day.rawExercise * 0.04}
                        fill="#10b981"
                      />
                      <text x={x - 7.5} y={baseY + (day.rawExercise * 0.04) + 15} fontSize="10" 
                            fill="#10b981" textAnchor="middle" fontWeight="bold">
                        {day.rawExercise.toLocaleString()}
                      </text>
                    </>
                  )}
                  
                  {/* Net energy horizontal line with larger label */}
                  <line 
                    x1={x - 25} 
                    y1={baseY - (day.netKcal * 0.04)} 
                    x2={x + 25} 
                    y2={baseY - (day.netKcal * 0.04)} 
                    stroke="#3b82f6" 
                    strokeWidth="4"
                  />
                  <circle
                    cx={x}
                    cy={baseY - (day.netKcal * 0.04)}
                    r="3"
                    fill="#3b82f6"
                  />
                  <text x={x + 30} y={baseY - (day.netKcal * 0.04) + 4} fontSize="12" 
                        fill="#3b82f6" textAnchor="start" fontWeight="bold">
                    {day.netKcal.toLocaleString()}
                  </text>
                  
                  {/* Day label */}
                  <text x={x} y={320} fontSize="12" fill="#374151" textAnchor="middle" fontWeight="medium">
                    {day.day}
                  </text>
                </g>
              );
            })}

            {/* Average column */}
            {chartData && (
              <g>
                <text x="730" y="320" fontSize="12" fill="#374151" textAnchor="center" fontWeight="medium">
                  Avg
                </text>
                
                {/* Average intake bar */}
                <rect
                  x={715}
                  y={175 - (chartData.avgIntake * 0.04)}
                  width="15"
                  height={chartData.avgIntake * 0.04}
                  fill="#ef4444"
                  opacity="0.7"
                />
                <text x={722.5} y={175 - (chartData.avgIntake * 0.04) - 5} fontSize="10" 
                      fill="#ef4444" textAnchor="middle" fontWeight="bold">
                  {chartData.avgIntake.toLocaleString()}
                </text>
                
                {/* Average exercise bar */}
                {chartData.avgExercise > 0 && (
                  <>
                    <rect
                      x={715}
                      y={175}
                      width="15"
                      height={chartData.avgExercise * 0.04}
                      fill="#10b981"
                      opacity="0.7"
                    />
                    <text x={722.5} y={175 + (chartData.avgExercise * 0.04) + 15} fontSize="10" 
                          fill="#10b981" textAnchor="middle" fontWeight="bold">
                      {chartData.avgExercise.toLocaleString()}
                    </text>
                  </>
                )}
                
                {/* Average net line */}
                <line 
                  x1={705} 
                  y1={175 - (chartData.avgNet * 0.04)} 
                  x2={745} 
                  y2={175 - (chartData.avgNet * 0.04)} 
                  stroke="#3b82f6" 
                  strokeWidth="4"
                />
                <circle
                  cx={730}
                  cy={175 - (chartData.avgNet * 0.04)}
                  r="3"
                  fill="#3b82f6"
                />
                <text x={750} y={175 - (chartData.avgNet * 0.04) + 4} fontSize="12" 
                      fill="#3b82f6" textAnchor="start" fontWeight="bold">
                  {chartData.avgNet.toLocaleString()}
                </text>
              </g>
            )}
            
            {/* Y-axis label */}
            <text x="25" y="175" fontSize="14" fill="#6b7280" textAnchor="middle" transform="rotate(-90 25 175)">
              kcal
            </text>
          </svg>
          
          {/* Legend */}
          <div className="absolute bottom-4 left-4 flex gap-6 text-sm">
            <div className="flex items-center gap-2">
              <div className="w-4 h-4 bg-red-500"></div>
              <span>Intake</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-4 h-4 bg-green-500"></div>
              <span>Exercise</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-4 h-4 bg-blue-500 rounded-full"></div>
              <span>Net Energy Balance</span>
            </div>
          </div>
        </div>

        {/* Performance Summary */}
        {weeklyStats && (
          <div className="border-l-4 border-blue-500 pl-4 bg-blue-50 p-4 rounded">
            <div className="space-y-2">
              <div className="text-lg font-bold">
                {weeklyStats.targetDays} of {weeklyStats.totalDays} days on Target (≤ {weeklyStats.targetDeficit} kcal)
              </div>
              <div className="text-lg">
                <strong>Weekly net: {weeklyStats.weeklyNetKcal} kcal/day</strong>
              </div>
              <div className="text-lg">
                <strong>Predicted ΔFat Mass {weeklyStats.predictedChange} ± {weeklyStats.uncertainty} lbs</strong>
              </div>
              <div className="text-lg">
                <strong>
                  Actual Fat Mass increased from {weeklyStats.startFatMass} to {weeklyStats.endFatMass} lbs 
                  ({weeklyStats.actualChange > 0 ? '+' : ''}{weeklyStats.actualChange} lbs), 
                  {Math.abs(parseFloat(weeklyStats.actualChange)) > (Math.abs(weeklyStats.predictedChange) + weeklyStats.uncertainty) 
                    ? ' outside predicted range' 
                    : ' within predicted range'}
                </strong>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default HealthMVP;