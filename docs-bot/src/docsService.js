const { google } = require('googleapis');

function normalizeEmails(participantEmails = []) {
  return Array.from(new Set(
    participantEmails
      .filter((email) => typeof email === 'string')
      .map((email) => email.trim().toLowerCase())
      .filter((email) => email && email.includes('@'))
  ));
}

async function createAndShareDoc(authClient, title, participantEmails) {
  const docs = google.docs({ version: 'v1', auth: authClient });
  const drive = google.drive({ version: 'v3', auth: authClient });

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
}

async function appendTextToDoc(authClient, docId, textToAppend) {
  const docs = google.docs({ version: 'v1', auth: authClient });
  const text = typeof textToAppend === 'string' ? textToAppend.trim() : '';
  if (!text) {
    return;
  }

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
}

module.exports = {
  createAndShareDoc,
  appendTextToDoc
};