const socket = io();
let playerName = null;
let playerAvatar = '😎';
let selectedAnswer = null;
let questionActive = false;
window.__playerDebug = { started: true };

function initPlayerPage() {
  window.__playerDebug.initCalled = true;
  const joinForm = document.getElementById('joinForm');
  const playerArea = document.getElementById('playerArea');
  const questionText = document.getElementById('questionText');
  const optionsEl = document.getElementById('options');
  const timerEl = document.getElementById('timer');
  const resultEl = document.getElementById('result');
  const playerNameEl = document.getElementById('playerName');
  const playerAvatarEl = document.getElementById('playerAvatar');
  const selectedAvatarEl = document.getElementById('selectedAvatar');
  const playerScoresEl = document.getElementById('playerScores');
  const joinBtn = document.getElementById('join');

  if (!joinForm || !joinBtn) {
    console.log('player.js: join page elements not found, aborting');
    return;
  }

  document.querySelectorAll('.avatar-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      playerAvatar = btn.dataset.avatar;
      window.__playerDebug.lastAction = 'avatar-click';
      window.__playerDebug.avatarPicked = playerAvatar;
      console.log('player.js avatar clicked', playerAvatar);
      if (selectedAvatarEl) {
        selectedAvatarEl.innerText = playerAvatar;
      }
    });
  });

  joinBtn.addEventListener('click', () => {
    const nameInput = document.getElementById('name');
    const name = nameInput ? nameInput.value.trim() : '';
    window.__playerDebug.lastAction = 'join-click';
    if (!name) {
      alert('Entrez un nom');
      return;
    }
    playerName = name;
    joinBtn.disabled = true;
    console.log('player.js join click', name, playerAvatar);
    socket.emit('player_join', { game_id: GAME_ID, name, avatar: playerAvatar });
    const joinTimeout = setTimeout(() => {
      joinBtn.disabled = false;
      alert('Impossible de rejoindre la partie — vérifier le code ou la connexion au serveur.');
    }, 3000);
    socket.once('joined', () => clearTimeout(joinTimeout));
  });

  socket.on('joined', () => {
    joinForm.style.display = 'none';
    playerArea.style.display = 'block';
    if (playerNameEl) playerNameEl.innerText = playerName;
    if (playerAvatarEl) playerAvatarEl.innerText = playerAvatar;
    if (resultEl) resultEl.innerText = 'En attente de la prochaine question...';
  });

  socket.on('error', (d) => {
    try {
      alert(d.msg || JSON.stringify(d));
    } catch (e) {
      console.warn('socket error', d);
    }
  });

  socket.on('connect_error', (err) => {
    console.warn('connect_error', err);
  });

  const progressContainer = document.createElement('div');
  progressContainer.className = 'progress-container';
  progressContainer.innerHTML = `
    <div class="progress-text">Question 0 / 0</div>
    <div class="progress-track"><div class="progress-fill"></div></div>
  `;
  if (playerArea) {
    playerArea.insertBefore(progressContainer, playerArea.firstChild);
  }
  const progressTextEl = progressContainer.querySelector('.progress-text');
  const progressFillEl = progressContainer.querySelector('.progress-fill');
  const summaryEl = document.createElement('div');
  summaryEl.className = 'summary-box';
  summaryEl.style.display = 'none';
  summaryEl.innerHTML = `
    <h3>Résumé de la partie</h3>
    <div id="summaryResult" class="summary-result"></div>
    <div id="summaryDetails"></div>
    <h4>Classement final</h4>
    <ul id="finalRanking" class="list"></ul>
  `;
  if (playerArea) {
    playerArea.appendChild(summaryEl);
  }

  function updateProgressBar(index, total) {
    if (progressTextEl) progressTextEl.innerText = `Question ${index + 1} / ${total}`;
    if (progressFillEl) progressFillEl.style.width = `${Math.round(((index + 1) / total) * 100)}%`;
  }

  function clearSummary() {
    if (summaryEl) summaryEl.style.display = 'none';
    if (playerArea) playerArea.style.display = 'block';
    if (questionText) questionText.style.display = '';
    if (optionsEl) optionsEl.style.display = '';
    if (timerEl) timerEl.style.display = '';
  }

  socket.on('question', (q) => {
    clearSummary();
    selectedAnswer = null;
    questionActive = true;
    if (resultEl) resultEl.innerText = '';
    if (questionText) questionText.innerText = q.question;
    if (optionsEl) optionsEl.innerHTML = '';
    if (playerScoresEl) playerScoresEl.innerHTML = '';
    updateProgressBar(q.index, q.total);

    q.options.forEach((o, i) => {
      const btn = document.createElement('button');
      btn.className = 'option-btn';
      btn.innerText = o;
      btn.onclick = () => {
        if (!questionActive) return;
        selectedAnswer = i;
        socket.emit('submit_answer', { game_id: GAME_ID, name: playerName, answer: i });
        if (resultEl) resultEl.innerText = 'Réponse sélectionnée. Tu peux changer tant que le timer tourne.';
        if (optionsEl) {
          Array.from(optionsEl.children).forEach((other, idx) => {
            other.classList.toggle('selected', idx === i);
          });
        }
      };
      if (optionsEl) optionsEl.appendChild(btn);
    });

    let t = q.time;
    if (timerEl) timerEl.innerText = t;
    const iv = setInterval(() => {
      t -= 1;
      if (timerEl) timerEl.innerText = t;
      if (t <= 0) {
        clearInterval(iv);
        questionActive = false;
        if (selectedAnswer === null && resultEl) {
          resultEl.innerText = 'Temps écoulé, réponse verrouillée.';
        }
        if (optionsEl) {
          Array.from(optionsEl.children).forEach(btn => btn.disabled = true);
        }
      }
    }, 1000);
  });

  socket.on('reveal', (r) => {
    if (resultEl) resultEl.innerText = `Bonne réponse: ${r.correct}`;
    if (playerScoresEl) playerScoresEl.innerHTML = '';
    if (r.players && playerScoresEl) {
      r.players.sort((a, b) => b.score - a.score).forEach(p => {
        const li = document.createElement('li');
        li.innerText = `${p.avatar || '😎'} ${p.name} — ${p.score} pts`;
        playerScoresEl.appendChild(li);
      });
    }
  });

  socket.on('end', (data) => {
    if (playerArea) {
      playerArea.style.display = 'none';
    }
    if (summaryEl) {
      summaryEl.style.display = 'block';
    }
    if (resultEl) resultEl.innerText = '';
    if (progressTextEl) progressTextEl.innerText = 'Partie terminée';
    if (progressFillEl) progressFillEl.style.width = '100%';

    const summaryResult = document.getElementById('summaryResult');
    const summaryDetails = document.getElementById('summaryDetails');
    const finalRanking = document.getElementById('finalRanking');
    if (summaryResult) summaryResult.innerText = 'Merci d’avoir joué ! Voici le bilan final.';

    if (data && data.players) {
      const player = data.players.find(p => p.name === playerName);
      const rank = data.players.findIndex(p => p.name === playerName) + 1;
      if (player && summaryDetails) {
        summaryDetails.innerHTML = `
          <p><strong>Ton classement:</strong> ${rank} / ${data.players.length}</p>
          <p><strong>Points:</strong> ${player.score} pts</p>
          <p><strong>Réponses correctes:</strong> ${player.correct_count || 0} / ${data.scores.length}</p>
        `;
      }
      if (finalRanking) {
        finalRanking.innerHTML = '';
        data.players.forEach((p, idx) => {
          const li = document.createElement('li');
          li.innerText = `${idx + 1}. ${p.avatar || '😎'} ${p.name} — ${p.score} pts`;
          finalRanking.appendChild(li);
        });
      }
    }
  });
}

if (document.readyState === 'loading') {
  window.addEventListener('DOMContentLoaded', initPlayerPage);
} else {
  initPlayerPage();
}

