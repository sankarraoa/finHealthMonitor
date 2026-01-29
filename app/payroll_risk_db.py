"""Database storage for Payroll Risk analyses."""
import sqlite3
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path

logger = logging.getLogger(__name__)

# Database file path
DB_PATH = Path(__file__).parent.parent / "payroll_risk.db"


class PayrollRiskDB:
    """Database manager for Payroll Risk analyses."""
    
    def __init__(self, db_path: Optional[Path] = None):
        """Initialize database connection."""
        self.db_path = db_path or DB_PATH
        self._init_db()
    
    def _init_db(self):
        """Initialize database schema."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS payroll_risk_analyses (
                id TEXT PRIMARY KEY,
                connection_id TEXT NOT NULL,
                connection_name TEXT NOT NULL,
                tenant_id TEXT,
                tenant_name TEXT,
                status TEXT NOT NULL,
                initiated_at TEXT NOT NULL,
                completed_at TEXT,
                result_data TEXT,
                error_message TEXT,
                progress INTEGER DEFAULT 0,
                progress_message TEXT
            )
        """)
        
        # Create index for faster queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_connection_id ON payroll_risk_analyses(connection_id)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_status ON payroll_risk_analyses(status)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_initiated_at ON payroll_risk_analyses(initiated_at DESC)
        """)
        
        conn.commit()
        conn.close()
        logger.info(f"Database initialized at {self.db_path}")
    
    def create_analysis(
        self,
        analysis_id: str,
        connection_id: str,
        connection_name: str,
        tenant_id: Optional[str] = None,
        tenant_name: Optional[str] = None
    ) -> bool:
        """Create a new payroll risk analysis record."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO payroll_risk_analyses 
                (id, connection_id, connection_name, tenant_id, tenant_name, status, initiated_at, progress, progress_message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                analysis_id,
                connection_id,
                connection_name,
                tenant_id,
                tenant_name,
                "running",
                datetime.now().isoformat(),
                0,
                "Initializing..."
            ))
            conn.commit()
            logger.info(f"Created payroll risk analysis: {analysis_id}")
            return True
        except sqlite3.Error as e:
            logger.error(f"Error creating analysis: {str(e)}")
            conn.rollback()
            return False
        finally:
            conn.close()
    
    def update_progress(
        self,
        analysis_id: str,
        progress: int,
        progress_message: str
    ) -> bool:
        """Update progress for an analysis."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                UPDATE payroll_risk_analyses
                SET progress = ?, progress_message = ?
                WHERE id = ?
            """, (progress, progress_message, analysis_id))
            conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Error updating progress: {str(e)}")
            conn.rollback()
            return False
        finally:
            conn.close()
    
    def complete_analysis(
        self,
        analysis_id: str,
        result_data: Dict[str, Any]
    ) -> bool:
        """Mark analysis as complete and store results."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                UPDATE payroll_risk_analyses
                SET status = ?, completed_at = ?, result_data = ?, progress = 100, progress_message = ?
                WHERE id = ?
            """, (
                "completed",
                datetime.now().isoformat(),
                json.dumps(result_data),
                100,
                "Analysis complete",
                analysis_id
            ))
            conn.commit()
            logger.info(f"Completed payroll risk analysis: {analysis_id}")
            return True
        except sqlite3.Error as e:
            logger.error(f"Error completing analysis: {str(e)}")
            conn.rollback()
            return False
        finally:
            conn.close()
    
    def fail_analysis(
        self,
        analysis_id: str,
        error_message: str
    ) -> bool:
        """Mark analysis as failed."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                UPDATE payroll_risk_analyses
                SET status = ?, completed_at = ?, error_message = ?, progress_message = ?
                WHERE id = ?
            """, (
                "failed",
                datetime.now().isoformat(),
                error_message,
                f"Error: {error_message}",
                analysis_id
            ))
            conn.commit()
            logger.info(f"Failed payroll risk analysis: {analysis_id}")
            return True
        except sqlite3.Error as e:
            logger.error(f"Error failing analysis: {str(e)}")
            conn.rollback()
            return False
        finally:
            conn.close()
    
    def get_analysis(self, analysis_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific analysis by ID."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT * FROM payroll_risk_analyses WHERE id = ?
            """, (analysis_id,))
            row = cursor.fetchone()
            
            if row:
                result = dict(row)
                # Parse JSON fields
                if result.get("result_data"):
                    try:
                        result["result_data"] = json.loads(result["result_data"])
                    except json.JSONDecodeError:
                        result["result_data"] = None
                return result
            return None
        except sqlite3.Error as e:
            logger.error(f"Error getting analysis: {str(e)}")
            return None
        finally:
            conn.close()
    
    def get_all_analyses(
        self,
        limit: Optional[int] = None,
        offset: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get all analyses, ordered by initiated_at DESC."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        try:
            query = "SELECT * FROM payroll_risk_analyses ORDER BY initiated_at DESC"
            params = []
            
            if limit:
                query += " LIMIT ?"
                params.append(limit)
            if offset:
                query += " OFFSET ?"
                params.append(offset)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            results = []
            for row in rows:
                result = dict(row)
                # Parse JSON fields
                if result.get("result_data"):
                    try:
                        result["result_data"] = json.loads(result["result_data"])
                    except json.JSONDecodeError:
                        result["result_data"] = None
                results.append(result)
            
            return results
        except sqlite3.Error as e:
            logger.error(f"Error getting all analyses: {str(e)}")
            return []
        finally:
            conn.close()
    
    def delete_analysis(self, analysis_id: str) -> bool:
        """Delete an analysis."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute("DELETE FROM payroll_risk_analyses WHERE id = ?", (analysis_id,))
            conn.commit()
            logger.info(f"Deleted payroll risk analysis: {analysis_id}")
            return True
        except sqlite3.Error as e:
            logger.error(f"Error deleting analysis: {str(e)}")
            conn.rollback()
            return False
        finally:
            conn.close()


# Global instance
payroll_risk_db = PayrollRiskDB()
