import os
import socket
from flask import Flask, render_template, request, redirect, url_for, send_file
from flask import jsonify
from flask_socketio import SocketIO, join_room, emit
import pandas as pd
import uuid
import qrcode
import io
import base64

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, cors_allowed_origins="*")

games = {}


def excel_to_questions(file_stream):
    df = pd.read_excel(file_stream, engine='openpyxl')
    rows = []
    for _, r in df.iterrows():
        q = str(r.iloc[0] if 'question' not in r.index else r['question'])
        options = [
            str(r.iloc[1] if 'opt1' not in r.index else r['opt1']),
            str(r.iloc[2] if 'opt2' not in r.index else r['opt2']),
            str(r.iloc[3] if 'opt3' not in r.index else r['opt3']),
            str(r.iloc[4] if 'opt4' not in r.index else r['opt4'])
        ]
        correct = r.iloc[5] if 'correct' not in r.index else r['correct']
        # Accept either index (0-3) or exact text
        try:
            correct_idx = int(correct)
        except Exception:
            # find index by matching text
            correct_idx = 0
            for i, o in enumerate(options):
                if str(o).strip() == str(correct).strip():
                    correct_idx = i
                    break
        rows.append({'question': q, 'options': options, 'answer': int(correct_idx)})
    return rows


def get_local_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(('8.8.8.8', 80))
            return s.getsockname()[0]
    except Exception:
        return 'localhost'


def make_qr_datauri(url):
    img = qrcode.make(url)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    data = base64.b64encode(buf.getvalue()).decode('ascii')
    return f"data:image/png;base64,{data}"


def format_player_list(g):
    return [
        {
            'name': name,
            'avatar': p['avatar'],
            'score': p['score'],
            'connected': p.get('connected', True),
        }
        for name, p in g['players'].items()
    ]


def count_connected_players(g):
    return sum(1 for p in g['players'].values() if p.get('connected', True))


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/create', methods=['POST'])
def create():
    f = request.files.get('file')
    time_per_q = int(request.form.get('time', 20))
    if not f:
        return 'No file', 400
    qs = excel_to_questions(f)
    game_id = str(uuid.uuid4())[:8]
    games[game_id] = {
        'questions': qs,
        'time_per_q': time_per_q,
        'players': {},
        'answers': {},
        'history': [],
        'current': -1,
        'state': 'waiting'
    }
    return redirect(url_for('host', game_id=game_id))


@app.route('/host/<game_id>')
def host(game_id):
    g = games.get(game_id)
    if not g:
        return 'Game not found', 404
    local_ip = get_local_ip()
    join_url = request.host_url.rstrip('/') + url_for('join_page', game_id=game_id)
    if 'localhost' in join_url:
        join_url = join_url.replace('localhost', local_ip)
    qr = make_qr_datauri(join_url)
    return render_template(
        'host.html',
        game_id=game_id,
        qr=qr,
        join_url=join_url,
        time=g['time_per_q'],
        questions=g['questions']
    )


@app.route('/join/<game_id>')
def join_page(game_id):
    g = games.get(game_id)
    if not g:
        return 'Game not found', 404
    return render_template('join.html', game_id=game_id)


@app.route('/debug_players/<game_id>')
def debug_players(game_id):
    g = games.get(game_id)
    if not g:
        return jsonify({'error': 'Game not found'}), 404
    return jsonify({'players': format_player_list(g), 'raw_players': g['players']})


@app.route('/template')
def download_template():
    # Provide a simple Excel template with header and one example row
    df = pd.DataFrame([
        [
            "Exemple : Quel est 2+2 ?",
            "3",
            "4",
            "5",
            "6",
            1,
        ]
    ], columns=["question", "opt1", "opt2", "opt3", "opt4", "correct"])
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    buf.seek(0)
    return send_file(
        buf,
        as_attachment=True,
        download_name='quiz_template.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


@socketio.on('host_start')
def handle_host_start(data):
    game_id = data.get('game_id')
    g = games.get(game_id)
    if not g:
        emit('error', {'msg': 'Game not found'})
        return
    if g['state'] != 'playing':
        g['state'] = 'playing'
        socketio.start_background_task(game_loop, game_id)


def game_loop(game_id):
    g = games.get(game_id)
    if not g:
        return
    for idx, q in enumerate(g['questions']):
        g['current'] = idx
        g['answers'] = {}
        payload = {
            'index': idx,
            'total': len(g['questions']),
            'question': q['question'],
            'options': q['options'],
            'time': g['time_per_q'],
            'players': format_player_list(g),
            'connected_count': count_connected_players(g),
        }
        socketio.emit('question', payload, room=game_id)
        remaining = g['time_per_q']
        while remaining > 0:
            socketio.sleep(1)
            remaining -= 1
            if len(g['answers']) >= len(g['players']) and len(g['players']) > 0:
                break
        # scoring
        correct_idx = q['answer']
        results = []
        for name, p in g['players'].items():
            ans = g['answers'].get(name)
            correct = (ans is not None and int(ans) == correct_idx)
            if correct:
                p['score'] += 100  # simple scoring
            results.append({'name': name, 'answer': ans, 'score': p['score'], 'correct': correct})

        history_entry = {
            'index': idx,
            'question': q['question'],
            'options': q['options'],
            'correct': correct_idx,
            'answers': {
                name: (None if g['answers'].get(name) is None else int(g['answers'].get(name)))
                for name in g['players'].keys()
            },
            'results': results,
        }
        g['history'].append(history_entry)

        socketio.emit(
            'reveal',
            {
                'index': idx,
                'total': len(g['questions']),
                'correct': correct_idx,
                'results': results,
                'players': format_player_list(g),
            },
            room=game_id
        )
        socketio.sleep(2)
    g['state'] = 'finished'
    final = sorted(
        [
            {
                'name': name,
                'score': player['score'],
                'avatar': player['avatar'],
                'connected': player.get('connected', True),
                'correct_count': sum(
                    1 for entry in g['history'] if entry['answers'].get(name) == entry['correct']
                ),
            }
            for name, player in g['players'].items()
        ],
        key=lambda x: -x['score']
    )
    socketio.emit('end', {
        'scores': final,
        'players': format_player_list(g),
        'history': g['history'],
    }, room=game_id)


@socketio.on('player_join')
def handle_player_join(data):
    game_id = data.get('game_id')
    name = data.get('name')
    avatar = data.get('avatar', '😎')
    sid = request.sid
    g = games.get(game_id)
    if not g:
        emit('error', {'msg': 'Game not found'})
        return
    # simple uniqueness
    if name in g['players']:
        name = name + '_' + sid[:4]
    g['players'][name] = {'sid': sid, 'score': 0, 'avatar': avatar, 'connected': True}
    join_room(game_id)
    emit('joined', {'name': name, 'avatar': avatar})
    socketio.emit(
        'player_list',
        {'players': format_player_list(g), 'connected_count': count_connected_players(g)},
        room=game_id
    )


@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid
    for game_id, g in games.items():
        for player_name, player in g['players'].items():
            if player.get('sid') == sid and player.get('connected', True):
                player['connected'] = False
                socketio.emit(
                    'player_list',
                    {'players': format_player_list(g), 'connected_count': count_connected_players(g)},
                    room=game_id
                )
                socketio.emit('player_left', {'name': player_name}, room=game_id)
                return


@socketio.on('host_connect')
def handle_host_connect(data):
    game_id = data.get('game_id')
    g = games.get(game_id)
    if not g:
        emit('error', {'msg': 'Game not found'})
        return
    join_room(game_id)
    emit('player_list', {'players': format_player_list(g), 'connected_count': count_connected_players(g)})


@socketio.on('submit_answer')
def handle_submit_answer(data):
    game_id = data.get('game_id')
    name = data.get('name')
    ans = data.get('answer')
    g = games.get(game_id)
    if not g:
        emit('error', {'msg': 'Game not found'})
        return
    # record latest answer so players can change until timer ends
    g['answers'][name] = ans


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port)
