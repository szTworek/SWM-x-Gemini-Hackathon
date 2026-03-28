const docsService = require('./docsService');
const aiService = require('./aiService');

const meetingSessions = new Map();

function toCleanText(value) {
  return typeof value === 'string' ? value.trim() : '';
}

function ensureSession(meetingId) {
  const session = meetingSessions.get(meetingId);
  if (!session) {
    throw new Error(`Meeting session not found for meetingId: ${meetingId}`);
  }
  return session;
}

function buildTranscriptLine({ speaker, text, timestamp }) {
  const speakerText = toCleanText(speaker) || 'Participant';
  const body = toCleanText(text);
  if (!body) {
    return '';
  }

  const prefix = timestamp ? `[${timestamp}] ` : '';
  return `${prefix}${speakerText}: ${body}`;
}

async function handleMeetingStart(authClient, meetingName, participantEmails, meetingId) {
  const resolvedMeetingId = toCleanText(meetingId) || `meeting-${Date.now()}`;
  const safeMeetingName = toCleanText(meetingName) || resolvedMeetingId;

  console.log(`Starting meeting flow for: ${safeMeetingName} (${resolvedMeetingId})`);

  const initialDoc = await docsService.createAndShareDoc(
    authClient,
    `${safeMeetingName} - Live Transcript`,
    participantEmails
  );

  meetingSessions.set(resolvedMeetingId, {
    meetingId: resolvedMeetingId,
    meetingName: safeMeetingName,
    participantEmails: Array.isArray(participantEmails) ? participantEmails : [],
    liveDocId: initialDoc.docId,
    liveDocUrl: initialDoc.url,
    transcriptLines: [],
  });

  return {
    ...initialDoc,
    meetingId: resolvedMeetingId,
  };
}

async function appendTranscriptChunk(authClient, meetingId, payload) {
  const session = ensureSession(meetingId);
  const line = buildTranscriptLine(payload || {});

  if (!line) {
    return { appended: false };
  }

  session.transcriptLines.push(line);
  await docsService.appendTextToDoc(authClient, session.liveDocId, line);
  return { appended: true, line };
}

async function appendTranscriptBatch(authClient, meetingId, transcriptText) {
  const session = ensureSession(meetingId);
  const lines = toCleanText(transcriptText)
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);

  if (lines.length === 0) {
    return { appended: 0 };
  }

  const combined = lines.join('\n');
  await docsService.appendTextToDoc(authClient, session.liveDocId, combined);
  session.transcriptLines.push(...lines);
  return { appended: lines.length };
}

async function handleMeetingEnd(authClient, meetingId, fullTranscriptText, participantEmails) {
  const session = ensureSession(meetingId);
  console.log("Meeting ended. Starting summarization flow...");

  const sessionParticipants = session.participantEmails?.length
    ? session.participantEmails
    : (Array.isArray(participantEmails) ? participantEmails : []);

  const providedTranscript = toCleanText(fullTranscriptText);
  if (providedTranscript) {
    await appendTranscriptBatch(authClient, meetingId, providedTranscript);
  }

  const transcriptForSummary = session.transcriptLines.join('\n');
  const summaryText = await aiService.generateMeetingSummary(transcriptForSummary);

  const summaryDoc = await docsService.createAndShareDoc(
    authClient,
    `${session.meetingName} - Summary`,
    sessionParticipants
  );

  const summaryBody = [
    `Meeting: ${session.meetingName}`,
    `Live transcript: ${session.liveDocUrl}`,
    '',
    summaryText,
  ].join('\n');
  await docsService.appendTextToDoc(authClient, summaryDoc.docId, summaryBody);

  console.log(`Final summary available at: ${summaryDoc.url}`);

  meetingSessions.delete(meetingId);

  return {
    summaryDocId: summaryDoc.docId,
    summaryUrl: summaryDoc.url,
  };
}

module.exports = {
  handleMeetingStart,
  appendTranscriptChunk,
  appendTranscriptBatch,
  handleMeetingEnd,
};