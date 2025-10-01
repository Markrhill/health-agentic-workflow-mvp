#!/usr/bin/env python3
"""
Backfill Progress Tracker - Utility for monitoring and managing backfill progress.

This module provides utilities for tracking, analyzing, and managing the progress
of Withings historical data backfill operations.
"""

import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import argparse

class BackfillProgressTracker:
    """Tracks and manages backfill progress."""
    
    def __init__(self, progress_file: str = "backfill_progress.json"):
        self.progress_file = progress_file
        self.progress_data = self._load_progress()
    
    def _load_progress(self) -> Dict:
        """Load progress data from file."""
        if os.path.exists(self.progress_file):
            try:
                with open(self.progress_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Failed to load progress file: {e}")
        
        return {
            "completed_chunks": [],
            "total_measurements_extracted": 0,
            "total_errors": 0,
            "last_chunk_completed": None,
            "start_time": None,
            "chunk_details": {}
        }
    
    def get_progress_summary(self) -> Dict:
        """Get summary of backfill progress."""
        if not self.progress_data.get("start_time"):
            return {"status": "not_started"}
        
        start_time = datetime.fromisoformat(self.progress_data["start_time"])
        current_time = datetime.now()
        elapsed_time = current_time - start_time
        
        return {
            "status": "in_progress" if self.progress_data["completed_chunks"] else "started",
            "start_time": self.progress_data["start_time"],
            "elapsed_time": str(elapsed_time),
            "completed_chunks": len(self.progress_data["completed_chunks"]),
            "total_measurements_extracted": self.progress_data["total_measurements_extracted"],
            "total_errors": self.progress_data["total_errors"],
            "last_chunk_completed": self.progress_data["last_chunk_completed"],
            "success_rate": self._calculate_success_rate()
        }
    
    def _calculate_success_rate(self) -> float:
        """Calculate success rate based on measurements vs errors."""
        total_attempts = self.progress_data["total_measurements_extracted"] + self.progress_data["total_errors"]
        if total_attempts == 0:
            return 0.0
        return (self.progress_data["total_measurements_extracted"] / total_attempts) * 100
    
    def get_chunk_analysis(self) -> Dict:
        """Analyze chunk processing performance."""
        chunk_details = self.progress_data.get("chunk_details", {})
        
        if not chunk_details:
            return {"message": "No chunk details available"}
        
        # Calculate statistics
        measurements_per_chunk = [details.get("measurements", 0) for details in chunk_details.values()]
        errors_per_chunk = [details.get("errors", 0) for details in chunk_details.values()]
        
        return {
            "total_chunks_processed": len(chunk_details),
            "avg_measurements_per_chunk": sum(measurements_per_chunk) / len(measurements_per_chunk) if measurements_per_chunk else 0,
            "max_measurements_in_chunk": max(measurements_per_chunk) if measurements_per_chunk else 0,
            "min_measurements_in_chunk": min(measurements_per_chunk) if measurements_per_chunk else 0,
            "total_errors": sum(errors_per_chunk),
            "chunks_with_errors": sum(1 for errors in errors_per_chunk if errors > 0)
        }
    
    def get_remaining_chunks(self, all_chunks: List[str]) -> List[str]:
        """Get list of chunks that haven't been completed yet."""
        completed = set(self.progress_data["completed_chunks"])
        return [chunk for chunk in all_chunks if chunk not in completed]
    
    def estimate_completion_time(self, remaining_chunks: List[str]) -> Optional[str]:
        """Estimate time to completion based on historical performance."""
        if not self.progress_data.get("start_time") or not remaining_chunks:
            return None
        
        start_time = datetime.fromisoformat(self.progress_data["start_time"])
        current_time = datetime.now()
        elapsed_time = current_time - start_time
        
        completed_chunks = len(self.progress_data["completed_chunks"])
        if completed_chunks == 0:
            return "Unable to estimate (no completed chunks)"
        
        avg_time_per_chunk = elapsed_time / completed_chunks
        estimated_remaining_time = avg_time_per_chunk * len(remaining_chunks)
        
        return str(estimated_remaining_time)
    
    def generate_report(self) -> str:
        """Generate a comprehensive progress report."""
        summary = self.get_progress_summary()
        chunk_analysis = self.get_chunk_analysis()
        
        report = []
        report.append("📊 WITHINGS HISTORICAL BACKFILL PROGRESS REPORT")
        report.append("=" * 60)
        
        if summary["status"] == "not_started":
            report.append("Status: Not started")
            return "\n".join(report)
        
        report.append(f"Status: {summary['status'].title()}")
        report.append(f"Start Time: {summary['start_time']}")
        report.append(f"Elapsed Time: {summary['elapsed_time']}")
        report.append(f"Completed Chunks: {summary['completed_chunks']}")
        report.append(f"Total Measurements Extracted: {summary['total_measurements_extracted']:,}")
        report.append(f"Total Errors: {summary['total_errors']}")
        report.append(f"Success Rate: {summary['success_rate']:.1f}%")
        report.append(f"Last Chunk Completed: {summary['last_chunk_completed']}")
        
        if chunk_analysis.get("total_chunks_processed", 0) > 0:
            report.append("\n📈 CHUNK ANALYSIS")
            report.append("-" * 30)
            report.append(f"Total Chunks Processed: {chunk_analysis['total_chunks_processed']}")
            report.append(f"Avg Measurements per Chunk: {chunk_analysis['avg_measurements_per_chunk']:.1f}")
            report.append(f"Max Measurements in Chunk: {chunk_analysis['max_measurements_in_chunk']}")
            report.append(f"Min Measurements in Chunk: {chunk_analysis['min_measurements_in_chunk']}")
            report.append(f"Chunks with Errors: {chunk_analysis['chunks_with_errors']}")
        
        if self.progress_data["completed_chunks"]:
            report.append("\n✅ COMPLETED CHUNKS")
            report.append("-" * 30)
            for chunk in self.progress_data["completed_chunks"]:
                report.append(f"  {chunk}")
        
        return "\n".join(report)
    
    def reset_progress(self):
        """Reset progress data (use with caution)."""
        self.progress_data = {
            "completed_chunks": [],
            "total_measurements_extracted": 0,
            "total_errors": 0,
            "last_chunk_completed": None,
            "start_time": None,
            "chunk_details": {}
        }
        self._save_progress()
        print("Progress data reset successfully")
    
    def _save_progress(self):
        """Save progress data to file."""
        try:
            with open(self.progress_file, 'w') as f:
                json.dump(self.progress_data, f, indent=2)
        except Exception as e:
            print(f"Failed to save progress: {e}")

def main():
    """CLI interface for progress tracker."""
    parser = argparse.ArgumentParser(description="Withings Backfill Progress Tracker")
    parser.add_argument("--report", action="store_true", help="Generate progress report")
    parser.add_argument("--summary", action="store_true", help="Show progress summary")
    parser.add_argument("--reset", action="store_true", help="Reset progress data")
    parser.add_argument("--file", default="backfill_progress.json", help="Progress file path")
    
    args = parser.parse_args()
    
    tracker = BackfillProgressTracker(args.file)
    
    if args.reset:
        tracker.reset_progress()
    elif args.summary:
        summary = tracker.get_progress_summary()
        print(json.dumps(summary, indent=2))
    elif args.report:
        print(tracker.generate_report())
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
