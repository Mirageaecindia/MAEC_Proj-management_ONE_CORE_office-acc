"""No directory is served publicly (TODO S5): files must go through an
authenticated endpoint that checks project access."""

from starlette.routing import Mount

import main


def test_no_public_static_file_mounts():
    mounts = [route.path for route in main.app.routes if isinstance(route, Mount)]

    assert mounts == []
