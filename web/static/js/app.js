// Music Downloader - Spotify Style Web App

let currentTrack = null;
let searchTimeout = null;
let resultsData = [];
let userData = JSON.parse(localStorage.getItem('userData') || 'null');
const audioPlayer = document.getElementById('audioPlayer');

// Initialize app
document.addEventListener('DOMContentLoaded', () => {
    checkAuthToken();
    updateUserUI();
    initializeNavigation();
    initializeSearch();
    initializePlayer();
    initializePlaylists();

    if (userData) {
        loadPlaylists();
    }
});

// Auth Logic
async function checkAuthToken() {
    const urlParams = new URLSearchParams(window.location.search);
    const hostToken = urlParams.get('auth');

    if (hostToken) {
        try {
            showNotification('Authenticating...', 'info');
            const response = await fetch('/api/auth', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ token: hostToken })
            });

            const data = await response.json();
            if (data.success) {
                userData = data.user;
                localStorage.setItem('userData', JSON.stringify(userData));
                showNotification(`Welcome back, ${userData.first_name || userData.username}!`, 'success');
                // Clear URL param
                window.history.replaceState({}, document.title, window.location.pathname);
                updateUserUI();
                loadPlaylists();
            } else {
                showNotification('Invalid or expired token', 'error');
            }
        } catch (error) {
            console.error('Auth error:', error);
            showNotification('Authentication failed', 'error');
        }
    }
}

function updateUserUI() {
    const userInfo = document.getElementById('userInfo');
    const loginBtn = document.getElementById('loginBtn');
    const displayUsername = document.getElementById('displayUsername');

    if (userData) {
        userInfo.style.display = 'flex';
        loginBtn.style.display = 'none';
        displayUsername.textContent = userData.first_name || userData.username;
    } else {
        userInfo.style.display = 'none';
        loginBtn.style.display = 'block';
    }
}

document.getElementById('loginBtn').addEventListener('click', () => {
    showNotification('Please use /login command in the Telegram bot', 'info');
});

// Navigation
function initializeNavigation() {
    const navItems = document.querySelectorAll('.nav-item');
    const sections = document.querySelectorAll('.content-section');

    navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const page = item.dataset.page;

            navItems.forEach(nav => nav.classList.remove('active'));
            item.classList.add('active');

            sections.forEach(section => section.classList.remove('active'));
            document.getElementById(page === 'search' ? 'searchResults' : page).classList.add('active');

            if (page === 'playlists' && userData) {
                loadPlaylists();
            }
        });
    });
}

// Search functionality
function initializeSearch() {
    const searchInput = document.getElementById('searchInput');

    searchInput.addEventListener('input', (e) => {
        clearTimeout(searchTimeout);
        const query = e.target.value.trim();

        if (query.length < 2) {
            document.getElementById('resultsGrid').innerHTML = '';
            return;
        }

        searchTimeout = setTimeout(() => {
            if (query.includes('spotify.com') || query.includes('open.spotify')) {
                searchTracks(query);
            } else {
                searchTracks(query);
            }
        }, 500);
    });
}

async function searchTracks(query) {
    try {
        const response = await fetch('/api/search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query })
        });

        const data = await response.json();
        displayResults(data.tracks || []);
    } catch (error) {
        console.error('Search error:', error);
        showNotification('Search failed', 'error');
    }
}

function displayResults(tracks) {
    const resultsGrid = document.getElementById('resultsGrid');
    resultsData = tracks;

    if (tracks.length === 0) {
        resultsGrid.innerHTML = '<p style="grid-column: 1/-1; text-align: center; color: var(--spotify-light-gray); padding: 48px;">No results found</p>';
        return;
    }

    resultsGrid.innerHTML = tracks.map((track, index) => `
        <div class="track-card" data-index="${index}">
            <div class="track-image">
                ${track.image ? `<img src="${track.image}" alt="${track.name}" />` :
            `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"/></svg>`}
            </div>
            <div class="track-info">
                <div class="track-name" title="${track.name}">${track.name}</div>
                <div class="track-artist" title="${track.artist}">${track.artist}</div>
            </div>
            <div class="track-actions">
                <button class="action-btn" onclick="playTrack(this)">
                    <svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
                </button>
                <button class="action-btn secondary" onclick="openDownloadModal(this)">
                    <svg viewBox="0 0 24 24" fill="currentColor"><path d="M19 12v7H5v-7H3v7c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2v-7h-2zm-6 .67l2.59-2.58L17 11.5l-5 5-5-5 1.41-1.41L11 12.67V3h2z"/></svg>
                </button>
                ${userData ? `<button class="action-btn secondary" onclick="openAddToPlaylistModal(${index})">
                    <svg viewBox="0 0 24 24" fill="currentColor"><path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/></svg>
                </button>` : ''}
            </div>
        </div>
    `).join('');
}

// Playback Logic
function playTrack(button) {
    const card = button.closest('.track-card');
    const index = parseInt(card.dataset.index);
    const track = resultsData[index];

    if (!track) return;

    if (track.preview_url) {
        currentTrack = track;
        audioPlayer.src = track.preview_url;
        audioPlayer.play().catch(err => showNotification('Error playing preview', 'error'));
        updatePlayerUI(track);
        updatePlayButton(true);
    } else {
        showNotification('Preview not available. You can still download it!', 'info');
    }
}

function updatePlayerUI(track) {
    const playerTrackInfo = document.querySelector('.player-track-info');
    playerTrackInfo.querySelector('.track-image').innerHTML = track.image ?
        `<img src="${track.image}" style="width: 100%; height: 100%; object-fit: cover; border-radius: 4px;" />` :
        `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"/></svg>`;
    playerTrackInfo.querySelector('.track-name').textContent = track.name;
    playerTrackInfo.querySelector('.track-artist').textContent = track.artist;
}

function initializePlayer() {
    const playBtn = document.getElementById('playBtn');
    const volumeSlider = document.querySelector('.volume-slider');

    playBtn.addEventListener('click', () => {
        if (audioPlayer.paused) {
            audioPlayer.play();
            updatePlayButton(true);
        } else {
            audioPlayer.pause();
            updatePlayButton(false);
        }
    });

    volumeSlider.addEventListener('input', (e) => audioPlayer.volume = e.target.value / 100);
    audioPlayer.addEventListener('ended', () => updatePlayButton(false));
}

function updatePlayButton(isPlaying) {
    document.getElementById('playBtn').innerHTML = isPlaying ?
        `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>` :
        `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>`;
}

// Playlists Logic
function initializePlaylists() {
    // Modal events
    document.getElementById('createPlaylistModal').addEventListener('click', (e) => {
        if (e.target.id === 'createPlaylistModal') closeCreatePlaylistModal();
    });
    document.getElementById('addToPlaylistModal').addEventListener('click', (e) => {
        if (e.target.id === 'addToPlaylistModal') closeAddToPlaylistModal();
    });
}

async function loadPlaylists() {
    if (!userData) return;
    try {
        const response = await fetch('/api/playlists', {
            headers: { 'X-User-ID': userData.id.toString() }
        });
        const data = await response.json();
        displayPlaylists(data.playlists || []);
    } catch (error) {
        console.error('Load playlists error:', error);
    }
}

function displayPlaylists(playlists) {
    const grid = document.getElementById('playlistsGrid');
    if (playlists.length === 0) {
        grid.innerHTML = '<p style="grid-column: 1/-1; text-align: center; color: var(--spotify-light-gray); padding: 48px;">No playlists created yet.</p>';
        return;
    }

    grid.innerHTML = playlists.map(pl => `
        <div class="playlist-card">
            <div class="playlist-icon">
                <svg viewBox="0 0 24 24" fill="currentColor"><path d="M15 6H3v2h12V6zm0 4H3v2h12v-2zM3 16h8v-2H3v2zM17 6v8.18c-.31-.11-.65-.18-1-.18-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3V8h3V6h-5z"/></svg>
            </div>
            <div class="playlist-name">${pl.name}</div>
            <div class="playlist-count">${pl.track_count} tracks</div>
        </div>
    `).join('');
}

function openCreatePlaylistModal() {
    if (!userData) {
        showNotification('Please login first', 'info');
        return;
    }
    document.getElementById('createPlaylistModal').classList.add('active');
}

function closeCreatePlaylistModal() {
    document.getElementById('createPlaylistModal').classList.remove('active');
}

async function createPlaylist() {
    const name = document.getElementById('playlistNameInput').value.trim();
    const description = document.getElementById('playlistDescInput').value.trim();

    if (!name) return;

    try {
        const response = await fetch('/api/playlists', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-User-ID': userData.id.toString()
            },
            body: JSON.stringify({ name, description })
        });

        if (response.ok) {
            showNotification('Playlist created!', 'success');
            closeCreatePlaylistModal();
            loadPlaylists();
        }
    } catch (error) {
        showNotification('Failed to create playlist', 'error');
    }
}

let trackToPlaylist = null;
function openAddToPlaylistModal(trackIndex) {
    trackToPlaylist = resultsData[trackIndex];
    loadPlaylistsForSelection();
    document.getElementById('addToPlaylistModal').classList.add('active');
}

function closeAddToPlaylistModal() {
    document.getElementById('addToPlaylistModal').classList.remove('active');
}

async function loadPlaylistsForSelection() {
    try {
        const response = await fetch('/api/playlists', {
            headers: { 'X-User-ID': userData.id.toString() }
        });
        const data = await response.json();
        const list = document.getElementById('playlistsSelectionList');

        if (data.playlists.length === 0) {
            list.innerHTML = '<p>No playlists found. Create one first!</p>';
            return;
        }

        list.innerHTML = data.playlists.map(pl => `
            <div class="pl-selection-item" onclick="addTrackToPlaylist(${pl.id})">
                ${pl.name} (${pl.track_count} tracks)
            </div>
        `).join('');
    } catch (error) {
        console.error('Load selection error:', error);
    }
}

async function addTrackToPlaylist(playlistId) {
    if (!trackToPlaylist) return;

    try {
        const response = await fetch('/api/playlists/add_track', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-User-ID': userData.id.toString()
            },
            body: JSON.stringify({
                playlist_id: playlistId,
                track: trackToPlaylist
            })
        });

        const data = await response.json();
        if (response.ok) {
            showNotification('Added to playlist!', 'success');
            closeAddToPlaylistModal();
            loadPlaylists();
        } else {
            showNotification(data.error || 'Failed to add track', 'error');
        }
    } catch (error) {
        showNotification('Critical error', 'error');
    }
}

// Download & Modal Helpers
function openDownloadModal(button) {
    const card = button.closest('.track-card');
    const index = parseInt(card.dataset.index);
    currentTrack = resultsData[index];
    document.getElementById('downloadModal').classList.add('active');
}

function closeDownloadModal() {
    document.getElementById('downloadModal').classList.remove('active');
}

async function startDownload() {
    if (!currentTrack) return;
    const format = document.querySelector('input[name="format"]:checked').value;
    const quality = document.getElementById('qualitySelect').value;

    try {
        showNotification('Starting download...', 'info');
        const response = await fetch('/api/download', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                track_id: currentTrack.id || '',
                track_name: currentTrack.name,
                track_artist: currentTrack.artist,
                quality: quality,
                format: format
            })
        });

        if (response.ok) {
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `${currentTrack.artist} - ${currentTrack.name}.${format}`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
            showNotification('Download completed!', 'success');
            closeDownloadModal();
        } else {
            showNotification('Download failed', 'error');
        }
    } catch (error) {
        showNotification('Download error', 'error');
    }
}

function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.style.cssText = `
        position: fixed; top: 24px; right: 24px;
        background: ${type === 'error' ? '#e22134' : type === 'success' ? '#1db954' : '#2a2a2a'};
        color: white; padding: 16px 24px; border-radius: 8px;
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3); z-index: 10000;
        animation: slideIn 0.3s ease; font-size: 14px; font-weight: 600;
    `;
    notification.textContent = message;
    document.body.appendChild(notification);
    setTimeout(() => {
        notification.style.animation = 'slideOut 0.3s ease';
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

document.getElementById('downloadModal').addEventListener('click', (e) => {
    if (e.target.id === 'downloadModal') closeDownloadModal();
});

// Format Quality Switcher
document.querySelectorAll('input[name="format"]').forEach(radio => {
    radio.addEventListener('change', (e) => {
        const qualitySelect = document.getElementById('qualitySelect');
        if (e.target.value === 'flac') {
            qualitySelect.innerHTML = `<option value="1411">1411 kbps (CD)</option><option value="2300">2300 kbps (Hi-Res)</option>`;
        } else {
            qualitySelect.innerHTML = `<option value="128">128 kbps</option><option value="192">192 kbps</option><option value="320" selected>320 kbps</option>`;
        }
    });
});
