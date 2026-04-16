from app.schemas.questions import CreateQuestionRequest, BulkDeleteRequest
from app.schemas.quiz import SubmitAnswerRequest, TopicsRequest, CreateTopicRequest


"""Schema-level tests to ensure expected request payload shapes."""

# Convention: tests below follow Arrange / Act / Assert flow.


def test_create_question_schema_accepts_mcq():
    # Valid MCQ payload should parse without validation errors.
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
    # Bulk delete accepts a list of integer IDs.
    payload = BulkDeleteRequest(ids=[1, 2, 3])
    assert payload.ids == [1, 2, 3]


def test_submit_answer_schema():
    # Submit answer supports question id + selected option + response time.
    payload = SubmitAnswerRequest(question_id=7, selected_option="A", response_time=3.2)
    assert payload.question_id == 7
    assert payload.selected_option == "A"


def test_topics_and_create_topic_schema():
    # Topic endpoints use simple list-of-ids and topic-name payloads.
    topics = TopicsRequest(topics=[1, 2])
    topic = CreateTopicRequest(name="Algebra")
    assert topics.topics == [1, 2]
    assert topic.name == "Algebra"
