# reset_db.py
from app.database import engine
from app.models import Base
import sqlalchemy

def reset_database():
    print("⚠️ 데이터베이스 초기화를 시작합니다...")
    try:
        # 1. 모든 테이블 삭제
        # 새로운 컬럼이 반영되지 않은 기존 테이블을 강제로 삭제합니다.
        Base.metadata.drop_all(bind=engine)
        print("✅ 기존 테이블이 모두 삭제되었습니다.")
        
        # 2. 새로운 테이블 생성
        # models.py에 정의된 최신 스키마(employment_type 등 포함)로 테이블을 다시 만듭니다.
        Base.metadata.create_all(bind=engine)
        print("✅ 최신 컬럼이 반영된 테이블이 새로 생성되었습니다.")
        
        print("\n🚀 이제 'python run.py'를 실행하여 다시 시작하세요!")
    except Exception as e:
        print(f"❌ 오류 발생: {e}")

if __name__ == "__main__":
    reset_database()