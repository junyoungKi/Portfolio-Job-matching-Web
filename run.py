# run.py
import uvicorn
import asyncio
import sys

if __name__ == "__main__":
    
    # reload=False로 설정하여 윈도우 루프 충돌을 방지합니다.
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)