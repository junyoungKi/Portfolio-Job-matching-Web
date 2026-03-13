import asyncio
from app.database import SessionLocal
from app.models import JobPosting
from app.services.ai import ai_service

REALISTIC_JOBS = [
    {
        "title": "Senior Graphics Programmer (RAGE Engine)",
        "company": "Rockstar Games",
        "description": "Develop and optimize the rendering pipeline for our next-gen open-world titles. Expertise in DirectX 12 or Vulkan is mandatory. Deep knowledge of shader authoring (HLSL/GLSL), ray tracing, and multi-threaded engine architecture. Must have experience with low-level memory management and SIMD optimization for console hardware."
    },
    {
        "title": "Real-Time Simulation Engineer (Starship)",
        "company": "SpaceX",
        "description": "Build high-fidelity, real-time physics simulations for flight software. Focus on rigid body dynamics and thermal fluid systems. Requires strong C++ skills and experience with high-performance computing. Knowledge of numerical integration methods and SIMD-accelerated math libraries is highly preferred."
    },
    {
        "title": "Game Engine Generalist",
        "company": "Naughty Dog",
        "description": "Maintain and extend our proprietary game engine. Optimize core systems including physics, animation, and I/O. Strong C++ and assembly knowledge. Experience with data-oriented design (DOD) and cache-friendly data structures is essential for maximizing frame rates on PS5."
    },
    {
        "title": "GPU Driver Engineer",
        "company": "NVIDIA",
        "description": "Design and implement features within the GPU driver stack. Work at the intersection of hardware and software. Requires deep understanding of computer architecture, memory management unit (MMU), and OS internals. C and C++ expertise is a must."
    },
    {
        "title": "Software Development Engineer (AWS S3)",
        "company": "Amazon",
        "description": "Build and scale distributed storage systems. Focus on high availability and low latency. Expertise in Java, Go, or C++. Experience with RESTful APIs, microservices architecture, and cloud-native databases. Knowledge of consistency models and distributed consensus algorithms like Raft or Paxos."
    },
    {
        "title": "Junior Gameplay Programmer",
        "company": "Supercell",
        "description": "Create engaging gameplay experiences for millions of players. Work with game designers to implement new features using C++ and internal tools. Strong problem-solving skills and a passion for mobile games. Experience with Unity/C# is a plus but not required if C++ fundamentals are strong."
    }
]

async def seed():
    db = SessionLocal()
    for job in REALISTIC_JOBS:
        print(f"Embedding & Saving: {job['company']} - {job['title']}...")
        embedding = ai_service.get_embedding(job['description'])
        db_job = JobPosting(
            title=job['title'],
            company=job['company'],
            description=job['description'],
            embedding=embedding
        )
        db.add(db_job)
    db.commit()
    db.close()
    print("\n 하이퍼 리얼리즘 공고 6건 추가 완료!")

if __name__ == "__main__":
    asyncio.run(seed())