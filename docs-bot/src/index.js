const meetingFlow = require('./meetingFlow');
const { getAuthClient } = require('./auth');

function readPayload(req) {
    return req?.body || {};
}

function send(res, status, payload) {
    if (res && typeof res.status === 'function') {
        return res.status(status).send(payload);
    }

    return { status, payload };
}

function getParticipants(payload) {
    if (Array.isArray(payload.participants)) {
        return payload.participants;
    }
    return [];
}

function getAuthClientFromCtx(ctx = {}) {
    if (ctx.authClient) {
        return ctx.authClient;
    }
    return getAuthClient();
}

async function onMeetingStartWebhook(req, res, ctx = {}) {
    const payload = readPayload(req);
    const authClient = getAuthClientFromCtx(ctx);

    const meetingId = payload.meetingId || payload.meetId;
    const meetingName = payload.meetingName || payload.title || meetingId;

    if (!meetingId) {
        return send(res, 400, { success: false, error: 'meetingId is required' });
    }

    try {
        const result = await meetingFlow.handleMeetingStart(
            authClient,
            meetingName,
            getParticipants(payload),
            meetingId
        );

        return send(res, 200, { success: true, meetingId: result.meetingId, transcriptDoc: result });
    } catch (error) {
        return send(res, 500, { success: false, error: error.message || 'Failed to start meeting flow' });
    }
}

async function onTranscriptWebhook(req, res, ctx = {}) {
    const payload = readPayload(req);
    const authClient = getAuthClientFromCtx(ctx);

    const meetingId = payload.meetingId || payload.meetId;
    if (!meetingId) {
        return send(res, 400, { success: false, error: 'meetingId is required' });
    }

    try {
        const text = typeof payload.text === 'string' ? payload.text.trim() : '';

        let appendResult;
        if (text.includes('\n')) {
            appendResult = await meetingFlow.appendTranscriptBatch(authClient, meetingId, text);
        } else {
            appendResult = await meetingFlow.appendTranscriptChunk(authClient, meetingId, {
                speaker: payload.speaker,
                text,
                timestamp: payload.timestamp,
            });
        }

        return send(res, 200, { success: true, result: appendResult });
    } catch (error) {
        return send(res, 500, { success: false, error: error.message || 'Failed to append transcript' });
    }
}

async function onMeetingEndWebhook(req, res, ctx = {}) {
    const payload = readPayload(req);
    const authClient = getAuthClientFromCtx(ctx);

    const meetingId = payload.meetingId || payload.meetId;
    if (!meetingId) {
        return send(res, 400, { success: false, error: 'meetingId is required' });
    }

    try {
        const summaryResult = await meetingFlow.handleMeetingEnd(
            authClient,
            meetingId,
            payload.transcript,
            getParticipants(payload)
        );

        return send(res, 200, {
            success: true,
            meetingId,
            summaryUrl: summaryResult.summaryUrl,
            summaryDocId: summaryResult.summaryDocId,
        });
    } catch (error) {
        return send(res, 500, { success: false, error: error.message || 'Processing failed' });
    }
}

module.exports = {
    onMeetingStartWebhook,
    onTranscriptWebhook,
    onMeetingEndWebhook,
};