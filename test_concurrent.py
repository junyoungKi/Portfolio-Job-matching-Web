import asyncio
import httpx

URL = "http://127.0.0.1:8000/process-resume"
FILE_PATH = "test_resume.pdf"  # 프로젝트 폴더 내 테스트용 PDF 파일

async def send_request(client, request_id):
    print(f"🚀 [요청 {request_id}] 전송 시작")
    try:
        with open(FILE_PATH, "rb") as f:
            files = {"file": (FILE_PATH, f, "application/pdf")}
            params = {"keyword": "software engineer", "location": "North America"}
            response = await client.post(URL, files=files, params=params, timeout=30.0)
            print(f"✅ [응답 {request_id}] Status: {response.status_code}")
            return response.status_code
    except Exception as e:
        print(f"❌ [에러 {request_id}] {e}")
        return None

async def main():
    # 동시 요청 15개 생성 (기존 10개 제한 초과 검증)
    async with httpx.AsyncClient() as client:
        tasks = [send_request(client, i) for i in range(1, 100)]
        results = await asyncio.gather(*tasks)
        print(f"\n총 {len(results)}개 요청 완료 (성공: {results.count(200)}개)")

if __name__ == "__main__":
    asyncio.run(main())