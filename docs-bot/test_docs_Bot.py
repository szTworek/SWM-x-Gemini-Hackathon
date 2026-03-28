import time
from docsBot import create_and_share_doc, append_text_to_doc

def run_integration_test():
    print("🚀 Starting DocsBot Append Test...\n")

    # 1. Create a test document
    print("📝 Creating a fresh test document...")
    try:
        # Note: This assumes your create_and_share_doc function returns BOTH the ID and the Link
        doc_id, doc_link = create_and_share_doc("Bot Integration Test Doc")
        print("✅ Document created successfully!")
        print(f"🔗 View it live here: {doc_link}\n")
    except Exception as e:
        print(f"❌ Failed to create document: {e}")
        return

    # 2. Prepare our mock "finalized" transcript lines
    test_lines = [
        "System: Meeting recording has started.",
        "Alice: Hey team, thanks for joining the hackathon sync.",
        "Bob: Excited to be here! Are we testing the Docs integration?",
        "Charlie: Yes, this text should be appearing in the doc right now.",
        "Alice: Perfect. Let's make sure the newlines are working correctly."
    ]

    print("✍️ Appending text to the document...")

    # 3. Loop through and write each line to the Google Doc
    for line in test_lines:
        print(f"   -> Writing: {line}")
        try:
            append_text_to_doc(doc_id, line)
            
            # Optional: A short 1-second pause just to let you watch it type live in the doc, 
            # and to ensure we don't accidentally hit Google's rapid API rate limits.
            time.sleep(1) 
        except Exception as e:
            print(f"❌ Failed to write line: {e}")

    print("\n🎉 Test complete! Check the Google Doc link above to verify the formatting.")

if __name__ == "__main__":
    run_integration_test()