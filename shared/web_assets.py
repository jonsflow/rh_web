"""Serves the frontend files that every dashboard uses.

The options and futures dashboards loaded byte-identical copies of the same
table, summary-card, sorting and api-service files. One copy now lives in
`shared/static/` and each app mounts it at `/shared/static/...`.
"""

from flask import Blueprint


def shared_static_blueprint():
    """Blueprint serving `shared/static/` at `/shared/static/`.

    Returned fresh per call because a Blueprint instance can only be
    registered on one app.
    """
    return Blueprint(
        'shared_static',
        __name__,
        static_folder='static',
        static_url_path='/shared/static',
    )
