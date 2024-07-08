import pytest
from firebench.ros_models import RateOfSpreadModel

# Subclass for testing purposes
class TestRateOfSpreadModel(RateOfSpreadModel):
    @staticmethod
    def compute_ros(input_dict, **opt) -> float:
        return 0.5  # Dummy implementation for testing


# Test cases
def test_base_class_not_implemented():
    with pytest.raises(NotImplementedError):
        RateOfSpreadModel.compute_ros({})


def test_subclass_implementation():
    input_data = {"dummy_input": [1.0, 2.0, 3.0]}
    result = TestRateOfSpreadModel.compute_ros(input_data)
    assert result == 0.5
