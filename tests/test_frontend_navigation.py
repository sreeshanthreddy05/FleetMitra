"""Pure browser-geometry checks; Node is optional and not an application dependency."""
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.skipif(not shutil.which('node'),reason='Node unavailable for optional JS unit checks')
@pytest.mark.parametrize('script',['frontend_navigation.test.cjs','frontend_contracts.test.cjs'])
def test_navigation_javascript_geometry(script):
    result=subprocess.run(['node','--test','tests/'+script],cwd=Path(__file__).parents[1],capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr
