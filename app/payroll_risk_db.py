"""Database storage for Payroll Risk analyses using SQLAlchemy."""
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.database import SessionLocal
from app.models.payroll_risk import PayrollRiskAnalysis

logger = logging.getLogger(__name__)


class PayrollRiskDB:
    """Database manager for Payroll Risk analyses using SQLAlchemy."""
    
    def __init__(self):
        """Initialize database connection."""
        # No need to initialize schema - Alembic handles migrations
        logger.info("PayrollRiskDB initialized with SQLAlchemy")
    
    def _get_db(self) -> Session:
        """Get database session."""
        return SessionLocal()
    
    def create_analysis(
        self,
        analysis_id: str,
        connection_id: str,
        connection_name: str,
        tenant_id: Optional[str] = None,
        xero_tenant_id: Optional[str] = None,
        xero_tenant_name: Optional[str] = None
    ) -> bool:
        """Create a new payroll risk analysis record."""
        db = self._get_db()
        try:
            now = datetime.now().isoformat()
            analysis = PayrollRiskAnalysis(
                id=analysis_id,
                tenant_id=tenant_id,
                connection_id=connection_id,
                connection_name=connection_name,
                xero_tenant_id=xero_tenant_id,
                xero_tenant_name=xero_tenant_name,
                status="running",
                initiated_at=now,
                progress=0,
                progress_message="Initializing..."
            )
            db.add(analysis)
            db.commit()
            logger.info(f"Created payroll risk analysis: {analysis_id}")
            return True
        except SQLAlchemyError as e:
            logger.error(f"Error creating analysis: {str(e)}")
            db.rollback()
            return False
        finally:
            db.close()
    
    def update_progress(
        self,
        analysis_id: str,
        progress: int,
        progress_message: str,
        tenant_id: Optional[str] = None
    ) -> bool:
        """Update progress for an analysis."""
        db = self._get_db()
        try:
            query = db.query(PayrollRiskAnalysis).filter(PayrollRiskAnalysis.id == analysis_id)
            if tenant_id:
                query = query.filter(PayrollRiskAnalysis.tenant_id == tenant_id)
            analysis = query.first()
            if not analysis:
                logger.warning(f"Analysis not found: {analysis_id}")
                return False
            
            analysis.progress = progress
            analysis.progress_message = progress_message
            db.commit()
            return True
        except SQLAlchemyError as e:
            logger.error(f"Error updating progress: {str(e)}")
            db.rollback()
            return False
        finally:
            db.close()
    
    def complete_analysis(
        self,
        analysis_id: str,
        result_data: Dict[str, Any],
        tenant_id: Optional[str] = None
    ) -> bool:
        """Mark analysis as complete and store results."""
        db = self._get_db()
        try:
            query = db.query(PayrollRiskAnalysis).filter(PayrollRiskAnalysis.id == analysis_id)
            if tenant_id:
                query = query.filter(PayrollRiskAnalysis.tenant_id == tenant_id)
            analysis = query.first()
            if not analysis:
                logger.warning(f"Analysis not found: {analysis_id}")
                return False
            
            analysis.status = "completed"
            analysis.completed_at = datetime.now().isoformat()
            analysis.result_data = json.dumps(result_data)
            analysis.progress = 100
            analysis.progress_message = "Analysis complete"
            db.commit()
            logger.info(f"Completed payroll risk analysis: {analysis_id}")
            return True
        except SQLAlchemyError as e:
            logger.error(f"Error completing analysis: {str(e)}")
            db.rollback()
            return False
        finally:
            db.close()
    
    def fail_analysis(
        self,
        analysis_id: str,
        error_message: str,
        tenant_id: Optional[str] = None
    ) -> bool:
        """Mark analysis as failed."""
        db = self._get_db()
        try:
            query = db.query(PayrollRiskAnalysis).filter(PayrollRiskAnalysis.id == analysis_id)
            if tenant_id:
                query = query.filter(PayrollRiskAnalysis.tenant_id == tenant_id)
            analysis = query.first()
            if not analysis:
                logger.warning(f"Analysis not found: {analysis_id}")
                return False
            
            analysis.status = "failed"
            analysis.completed_at = datetime.now().isoformat()
            analysis.error_message = error_message
            analysis.progress_message = f"Error: {error_message}"
            db.commit()
            logger.info(f"Failed payroll risk analysis: {analysis_id}")
            return True
        except SQLAlchemyError as e:
            logger.error(f"Error failing analysis: {str(e)}")
            db.rollback()
            return False
        finally:
            db.close()
    
    def get_analysis(self, analysis_id: str, tenant_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get a specific analysis by ID.
        
        Args:
            analysis_id: Analysis ID to fetch
            tenant_id: Optional tenant ID to verify analysis belongs to this tenant
        """
        db = self._get_db()
        try:
            query = db.query(PayrollRiskAnalysis).filter(PayrollRiskAnalysis.id == analysis_id)
            if tenant_id:
                query = query.filter(PayrollRiskAnalysis.tenant_id == tenant_id)
            analysis = query.first()
            if not analysis:
                return None
            
            result = {
                "id": analysis.id,
                "connection_id": analysis.connection_id,
                "connection_name": analysis.connection_name,
                "xero_tenant_id": analysis.xero_tenant_id,
                "xero_tenant_name": analysis.xero_tenant_name,
                "tenant_name": analysis.xero_tenant_name,  # Add tenant_name alias for template compatibility
                "status": analysis.status,
                "initiated_at": analysis.initiated_at,
                "completed_at": analysis.completed_at,
                "result_data": None,
                "error_message": analysis.error_message,
                "progress": analysis.progress,
                "progress_message": analysis.progress_message
            }
            
            # Parse JSON fields
            if analysis.result_data:
                try:
                    result["result_data"] = json.loads(analysis.result_data)
                except json.JSONDecodeError:
                    result["result_data"] = None
            
            return result
        except SQLAlchemyError as e:
            logger.error(f"Error getting analysis: {str(e)}")
            return None
        finally:
            db.close()
    
    def get_all_analyses(
        self,
        tenant_id: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get all analyses, ordered by initiated_at DESC.
        
        Args:
            tenant_id: Optional tenant ID to filter analyses. If provided, only returns analyses for this tenant.
            limit: Optional limit on number of results
            offset: Optional offset for pagination
        """
        db = self._get_db()
        try:
            query = db.query(PayrollRiskAnalysis)
            if tenant_id:
                query = query.filter(PayrollRiskAnalysis.tenant_id == tenant_id)
            query = query.order_by(PayrollRiskAnalysis.initiated_at.desc())
            
            if offset:
                query = query.offset(offset)
            if limit:
                query = query.limit(limit)
            
            analyses = query.all()
            
            results = []
            for analysis in analyses:
                result = {
                    "id": analysis.id,
                    "connection_id": analysis.connection_id,
                    "connection_name": analysis.connection_name,
                    "xero_tenant_id": analysis.xero_tenant_id,
                    "tenant_name": analysis.xero_tenant_name,  # Use xero_tenant_name for display
                    "status": analysis.status,
                    "initiated_at": analysis.initiated_at,
                    "completed_at": analysis.completed_at,
                    "result_data": None,
                    "error_message": analysis.error_message,
                    "progress": analysis.progress,
                    "progress_message": analysis.progress_message
                }
                
                # Parse JSON fields
                if analysis.result_data:
                    try:
                        result["result_data"] = json.loads(analysis.result_data)
                    except json.JSONDecodeError:
                        result["result_data"] = None
                
                results.append(result)
            
            return results
        except SQLAlchemyError as e:
            logger.error(f"Error getting all analyses: {str(e)}")
            return []
        finally:
            db.close()
    
    def delete_analysis(self, analysis_id: str, tenant_id: Optional[str] = None) -> bool:
        """Delete an analysis."""
        db = self._get_db()
        try:
            query = db.query(PayrollRiskAnalysis).filter(PayrollRiskAnalysis.id == analysis_id)
            if tenant_id:
                query = query.filter(PayrollRiskAnalysis.tenant_id == tenant_id)
            analysis = query.first()
            if not analysis:
                logger.warning(f"Analysis not found: {analysis_id}")
                return False
            
            db.delete(analysis)
            db.commit()
            logger.info(f"Deleted payroll risk analysis: {analysis_id}")
            return True
        except SQLAlchemyError as e:
            logger.error(f"Error deleting analysis: {str(e)}")
            db.rollback()
            return False
        finally:
            db.close()


# Global instance
payroll_risk_db = PayrollRiskDB()
