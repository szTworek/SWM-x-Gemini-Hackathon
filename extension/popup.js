document.addEventListener('DOMContentLoaded', async () => {
    const statusEl = document.getElementById('status');
    const openPanelBtn = document.getElementById('open-panel-btn');

    let [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

    if (tab.url && tab.url.includes('meet.google.com/')) {
        const urlParts = tab.url.split('meet.google.com/');
        const meetId = urlParts[1].split('?')[0];

        statusEl.textContent = `Spotkanie: ${meetId}`;
        openPanelBtn.disabled = false;

        openPanelBtn.onclick = () => {
            chrome.windows.create({
                url: `panel.html?meetId=${meetId}`,
                type: 'popup',
                width: 450,
                height: 600,
            }).catch(err => console.error("Błąd otwierania panelu:", err));
        };
    } else {
        statusEl.textContent = 'Nie jesteś na Google Meet.';
    }
});