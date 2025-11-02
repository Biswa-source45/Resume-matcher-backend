# ...existing code...
from fastapi import FastAPI, Request, Response, UploadFile, File, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv
from datetime import datetime
import os

from utils.auth import (
    create_jwt,
    verify_jwt_cookie,
    set_auth_cookie,
    clear_auth_cookie,
)
from utils.pdf_reader import extract_text_from_pdf, validate_pdf
from utils.ai_analyzer import ResumeAnalyzer
from utils.db import SupabaseDB

# Load environment variables
load_dotenv()

# FRONTEND_URL may contain a comma-separated list of allowed origins
_frontend_env = os.getenv("FRONTEND_URL", "http://localhost:5173")
FRONTEND_ORIGINS = [o.strip() for o in _frontend_env.split(",") if o.strip()]

app = FastAPI(title="AI Resume Matcher API", version="1.0.0")

# Configure CORS: exact origin(s) and credentials required
app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS or ["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize services (assume these are implemented in utils)
analyzer = ResumeAnalyzer()
db = SupabaseDB()


@app.get("/")
async def root():
    return {"message": "AI Resume Matcher API", "version": "1.0.0"}


@app.post("/set-cookie")
async def set_cookie_endpoint(request: Request, response: Response):
    """
    Accepts JSON with a Supabase session object (recommended):
      { "session": { "access_token": "...", "user": { "id": "...", "email": "..." } } }
    Creates a backend-signed JWT containing minimal user info and sets it as an httpOnly cookie
    so subsequent browser requests will be authenticated by the backend.
    """
    body = await request.json()
    session = body.get("session") or {}
    user = session.get("user") or body.get("user")

    if not user or not user.get("id"):
        return JSONResponse({"detail": "missing user in session"}, status_code=400)

    # Build payload for backend JWT (minimal info)
    payload = {
        "sub": user.get("id"),
        "email": user.get("email"),
        "iat": datetime.utcnow().timestamp(),
    }
    token = create_jwt(payload)
    set_auth_cookie(response, token)
    return {"detail": "cookie set"}


@app.post("/logout")
async def logout_endpoint(response: Response):
    clear_auth_cookie(response)
    return {"detail": "logged out"}


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
    user: Dict[str, Any] = Depends(verify_jwt_cookie),
):
    """Analyze uploaded resume"""

    try:
        # Read bytes (validate content rather than rely on filename)
        file_content = await file.read()

        # Basic size validation
        if len(file_content) > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="File size too large (max 10MB)")

        # Validate PDF from bytes (do not rely on file.filename)
        if not validate_pdf(file_content):
            raise HTTPException(status_code=400, detail="Invalid or unsupported file. Please upload a PDF.")

        # Extract text
        resume_text = extract_text_from_pdf(file_content)
        if not resume_text or not resume_text.strip():
            raise HTTPException(status_code=400, detail="No text found in PDF")

        # AI Analysis
        analysis = analyzer.analyze_resume(resume_text)

        # Save to DB (assume async save)
        user_id = user.get("sub")
        saved_analysis = await db.save_resume_analysis(
            user_id=user_id, resume_title=(file.filename or "resume.pdf"), analysis=analysis
        )

        return {"message": "Analysis completed successfully", "analysis": saved_analysis}
    except HTTPException:
        raise
    except Exception as e:
        # Avoid leaking internal errors to client
        raise HTTPException(status_code=500, detail="Error processing resume")


@app.post("/chat")
async def chat_with_ai(request: Request, user: Dict[str, Any] = Depends(verify_jwt_cookie)):
    """Chat with AI using resume context"""
    try:
        body = await request.json()
        message = body.get("message")
        if not message:
            raise HTTPException(status_code=400, detail="Message is required")

        # Get user's latest resume analysis
        user_id = user.get("sub")
        latest_analysis = await db.get_latest_analysis(user_id)

        if not latest_analysis:
            raise HTTPException(status_code=404, detail="No resume analysis found")

        # Create resume summary for context
        resume_summary = (
            f"Summary: {latest_analysis.get('summary_text', '')}\n"
            f"Job Roles: {', '.join(latest_analysis.get('job_roles', []) or [])}\n"
            f"Skills: {', '.join((latest_analysis.get('soft_skills') or []) + (latest_analysis.get('technical_skills') or []))}\n"
            f"Experience Level: {latest_analysis.get('experience_level', '')}"
        )

        # Generate AI response
        response_text = analyzer.chat_with_context(resume_summary, message)

        return {"reply": response_text, "timestamp": datetime.utcnow().isoformat()}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Error in chat")


@app.get("/summaries")
async def get_summaries(user: Dict[str, Any] = Depends(verify_jwt_cookie)):
    """Get all resume analyses for the current user"""
    try:
        user_id = user.get("sub")
        analyses = await db.get_user_analyses(user_id)
        return {"summaries": analyses, "count": len(analyses or [])}
    except Exception:
        raise HTTPException(status_code=500, detail="Error fetching summaries")


@app.delete("/summaries/{analysis_id}")
async def delete_summary(analysis_id: str, user: Dict[str, Any] = Depends(verify_jwt_cookie)):
    """Delete a specific resume analysis"""
    try:
        user_id = user.get("sub")
        success = await db.delete_analysis(analysis_id, user_id)
        if not success:
            raise HTTPException(status_code=404, detail="Analysis not found")
        return {"message": "Analysis deleted successfully"}
    except Exception:
        raise HTTPException(status_code=500, detail="Error deleting summary")


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "services": {"database": "connected", "ai_analyzer": "ready"},
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)), reload=True)
# ...existing code...