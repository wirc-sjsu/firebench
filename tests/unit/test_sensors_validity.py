import firebench.sensors as fbs
import numpy as np
import pytest


def test_CS506_rms_outside_validity_range():
    with pytest.raises(ValueError, match="Fuel moisture value must be between 0 and 50 percent"):
        a = fbs.CS506_rms(-1, None)
        print(a)
    with pytest.raises(ValueError, match="Fuel moisture value must be between 0 and 50 percent"):
        fbs.CS506_rms(50.1, None)


def test_CS506_range90_outside_validity_range():
    with pytest.raises(ValueError, match="Fuel moisture value must be between 0 and 50 percent"):
        a = fbs.CS506_range90(-1, None)
        print(a)
    with pytest.raises(ValueError, match="Fuel moisture value must be between 0 and 50 percent"):
        fbs.CS506_range90(50.1, None)
