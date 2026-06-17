    # ...existing code...

    # ...existing code...
import os
import uuid
import time

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO, emit, join_room
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, '..', 'frontend')
DATA_DIR = os.path.join(BASE_DIR, '..', 'data')

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path='')
CORS(app)
socketio = SocketIO(app, cors_allowed_origins='*', async_mode='threading')

# ── In-memory sessions ────────────────────────────────────────────────────────
# session = {
#   code, questions, current_q (-1=not started),
#   chrono, answers {name: answer_idx}, students {name: score},
#   phase: 'waiting' | 'question' | 'results' | 'finished'
# }
sessions: dict = {}

ALLOWED_EXT = {'csv', 'xlsx', 'xls'}


def allowed(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXT


def parse_file(path: str) -> list:
    ext = path.rsplit('.', 1)[1].lower()
    df = pd.read_csv(path) if ext == 'csv' else pd.read_excel(path)
    required = ['question', 'reponse_1', 'reponse_2', 'reponse_3', 'reponse_4', 'bonne_reponse']
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Colonnes manquantes : {', '.join(missing)}")
    questions = []
    for idx, row in df.iterrows():
        val = row['bonne_reponse']
        if pd.isna(val) or str(val).strip() == '':
            raise ValueError(f"Ligne {idx+2} : 'bonne_reponse' manquant ou vide.")
        try:
            br = int(float(val))
        except Exception:
            raise ValueError(f"Ligne {idx+2} : 'bonne_reponse' invalide : {val}")
        if br < 1 or br > 4:
            raise ValueError(f"Ligne {idx+2} : 'bonne_reponse' doit être entre 1 et 4 (trouvé : {val})")
        questions.append({
            'question': str(row['question']),
            'reponses': [
                str(row['reponse_1']),
                str(row['reponse_2']),
                str(row['reponse_3']),
                str(row['reponse_4']),
            ],
            'bonne_reponse': br - 1,          # 0-indexed
            'cours': str(row.get('cours', '')),
            'sujet': str(row.get('sujet', '')),
        })
    if not questions:
        raise ValueError("Le fichier ne contient aucune question.")
    return questions


# ── Static pages ──────────────────────────────────────────────────────────────

@app.route('/')
def root():
    return send_from_directory(app.static_folder, 'index.html')


@app.route('/prof')
def prof_page():
    return send_from_directory(app.static_folder, 'prof.html')


@app.route('/student')
def student_page():
    return send_from_directory(app.static_folder, 'student.html')


# ── REST API ──────────────────────────────────────────────────────────────────

@app.route('/api/upload', methods=['POST'])
def upload():
    f = request.files.get('file')
    if not f or not f.filename or not allowed(f.filename):
        return jsonify({'error': 'Fichier invalide. Formats acceptés : .csv, .xlsx, .xls'}), 400
    # Sanitise filename
    safe_name = os.path.basename(f.filename)
    os.makedirs(DATA_DIR, exist_ok=True)
    path = os.path.join(DATA_DIR, safe_name)
    f.save(path)
    try:
        questions = parse_file(path)
    except Exception as e:
        return jsonify({'error': str(e)}), 400
    code = uuid.uuid4().hex[:6].upper()
    sessions[code] = {
        'code': code,
        'questions': questions,
        'current_q': -1,
        'chrono': 20,
        'answers': {},
        'students': {},
        'phase': 'waiting',
    }
    return jsonify({'session_code': code, 'nb_questions': len(questions)})


# ── SocketIO events ───────────────────────────────────────────────────────────

@socketio.on('join_prof')
def on_join_prof(data):
    code = str(data.get('code', '')).upper()
    if code not in sessions:
        emit('error', {'message': 'Session introuvable'})
        return
    join_room(code)
    s = sessions[code]
    emit('session_info', {
        'code': code,
        'nb_questions': len(s['questions']),
        'phase': s['phase'],
        'students': list(s['students'].keys()),
        'scores': s['students'],
    })


@socketio.on('join_student')
def on_join_student(data):
    code = str(data.get('code', '')).upper()
    name = str(data.get('name', 'Anonyme')).strip() or 'Anonyme'
    if code not in sessions:
        emit('error', {'message': 'Code de session invalide.'})
        return
    s = sessions[code]
    if s['phase'] != 'waiting':
        emit('error', {'message': 'La session a déjà commencé. Attendez la prochaine session.'})
        return
    join_room(code)
    if name not in s['students']:
        s['students'][name] = 0
    emit('joined', {'code': code, 'name': name})
    socketio.emit('students_update', {
        'students': list(s['students'].keys()),
        'count': len(s['students']),
    }, room=code)


@socketio.on('set_chrono')
def on_set_chrono(data):
    code = str(data.get('code', '')).upper()
    if code in sessions:
        sessions[code]['chrono'] = int(data.get('chrono', 20))


@socketio.on('next_question')
def on_next_question(data):
    code = str(data.get('code', '')).upper()
    if code not in sessions:
        return
    s = sessions[code]
    s['current_q'] += 1
    s['answers'] = {}

    if s['current_q'] >= len(s['questions']):
        s['phase'] = 'finished'
        ranking = sorted(s['students'].items(), key=lambda x: x[1], reverse=True)
        socketio.emit('quiz_finished', {
            'ranking': [[n, sc] for n, sc in ranking]
        }, room=code)
        return

    s['phase'] = 'question'
    q = s['questions'][s['current_q']]
    chrono = s['chrono']
    socketio.emit('new_question', {
        'index': s['current_q'],
        'total': len(s['questions']),
        'question': q['question'],
        'reponses': q['reponses'],
        'cours': q['cours'],
        'sujet': q['sujet'],
        'chrono': chrono,
    }, room=code)
    socketio.start_background_task(_run_countdown, code, s['current_q'], chrono)


def _run_countdown(code: str, question_index: int, chrono: int):
    """Background countdown — ticks every second; triggers results when time is up."""
    for remaining in range(chrono, -1, -1):
        s = sessions.get(code)
        if not s or s['phase'] != 'question' or s['current_q'] != question_index:
            return
        socketio.emit('chrono_tick', {'remaining': remaining, 'total': chrono}, room=code)
        socketio.sleep(1)
    s = sessions.get(code)
    if s and s['phase'] == 'question' and s['current_q'] == question_index:
        _show_results(code)


@socketio.on('submit_answer')
def on_submit_answer(data):
    code = str(data.get('code', '')).upper()
    name = str(data.get('name', ''))
    answer = int(data.get('answer', -1))
    if code not in sessions:
        return
    s = sessions[code]
    if s['phase'] != 'question' or name in s['answers']:
        return
    s['answers'][name] = answer
    socketio.emit('answer_count', {
        'count': len(s['answers']),
        'total': len(s['students']),
    }, room=code)
    # All students answered → show results early
    if len(s['students']) > 0 and len(s['answers']) >= len(s['students']):
        _show_results(code)


def _show_results(code: str):
    s = sessions.get(code)
    if not s or s['phase'] != 'question':
        return
    s['phase'] = 'results'
    q = s['questions'][s['current_q']]
    correct = q['bonne_reponse']
    # Update scores
    for name, ans in s['answers'].items():
        if ans == correct and name in s['students']:
            s['students'][name] += 1
    # Per-answer stats
    stats = [0, 0, 0, 0]
    for ans in s['answers'].values():
        if 0 <= ans <= 3:
            stats[ans] += 1
    ranking = sorted(s['students'].items(), key=lambda x: x[1], reverse=True)
    has_next = s['current_q'] + 1 < len(s['questions'])
    socketio.emit('show_results', {
        'correct': correct,
        'stats': stats,
        'ranking': [[n, sc] for n, sc in ranking],
        'question': q['question'],
        'reponses': q['reponses'],
        'total_students': len(s['students']),
        'index': s['current_q'],
        'total': len(s['questions']),
        'has_next': has_next,
    }, room=code)


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
