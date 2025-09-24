import React, { useState, useEffect } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { getWeeklyData, getDailyData } from '../services/api';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, BarChart, Bar, ReferenceLine, LabelList } from 'recharts';

const HealthMVP = () => {
  const [selectedWeekIndex, setSelectedWeekIndex] = useState(0);
  const [weeklyData, setWeeklyData] = useState([]);
  const [dailyData, setDailyData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const handleWeekChange = (direction) => {
    const newIndex = direction === 'prev' ? selectedWeekIndex + 1 : selectedWeekIndex - 1;
    if (newIndex >= 0 && newIndex < weeklyData.length) {
      setSelectedWeekIndex(newIndex);
      // Daily data will be loaded by useEffect when selectedWeekIndex changes
    }
  };


  const formatWeekDate = (dateString) => {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric'
    });
  };

  useEffect(() => {
    const loadData = async () => {
      try {
        setLoading(true);
        
        const weeklyData = await getWeeklyData(13);
        setWeeklyData(weeklyData);
        
        // Load daily data for first week
        if (weeklyData.length > 0) {
          const week = weeklyData[0];
          const weekStart = new Date(week.week_start_monday);
          const weekEnd = new Date(weekStart.getTime() + 6 * 24 * 60 * 60 * 1000);
          
          const dailyData = await getDailyData(
            week.week_start_monday,
            weekEnd.toISOString().split('T')[0]
          );
          
          setDailyData(dailyData);
        }
        
      } catch (err) {
        setError(`Failed to load data: ${err.message}`);
      } finally {
        setLoading(false);
      }
    };
    
    loadData();
  }, []); // Empty dependency array - only run once on mount

  // Load daily data when selectedWeekIndex changes (but only after weeklyData is loaded)
  useEffect(() => {
    if (weeklyData.length > 0 && selectedWeekIndex >= 0) {
      const loadDailyData = async () => {
        try {
          const week = weeklyData[selectedWeekIndex];
          if (week) {
            const weekStart = new Date(week.week_start_monday);
            const weekEnd = new Date(weekStart.getTime() + 6 * 24 * 60 * 60 * 1000);
            
            const dailyData = await getDailyData(
              week.week_start_monday,
              weekEnd.toISOString().split('T')[0]
            );
            
            setDailyData(dailyData);
          }
        } catch (err) {
          console.error('Daily data error:', err);
        }
      };
      
      loadDailyData();
    }
  }, [selectedWeekIndex, weeklyData]); // Include weeklyData in dependencies

  if (loading) return <div className="p-6 text-center">Loading...</div>;
  if (error) return <div className="p-6 text-red-600">Error: {error}</div>;

  const currentWeek = weeklyData[selectedWeekIndex];
  
  // Transform API data to match the visual component structure with robust error handling
  const currentWeekData = currentWeek ? {
    weekStart: formatWeekDate(currentWeek.week_start_monday),
    weekEnd: dailyData.length > 0 ? formatWeekDate(dailyData[dailyData.length - 1].fact_date) : 'N/A',
    dailyData: dailyData.length > 0 ? dailyData.map(day => ({
      day: day.day_name?.trim()?.substring(0, 3) || 'N/A',
      date: day.fact_date?.split('T')[0]?.substring(5)?.replace('-', '-') || 'N/A',
      fatMassLbs: parseFloat(day.fat_mass_ema_lbs || 0),
      netKcal: Math.round(parseFloat(day.net_kcal || 0)),
      intake: Math.round(parseFloat(day.intake_kcal || 0)),
      rawExercise: Math.round(parseFloat(day.raw_exercise_kcal || 0)),
      exercise: -Math.round(parseFloat(day.raw_exercise_kcal || 0)), // Negative for display below baseline
      compensatedExercise: Math.round(parseFloat(day.compensated_exercise_kcal || 0)),
      rawFatMass: parseFloat(day.raw_fat_mass_lbs || day.fat_mass_ema_lbs || 0),
      uncertainty: parseFloat(day.fat_mass_uncertainty_lbs || 0),
      kcalPerKgFat: parseFloat(day.kcal_per_kg_fat || 9700), // Model parameter for fat energy density
      fiberG: parseFloat(day.fiber_g || 0)
    })) : [],
      trendData: weeklyData.slice(0, 13).filter(week => week.avg_fat_mass_ema).map(week => {
        const date = new Date(week.week_start_monday);
        const month = date.toLocaleDateString('en-US', { month: 'short' });
        const day = date.getDate();
        const fatMassLbs = parseFloat(week.avg_fat_mass_ema || 0) * 2.20462;
        const rawLbs = week.avg_fat_mass_raw ? parseFloat(week.avg_fat_mass_raw) * 2.20462 : null;
        return {
          date: `${month} ${day}`,
          fatMass: fatMassLbs, // Convert kg to lbs (smoothed EMA)
          raw: rawLbs // Convert kg to lbs (raw data) - null if no raw data
        };
      }).reverse()
  } : null;

  // Debug: Log raw daily data for verification
  console.log('Raw dailyData:', dailyData);
  console.log('Processed dailyData:', currentWeekData?.dailyData);
  
  // Debug: Log data availability
  console.log('Debug - weeklyData length:', weeklyData.length);
  console.log('Debug - dailyData length:', dailyData.length);
  console.log('Debug - currentWeek:', currentWeek);
  console.log('Debug - selectedWeekIndex:', selectedWeekIndex);
  console.log('Debug - currentWeekData:', currentWeekData);
  console.log('Debug - trendData:', currentWeekData?.trendData);
  console.log('Debug - first 3 weeks of weeklyData:', weeklyData.slice(0, 3).map(week => ({
    week_start: week.week_start_monday,
    avg_fat_mass_ema: week.avg_fat_mass_ema,
    avg_fat_mass_raw: week.avg_fat_mass_raw
  })));
  
  // Debug the trend data calculation step by step
  if (weeklyData.length > 0) {
    const trendDataDebug = weeklyData.slice(0, 13).filter(week => week.avg_fat_mass_ema).map(week => {
      const date = new Date(week.week_start_monday);
      const month = date.toLocaleDateString('en-US', { month: 'short' });
      const day = date.getDate();
      const fatMassLbs = parseFloat(week.avg_fat_mass_ema || 0) * 2.20462;
      const rawLbs = week.avg_fat_mass_raw ? parseFloat(week.avg_fat_mass_raw) * 2.20462 : null;
      return {
        date: `${month} ${day}`,
        fatMass: fatMassLbs,
        raw: rawLbs,
        original_kg: week.avg_fat_mass_ema,
        original_raw_kg: week.avg_fat_mass_raw
      };
    }).reverse();
    console.log('Debug - calculated trendData step by step:', trendDataDebug);
  }

  // Safety check for insufficient daily data
  if (!currentWeekData || currentWeekData.dailyData.length < 4) {
    console.log('Insufficient daily data:', currentWeekData?.dailyData.length);
  }
  
  // Function to pad incomplete weekly data with placeholder days
  const padWeekData = (dailyData) => {
    const days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
    const paddedData = [];
    
    days.forEach((dayName) => {
      const existingDay = dailyData.find(d => d.day === dayName);
      if (existingDay) {
        paddedData.push(existingDay);
      } else {
        // Add placeholder for missing days
        paddedData.push({
          day: dayName,
          date: '-',
          intake: 0,
          exercise: 0,
          exerciseNegative: 0,
          netKcal: null,
          fatMassLbs: null,
          fiberG: null,
          // Add other fields as needed
        });
      }
    });
    
    return paddedData;
  };

  // Prepare data for weekly discipline chart
  const weeklyChartData = currentWeekData ? (() => {
    const days = currentWeekData.dailyData;
    const avgBMR = 1625; // Average BMR for the week
    
    // Calculate weekly averages (only from existing data)
    const existingDays = days.filter(day => day.netKcal !== null);
    const avgIntake = existingDays.length > 0 ? Math.round(existingDays.reduce((sum, day) => sum + day.intake, 0) / existingDays.length) : 0;
    const avgExercise = existingDays.length > 0 ? Math.round(existingDays.reduce((sum, day) => sum + day.exercise, 0) / existingDays.length) : 0;
    const avgNet = existingDays.length > 0 ? Math.round(existingDays.reduce((sum, day) => sum + day.netKcal, 0) / existingDays.length) : 0;
    
    // Pad the data to ensure all 7 days are present
    const paddedDays = padWeekData(days);
    
    // Transform daily data for Recharts
    const chartData = paddedDays.map(day => ({
      day: day.day,
      date: day.date,
      intake: day.intake,
      exercise: day.exercise, // Use negative exercise values
      exerciseNegative: day.exercise, // Already negative from dailyData mapping
      netKcal: day.netKcal
    }));
    
    // Add average column
    chartData.push({
      day: 'Avg',
      date: 'Avg',
      intake: avgIntake,
      exercise: avgExercise,
      exerciseNegative: avgExercise, // Already negative
      netKcal: avgNet
    });
    
    return {
      chartData,
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
    
    // Use trend data to match chart display (previous week and current week from trendData)
    // trendData is reversed (oldest to newest), so we need to map selectedWeekIndex to the correct trendData indices
    const trendData = currentWeekData?.trendData || [];
    
    // Debug: Let's see what we're working with
    console.log('Debug fat mass calculation:');
    console.log('selectedWeekIndex:', selectedWeekIndex);
    console.log('trendData length:', trendData.length);
    console.log('trendData dates:', trendData.map((item, index) => `${index}: ${item.date} (${item.fatMass} lbs)`));
    
    // Dynamic mapping based on selectedWeekIndex
    // selectedWeekIndex 0 = current week, 1 = previous week, etc.
    // trendData is reversed (oldest to newest), so we need to map correctly
    // For fat mass comparison, we want current week and previous week
    const currentWeekTrendIndex = trendData.length - 1 - selectedWeekIndex;
    const previousWeekTrendIndex = currentWeekTrendIndex - 1;
    
    console.log('currentWeekTrendIndex:', currentWeekTrendIndex, 'previousWeekTrendIndex:', previousWeekTrendIndex);
    
    // For fat mass change, we want to show the change that happened during the selected week
    // If selectedWeekIndex points to a week, we want to show the change FROM that week TO the next week
    const startFatMass = currentWeekTrendIndex >= 0 ? trendData[currentWeekTrendIndex]?.fatMass || 0 : 0;
    const endFatMass = currentWeekTrendIndex + 1 < trendData.length ? trendData[currentWeekTrendIndex + 1]?.fatMass || 0 : 0;
    
    console.log('startFatMass:', startFatMass, 'endFatMass:', endFatMass);
    const actualChange = endFatMass - startFatMass;
    
    // Get model parameter for fat energy density (use first day's value since it should be consistent)
    const kcalPerKgFat = days.length > 0 ? days[0].kcalPerKgFat : 9700;
    
    return {
      weeklyNetKcal: Math.round(weeklyNetKcal),
      targetDays,
      totalDays: days.length,
      startFatMass: startFatMass.toFixed(1),
      endFatMass: endFatMass.toFixed(1),
      actualChange: actualChange.toFixed(1),
      predictedChange: (weeklyNetKcal * 7 / kcalPerKgFat * 2.20462).toFixed(1), // Use model parameter
      uncertainty: 0.4, // Keep uncertainty constant for now
      targetDeficit: -500 // Target daily deficit from schema
    };
  })() : null;

  return (
    <div className="p-6 space-y-6">
      {/* 13-Week Fat Mass Trend */}
      <div className="bg-white rounded-lg shadow-sm p-8 mb-6">
        <h2 className="text-xl font-bold text-blue-900 mb-4">
          13-Week Fat Mass Trend
        </h2>
        
        <div className="h-80 mb-6" style={{ width: '100%', height: '320px' }}>
          <ResponsiveContainer 
            width="100%" 
            height="100%"
            onResize={(width, height) => console.log('Chart resize:', width, height)}
          >
            <LineChart data={(currentWeekData?.trendData || []).filter(point => 
              point.fatMass && point.fatMass > 0 && (!point.raw || point.raw > 0)
            )}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
              <XAxis 
                dataKey="date" 
                stroke="#6b7280"
                fontSize={12}
                tickLine={false}
                axisLine={false}
              />
              <YAxis 
                domain={[30, 50]}
                type="number"
                scale="linear"
                allowDataOverflow={false}
                stroke="#6b7280"
                fontSize={12}
                tickLine={false}
                axisLine={false}
                label={{ value: 'Fat Mass (lbs)', angle: -90, position: 'insideLeft' }}
              />
              <Tooltip 
                contentStyle={{
                  backgroundColor: '#f9fafb',
                  border: '1px solid #e5e7eb',
                  borderRadius: '8px',
                  fontSize: '12px'
                }}
                formatter={(value, name) => [
                  `${value.toFixed(1)} lbs`, 
                  name === 'raw' ? 'Raw Withings' : 'Smoothed Fat Mass'
                ]}
              />
              <Legend />
                  <Line 
                    type="monotone" 
                    dataKey="raw" 
                    stroke="transparent"
                    strokeWidth={0}
                    dot={{ fill: '#6b7280', strokeWidth: 2, r: 4 }}
                    name="Raw Withings"
                    connectNulls={false}
                  />
              <Line 
                type="monotone" 
                dataKey="fatMass" 
              stroke="#dc2626"
                strokeWidth={3}
                dot={{ fill: '#dc2626', strokeWidth: 2, r: 4 }}
                name="Smoothed Fat Mass (α=0.25)"
                connectNulls={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Weekly Process Discipline */}
      <div className="bg-white rounded-lg shadow-sm p-8 mb-6">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-xl font-bold text-gray-900 mb-4">Weekly Process Discipline</h2>
          <div className="flex items-center gap-4 mb-6">
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
        <div className="h-96 mb-6" style={{ width: '100%', height: '400px' }}>
          <ResponsiveContainer 
            width="100%" 
            height="100%"
            onResize={(width, height) => console.log('BarChart resize:', width, height)}
          >
            <BarChart 
              data={weeklyChartData?.chartData || []}
              stackOffset="sign"
              margin={{ top: 20, right: 30, bottom: 20, left: 85 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
              <XAxis 
                dataKey="day" 
                stroke="#6b7280"
                fontSize={12}
                tickLine={false}
                axisLine={false}
              />
              <YAxis 
                domain={[-3000, 3000]} 
                type="number"
                scale="linear"
                allowDataOverflow={false}
                allowDecimals={false}
                includeHidden={false}
                tickCount={7}
                interval={0}
                stroke="#6b7280"
                fontSize={12}
                tickLine={false}
                axisLine={false}
                label={{ value: 'kcal', angle: -90, position: 'insideLeft' }}
                tickFormatter={(value) => value.toLocaleString()}
              />
              <Tooltip 
                contentStyle={{
                  backgroundColor: '#f9fafb',
                  border: '1px solid #e5e7eb',
                  borderRadius: '8px',
                  fontSize: '12px'
                }}
                formatter={(value, name) => [
                  `${value.toLocaleString()} kcal`, 
                  name === 'intake' ? 'Intake' : name === 'exerciseNegative' ? 'Exercise' : 'Net Energy Balance'
                ]}
              />
              <Legend />
              <ReferenceLine 
                y={1630} 
                stroke="#6b7280" 
                strokeDasharray="5 5"
              />
              <Bar 
                dataKey="intake" 
                fill="#ef4444"
                name="Intake"
                stackId="a"
                radius={[2, 2, 0, 0]}
              >
                <LabelList 
                  dataKey="intake" 
                  position="top" 
                  formatter={(value) => value.toLocaleString()}
                />
              </Bar>
              <Bar 
                dataKey="exerciseNegative" 
                fill="#10b981"
                name="Exercise"
                stackId="a"
                radius={[0, 0, 2, 2]}
              >
                <LabelList 
                  dataKey="exerciseNegative" 
                  position="top" 
                  formatter={(value) => value.toLocaleString()}
                />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Weekly Metrics Table */}
        {currentWeekData?.dailyData && (() => {
          const paddedDays = padWeekData(currentWeekData.dailyData);
          return (
          <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6 mb-6">
            <h3 className="text-lg font-bold text-gray-900 mb-4">Weekly Metrics</h3>
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="w-28 px-2 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Metric
                    </th>
                    <th className="px-3 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Mon
                    </th>
                    <th className="px-3 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Tue
                    </th>
                    <th className="px-3 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Wed
                    </th>
                    <th className="px-3 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Thu
                    </th>
                    <th className="px-3 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Fri
                    </th>
                    <th className="px-3 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Sat
                    </th>
                    <th className="px-3 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Sun
                    </th>
                    <th className="px-3 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider bg-yellow-50">
                      Avg
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {/* Net Calories Row */}
                  <tr>
                    <td className="w-28 px-2 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                      Net Calories
                    </td>
                    {paddedDays.map((day, index) => (
                      <td key={index} className={`px-3 py-4 whitespace-nowrap text-sm text-gray-900 text-center ${
                        day.netKcal !== null && day.netKcal <= -500 ? 'bg-green-100' : ''
                      }`}>
                        {day.netKcal !== null ? Math.round(day.netKcal) : '-'}
                      </td>
                    ))}
                    <td className={`px-3 py-4 whitespace-nowrap text-sm font-medium text-gray-900 text-center bg-yellow-50 ${
                      (() => {
                        const avgNetCalories = Math.round(
                          paddedDays.filter(day => day.netKcal !== null).reduce((sum, day) => sum + day.netKcal, 0) / 
                          Math.max(paddedDays.filter(day => day.netKcal !== null).length, 1)
                        );
                        return avgNetCalories <= -500 ? 'ring-2 ring-green-400' : '';
                      })()
                    }`}>
                      {Math.round(
                        paddedDays.filter(day => day.netKcal !== null).reduce((sum, day) => sum + day.netKcal, 0) / 
                        Math.max(paddedDays.filter(day => day.netKcal !== null).length, 1)
                      )}
                    </td>
                  </tr>
                  
                  {/* Protein Row - Placeholder */}
                  <tr>
                    <td className="w-28 px-2 py-4 whitespace-nowrap text-sm font-medium text-gray-500">
                      Protein (g)
                    </td>
                    {paddedDays.map((day, index) => (
                      <td key={index} className="px-3 py-4 whitespace-nowrap text-sm text-gray-400 text-center">
                        -
                      </td>
                    ))}
                    <td className="px-3 py-4 whitespace-nowrap text-sm font-medium text-gray-400 text-center bg-yellow-50">
                      -
                    </td>
                  </tr>
                  
                  {/* Fiber Row */}
                  <tr>
                    <td className="w-28 px-2 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                      Fiber (g)
                    </td>
                    {paddedDays.map((day, index) => (
                      <td key={index} className="px-3 py-4 whitespace-nowrap text-sm text-gray-900 text-center">
                        {day.fiberG !== null && day.fiberG > 0 ? day.fiberG.toFixed(1) : '-'}
                      </td>
                    ))}
                    <td className="px-3 py-4 whitespace-nowrap text-sm font-medium text-gray-900 text-center bg-yellow-50">
                      {(
                        paddedDays.filter(day => day.fiberG !== null && day.fiberG > 0).reduce((sum, day) => sum + day.fiberG, 0) / 
                        Math.max(paddedDays.filter(day => day.fiberG !== null && day.fiberG > 0).length, 1)
                      ).toFixed(1)}
                    </td>
                  </tr>
                  
                  {/* Fat Mass Row */}
                  <tr>
                    <td className="w-28 px-2 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                      Fat Mass (lbs)
                    </td>
                    {paddedDays.map((day, index) => (
                      <td key={index} className="px-3 py-4 whitespace-nowrap text-sm text-gray-900 text-center">
                        {day.fatMassLbs !== null ? day.fatMassLbs.toFixed(1) : '-'}
                      </td>
                    ))}
                    <td className="px-3 py-4 whitespace-nowrap text-sm font-medium text-gray-900 text-center bg-yellow-50">
                      {(
                        paddedDays.filter(day => day.fatMassLbs !== null).reduce((sum, day) => sum + day.fatMassLbs, 0) / 
                        Math.max(paddedDays.filter(day => day.fatMassLbs !== null).length, 1)
                      ).toFixed(1)}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
          );
        })()}

        {/* Fat Mass Performance */}
        {weeklyStats && (
          <div className="border-l-4 border-blue-500 pl-6 bg-blue-50 p-6 rounded-lg mb-6">
            <h3 className="text-lg font-bold text-gray-900 mb-4">Fat Mass Performance</h3>
            <div className="space-y-3">
              <div className="text-lg text-left pl-6 py-1">
                • <strong>Predicted ΔFat Mass {weeklyStats.predictedChange} ± {weeklyStats.uncertainty} lbs</strong>
              </div>
              <div className="text-lg text-left pl-6 py-1">
                • <strong>
                  Actual Fat Mass {weeklyStats.actualChange >= 0 ? 'increased' : 'decreased'} from {weeklyStats.startFatMass} to {weeklyStats.endFatMass} lbs 
                  ({Math.abs(parseFloat(weeklyStats.actualChange)).toFixed(1)} lbs), 
                  {(() => {
                    const actual = parseFloat(weeklyStats.actualChange);
                    const predicted = parseFloat(weeklyStats.predictedChange);
                    const uncertainty = weeklyStats.uncertainty;
                    const lowerBound = predicted - uncertainty;
                    const upperBound = predicted + uncertainty;
                    return (actual >= lowerBound && actual <= upperBound) ? ' within predicted range' : ' outside predicted range';
                  })()}
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