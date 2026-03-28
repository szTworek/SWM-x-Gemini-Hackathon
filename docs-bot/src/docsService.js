const { google } = require('googleapis');

function normalizeEmails(participantEmails = []) {
  const unique = new Set();

  for (const email of participantEmails) {
    if (typeof email !== 'string') {
      continue;
    }

    const normalized = email.trim().toLowerCase();
    if (!normalized || !normalized.includes('@')) {
      continue;
    }

    unique.add(normalized);
  }

  return Array.from(unique);
}

async function createAndShareDoc(authClient, title, participantEmails) {
  const docs = google.docs({ version: 'v1', auth: authClient });
  const drive = google.drive({ version: 'v3', auth: authClient });

  try {
    const doc = await docs.documents.create({ requestBody: { title } });
    const docId = doc.data.documentId;
    const validEmails = normalizeEmails(participantEmails);
    const sharedWith = [];
    const shareErrors = [];

    for (const email of validEmails) {
      try {
        await drive.permissions.create({
          fileId: docId,
          requestBody: { type: 'user', role: 'writer', emailAddress: email },
          fields: 'id',
          sendNotificationEmail: true,
        });
        sharedWith.push(email);
      } catch (error) {
        shareErrors.push({ email, message: error?.message || 'Unknown sharing error' });
      }
    }

    return {
      docId,
      url: `https://docs.google.com/document/d/${docId}/edit`,
      sharedWith,
      shareErrors,
    };
  } catch (error) {
    console.error('Error creating/sharing doc:', error);
    throw error;
  }
}

async function appendTextToDoc(authClient, docId, textToAppend) {
  const docs = google.docs({ version: 'v1', auth: authClient });
  const text = typeof textToAppend === 'string' ? textToAppend.trim() : '';
  if (!text) {
    return;
  }

  try {
    await docs.documents.batchUpdate({
      documentId: docId,
      requestBody: {
        requests: [{
          insertText: {
            endOfSegmentLocation: {},
            text: `${text}\n`,
          },
        }],
      },
    });
  } catch (error) {
    console.error('Error appending text:', error);
    throw error;
  }
}

module.exports = {
  createAndShareDoc,
  appendTextToDoc
};