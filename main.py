from fastapi import FastAPI, Request, Response, UploadFile, File, Form, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import Optional, Dict, Any, List
import os
from dotenv import load_dotenv
from datetime import datetime

from utils.auth import (
    create_jwt, 
    verify_jwt_cookie, 
    set_auth_cookie, 
    clear_auth_cookie,
    Depends
)
from utils.pdf_reader import extract_text_from_pdf, validate_pdf
from utils.ai_analyzer import ResumeAnalyzer
from utils.db import SupabaseDB

# Load environment variables
load_dotenv()

# Create FastAPI app
app = FastAPI(title="AI Resume Matcher API", version="1.0.0")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize services
analyzer = ResumeAnalyzer()
db = SupabaseDB()

@app.get("/")
async def root():
    return {"message": "AI Resume Matcher API", "version": "1.0.0"}

@app.post("/set-cookie")
async def set_cookie(request: Request, response: Response):
    """Set authentication cookie from Supabase session"""
    try:
        body = await request.json()
        access_token = body.get("access_token")
        user = body.get("user")
        refresh_token = body.get("refresh_token")

        if not access_token or not user:
            raise HTTPException(status_code=400, detail="Invalid session data")

        # Create custom backend JWT for cookie
        jwt_payload = {
            "sub": user["id"],
            "email": user["email"],
            "supabase_token": access_token,
            "refresh_token": refresh_token
        }
        
        jwt_token = create_jwt(jwt_payload)
        set_auth_cookie(response, jwt_token)
        
        return {"message": "Cookie set successfully", "user": user}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/logout")
async def logout(response: Response):
    """Clear authentication cookie"""
    clear_auth_cookie(response)
    return {"message": "Logged out successfully"}

@app.get("/protected")
async def protected_route(user: Dict[str, Any] = Depends(verify_jwt_cookie)):
    """Protected route for testing authentication"""
    return {"message": "Authenticated!", "user": user}

@app.get("/me")
async def get_current_user(user: Dict[str, Any] = Depends(verify_jwt_cookie)):
    """Get current authenticated user"""
    return {"user": user}

@app.post("/analyze-resume")
async def analyze_resume(
    request: Request,
    file: UploadFile = File(...),
    user: Dict[str, Any] = Depends(verify_jwt_cookie)
):
    """Analyze uploaded resume"""

    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    try:
        # Read bytes
        file_content = await file.read()

        # File size validation
        if len(file_content) > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="File size too large")

        # Validate PDF
        if not validate_pdf(file_content):
            raise HTTPException(status_code=400, detail="Invalid PDF file")

        # Extract text
        resume_text = extract_text_from_pdf(file_content)
        if not resume_text.strip():
            raise HTTPException(status_code=400, detail="No text found in PDF")

        # AI Analysis
        analysis = analyzer.analyze_resume(resume_text)

        # Save to DB
        user_id = user["sub"]
        saved_analysis = await db.save_resume_analysis(
            user_id=user_id,
            resume_title=file.filename,
            analysis=analysis
        )

        return {
            "message": "Analysis completed successfully",
            "analysis": saved_analysis
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing resume: {str(e)}")


@app.post("/chat")
async def chat_with_ai(
    request: Request,
    user: Dict[str, Any] = Depends(verify_jwt_cookie)
):
    """Chat with AI using resume context"""
    
    try:
        body = await request.json()
        message = body.get("message")
        
        if not message:
            raise HTTPException(status_code=400, detail="Message is required")
        
        # Get user's latest resume analysis
        user_id = user["sub"]
        latest_analysis = await db.get_latest_analysis(user_id)
        
        if not latest_analysis:
            raise HTTPException(status_code=404, detail="No resume analysis found")
        
        # Create resume summary for context
        resume_summary = f"""
        Summary: {latest_analysis.get('summary_text', '')}
        Job Roles: {', '.join(latest_analysis.get('job_roles', []))}
        Skills: {', '.join(latest_analysis.get('soft_skills', []) + latest_analysis.get('technical_skills', []))}
        Experience Level: {latest_analysis.get('experience_level', '')}
        """
        
        # Generate AI response
        response = analyzer.chat_with_context(resume_summary, message)
        
        return {
            "reply": response,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error in chat: {str(e)}")

@app.get("/summaries")
async def get_summaries(
    user: Dict[str, Any] = Depends(verify_jwt_cookie)
):
    """Get all resume analyses for the current user"""
    
    try:
        user_id = user["sub"]
        analyses = await db.get_user_analyses(user_id)
        
        return {
            "summaries": analyses,
            "count": len(analyses)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching summaries: {str(e)}")

@app.delete("/summaries/{analysis_id}")
async def delete_summary(
    analysis_id: str,
    user: Dict[str, Any] = Depends(verify_jwt_cookie)
):
    """Delete a specific resume analysis"""
    
    try:
        user_id = user["sub"]
        success = await db.delete_analysis(analysis_id, user_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Analysis not found")
        
        return {"message": "Analysis deleted successfully"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting summary: {str(e)}")

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "services": {
            "database": "connected",
            "ai_analyzer": "ready"
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)