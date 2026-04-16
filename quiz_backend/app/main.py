import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes import auth, questions, quiz, topics, uploads



app = FastAPI()
app.include_router(auth.router, prefix="/auth")
app.include_router(questions.router)
app.include_router(quiz.router, prefix="/quiz")
app.include_router(topics.router)
app.include_router(uploads.router)

origins_env = os.getenv("FRONTEND_ORIGINS")
if origins_env:
    allowed_origins = [origin.strip() for origin in origins_env.split(",") if origin.strip()]
else:
    single_origin = os.getenv("FRONTEND_ORIGIN")
    if single_origin:
        allowed_origins = [single_origin.strip()]
    else:
        allowed_origins = [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "Adaptive Quiz Engine Backend Running!"}