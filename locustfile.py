import os
from locust import HttpUser, task, between

class SmartJobUser(HttpUser):
    # 각 가상 유저가 다음 행동을 하기 전까지 기다리는 시간 (1~3초 사이 랜덤)
    wait_time = between(1, 3)

    @task(2) # @task 숫자는 실행 빈도의 가중치입니다. (조회를 더 자주 함)
    def check_stats(self):
        """DB 통신 부하 테스트: 저장된 공고 개수 조회"""
        self.client.get("/stats")

    @task(1)
    def upload_resume(self):
        """
        파일 I/O 및 AI 분석 부하 테스트 (가장 큰 병목 예상 지점)
        이력서를 업로드하고 매칭 결과를 요청합니다.
        """
        file_path = "test_resume.pdf"
        
        # 테스트를 위해 임시 PDF 파일이 없다면 생성합니다 (에러 방지용)
        if not os.path.exists(file_path):
            with open(file_path, "wb") as f:
                f.write(b"%PDF-1.4 Dummy PDF Content for Load Testing")

        with open(file_path, "rb") as f:
            # main.py의 /process-resume 엔드포인트 구조에 맞춰 데이터 전송
            self.client.post(
                "/process-resume",
                data={
                    "keyword": "Software Engineer", 
                    "location": "North America"
                },
                files={"file": ("test_resume.pdf", f, "application/pdf")}
            )