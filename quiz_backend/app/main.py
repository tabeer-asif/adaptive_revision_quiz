# from fastapi import FastAPI, Depends
# from sqlalchemy.orm import Session
# from . import models, crud, schemas, database
# from fastapi.middleware.cors import CORSMiddleware

# app = FastAPI()
# models.Base.metadata.create_all(bind=database.engine)

# # Allow React frontend to call API
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],  # change in production
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )



# @app.get("/next_question")
# def next_question(student_id: int, db: Session = Depends(database.get_db)):
#     question = crud.select_next_question(db, student_id)

#     if not question:
#         return {
#             "id": 0,
#             "question": "No questions available",
#             "options": [],
#             "topic": "",
#             "difficulty": 1
#         }

#     return question

# @app.post("/submit_answer", response_model=schemas.SubmitAnswerResponse)
# def submit_answer(req: schemas.SubmitAnswerRequest, db: Session = Depends(database.get_db)):
#     return crud.submit_answer(db, req.student_id, req.question_id, req.selected)

# from fastapi.responses import JSONResponse
# from sqlalchemy import func

# @app.get("/student_topics")
# def get_student_topics(student_id: int, db: Session = Depends(database.get_db)):
#     topics = db.query(models.StudentTopicProgress).filter_by(student_id=student_id).all()
#     return JSONResponse(content=[
#         {
#             "topic": t.topic,
#             "mastery": t.mastery,
#             "attempts": t.attempts,
#             "correct": t.correct
#         } for t in topics
#     ])

# backend/app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes import auth, questions, quiz, topics



app = FastAPI()
app.include_router(auth.router, prefix="/auth")
app.include_router(questions.router)
app.include_router(quiz.router, prefix="/quiz")
app.include_router(topics.router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "Adaptive Quiz Engine Backend Running!"}