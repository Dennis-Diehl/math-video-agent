import pytest
from pydantic import ValidationError

from schemas import Classification


def test_classification_accepts_valid_values():
    classification = Classification(topic="algebra", difficulty="school")
    assert classification.topic == "algebra"
    assert classification.difficulty == "school"


def test_classification_rejects_invalid_topic():
    with pytest.raises(ValidationError):
        Classification(topic="not_a_real_topic", difficulty="school")


def test_classification_rejects_invalid_difficulty():
    with pytest.raises(ValidationError):
        Classification(topic="algebra", difficulty="not_a_real_difficulty")
