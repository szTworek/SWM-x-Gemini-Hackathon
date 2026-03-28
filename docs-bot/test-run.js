const { getAuthClient } = require('./src/auth');
const meetingFlow = require('./src/meetingFlow');

async function runLocalTest() {
  console.log("Starting local test...");
  
  try {
    // 1. Authenticate
    const authClient = getAuthClient();
    
    // 2. Define fake meeting data
    const meetingId = 'project-alpha-sync-001';
    const meetingName = "Project Alpha Sync";
    // IMPORTANT: Put YOUR real email here so you can open the generated doc
    const participants = ["wafelvvv@gmail.com"];
    const fakeTranscript = [
      "Alice: Hi everyone, let's start the project.",
      "Bob: Sounds good, I'll take care of the database.",
      "Alice: Great, I'll do the frontend.",
    ].join('\n');

    // 3. Test the Start Flow (Creates the Doc)
    const initialDoc = await meetingFlow.handleMeetingStart(authClient, meetingName, participants, meetingId);
    console.log("Start Flow Success! Live Doc URL:", initialDoc.url);

    // 4. Test Transcript Updates (Writes directly into the live transcript doc)
    await meetingFlow.appendTranscriptChunk(authClient, meetingId, {
      speaker: 'Alice',
      text: "Let's align on ownership.",
      timestamp: new Date().toISOString(),
    });
    await meetingFlow.appendTranscriptBatch(authClient, meetingId, fakeTranscript);

    // 5. Test the End Flow (Summarizes and Creates Final Doc)
    console.log("Simulating meeting end...");
    const summaryResult = await meetingFlow.handleMeetingEnd(authClient, meetingId, '', participants);
    console.log("End Flow Success! Summary URL:", summaryResult.summaryUrl);

  } catch (error) {
    console.error("Test failed:", error);
  }
}

runLocalTest();