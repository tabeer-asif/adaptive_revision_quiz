from app.schemas.questions import CreateQuestionRequest, BulkDeleteRequest
from app.schemas.quiz import SubmitAnswerRequest, TopicsRequest, CreateTopicRequest


def test_create_question_schema_accepts_mcq():
    payload = CreateQuestionRequest(
        topic_id=1,
        text="What is 2+2?",
        type="MCQ",
        options={"A": "3", "B": "4"},
        answer="B",
        difficulty=2,
    )
    assert payload.topic_id == 1
    assert payload.type == "MCQ"


def test_bulk_delete_schema():
    payload = BulkDeleteRequest(ids=[1, 2, 3])
    assert payload.ids == [1, 2, 3]


def test_submit_answer_schema():
    payload = SubmitAnswerRequest(question_id=7, selected_option="A", response_time=3.2)
    assert payload.question_id == 7
    assert payload.selected_option == "A"


def test_topics_and_create_topic_schema():
    topics = TopicsRequest(topics=[1, 2])
    topic = CreateTopicRequest(name="Algebra")
    assert topics.topics == [1, 2]
    assert topic.name == "Algebra"
