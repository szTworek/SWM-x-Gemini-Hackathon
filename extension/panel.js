document.addEventListener('DOMContentLoaded', () => {
    const urlParams = new URLSearchParams(window.location.search);
    const meetId = urlParams.get('meetId');

    const chatContainer = document.getElementById('chat-container');
    const botStatusBadge = document.getElementById('bot-status');
    const addBotBtn = document.getElementById('add-bot-btn');
    const removeBotBtn = document.getElementById('remove-bot-btn');
    const toggleGeminiBtn = document.getElementById('toggle-gemini-btn');
    const jiraKeyInput = document.getElementById('jira-key');
    const saveConfigBtn = document.getElementById('save-config-btn');
    const systemLogs = document.getElementById('system-logs');

    if (!meetId) {
        setLog('Błąd: Brak ID spotkania w URL.', true);
        return;
    }

    // Ładowanie ostatnio używanego klucza Jira z pamięci przeglądarki (wygoda UX)
    const savedJiraKey = localStorage.getItem('swm_jira_key');
    if (savedJiraKey) {
        jiraKeyInput.value = savedJiraKey;
    }

    let isBotActionPending = false; // Globalna blokada akcji bota

    addBotBtn.addEventListener('click', async () => {
        if (isBotActionPending) return; // Zapobiega podwójnym kliknięciom

        isBotActionPending = true;
        setButtonLoading(addBotBtn, true, 'Tworzenie...');

        try {
            const res = await fetch(`http://localhost:8000/meeting/${meetId}/bot`, { method: 'POST' });
            if (!res.ok) {
                const json = await res.json().catch(() => ({}));
                alert("Błąd: " + (json.detail || "Nie można stworzyć bota"));
            } else {
                setLog("🤖 Bot wysłany na spotkanie.");
                updateBotStatus(true);

                // Automatycznie wysyłamy konfigurację
                if (jiraKeyInput.value.trim()) {
                    saveConfigBtn.click();
                }
            }
        } catch (err) {
            console.error("Fetch error:", err);
            alert("Wystąpił problem z połączeniem z serwerem.");
        } finally {
            setButtonLoading(addBotBtn, false, 'Zaproś Bota');
            isBotActionPending = false; // Zdejmujemy blokadę
        }
    });

    removeBotBtn.addEventListener('click', async () => {
        if (isBotActionPending) return;

        isBotActionPending = true;
        setButtonLoading(removeBotBtn, true, 'Usuwanie...');

        try {
            const res = await fetch(`http://localhost:8000/meeting/${meetId}/bot`, { method: 'DELETE' });

            if (res.ok) {
                setLog("👋 Bot opuścił spotkanie.");
                updateBotStatus(false);
            } else {
                const json = await res.json().catch(() => ({}));
                setLog(`🔴 Nie udało się wyrzucić bota: ${json.detail}`, true);
            }
        } catch (err) {
            console.error(err);
            setLog("🔴 Błąd połączenia przy usuwaniu bota.", true);
        } finally {
            setButtonLoading(removeBotBtn, false, 'Wyrzuć Bota');
            isBotActionPending = false;
        }
    });

    // ==========================================
    // 2. KONTROLA GEMINI (HTTP)
    // ==========================================

    toggleGeminiBtn.addEventListener('click', async () => {
        toggleGeminiBtn.disabled = true;
        try {
            const res = await fetch(`http://localhost:8000/meeting/${meetId}/toggle-gemini`, { method: 'POST' });
            if (res.ok) {
                const json = await res.json();
                const isGeminiActive = json.sending_to_gemini;

                toggleGeminiBtn.textContent = isGeminiActive ? "Wyłącz Gemini Live" : "Włącz Gemini Live";
                if (isGeminiActive) {
                    toggleGeminiBtn.classList.add('active');
                    setLog("✨ Gemini aktywne.");
                } else {
                    toggleGeminiBtn.classList.remove('active');
                    setLog("🛑 Gemini wyłączone.");
                }
            }
        } catch (err) {
            console.error(err);
        } finally {
            toggleGeminiBtn.disabled = false;
        }
    });

    // ==========================================
    // 3. KONFIGURACJA ZAPISYWANA PER SPOTKANIE
    // ==========================================

    saveConfigBtn.addEventListener('click', async () => {
        const key = jiraKeyInput.value.trim();

        if (!key) {
            alert("Klucz Jira nie może być pusty!");
            return;
        }

        saveConfigBtn.disabled = true;
        saveConfigBtn.textContent = "Zapisywanie...";

        try {
            // Zapisujemy w przeglądarce, aby przy kolejnym spotkaniu pole było już wypełnione
            localStorage.setItem('swm_jira_key', key);

            // Zapisujemy konfigurację W BAZIE przypisanej do tego konkretnego meetId
            const res = await fetch(`http://localhost:8000/meeting/${meetId}/config`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ jira_key: key })
            });

            if (res.ok) {
                setLog("💾 Konfiguracja przypisana do spotkania.");
                saveConfigBtn.textContent = "Zapisano!";
            } else {
                const json = await res.json().catch(() => ({}));
                throw new Error(json.detail || "Błąd zapisu na serwerze");
            }

        } catch (err) {
            console.error("Błąd zapisu konfiguracji:", err);
            setLog(`🔴 Błąd konfiguracji: ${err.message}`, true);
            saveConfigBtn.textContent = "Błąd!";
        } finally {
            // Po 2 sekundach wracamy do normalnego stanu przycisku
            setTimeout(() => {
                saveConfigBtn.disabled = false;
                if(saveConfigBtn.textContent === "Zapisano!" || saveConfigBtn.textContent === "Błąd!") {
                    saveConfigBtn.textContent = "Zapisz konfigurację";
                }
            }, 2000);
        }
    });

    // ==========================================
    // 4. WEBSOCKET (Nasłuchiwanie ogólne)
    // ==========================================

    const socket = new WebSocket('ws://localhost:8000/meeting/ws');

    socket.onopen = () => {
        socket.send(JSON.stringify({ meetId: meetId }));
        setLog("🟢 Aktywny panel komunikacji z serwerem.");
    };

    socket.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            // Jeśli backend wyśle event o wyjściu bota z innej przyczyny (np. koniec czasu)
            if (data.status === 'bot_left') {
                updateBotStatus(false);
                setLog("ℹ️ Bot zakończył pracę w tym spotkaniu.");
            }
        } catch (e) {
            console.error("WS parse error:", e);
        }
    };

    socket.onerror = (error) => {
        console.error("WS error:", error);
        setLog("🔴 Problem z połączeniem na żywo.", true);
    };

    socket.onclose = () => {
        setLog("⚫ Rozłączono z serwerem.");
    };

    // ==========================================
    // FUNKCJE POMOCNICZE
    // ==========================================

    function updateBotStatus(isConnected) {
        if (isConnected) {
            botStatusBadge.className = 'status-badge status-connected';
            botStatusBadge.textContent = '🟢 Połączony';
            addBotBtn.style.display = 'none';
            removeBotBtn.style.display = 'block';
        } else {
            botStatusBadge.className = 'status-badge status-disconnected';
            botStatusBadge.textContent = '🔴 Odłączony';
            addBotBtn.style.display = 'block';
            removeBotBtn.style.display = 'none';

            toggleGeminiBtn.textContent = "Włącz Gemini Live";
            toggleGeminiBtn.classList.remove('active');
        }
    }

    function setLog(msg, isError = false) {
        systemLogs.textContent = msg;
        systemLogs.style.color = isError ? '#d93025' : '#80868b';
    }

    function setButtonLoading(btn, isLoading, text) {
        btn.disabled = isLoading;
        if (text) {
            btn.textContent = text;
        }
    }
});