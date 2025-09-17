# UI and Weekly Process Documentation

This document describes the user interface design and weekly coaching process for the Health Agentic Workflow MVP.

## 🎯 Overview

The system provides a weekly coaching workflow that:
- **Reviews progress** against goals using data from multiple sources
- **Makes recommendations** based on predicted vs. observed fat mass changes
- **Tracks decisions** for audit and learning
- **Supports goal setting** with performance targets

## 📱 User Interface Components

### Weekly Dashboard
The main interface shows the current week's progress:

#### Key Metrics
- **Fat Mass Change**: Predicted vs. observed change
- **Net Calorie Balance**: Average daily net calories
- **Days on Target**: Count of days meeting deficit goals
- **Data Completeness**: Percentage of days with sufficient data

#### Visual Indicators
- **Green**: Within expected range
- **Yellow**: Requires investigation
- **Red**: Significant deviation from prediction

### Goal Setting Interface
Users can set and track performance goals:

#### Goal Types
- **Fat Mass Target**: Target fat mass by date
- **Performance Goals**: Cycling power targets (W/kg)
- **Deficit Targets**: Daily calorie deficit goals
- **Training Plans**: TSS progression plans

#### Goal Tracking
- Progress visualization against timeline
- Performance metrics vs. targets
- Automatic W/kg calculations

## 🔄 Weekly Process Workflow

### 1. Data Collection (Monday-Sunday)
- **Daily weigh-ins**: Withings scale measurements
- **Nutrition logging**: MyFitnessPal meal tracking
- **Exercise tracking**: TrainingPeaks workout data
- **Data validation**: Automated quality checks

### 2. Weekly Review (Sunday Evening)
- **Data freeze**: Snapshot of week's data
- **Model calculation**: Apply current parameters
- **Prediction generation**: Expected fat mass change
- **Comparison**: Predicted vs. observed changes

### 3. Decision Making (Monday Morning)
- **Review snapshot**: Human review of weekly data
- **Decision options**:
  - **Approve**: Continue current approach
  - **Within Noise**: Acceptable variation
  - **Investigate**: Significant deviation, needs attention

### 4. Action Items
- **Parameter updates**: If model needs adjustment
- **Goal adjustments**: If targets need modification
- **Data quality**: Address missing or invalid data

## 📊 Data Visualization

### Weekly Trends
- **Fat Mass**: EMA-smoothed trend line
- **Net Calories**: Daily balance with weekly average
- **Exercise**: Workout calories and intensity
- **Intake**: Calorie consumption patterns

### Performance Metrics
- **W/kg Progress**: Power-to-weight ratio trends
- **Deficit Consistency**: Days meeting calorie targets
- **Data Quality**: Completeness and accuracy metrics

### Historical Context
- **Previous Weeks**: Comparison with past performance
- **Seasonal Patterns**: Long-term trends and cycles
- **Goal Progress**: Distance to target dates

## 🎛️ User Controls

### Parameter Adjustment
When investigation is needed:
- **Exercise Compensation**: Adjust workout calorie compensation
- **EMA Parameters**: Modify smoothing factors
- **BMR Parameters**: Update metabolic rate calculations
- **Imputation Methods**: Change missing data handling

### Goal Management
- **Add Goals**: Set new performance targets
- **Modify Goals**: Adjust existing targets
- **Track Progress**: Monitor goal achievement
- **Archive Goals**: Complete or cancel goals

### Data Management
- **Imputation Review**: Check and correct imputed data
- **Quality Flags**: Review data quality issues
- **Source Validation**: Verify data from different sources

## 🔍 Decision Support

### Automated Analysis
- **Trend Detection**: Identify significant changes
- **Anomaly Detection**: Flag unusual data points
- **Pattern Recognition**: Spot recurring issues
- **Prediction Accuracy**: Track model performance

### Human Oversight
- **Context Consideration**: Account for external factors
- **Goal Alignment**: Ensure decisions support objectives
- **Risk Assessment**: Evaluate potential consequences
- **Learning Integration**: Apply past experience

## 📈 Performance Tracking

### Key Performance Indicators
- **Prediction Accuracy**: How well the model predicts changes
- **Goal Achievement**: Success rate in meeting targets
- **Data Quality**: Completeness and accuracy metrics
- **Decision Consistency**: Alignment with coaching principles

### Reporting
- **Weekly Summaries**: Progress against goals
- **Monthly Reviews**: Longer-term trends and patterns
- **Quarterly Assessments**: Goal achievement and adjustments
- **Annual Planning**: Strategic goal setting

## 🛠️ Technical Implementation

### Data Flow
1. **Ingestion**: Raw data from multiple sources
2. **Processing**: Cleaning, validation, and imputation
3. **Calculation**: Apply model parameters
4. **Materialization**: Pre-compute for UI performance
5. **Snapshot**: Create immutable weekly records

### UI Architecture
- **Real-time Updates**: Live data refresh
- **Responsive Design**: Mobile and desktop support
- **Accessibility**: Screen reader and keyboard navigation
- **Performance**: Fast loading with materialized views

### Integration Points
- **Withings API**: Scale measurements
- **MyFitnessPal API**: Nutrition data
- **TrainingPeaks API**: Workout data
- **Database**: PostgreSQL with materialized views

## 📝 User Experience Principles

### Simplicity
- **Clear Metrics**: Easy-to-understand indicators
- **Minimal Clicks**: Streamlined workflows
- **Consistent Design**: Familiar patterns throughout

### Transparency
- **Data Sources**: Clear attribution of information
- **Calculation Methods**: Explainable algorithms
- **Decision Rationale**: Documented reasoning

### Actionability
- **Clear Next Steps**: Obvious actions to take
- **Progress Tracking**: Visible goal advancement
- **Feedback Loops**: Learn from decisions

## 🔮 Future Enhancements

### Planned Features
- **Mobile App**: Native iOS/Android applications
- **Notifications**: Push alerts for important events
- **Social Features**: Share progress with coaches
- **Advanced Analytics**: Machine learning insights

### Integration Opportunities
- **Wearable Devices**: Additional health metrics
- **Weather Data**: Environmental factors
- **Calendar Integration**: Schedule-aware recommendations
- **Third-party APIs**: Expanded data sources
