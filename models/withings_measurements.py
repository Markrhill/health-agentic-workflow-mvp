#!/usr/bin/env python3
"""
Withings Raw Measurements Database Model.

This module defines the database schema and operations for storing raw Withings measurements.
Keeps raw data separate from processed daily_facts for flexibility.
"""

from sqlalchemy import create_engine, text, MetaData, Table, Column, Integer, String, Numeric, DateTime, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import os
import logging
from typing import Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class WithingsMeasurementsDB:
    """Database operations for Withings raw measurements."""
    
    def __init__(self, database_url: Optional[str] = None):
        self.database_url = database_url or os.getenv("DATABASE_URL")
        if not self.database_url:
            raise ValueError("DATABASE_URL environment variable must be set")
        
        self.engine = create_engine(self.database_url)
        self.metadata = MetaData()
        
        # Define table schema
        self.withings_raw_measurements = Table(
            'withings_raw_measurements',
            self.metadata,
            Column('id', Integer, primary_key=True, autoincrement=True),
            Column('measurement_id', String(50), unique=True, nullable=False),
            Column('weight_kg', Numeric(5, 2), nullable=False),
            Column('timestamp_utc', DateTime(timezone=True), nullable=False),
            Column('timestamp_user', DateTime(timezone=True), nullable=False),
            Column('original_timezone', String(50)),
            Column('user_timezone', String(50)),
            Column('source_format', String(30), default='withings_api'),
            Column('raw_value', Integer),  # Original API value for audit
            Column('raw_unit', Integer),   # Original API unit for audit
            Column('created_at', DateTime(timezone=True), default=func.now()),
            
            # Body composition fields
            Column('fat_mass_kg', Numeric(5, 2)),
            Column('fat_free_mass_kg', Numeric(5, 2)),
            Column('muscle_mass_kg', Numeric(5, 2)),
            Column('bone_mass_kg', Numeric(5, 2)),
            Column('body_water_kg', Numeric(5, 2)),
            Column('fat_ratio_pct', Numeric(4, 2)),
            
            # Indexes for performance
            Index('idx_withings_timestamp_utc', 'timestamp_utc'),
            Index('idx_withings_timestamp_user', 'timestamp_user'),
            Index('idx_withings_measurement_id', 'measurement_id'),
            Index('idx_withings_created_at', 'created_at')
        )
    
    def create_table(self):
        """Create the withings_raw_measurements table if it doesn't exist."""
        try:
            self.metadata.create_all(self.engine)
            logger.info("✅ withings_raw_measurements table created/verified")
        except Exception as e:
            logger.error(f"❌ Failed to create table: {e}")
            raise
    
    def upsert_measurement(self, measurement_data: Dict) -> bool:
        """
        Insert or update a Withings measurement.
        
        Args:
            measurement_data: Dictionary containing measurement data
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            upsert_sql = text("""
                INSERT INTO withings_raw_measurements (
                    measurement_id, weight_kg, timestamp_utc, timestamp_user,
                    original_timezone, user_timezone, source_format,
                    raw_value, raw_unit,
                    fat_mass_kg, fat_free_mass_kg, muscle_mass_kg,
                    bone_mass_kg, body_water_kg, fat_ratio_pct
                ) VALUES (
                    :measurement_id, :weight_kg, :timestamp_utc, :timestamp_user,
                    :original_timezone, :user_timezone, :source_format,
                    :raw_value, :raw_unit,
                    :fat_mass_kg, :fat_free_mass_kg, :muscle_mass_kg,
                    :bone_mass_kg, :body_water_kg, :fat_ratio_pct
                )
                ON CONFLICT (measurement_id) DO UPDATE SET
                    weight_kg = EXCLUDED.weight_kg,
                    timestamp_utc = EXCLUDED.timestamp_utc,
                    timestamp_user = EXCLUDED.timestamp_user,
                    original_timezone = EXCLUDED.original_timezone,
                    user_timezone = EXCLUDED.user_timezone,
                    source_format = EXCLUDED.source_format,
                    raw_value = EXCLUDED.raw_value,
                    raw_unit = EXCLUDED.raw_unit,
                    fat_mass_kg = COALESCE(EXCLUDED.fat_mass_kg, withings_raw_measurements.fat_mass_kg),
                    fat_free_mass_kg = COALESCE(EXCLUDED.fat_free_mass_kg, withings_raw_measurements.fat_free_mass_kg),
                    muscle_mass_kg = COALESCE(EXCLUDED.muscle_mass_kg, withings_raw_measurements.muscle_mass_kg),
                    bone_mass_kg = COALESCE(EXCLUDED.bone_mass_kg, withings_raw_measurements.bone_mass_kg),
                    body_water_kg = COALESCE(EXCLUDED.body_water_kg, withings_raw_measurements.body_water_kg),
                    fat_ratio_pct = COALESCE(EXCLUDED.fat_ratio_pct, withings_raw_measurements.fat_ratio_pct),
                    created_at = NOW()
            """)
            
            with self.engine.begin() as conn:
                conn.execute(upsert_sql, measurement_data)
            
            logger.debug(f"✅ Upserted measurement {measurement_data['measurement_id']}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to upsert measurement: {e}")
            return False
    
    def get_latest_measurement_timestamp(self) -> Optional[datetime]:
        """
        Get the timestamp of the most recent measurement for incremental sync.
        
        Returns:
            datetime: Latest measurement timestamp in UTC, or None if no data
        """
        try:
            query = text("""
                SELECT MAX(timestamp_utc) as latest_timestamp
                FROM withings_raw_measurements
            """)
            
            with self.engine.connect() as conn:
                result = conn.execute(query).fetchone()
                return result.latest_timestamp if result else None
                
        except Exception as e:
            logger.error(f"❌ Failed to get latest timestamp: {e}")
            return None
    
    def get_measurement_count(self) -> int:
        """
        Get total count of measurements in the database.
        
        Returns:
            int: Total measurement count
        """
        try:
            query = text("SELECT COUNT(*) as count FROM withings_raw_measurements")
            
            with self.engine.connect() as conn:
                result = conn.execute(query).fetchone()
                return result.count if result else 0
                
        except Exception as e:
            logger.error(f"❌ Failed to get measurement count: {e}")
            return 0
    
    def get_recent_measurements(self, limit: int = 10) -> List[Dict]:
        """
        Get recent measurements for debugging.
        
        Args:
            limit: Number of recent measurements to return
            
        Returns:
            List[Dict]: Recent measurements
        """
        try:
            query = text("""
                SELECT measurement_id, weight_kg, timestamp_utc, timestamp_user,
                       original_timezone, user_timezone, raw_value, raw_unit, created_at
                FROM withings_raw_measurements
                ORDER BY timestamp_utc DESC
                LIMIT :limit
            """)
            
            with self.engine.connect() as conn:
                result = conn.execute(query, {"limit": limit}).fetchall()
                return [dict(row._mapping) for row in result]
                
        except Exception as e:
            logger.error(f"❌ Failed to get recent measurements: {e}")
            return []
    
    def validate_data_integrity(self) -> Dict[str, any]:
        """
        Validate data integrity and return statistics.
        
        Returns:
            Dict containing validation results
        """
        try:
            stats_query = text("""
                SELECT 
                    COUNT(*) as total_count,
                    MIN(timestamp_utc) as earliest_measurement,
                    MAX(timestamp_utc) as latest_measurement,
                    MIN(weight_kg) as min_weight,
                    MAX(weight_kg) as max_weight,
                    AVG(weight_kg) as avg_weight,
                    COUNT(DISTINCT measurement_id) as unique_measurements
                FROM withings_raw_measurements
            """)
            
            with self.engine.connect() as conn:
                result = conn.execute(stats_query).fetchone()
                stats = dict(result._mapping) if result else {}
                
                # Check for duplicates
                duplicate_query = text("""
                    SELECT COUNT(*) as duplicate_count
                    FROM (
                        SELECT measurement_id, COUNT(*) as cnt
                        FROM withings_raw_measurements
                        GROUP BY measurement_id
                        HAVING COUNT(*) > 1
                    ) duplicates
                """)
                
                duplicate_result = conn.execute(duplicate_query).fetchone()
                stats['duplicate_count'] = duplicate_result.duplicate_count if duplicate_result else 0
                
                return stats
                
        except Exception as e:
            logger.error(f"❌ Failed to validate data integrity: {e}")
            return {}

def main():
    """Test database operations."""
    logging.basicConfig(level=logging.INFO)
    
    try:
        db = WithingsMeasurementsDB()
        
        print("🗄️  Testing Withings Measurements Database")
        print("=" * 50)
        
        # Create table
        db.create_table()
        
        # Get statistics
        count = db.get_measurement_count()
        print(f"Total measurements: {count}")
        
        if count > 0:
            # Get latest timestamp
            latest = db.get_latest_measurement_timestamp()
            print(f"Latest measurement: {latest}")
            
            # Get recent measurements
            recent = db.get_recent_measurements(5)
            print(f"\nRecent measurements:")
            for m in recent:
                print(f"  {m['measurement_id']}: {m['weight_kg']} kg at {m['timestamp_user']}")
            
            # Validate integrity
            stats = db.validate_data_integrity()
            print(f"\nData integrity stats:")
            print(f"  Min weight: {stats.get('min_weight', 'N/A')} kg")
            print(f"  Max weight: {stats.get('max_weight', 'N/A')} kg")
            print(f"  Avg weight: {stats.get('avg_weight', 'N/A')} kg")
            print(f"  Duplicates: {stats.get('duplicate_count', 'N/A')}")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()
