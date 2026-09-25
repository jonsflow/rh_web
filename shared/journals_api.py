"""
Journal routes, mounted by every dashboard.

A blueprint rather than routes copied into three apps, so a change lands once.
Read and write only touch journals.db; nothing here calls a broker.
"""

from flask import Blueprint, jsonify, request

from shared.journals import JournalsDatabase

# One database object per process; each call opens its own connection
_db = None


def _database(db_path):
    global _db
    if _db is None or _db.db_path != db_path:
        _db = JournalsDatabase(db_path)
    return _db


def journals_blueprint(db_path: str = "journals.db"):
    """Blueprint serving /api/journals.

    Returned fresh per call because a Blueprint can only be registered once.
    """
    bp = Blueprint('journals', __name__)
    db = _database(db_path)

    def _int_arg(name):
        value = request.args.get(name)
        if value is None or value == '':
            return None
        try:
            return int(value)
        except ValueError:
            return None

    @bp.route('/api/journals', methods=['GET'])
    def list_journals():
        """Entries matching the filters in the query string."""
        try:
            entries = db.find(
                date=request.args.get('date'),
                start_date=request.args.get('start_date'),
                end_date=request.args.get('end_date'),
                journal_type=request.args.get('type'),
                asset_type=request.args.get('asset_type'),
                account_number=request.args.get('account'),
                reference_id=request.args.get('reference_id'),
                search=request.args.get('search'),
                limit=_int_arg('limit'),
                offset=_int_arg('offset') or 0,
            )
            return jsonify({'success': True, 'count': len(entries), 'journals': entries})
        except Exception as error:
            print(f"Journals list error: {error}")
            return jsonify({'error': 'Failed to fetch journal entries'}), 500

    @bp.route('/api/journals/count-by-date', methods=['GET'])
    def count_by_date():
        """Entry counts per date, for marking days in the calendar."""
        try:
            counts = db.count_by_date(
                start_date=request.args.get('start_date'),
                end_date=request.args.get('end_date'),
                asset_type=request.args.get('asset_type'),
                account_number=request.args.get('account'),
            )
            return jsonify({'success': True, 'counts': counts})
        except Exception as error:
            print(f"Journals count error: {error}")
            return jsonify({'error': 'Failed to count journal entries'}), 500

    @bp.route('/api/journals/<int:journal_id>', methods=['GET'])
    def get_journal(journal_id):
        entry = db.get(journal_id)
        if entry is None:
            return jsonify({'error': 'Journal entry not found'}), 404
        return jsonify({'success': True, 'journal': entry})

    @bp.route('/api/journals', methods=['POST'])
    def create_journal():
        """Store a new entry and return it as stored."""
        payload = request.get_json(silent=True) or {}
        try:
            journal_id = db.create(payload)
        except ValueError as error:
            return jsonify({'error': str(error)}), 400
        except Exception as error:
            print(f"Journals create error: {error}")
            return jsonify({'error': 'Failed to create journal entry'}), 500

        return jsonify({'success': True, 'journal': db.get(journal_id)}), 201

    @bp.route('/api/journals/<int:journal_id>', methods=['PUT'])
    def update_journal(journal_id):
        """Change an entry's notes, tags or date."""
        payload = request.get_json(silent=True) or {}

        if db.get(journal_id) is None:
            return jsonify({'error': 'Journal entry not found'}), 404

        try:
            db.update(journal_id, payload)
        except ValueError as error:
            return jsonify({'error': str(error)}), 400
        except Exception as error:
            print(f"Journals update error: {error}")
            return jsonify({'error': 'Failed to update journal entry'}), 500

        return jsonify({'success': True, 'journal': db.get(journal_id)})

    @bp.route('/api/journals/<int:journal_id>', methods=['DELETE'])
    def delete_journal(journal_id):
        if db.delete(journal_id) == 0:
            return jsonify({'error': 'Journal entry not found'}), 404
        return jsonify({'success': True})

    return bp
