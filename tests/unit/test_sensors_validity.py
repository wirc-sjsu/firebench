import firebench.sensors as fbs
import pytest


def test_CS506_cl_outside_validity_range():
    with pytest.raises(ValueError, match="Fuel moisture value must be between 0 and 50 percent"):
        fbs.CS506_cl(-1, 68)
    with pytest.raises(ValueError, match="Fuel moisture value must be between 0 and 50 percent"):
        fbs.CS506_cl(50.1, 68)
    with pytest.raises(ValueError, match="Confidence level cl must be between 0 and 100"):
        fbs.CS506_cl(30, -1)


def test_z_from_cl_outside_validity_range():
    with pytest.raises(ValueError, match="Confidence level cl must be between 0 and 1"):
        fbs.z_from_cl(-1)
