const socket = io();
const startBtn = document.getElementById('startBtn');
const playersEl = document.getElementById('players');
const playerCountEl = document.getElementById('playerCount');
const scoresEl = document.getElementById('scores');
const progressText = document.getElementById('progressText');
const progressFill = document.getElementById('progressFill');
const stateEl = document.createElement('div');
stateEl.style.marginTop = '16px';
stateEl.style.color = 'var(--muted)';
stateEl.style.fontWeight = '600';
startBtn.parentNode.appendChild(stateEl);

let lastQuestionIndex = 0;
let lastQuestionTotal = 0;

function renderPlayerList(players, connectedCount) {
  playersEl.innerHTML = '';
  const sorted = players.slice().sort((a, b) => {
    if (a.connected === b.connected) {
      return (b.score || 0) - (a.score || 0);
    }
    return a.connected ? -1 : 1;
  });
  sorted.forEach(p => {
    const li = document.createElement('li');
    li.className = p.connected ? 'online' : 'offline';
    const name = p.name || 'Joueur';
    const avatar = p.avatar || '😎';
    const status = p.connected ? 'connecté' : 'déconnecté';
    const score = typeof p.score !== 'undefined' ? ` — ${p.score} pts` : '';
    li.innerText = `${avatar} ${name}${score}`;
    const statusSpan = document.createElement('span');
    statusSpan.innerText = status;
    statusSpan.className = 'status';
    li.appendChild(statusSpan);
    playersEl.appendChild(li);
  });
  if (playerCountEl) {
    playerCountEl.innerText = connectedCount != null ? connectedCount : players.filter(p => p.connected).length;
  }
}

function renderScores(players) {
  scoresEl.innerHTML = '';
  const sorted = players.slice().sort((a, b) => (b.score || 0) - (a.score || 0));
  sorted.forEach(p => {
    const li = document.createElement('li');
    const name = p.name || 'Joueur';
    const score = typeof p.score !== 'undefined' ? `${p.score} pts` : '0 pts';
    li.innerText = `${name}`;
    const right = document.createElement('span');
    right.innerText = score;
    li.appendChild(right);
    scoresEl.appendChild(li);
  });
}

function updateProgress(index, total) {
  lastQuestionIndex = index;
  lastQuestionTotal = total;
  if (progressText) {
    progressText.innerText = `Progression: ${index + 1} / ${total}`;
  }
  if (progressFill) {
    progressFill.style.width = `${Math.round(((index + 1) / total) * 100)}%`;
  }
}

startBtn.addEventListener('click', () => {
  socket.emit('host_start', { game_id: GAME_ID });
  stateEl.innerText = 'Partie démarrée';
});

socket.on('connect', () => {
  socket.emit('host_connect', { game_id: GAME_ID });
});

socket.on('player_list', (data) => {
  renderPlayerList(data.players, data.connected_count);
  renderScores(data.players);
  stateEl.innerText = `Joueurs connectés: ${data.connected_count != null ? data.connected_count : data.players.filter(p => p.connected).length}`;
});

socket.on('player_left', (data) => {
  if (data && data.name) {
    stateEl.innerText = `${data.name} a quitté la partie.`;
  }
});

socket.on('question', (q) => {
  stateEl.innerText = `Question ${q.index + 1}/${q.total} : ${q.question}`;
  updateProgress(q.index, q.total);
});

socket.on('reveal', (r) => {
  if (r.players) {
    renderScores(r.players);
  }
  stateEl.innerText = 'Résultats affichés. En attente de la prochaine question...';
});

socket.on('end', (data) => {
  stateEl.innerText = 'Partie terminée';
  if (progressText) {
    progressText.innerText = 'Progression: terminée';
  }
  if (progressFill) {
    progressFill.style.width = '100%';
  }
  if (data && data.scores) {
    const finalPlayers = data.scores.map(item => ({ name: item[0], score: item[1], avatar: '😎', connected: true }));
    renderScores(finalPlayers);
  }
});
