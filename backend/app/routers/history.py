from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from .. import database, models
from ..auth import get_current_user
from ..models import User

router = APIRouter(prefix="/api", tags=["history"])

@router.get("/history")
async def get_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(database.get_db)
):
    """Get execution history for the current user"""
    history = db.query(models.ExecutionHistory).filter(
        models.ExecutionHistory.user_id == current_user.id
    ).order_by(models.ExecutionHistory.created_at.desc()).limit(100).all()
    
    return {
        "history": [
            {
                "id": h.id,
                "filename": h.filename,
                "status": h.status,
                "output": h.output,
                "error": h.error,
                "return_code": h.return_code,
                "execution_time": h.execution_time,
                "memory_usage": h.memory_usage,
                "created_at": h.created_at.isoformat()
            }
            for h in history
        ]
    }

@router.delete("/history")
async def clear_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(database.get_db)
):
    """Clear execution history for the current user"""
    try:
        db.query(models.ExecutionHistory).filter(
            models.ExecutionHistory.user_id == current_user.id
        ).delete()
        db.commit()
        return {"message": "History cleared successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))