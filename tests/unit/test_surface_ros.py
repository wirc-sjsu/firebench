import pytest
from firebench.ros_models import RateOfSpreadModel
from firebench.tools import ParameterType


# Subclass for testing purposes
class TestRateOfSpreadModel(RateOfSpreadModel):
    @staticmethod
    def compute_ros(input_dict, **opt) -> float:
        return 0.5  # Dummy implementation for testing


# Test cases
def test_base_class_not_implemented_compute_ros():
    with pytest.raises(NotImplementedError):
        RateOfSpreadModel.compute_ros({})


# Test cases
def test_base_class_not_implemented_compute_ros_with_units():
    with pytest.raises(NotImplementedError):
        RateOfSpreadModel.compute_ros_with_units({})


def test_subclass_implementation():
    input_data = {"dummy_input": [1.0, 2.0, 3.0]}
    result = TestRateOfSpreadModel.compute_ros(input_data)
    assert result == 0.5


sample_metadata = {
    "fm_var_1": {
        "std_name": "svn_var_1",
        "type": ParameterType.input,
    },
    "var_2": {
        "std_name": "svn_var_2",
        "type": ParameterType.input,
    },
    "fm_var_3": {
        "std_name": "svn_var_3",
        "type": ParameterType.optional,
        "default": 1,
    },
    "var_4": {
        "std_name": "svn_var_4",
        "type": ParameterType.optional,
        "default": 2,
    },
    "output": {
        "std_name": "svn_var_5",
        "type": ParameterType.output,
    },
}


def test_prepare_fuel_properties_all_inputs_provided():
    """
    Test that the method correctly processes all mandatory and optional inputs when provided.
    """
    input_dict = {
        "svn_var_1": [0.5, 0.6],
        "svn_var_2": 1,
        "svn_var_3": [4, 2],
        "svn_var_4": 8,
    }
    fuel_cat = 1  # Use first fuel category

    expected_output = {
        "fm_var_1": 0.5,
        "var_2": 1.0,
        "fm_var_3": 4,
        "var_4": 8,
    }

    result = RateOfSpreadModel.prepare_fuel_properties(input_dict, sample_metadata, fuel_cat=fuel_cat)
    assert result == expected_output


def test_prepare_fuel_properties_all_manadatory_inputs_provided():
    """
    Test that the method correctly processes all mandatory and optional inputs when provided.
    """
    input_dict = {
        "svn_var_1": [0.5, 0.6],
        "svn_var_2": 1,
    }
    fuel_cat = 1  # Use first fuel category

    expected_output = {
        "fm_var_1": 0.5,
        "var_2": 1.0,
        "fm_var_3": 1,
        "var_4": 2,
    }

    result = RateOfSpreadModel.prepare_fuel_properties(input_dict, sample_metadata, fuel_cat=fuel_cat)
    assert result == expected_output


def test_prepare_fuel_properties_missing_mandatory_input():
    """
    Test that the method raises a KeyError when a mandatory input is missing.
    """
    input_dict = {
        # 'svn_var_1' is missing
        "svn_var_2": 1.0,
    }
    fuel_cat = 1

    with pytest.raises(KeyError, match="Mandatory key 'svn_var_1' not found in input_dict."):
        RateOfSpreadModel.prepare_fuel_properties(input_dict, sample_metadata, fuel_cat=fuel_cat)
