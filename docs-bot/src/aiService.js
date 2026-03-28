const GEMINI_MODEL = process.env.GEMINI_MODEL || 'gemini-1.5-flash';

function summarizeFallback(fullTranscriptText) {
  const text = (fullTranscriptText || '').trim();
  if (!text) {
    return 'Meeting Summary\n\nNo transcript content was provided.';
  }

  const lines = text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);

  const bullets = lines.slice(0, 8).map((line) => `- ${line}`);
  return [
    'Meeting Summary',
    '',
    'Key Notes:',
    ...bullets,
  ].join('\n');
}

async function generateSummaryWithGemini(fullTranscriptText) {
  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) {
    return null;
  }

  const prompt = [
    'You are an assistant that writes concise meeting summaries.',
    'Generate output with exactly these sections:',
    '1) Summary',
    '2) Decisions',
    '3) Action Items (owner + due date if stated)',
    '4) Open Questions',
    '',
    'Transcript:',
    fullTranscriptText,
  ].join('\n');

  const response = await fetch(
    `https://generativelanguage.googleapis.com/v1beta/models/${GEMINI_MODEL}:generateContent?key=${apiKey}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        contents: [{ parts: [{ text: prompt }] }],
        generationConfig: {
          temperature: 0.2,
          topP: 0.8,
        },
      }),
    }
  );

  if (!response.ok) {
    const errText = await response.text();
    throw new Error(`Gemini API request failed: ${response.status} ${errText}`);
  }

  const data = await response.json();
  const generated = data?.candidates?.[0]?.content?.parts
    ?.map((part) => part?.text)
    .filter(Boolean)
    .join('\n')
    .trim();

  return generated || null;
}

async function generateMeetingSummary(fullTranscriptText) {
  const transcriptText = (fullTranscriptText || '').trim();
  if (!transcriptText) {
    return summarizeFallback('');
  }

  console.log('Generating summary via AI...');

  try {
    const generated = await generateSummaryWithGemini(transcriptText);
    if (generated) {
      return generated;
    }
  } catch (modelError) {
    console.warn('Gemini summary failed. Falling back to local summary.', modelError.message);
  }

  return summarizeFallback(transcriptText);
}

module.exports = {
  generateMeetingSummary
};