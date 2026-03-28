document.addEventListener('DOMContentLoaded', () => {
    const urlParams = new URLSearchParams(window.location.search);
    const meetId = urlParams.get('meetId');
    const chatContainer = document.getElementById('chat-container');

    const addBotBtn = document.getElementById('add-bot-btn');
    const toggleGeminiBtn = document.getElementById('toggle-gemini-btn');

    if (!meetId) {
        chatContainer.innerHTML = '<p style="color:red; padding:10px;">Błąd: Brak ID spotkania w URL.</p>';
        return;
    }

    // ==========================================
    // 1. KOMUNIKACJA HTTP (Przyciski kontrolne)
    // ==========================================

    addBotBtn.addEventListener('click', async () => {
        addBotBtn.disabled = true;
        addBotBtn.textContent = 'Tworzenie...';
        try {
            const res = await fetch(`http://localhost:8000/meeting/${meetId}/bot`, { method: 'POST' });
            const json = await res.json();

            if (!res.ok) {
                alert("Błąd: " + (json.detail || "Nie można stworzyć bota"));
            } else {
                appendSystemMessage("🤖 Bot dołącza do spotkania...");
            }
        } catch (err) {
            console.error("Błąd fetch:", err);
            alert("Wystąpił problem z połączeniem z serwerem.");
        } finally {
            addBotBtn.disabled = false;
            addBotBtn.textContent = 'Dodaj Bota';
        }
    });

    toggleGeminiBtn.addEventListener('click', async () => {
        toggleGeminiBtn.disabled = true;
        try {
            const res = await fetch(`http://localhost:8000/meeting/${meetId}/toggle-gemini`, { method: 'POST' });
            if (res.ok) {
                const json = await res.json();
                const isGeminiActive = json.sending_to_gemini;

                toggleGeminiBtn.textContent = isGeminiActive ? "Wyłącz Gemini" : "Włącz Gemini";
                if (isGeminiActive) {
                    toggleGeminiBtn.classList.add('active');
                    appendSystemMessage("✨ Gemini zostało włączone.");
                } else {
                    toggleGeminiBtn.classList.remove('active');
                    appendSystemMessage("🛑 Gemini zostało wyłączone.");
                }
            }
        } catch (err) {
            console.error("Błąd fetch (Gemini):", err);
        } finally {
            toggleGeminiBtn.disabled = false;
        }
    });


    // ==========================================
    // 2. KOMUNIKACJA WEBSOCKET (Twój kod)
    // ==========================================

    const socket = new WebSocket('ws://localhost:8000/meeting/ws');

    socket.onopen = () => {
        socket.send(JSON.stringify({ meetId: meetId }));

        console.log("Nawiązano połączenie WS dla spotkania:", meetId);
        appendSystemMessage("🟢 Połączono z asystentem. Nasłuchiwanie transkrypcji...");
    };

    socket.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            if (data.participant && data.text) {
                renderTranscript(data);
            }
        } catch (e) {
            console.error("Błąd parsowania wiadomości z WS:", e);
        }
    };

    socket.onerror = (error) => {
        console.error("Błąd WebSocket:", error);
        appendSystemMessage("🔴 Wystąpił błąd połączenia z serwerem.");
    };

    socket.onclose = () => {
        console.log("WebSocket rozłączony.");
        appendSystemMessage("⚫ Rozłączono z serwerem.");
    };

    function renderTranscript(data) {
        const { participant, text, is_final } = data;
        const participantId = participant.replace(/\s+/g, '-').toLowerCase();
        const partialElementId = `partial-${participantId}`;

        let partialDiv = document.getElementById(partialElementId);

        if (is_final) {
            if (partialDiv) partialDiv.remove();
            const messageDiv = document.createElement('div');
            messageDiv.className = 'message final-message';
            messageDiv.innerHTML = `<strong>${participant}:</strong> ${text}`;
            chatContainer.appendChild(messageDiv);
        } else {
            if (!partialDiv) {
                partialDiv = document.createElement('div');
                partialDiv.id = partialElementId;
                partialDiv.className = 'message partial-message';
                chatContainer.appendChild(partialDiv);
            }
            partialDiv.innerHTML = `<strong>${participant}:</strong> <em>${text}</em>`;
        }

        chatContainer.scrollTop = chatContainer.scrollHeight;
    }

    function appendSystemMessage(msg) {
        const sysDiv = document.createElement('div');
        sysDiv.className = 'system-message';
        sysDiv.innerText = msg;
        chatContainer.appendChild(sysDiv);
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }
});