# run.py
"""
Author: Joonyoung Ki

Local development entry point: starts the FastAPI app (``app.main:app``) with uvicorn on
127.0.0.1:8000. Run it with ``python run.py``.
"""
import uvicorn
import asyncio
import sys

if __name__ == "__main__":
    
    # Set reload=False to avoid event-loop conflicts on Windows.
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)