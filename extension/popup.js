document.addEventListener('DOMContentLoaded', async () => {
    const statusEl = document.getElementById('status');
    const openPanelBtn = document.getElementById('open-panel-btn');

    let [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

    if (tab.url && tab.url.includes('meet.google.com/')) {
        const urlParts = tab.url.split('meet.google.com/');
        const meetId = urlParts[1].split('?')[0];

        statusEl.textContent = `Spotkanie: ${meetId}`;
        openPanelBtn.disabled = false;

        openPanelBtn.onclick = async () => {
            openPanelBtn.disabled = true;
            openPanelBtn.textContent = 'Otwieranie...';

            try {
                const data = await chrome.storage.local.get(['panelWindowId', 'panelMeetId']);

                if (data.panelWindowId) {
                    try {
                        await chrome.windows.get(data.panelWindowId);

                        if (data.panelMeetId === meetId) {
                            await chrome.windows.update(data.panelWindowId, { focused: true });
                            return;
                        } else {
                            await chrome.windows.remove(data.panelWindowId);
                        }
                    } catch (e) {

                    }
                }

                const newWin = await chrome.windows.create({
                    url: `panel.html?meetId=${meetId}`,
                    type: 'popup',
                    width: 450,
                    height: 600,
                });

                await chrome.storage.local.set({
                    panelWindowId: newWin.id,
                    panelMeetId: meetId
                });

            } catch (err) {
                console.error("Błąd zarządzania oknami:", err);
            } finally {
                openPanelBtn.disabled = false;
                openPanelBtn.textContent = 'Otwórz Panel';
            }
        };
    } else {
        statusEl.textContent = 'Nie jesteś na Google Meet.';
    }
});